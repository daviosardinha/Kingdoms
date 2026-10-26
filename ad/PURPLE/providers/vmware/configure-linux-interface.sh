#!/usr/bin/env bash
# Configure exactly the Purple Team lab NIC, selected by deterministic VMware MAC.
# No gateway, DNS, NAT, host route, or host networking changes.
set -euo pipefail
ipaddr="${1:?expected IPv4 address}"
mac="${2:?expected VMware NIC MAC}"
case "$ipaddr" in
  192.168.240.*) ;;
  *) echo "PURPLE: refusing address outside 192.168.240.0/24: $ipaddr" >&2; exit 1 ;;
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
