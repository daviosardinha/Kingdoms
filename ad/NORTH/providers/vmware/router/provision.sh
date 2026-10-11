#!/usr/bin/env bash
set -euo pipefail

# GOAD_NOMAD VMware routing-plane bootstrap.
# Vagrant keeps adapter 0 (NAT) available during provisioning.
# The three custom adapters below are identified by deterministic MAC addresses
# and configured as the gateways for the lab networks.

readonly NORTH_MAC="00:50:56:10:10:01"
readonly SEVENKINGDOMS_MAC="00:50:56:10:20:01"
readonly MANAGEMENT_MAC="00:50:56:10:99:01"

find_iface_by_mac() {
  local wanted
  wanted="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"

  local path current
  for path in /sys/class/net/*; do
    [[ -f "${path}/address" ]] || continue
    current="$(tr '[:upper:]' '[:lower:]' < "${path}/address")"
    if [[ "${current}" == "${wanted}" ]]; then
      basename "${path}"
      return 0
    fi
  done

  return 1
}

configure_lab_interface() {
  local label="$1"
  local mac="$2"
  local address="$3"
  local iface

  if ! iface="$(find_iface_by_mac "${mac}")"; then
    echo "[!] Could not find ${label} interface with MAC ${mac}" >&2
    ip -br link >&2 || true
    exit 1
  fi

  echo "[*] ${label}: ${iface} -> ${address}/24"
  ip link set dev "${iface}" up
  ip addr flush dev "${iface}"
  ip addr add "${address}/24" dev "${iface}"

  cat >> /etc/network/interfaces.d/goad-router <<EOF

auto ${iface}
iface ${iface} inet static
    address ${address}
    netmask 255.255.255.0
EOF
}

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends nftables

install -d -m 0755 /etc/network/interfaces.d
cat > /etc/network/interfaces.d/goad-router <<'EOF'
# Managed by GOAD_NOMAD. Do not add a default gateway on lab interfaces.
# Vagrant NAT bootstraps installation; installed lifecycle SSH uses MANAGEMENT.
# Exercise isolation is enforced by the router forward policy and by disconnecting
# the Windows guests' provisioning NAT adapters.
EOF

configure_lab_interface "NORTH" "${NORTH_MAC}" "10.4.10.1"
configure_lab_interface "SEVENKINGDOMS" "${SEVENKINGDOMS_MAC}" "10.4.20.1"
configure_lab_interface "MANAGEMENT" "${MANAGEMENT_MAC}" "10.4.99.1"

cat > /etc/sysctl.d/99-goad-nomad-router.conf <<'EOF'
net.ipv4.ip_forward = 1
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.default.rp_filter = 0
EOF

sysctl --system >/dev/null

# Router bootstrap starts in provisioning mode.
# Forwarding is intentionally permissive while Vagrant/Ansible configures the
# lab. Before training begins, scripts/lab-mode.sh switches the range to the
# validated deny-by-default exercise policy and isolates Windows NAT adapters.
cat > /etc/nftables.conf <<'EOF'
#!/usr/sbin/nft -f
flush ruleset

table inet goad_nomad {
    chain input {
        type filter hook input priority 0;
        policy accept;
    }

    chain forward {
        type filter hook forward priority 0;
        policy accept;
    }

    chain output {
        type filter hook output priority 0;
        policy accept;
    }
}
EOF

systemctl enable nftables >/dev/null
systemctl restart nftables

echo
printf '%s\n' "[+] GOAD_NOMAD router bootstrap complete"
printf '%s\n' "    NORTH          10.4.10.1/24"
printf '%s\n' "    SEVENKINGDOMS  10.4.20.1/24"
printf '%s\n' "    MANAGEMENT     10.4.99.1/24"
printf '%s\n' "    IPv4 forwarding enabled"
printf '%s\n' "    nftables active (provisioning allow-forward policy)"

ip -br address
nft list ruleset
