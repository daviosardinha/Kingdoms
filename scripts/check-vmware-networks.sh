#!/usr/bin/env bash
set -euo pipefail

# NORTH-only configuration check through existing Kingdoms entrypoint.
# Still read-only: runtime .254 addresses/services are verified separately.
if [[ "${1:-}" == "--north" ]]; then
  readonly KINGDOMS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  shift
  exec env PYTHONPATH="${KINGDOMS_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 -m goad.course1_vmnet_config check "$@"
fi

readonly NETWORKING_FILE="/etc/vmware/networking"
readonly VMWARE_NETWORKS="/usr/bin/vmware-networks"
readonly HOSTADDR_SERVICE="goad-nomad-vmnet-hostaddrs.service"
readonly HOSTADDR_TIMER="goad-nomad-vmnet-hostaddrs.timer"
readonly HOSTADDR_HELPER="/usr/local/sbin/goad-nomad-vmnet-hostaddrs"

failures=0

ok()   { printf '[OK]   %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*"; failures=$((failures + 1)); }

[[ -f "${NETWORKING_FILE}" ]] || { fail "${NETWORKING_FILE} not found"; exit 1; }

check_value() {
  local net="$1" key="$2" expected="$3"
  local actual
  actual="$(awk -v k="VNET_${net}_${key}" '$1=="answer" && $2==k {print $3}' "${NETWORKING_FILE}" | tail -n1)"
  if [[ "${actual}" == "${expected}" ]]; then
    ok "vmnet${net} ${key}=${expected}"
  else
    fail "vmnet${net} ${key}: expected '${expected}', got '${actual:-missing}'"
  fi
}

check_optional_hostaddr() {
  local net="$1" expected="$2"
  local actual
  actual="$(awk -v k="VNET_${net}_HOSTONLY_HOSTADDR" '$1=="answer" && $2==k {print $3}' "${NETWORKING_FILE}" | tail -n1)"
  if [[ -z "${actual}" ]]; then
    warn "vmnet${net} HOSTONLY_HOSTADDR metadata missing (Workstation 26 may strip it; live address is authoritative)"
  elif [[ "${actual}" == "${expected}" ]]; then
    ok "vmnet${net} HOSTONLY_HOSTADDR=${expected}"
  else
    fail "vmnet${net} HOSTONLY_HOSTADDR: expected '${expected}', got '${actual}'"
  fi
}

check_no_nat() {
  local net="$1"
  local actual
  actual="$(awk -v k="VNET_${net}_NAT" '$1=="answer" && $2==k {print $3}' "${NETWORKING_FILE}" | tail -n1)"
  if [[ -z "${actual}" || "${actual}" == "no" ]]; then
    ok "vmnet${net} NAT=off"
  else
    fail "vmnet${net} NAT is enabled"
  fi
}

for spec in \
  '10 10.4.10.0 yes NORTH' \
  '20 10.4.20.0 no SEVENKINGDOMS' \
  '30 10.4.30.0 no ESSOS' \
  '99 10.4.99.0 yes MANAGEMENT'
do
  read -r net subnet host_adapter label <<<"${spec}"
  echo "--- vmnet${net} / ${label} ---"
  check_value "${net}" DHCP no
  check_value "${net}" HOSTONLY_NETMASK 255.255.255.0
  check_value "${net}" HOSTONLY_SUBNET "${subnet}"
  check_value "${net}" VIRTUAL_ADAPTER "${host_adapter}"
  check_no_nat "${net}"
  echo
done

# Workstation 26 may remove these metadata keys after recreating vmnets.
# The runtime addresses below plus the persistence timer are authoritative.
check_optional_hostaddr 10 10.4.10.254
check_optional_hostaddr 99 10.4.99.254

# Only NORTH and MANAGEMENT intentionally expose host-side interfaces.
for spec in '10 10.4.10.254/24' '99 10.4.99.254/24'; do
  read -r net expected_cidr <<<"${spec}"
  if ip link show "vmnet${net}" >/dev/null 2>&1; then
    ok "host interface vmnet${net} exists"
    if ip -4 -o addr show dev "vmnet${net}" | awk '{print $4}' | grep -Fxq "${expected_cidr}"; then
      ok "vmnet${net} host address=${expected_cidr}"
    else
      fail "vmnet${net} does not have expected host address ${expected_cidr}"
    fi
  else
    fail "host interface vmnet${net} is missing"
  fi
done

for net in 20 30; do
  if ip link show "vmnet${net}" >/dev/null 2>&1; then
    fail "host interface vmnet${net} exists; this would bypass segmentation"
  else
    ok "host interface vmnet${net} is absent as designed"
  fi
done

echo
if [[ -x "${HOSTADDR_HELPER}" ]]; then
  ok "host-address helper installed"
else
  fail "host-address helper is missing"
fi

if systemctl is-enabled "${HOSTADDR_TIMER}" >/dev/null 2>&1; then
  ok "${HOSTADDR_TIMER} enabled"
else
  fail "${HOSTADDR_TIMER} is not enabled"
fi

timer_state="$(systemctl show "${HOSTADDR_TIMER}" -p SubState --value)"
timer_next="$(systemctl show "${HOSTADDR_TIMER}" -p NextElapseUSecMonotonic --value)"
service_state="$(systemctl show "${HOSTADDR_SERVICE}" -p ActiveState --value)"
if systemctl is-active "${HOSTADDR_TIMER}" >/dev/null 2>&1 &&
   { [[ "${timer_state}" == waiting && -n "${timer_next}" && "${timer_next}" != 0 && "${timer_next}" != infinity ]] ||
     [[ "${timer_state}" == running && "${service_state}" == activating ]]; }; then
  ok "${HOSTADDR_TIMER} scheduling repairs (${timer_state})"
else
  fail "${HOSTADDR_TIMER} has no scheduled repair or running service (${timer_state}, next=${timer_next:-missing})"
fi

if systemctl is-failed "${HOSTADDR_SERVICE}" >/dev/null 2>&1; then
  fail "${HOSTADDR_SERVICE} last run failed"
else
  ok "${HOSTADDR_SERVICE} is not failed"
fi

echo
if [[ -x "${VMWARE_NETWORKS}" ]]; then
  "${VMWARE_NETWORKS}" --status || warn "vmware-networks status returned non-zero (non-fatal on some Workstation 26 Linux builds)"
else
  warn "${VMWARE_NETWORKS} not found"
fi

echo
if (( failures == 0 )); then
  echo '[READY] VMware host networking matches GOAD_NOMAD design.'
else
  echo "[NOT READY] ${failures} validation check(s) failed."
  exit 1
fi
