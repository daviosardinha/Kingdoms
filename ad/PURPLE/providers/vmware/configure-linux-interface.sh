#!/usr/bin/env bash
# Configure exactly the Purple Team lab NIC, selected by deterministic VMware MAC.
# No gateway, DNS, NAT, host route, or host networking changes.
set -euo pipefail
ipaddr="${1:?expected IPv4 address}"
mac="${2:?expected VMware NIC MAC}"
case "$ipaddr" in
  172.28.233.*) ;;
  *) echo "PURPLE: refusing address outside 172.28.233.0/24: $ipaddr" >&2; exit 1 ;;
esac
if ! [[ "$mac" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
  echo "PURPLE: bad MAC format" >&2
  exit 1
fi

install -d -m 0755 /usr/local/sbin
# Vagrant copies provisioner scripts into the guest. Keep a copy for reboot.
script=/usr/local/sbin/purple-lab-interface
if [[ "$(readlink -f "$0")" != "$script" ]]; then
  install -m 0755 "$0" "$script"
fi

interface=""
for adapter in /sys/class/net/*; do
  name="${adapter##*/}"
  [[ "$name" != "lo" ]] || continue
  actual="$(cat "$adapter/address" | tr '[:upper:]' '[:lower:]')"
  if [[ "$actual" == "${mac,,}" ]]; then
    interface="$name"
    break
  fi
done
if [[ -z "$interface" ]]; then
  echo "PURPLE: required lab NIC MAC $mac not found; refusing to configure another NIC" >&2
  exit 1
fi

ip link set "$interface" up
ip -4 address replace "$ipaddr/24" dev "$interface"
ip -4 address show dev "$interface"

# Set the guest's stable Linux hostname on *fresh provisioning*, matching
# the source VM name (Linux static hostnames use lowercase). Vagrant may set
# the transient hostname earlier; resolve the static name locally before any
# Desktop/Wazuh/C2 package provisioning requires sudo or hostname lookups.
# The boot-time NIC service does not need to rename the machine again.
if [[ "${PURPLE_BOOT_SERVICE:-0}" != "1" ]]; then
  case "$ipaddr" in
    172.28.233.32) guest_hostname="purple-lx01" ;;
    172.28.233.51) guest_hostname="purple-wazuh" ;;
    172.28.233.60) guest_hostname="purple-c2" ;;
    *) echo "PURPLE: unsupported Linux lab address for hostname assignment: $ipaddr" >&2; exit 1 ;;
  esac
  [[ "$(id -u)" == "0" ]] || {
    echo "PURPLE: Linux hostname setup requires root" >&2; exit 1;
  }
  [[ -f /etc/hosts && ! -L /etc/hosts ]] || {
    echo "PURPLE: /etc/hosts must be a regular file" >&2; exit 1;
  }

  # Keep unrelated mappings intact, replacing just the Debian/Ubuntu
  # 127.0.1.1 local-hostname entry. Repeating provisioning never duplicates it.
  hosts_candidate="$(mktemp)"
  awk -v name="$guest_hostname" '
    $1 == "127.0.1.1" {
      if (!replaced) { print "127.0.1.1\t" name; replaced=1 }
      next
    }
    { print }
    END { if (!replaced) print "127.0.1.1\t" name }
  ' /etc/hosts > "$hosts_candidate"
  if ! cmp -s "$hosts_candidate" /etc/hosts; then
    cat "$hosts_candidate" > /etc/hosts
  fi
  rm -f "$hosts_candidate"

  if [[ "$(hostnamectl --static)" != "$guest_hostname" || "$(hostname)" != "$guest_hostname" ]]; then
    hostnamectl set-hostname "$guest_hostname"
  fi

  # Bento Ubuntu/Debian may ship cloud-init. Ensure it doesn't replace the
  # student-facing static hostname on the next ordinary VMware boot.
  if [[ -d /etc/cloud/cloud.cfg.d ]]; then
    printf 'preserve_hostname: true\n' > /etc/cloud/cloud.cfg.d/99-purple-guest-hostname.cfg
  fi
  [[ "$(hostname)" == "$guest_hostname" ]] || {
    echo "PURPLE: unexpected Linux hostname after provisioning" >&2; exit 1;
  }
  getent hosts "$guest_hostname" >/dev/null || {
    echo "PURPLE: guest hostname does not resolve via /etc/hosts" >&2; exit 1;
  }
  echo "PURPLE_LINUX_HOSTNAME_READY=$guest_hostname"
fi

# Preserve lab NIC configuration across guest restarts, without replacing
# NetworkManager/netplan/ifupdown or modifying the Vagrant management NIC.
if [[ "${PURPLE_BOOT_SERVICE:-0}" != "1" ]]; then
  cat > /etc/systemd/system/purple-lab-interface.service <<EOF
[Unit]
Description=Restore isolated Purple Team lab NIC
After=network.target NetworkManager.service systemd-networkd.service networking.service
[Service]
Type=oneshot
Environment=PURPLE_BOOT_SERVICE=1
ExecStart=/usr/local/sbin/purple-lab-interface $ipaddr $mac
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable purple-lab-interface.service
fi
echo "PURPLE_LAB_INTERFACE_READY=$interface $ipaddr"
