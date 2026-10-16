#!/usr/bin/env bash
# One command to verify NORTH-derived WSLPE reuse, without touching NORTH.
# READ ONLY: no VM, NIC, route, Windows or firewall modifications.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Existing GOAD Python environment missing'; exit 1; }

echo '===== WSLPE / NORTH ENGINEERING PARITY (SOURCE ONLY) ====='
"$PY" -m py_compile \
    kingdoms/wslpe_nat_cutover_contract.py \
    scripts/wslpe-p1c-north-cutover-preview.py \
    tests/test_wslpe_north_cutover_parity.py
"$PY" -m unittest -v \
    tests.test_wslpe_north_cutover_parity \
    tests.test_wslpe_ws01_parity \
    tests.test_wslpe_nat_readiness \
    tests.test_wslpe_isolation_policy \
    tests.test_wslpe_winrm_guard
echo '[PASS] NORTH-derived local, domain-free source reuse verified'

echo '===== WSLPE READ-ONLY EXACT VMX/NAT PREVIEW ====='
"$PY" scripts/wslpe-p1c-north-cutover-preview.py
echo '[NO CHANGES] No VMX, VMware, Windows, host nftables or NORTH mutations'
