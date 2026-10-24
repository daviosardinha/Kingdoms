#!/usr/bin/env bash
set -euo pipefail

# NORTH's reduced Kingdoms topology has exactly one protected parent route.
# Dispatch explicitly to the same script's instance-owned controller; when
# --north is absent, the full six-machine Kingdoms logic below is unchanged.
if [[ "${1:-}" == "--north" ]]; then
  readonly KINGDOMS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  shift
  exec env PYTHONPATH="${KINGDOMS_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 -m goad.course1_routes "$@"
fi

# Temporary host routes used only while provisioning the segmented VMware lab.
#
# The Kali/host machine intentionally has no VMware adapters on vmnet20 or
# vmnet30. Local Ansible therefore reaches protected zones through GOAD-ROUTER
# during provisioning. These routes must be removed before exercise mode so the
# student host cannot directly route into SEVENKINGDOMS or ESSOS.

readonly NORTH_IF="vmnet10"
readonly ROUTER_NORTH="10.4.10.1"
readonly SEVENKINGDOMS_NET="10.4.20.0/24"
readonly ESSOS_NET="10.4.30.0/24"
readonly HOSTADDR_HELPER="/usr/local/sbin/goad-nomad-vmnet-hostaddrs"

fail() {
  echo "[!] $*" >&2
  exit 1
}

require_root() {
  [[ ${EUID} -eq 0 ]] || fail "Run this mode with sudo."
}

ensure_host_addresses() {
  [[ -x "${HOSTADDR_HELPER}" ]] || fail "${HOSTADDR_HELPER} is missing. Run scripts/setup-vmware-networks.sh first."
  "${HOSTADDR_HELPER}"
}

check_base() {
  ip link show "${NORTH_IF}" >/dev/null 2>&1 || fail "${NORTH_IF} is missing. Run scripts/setup-vmware-networks.sh first."
  ip -4 addr show dev "${NORTH_IF}" | grep -q '10\.4\.10\.254/24' || fail "${NORTH_IF} does not have 10.4.10.254/24."
  ping -c 1 -W 1 "${ROUTER_NORTH}" >/dev/null 2>&1 || fail "GOAD-ROUTER is not reachable at ${ROUTER_NORTH}."
}

enable_routes() {
  require_root
  # VMware Workstation 26 can recreate vmnet10 and drop its host IPv4 address
  # during Vagrant operations. Repair the host-visible addresses immediately
  # before validating the router and installing temporary provisioning routes.
  ensure_host_addresses
  check_base

  ip route replace "${SEVENKINGDOMS_NET}" via "${ROUTER_NORTH}" dev "${NORTH_IF}"
  ip route replace "${ESSOS_NET}" via "${ROUTER_NORTH}" dev "${NORTH_IF}"

  echo "[+] Temporary provisioning routes enabled"
  ip route show "${SEVENKINGDOMS_NET}"
  ip route show "${ESSOS_NET}"
  echo
  echo "[!] These routes are provisioning-only. Remove them before exercise mode."
}

disable_routes() {
  require_root

  ip route del "${SEVENKINGDOMS_NET}" via "${ROUTER_NORTH}" dev "${NORTH_IF}" 2>/dev/null || true
  ip route del "${ESSOS_NET}" via "${ROUTER_NORTH}" dev "${NORTH_IF}" 2>/dev/null || true

  echo "[+] Temporary provisioning routes removed"
}

status_routes() {
  echo "--- GOAD_NOMAD provisioning routes ---"
  ip route show "${SEVENKINGDOMS_NET}" || true
  ip route show "${ESSOS_NET}" || true
}

case "${1:-status}" in
  enable)
    enable_routes
    ;;
  disable)
    disable_routes
    ;;
  status)
    status_routes
    ;;
  *)
    echo "Usage: $0 {enable|disable|status}" >&2
    exit 2
    ;;
esac
