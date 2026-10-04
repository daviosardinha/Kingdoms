#!/usr/bin/env bash
# Read-only preflight for permanent mitm6/WPAD -> HTTP -> LDAPS infrastructure.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
IFACE="${IFACE:-vmnet10}"
WS01_IP="${WS01_IP:-10.4.10.31}"
DC_IP="${DC_IP:-10.4.10.11}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-wpad-baseline.json}"
PLAYBOOK="$ROOT/ansible/phase03-wpad-baseline.yml"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"

find_ansible_playbook() {
  local candidate_file
  for candidate_file in \
    "$(command -v ansible-playbook 2>/dev/null || true)" \
    "$ROOT/.venv/bin/ansible-playbook" \
    "$ROOT/venv/bin/ansible-playbook" \
    "$HOME/.goad/.venv/bin/ansible-playbook" \
    "$HOME/.local/bin/ansible-playbook"; do
    [[ -n "$candidate_file" && -x "$candidate_file" ]] || continue
    printf '%s\n' "$candidate_file"
    return 0
  done
  return 1
}

cd "$ROOT"

echo '===== PHASE 03 WPAD / LDAPS PERMANENT PREFLIGHT ====='

echo '===== SOURCE / RUNTIME ====='
bash scripts/verify-test-source.sh || {
  echo "FAIL: source checkout does not match its configured upstream" >&2
  exit 1
}

if pgrep -af '(^|[ /])(mitm6|impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder)([ ]|$)' >/dev/null; then
  echo 'FAIL: conflicting Phase 03 attack runtime is active' >&2
  pgrep -af '(^|[ /])(mitm6|impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder)([ ]|$)' || true
  exit 1
fi
echo 'PASS: neutral Phase 03 runtime'

echo
echo '===== TOOLING ====='
for tool_name in mitm6 impacket-ntlmrelayx tcpdump tshark nc ip; do
  if command -v "$tool_name" >/dev/null 2>&1; then
    echo "FOUND: $tool_name -> $(command -v "$tool_name")"
  else
    echo "NOT_FOUND: $tool_name"
  fi
done

echo
echo '===== ATTACKER INTERFACE ====='
ip link show "$IFACE" >/dev/null 2>&1 || { echo "FAIL: interface $IFACE not found" >&2; exit 1; }
ip -br addr show dev "$IFACE"
ATTACKER_V6="$(ip -6 -o addr show dev "$IFACE" scope link | awk '{print $4}' | cut -d/ -f1 | head -n1)"
[[ -n "$ATTACKER_V6" ]] || { echo "FAIL: $IFACE has no IPv6 link-local address" >&2; exit 1; }
echo "PHASE03_WPAD_PREFLIGHT_ATTACKER_V6=$ATTACKER_V6"

echo
echo '===== TARGET REACHABILITY ====='
ip route get "$WS01_IP" | head -n1
ip route get "$DC_IP" | head -n1
timeout 4 nc -z -w3 "$DC_IP" 636 >/dev/null 2>&1 || { echo "FAIL: WINTERFELL TCP/636 unreachable" >&2; exit 1; }
echo 'PASS: WINTERFELL TCP/636 reachable'

echo
echo '===== LISTENER OWNERSHIP ====='
for port in 80 445; do
  if sudo ss -H -lnt 2>/dev/null | grep -Eq ":$port[[:space:]]"; then
    echo "FAIL: TCP/$port already has a listener" >&2
    sudo ss -H -lntp 2>/dev/null | grep -E ":$port[[:space:]]" || true
    exit 1
  fi
  echo "PASS: TCP/$port is free"
done

echo
echo '===== CAPTURE EXACT WS01 BASELINE ====='
ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo "FAIL: ansible-playbook not found" >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$PLAYBOOK"

[[ -f "$BASELINE" ]] || { echo "FAIL: WPAD baseline missing: $BASELINE" >&2; exit 1; }
[[ "$(stat -Lc '%a' "$BASELINE")" == "600" ]] || { echo "FAIL: WPAD baseline must be mode 600" >&2; exit 1; }

python3 - "$BASELINE" <<'PY'
import json,sys

d=json.load(open(sys.argv[1],encoding='utf-8'))
if d.get('Target') != 'WS01' or d.get('IPv4') != '10.4.10.31':
    raise SystemExit('FAIL: WPAD baseline does not describe WS01 / 10.4.10.31')

dns6 = [str(item) for item in d.get('IPv6DnsServers', []) if str(item).strip()]
dhcp6 = [
    str(item.get('Address', ''))
    for item in d.get('IPv6Addresses', [])
    if str(item.get('PrefixOrigin', '')).lower() == 'dhcp'
    or str(item.get('SuffixOrigin', '')).lower() == 'dhcp'
]

if dns6:
    raise SystemExit(
        'FAIL: WS01 baseline already contains IPv6 DNS state; '
        'refusing to arm WPAD from a potentially contaminated baseline: '
        + ','.join(dns6)
    )

if dhcp6:
    raise SystemExit(
        'FAIL: WS01 baseline already contains DHCP-originated IPv6 state; '
        'refusing to arm WPAD from a potentially contaminated baseline: '
        + ','.join(dhcp6)
    )

print(f"INTERFACE={d['InterfaceAlias']}")
print(f"INTERFACE_INDEX={d['InterfaceIndex']}")
print(f"IPV6_COUNT={len(d['IPv6Addresses'])}")
print(f"DNSV6_COUNT={len(d['IPv6DnsServers'])}")
for item in d['IPv6Addresses']:
    print('BASELINE_IPV6=' + item['Address'])
print('PHASE03_WPAD_BASELINE_CLEAN=True')
print('PHASE03_WPAD_BASELINE_VALID=True')
PY

echo
echo '===== FINAL REPOSITORY STATE ====='
git status --short --branch
