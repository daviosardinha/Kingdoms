#!/usr/bin/env bash
# Source-only NORTH -> standalone Windows LPE parity contract.
# This does NOT start, provision, modify or contact VMware/Windows guests.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Kingdoms existing Python venv unavailable'; exit 1; }
cd "$ROOT"
echo "KINGDOMS WSLPE | NORTH WS01 SOURCE PARITY (READ ONLY)"
"$PY" -m unittest -v \
    tests.test_wslpe_ws01_parity \
    tests.test_wslpe_native_lab_contract \
    tests.test_wslpe_resume \
    tests.test_wslpe_access_audit \
    tests.test_wslpe_https_trust_audit \
    tests.test_wslpe_https_auth_audit \
    tests.test_wslpe_p1c_topology_audit \
    tests.test_wslpe_isolation_policy \
    tests.test_wslpe_p1c_batch_review \
    tests.test_wslpe_p1c_host_filter_pilot \
    tests.test_wslpe_remote_operator \
    tests.test_wslpe_packet_acceptance \
    tests.test_wslpe_nat_readiness \
    tests.test_windows_lpe_learner_adapters
"$PY" scripts/windows-lpe-standalone-audit.py --strict
echo "[PASS] WSLPE/NORTH source contract"
echo "[NOT VERIFIED] Operator-only segment, learner RDP, exercise isolation, scenario exploitation"
echo "[NO CHANGES] VM state, Windows, VMware, NAT and NORTH remain untouched"
