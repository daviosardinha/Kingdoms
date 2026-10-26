#!/usr/bin/env bash
# Read-only network ownership gate for the Purple Team VMware baseline.
# This does NOT create networks, restart VMware, or alter running guests.
set -euo pipefail
vmnet=vmnet40
subnet=192.168.240.0
config=/etc/vmware/networking
fail() { echo "[FAIL] $*" >&2; exit 1; }
require_field() {
  local field="$1" expected="$2"
  grep -Eq "^answer VNET_40_${field} ${expected}$" "$config" ||
    fail "Expected VNET_40_${field}=${expected} in $config"
}

[[ -r "$config" ]] || fail "$config not readable"
[[ -c /dev/vmnet40 ]] || fail "/dev/vmnet40 missing: provision host-only network first"
ip link show "$vmnet" >/dev/null 2>&1 || fail "$vmnet host adapter missing"
require_field HOSTONLY_SUBNET "$subnet"
require_field HOSTONLY_NETMASK 255.255.255.0
require_field NAT no
require_field DHCP no

host_cidr="$(ip -o -4 address show dev "$vmnet" | awk '$3 == "inet" {print $4; exit}')"
[[ "$host_cidr" =~ ^192[.]168[.]240[.][0-9]{1,3}/24$ ]] ||
  fail "Expected a host adapter address on 192.168.240.0/24, found: $host_cidr"
case "$host_cidr" in
  192.168.240.30/24|192.168.240.31/24|192.168.240.32/24|192.168.240.51/24)
    fail "Host IP conflicts with a Purple Team guest"
    ;;
esac
ip -4 route show "$subnet/24" | grep -q "dev $vmnet" ||
  fail "Missing Purple Team route via vmnet40"

# A wrong remote route is an immediate failure, not an excuse to rewrite
# VPN/firewall configuration.
if ip -4 route show table all | grep -E '^192\.168\.240\.0/24' | grep -v 'dev vmnet40' >/dev/null; then
  fail "Competing route for Purple Team subnet"
fi
echo "[PASS] vmnet40 is host-only and matches 192.168.240.0/24"
echo "[PASS] no VMware host network changes performed"
echo "[NOTE] Windows/Linux Vagrant NAT NICs remain for provisioning until separately hardened."
