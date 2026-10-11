#!/usr/bin/env bash
set -euo pipefail

# Course 1 reuses this original Kingdoms setup entrypoint.
# --north plan/check/hostaddr-plan remain read-only; --north apply requires
# explicit privilege, a reviewed hash and instance identity. No NORTH VM
# lifecycle is unlocked here. Full-Kingdoms setup below remains unchanged.
if [[ "${1:-}" == "--north" ]]; then
  readonly KINGDOMS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  shift
  if [[ "${1:-}" == "verify" ]]; then
    shift
    # Installed-owner attestation is read-only and must inspect root-owned
    # mode-0600 transaction evidence. No VMware restart or network writes.
    exec env PYTHONPATH="${KINGDOMS_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
      python3 -m goad.course1_host_network_apply verify "$@"
  fi
  if [[ "${1:-}" == "apply" ]]; then
    shift
    # Explicit, reviewed host mutation. Nothing invokes this from the normal
    # source validator or while the NORTH provider install guard remains active.
    [[ ${EUID} -eq 0 ]] || { echo "[BLOCKED] sudo required for NORTH host apply" >&2; exit 1; }
    exec env PYTHONPATH="${KINGDOMS_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
      python3 -m goad.course1_host_network_apply "$@"
  fi
  exec env PYTHONPATH="${KINGDOMS_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 -m goad.course1_vmnet_config "$@"
fi

# GOAD_NOMAD VMware Workstation host network bootstrap.
#
# Creates only the project-owned networks and preserves all existing VMware
# networking (for example the default vmnet1 host-only and vmnet8 NAT networks).
#
# Project networks:
#   vmnet10  NORTH           10.4.10.0/24   host adapter: 10.4.10.254
#   vmnet20  SEVENKINGDOMS   10.4.20.0/24   host adapter: none
#   vmnet30  ESSOS           10.4.30.0/24   host adapter: none
#   vmnet99  MANAGEMENT      10.4.99.0/24   host adapter: 10.4.99.254
#
# DHCP and VMware NAT are disabled on all four networks. Routing between
# exercise networks is performed only by GOAD-ROUTER, whose gateway addresses
# are .1 on each subnet.

readonly NETWORKING_FILE="/etc/vmware/networking"
readonly BACKUP_ROOT="/etc/vmware/goad-nomad-backups"
readonly VMWARE_NETWORKS="/usr/bin/vmware-networks"
readonly HOSTADDR_HELPER="/usr/local/sbin/goad-nomad-vmnet-hostaddrs"
readonly HOSTADDR_SERVICE="/etc/systemd/system/goad-nomad-vmnet-hostaddrs.service"
readonly HOSTADDR_TIMER="/etc/systemd/system/goad-nomad-vmnet-hostaddrs.timer"
readonly HOSTADDR_SERVICE_NAME="goad-nomad-vmnet-hostaddrs.service"
readonly HOSTADDR_TIMER_NAME="goad-nomad-vmnet-hostaddrs.timer"

fail() {
  echo "[!] $*" >&2
  exit 1
}

[[ ${EUID} -eq 0 ]] || fail "Run this script with sudo."
[[ -x "${VMWARE_NETWORKS}" ]] || fail "${VMWARE_NETWORKS} was not found. Is VMware Workstation installed?"
[[ -f "${NETWORKING_FILE}" ]] || fail "${NETWORKING_FILE} was not found. Start VMware Workstation once so networking is initialized."
command -v python3 >/dev/null 2>&1 || fail "python3 is required to edit VMware networking safely."
command -v ip >/dev/null 2>&1 || fail "iproute2 is required."

# Do not change the host networking underneath running VMware guests.
if pgrep -x vmware-vmx >/dev/null 2>&1; then
  fail "VMware virtual machines are running. Shut them down before changing vmnet configuration."
fi

stamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="${BACKUP_ROOT}/${stamp}"
install -d -m 0700 "${backup_dir}"
cp -a "${NETWORKING_FILE}" "${backup_dir}/networking"
if [[ -f /etc/vmware/netmap.conf ]]; then
  cp -a /etc/vmware/netmap.conf "${backup_dir}/netmap.conf"
fi

echo "[*] Backed up VMware networking to ${backup_dir}"
echo "[*] Stopping VMware virtual networking"
"${VMWARE_NETWORKS}" --stop || true

python3 - "${NETWORKING_FILE}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
lines = text.splitlines()

# Remove only keys belonging to GOAD_NOMAD-owned vmnets. Everything else,
# including vmnet1/vmnet8 and bridge mappings, is preserved.
owned = {10, 20, 30, 99}
pattern = re.compile(r"^answer\s+VNET_(\d+)_")
kept = []
for line in lines:
    match = pattern.match(line)
    if match and int(match.group(1)) in owned:
        continue
    kept.append(line)

# Host adapter policy matters for the training model:
# - NORTH is intentionally reachable from the student's host.
# - SEVENKINGDOMS and ESSOS must not gain host-side adapters because that
#   would bypass the router/pivoting model.
# - MANAGEMENT remains host-visible for router control. Windows guests are not
#   attached to it, and the exercise router policy does not grant arbitrary
#   MANAGEMENT-to-zone forwarding.
#
# Host-visible adapters use .254 so they never collide with GOAD-ROUTER (.1).
networks = {
    10: {"subnet": "10.4.10.0", "host_adapter": "yes", "host_addr": "10.4.10.254", "label": "NORTH"},
    20: {"subnet": "10.4.20.0", "host_adapter": "no",  "host_addr": None,          "label": "SEVENKINGDOMS"},
    30: {"subnet": "10.4.30.0", "host_adapter": "no",  "host_addr": None,          "label": "ESSOS"},
    99: {"subnet": "10.4.99.0", "host_adapter": "yes", "host_addr": "10.4.99.254", "label": "MANAGEMENT"},
}

