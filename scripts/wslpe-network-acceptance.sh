#!/usr/bin/env bash
# Consolidated read-only WSLPE NAT firewall + Windows + private NIC validation.
# Requires sudo for current live nftables/ss evidence but never mutates host.
set -uo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$HOME/.goad/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo '[BLOCKED] Existing Kingdoms Python virtual environment missing' >&2
  exit 1
fi
cd "$ROOT"
printf '\nKINGDOMS WSLPE | POSTBOOT NETWORK ACCEPTANCE (READ ONLY)\n'
printf 'No nft apply, VMware operations, NAT disconnect or guest provisioning\n'

printf '\n[CHECK] WSLPE regression/source contracts\n'
"$PYTHON" -m unittest discover -s tests -p 'test_wslpe_*.py' -q
if [[ "$?" -ne 0 ]]; then
  echo '[BLOCKED] WSLPE regression tests failed'
  exit 1
fi

printf '\n[CHECK] Validate privileged nftables audit permissions\n'
if ! sudo -v; then
  echo '[BLOCKED] Cannot obtain read-only privileged network evidence'
  exit 1
fi

fail=0
printf '\n[CHECK] Scoped host-port firewall rule and listener ownership\n'
sudo "$PYTHON" scripts/wslpe-winrm-firewall.py || fail=1

printf '\n[CHECK] Stage 2 live Windows and WinRM baseline\n'
bash scripts/wslpe-stage2-acceptance.sh || fail=1

printf '\n[CHECK] NORTH-derived WSLPE dedicated exercise NIC/subnet contract\n'
"$PYTHON" scripts/wslpe-exercise-network-preflight.py || fail=1

if [[ "$fail" -ne 0 ]]; then
  echo '[BLOCKED] One or more WSLPE postboot gates remain unresolved'
  echo '[NO CHANGES] No WSLPE, NORTH, VMware or firewall state modified'
  exit 1
fi

echo '[PASS] WSLPE management-port guard, Windows baseline and exercise NIC preflight'
echo '[NOT VERIFIED] Authenticated direct management on exercise NIC; exercise-mode cutover'
echo '[NO CHANGES] No WSLPE, NORTH, VMware or firewall state modified'