if kept and kept[-1] != "":
    kept.append("")
kept.append("# GOAD_NOMAD managed networks - generated by scripts/setup-vmware-networks.sh")
for number, cfg in networks.items():
    kept.append(f"# vmnet{number}: {cfg['label']}")
    kept.append(f"answer VNET_{number}_DHCP no")
    # Workstation 26 may later strip HOSTONLY_HOSTADDR from this file. Keep it
    # as desired-state metadata, while the systemd helper below is authoritative
    # for the live host interface address.
    if cfg["host_addr"]:
        kept.append(f"answer VNET_{number}_HOSTONLY_HOSTADDR {cfg['host_addr']}")
    kept.append(f"answer VNET_{number}_HOSTONLY_NETMASK 255.255.255.0")
    kept.append(f"answer VNET_{number}_HOSTONLY_SUBNET {cfg['subnet']}")
    kept.append(f"answer VNET_{number}_VIRTUAL_ADAPTER {cfg['host_adapter']}")

path.write_text("\n".join(kept) + "\n")
PY

echo "[*] Starting VMware virtual networking"
if ! "${VMWARE_NETWORKS}" --start; then
  echo "[!] VMware networking failed to start. Restoring backup." >&2
  cp -a "${backup_dir}/networking" "${NETWORKING_FILE}"
  "${VMWARE_NETWORKS}" --start || true
  fail "Configuration was rolled back."
fi

# Workstation 26 can recreate host-only adapters during later Vagrant/VMware
# operations and drop manually assigned IPv4 addresses. The helper is
# idempotent: it changes an interface only when the expected address is absent.
cat > "${HOSTADDR_HELPER}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

configure_addr() {
  local iface="$1" cidr="$2"
  local i

  for i in $(seq 1 20); do
    if ip link show "${iface}" >/dev/null 2>&1; then
      ip link set dev "${iface}" up
      if ip -4 -o addr show dev "${iface}" | awk '{print $4}' | grep -Fxq "${cidr}"; then
        return 0
      fi
      ip -4 addr flush dev "${iface}"
      ip -4 addr add "${cidr}" dev "${iface}"
      return 0
    fi
    sleep 1
  done

  echo "[!] ${iface} did not appear within 20 seconds" >&2
  return 1
}

configure_addr vmnet10 10.4.10.254/24
configure_addr vmnet99 10.4.99.254/24
EOF
chmod 0755 "${HOSTADDR_HELPER}"

# Explicitly stop the old service/timer before replacing their definitions.
# Older GOAD_NOMAD revisions used RemainAfterExit=yes, which can leave systemd
# believing the oneshot is still active and prevent a later `start` from
# actually executing the updated helper.
systemctl stop "${HOSTADDR_TIMER_NAME}" >/dev/null 2>&1 || true
systemctl stop "${HOSTADDR_SERVICE_NAME}" >/dev/null 2>&1 || true
systemctl disable "${HOSTADDR_SERVICE_NAME}" >/dev/null 2>&1 || true

cat > "${HOSTADDR_SERVICE}" <<'EOF'
[Unit]
Description=GOAD_NOMAD VMware host-only interface addresses
After=network.target vmware.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/goad-nomad-vmnet-hostaddrs
EOF

cat > "${HOSTADDR_TIMER}" <<'EOF'
[Unit]
Description=Keep GOAD_NOMAD VMware host-only addresses present
After=vmware.service

[Timer]
OnActiveSec=3s
OnUnitInactiveSec=15s
AccuracySec=1s
Unit=goad-nomad-vmnet-hostaddrs.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl reset-failed "${HOSTADDR_SERVICE_NAME}" >/dev/null 2>&1 || true

# Apply desired state synchronously. Do not rely on service runtime state or the
# first timer tick for initial setup correctness.
systemctl start "${HOSTADDR_SERVICE_NAME}"

# Refuse to report success unless the live addresses are actually present.
ip -4 -o addr show dev vmnet10 | awk '{print $4}' | grep -Fxq '10.4.10.254/24' || fail "vmnet10 host address was not applied"
ip -4 -o addr show dev vmnet99 | awk '{print $4}' | grep -Fxq '10.4.99.254/24' || fail "vmnet99 host address was not applied"

systemctl enable --now "${HOSTADDR_TIMER_NAME}" >/dev/null

echo
echo "[+] GOAD_NOMAD VMware networks configured"
echo "    vmnet10  NORTH           10.4.10.0/24   host=10.4.10.254 DHCP=off NAT=off"
echo "    vmnet20  SEVENKINGDOMS   10.4.20.0/24   host=none        DHCP=off NAT=off"
echo "    vmnet30  ESSOS           10.4.30.0/24   host=none        DHCP=off NAT=off"
echo "    vmnet99  MANAGEMENT      10.4.99.0/24   host=10.4.99.254 DHCP=off NAT=off"
echo
echo "[*] Existing VMware networks were preserved."
echo "[*] Backup: ${backup_dir}"
echo "[*] Host-address persistence: goad-nomad-vmnet-hostaddrs.timer"
