#!/usr/bin/env bash
# All WSLPE host-filter PREVIEW checks in one command.
# No guest/VM/NAT operations, no nft installation, no NORTH network traffic.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Existing Kingdoms Python venv missing'; exit 1; }
command -v nft >/dev/null || { echo '[BLOCKED] nft is unavailable'; exit 1; }
command -v systemd-run >/dev/null || { echo '[BLOCKED] systemd-run unavailable'; exit 1; }
command -v systemctl >/dev/null || { echo '[BLOCKED] systemctl unavailable'; exit 1; }

echo '===== WSLPE HOST FILTER — SOURCE REGRESSION ====='
"$PY" -m py_compile scripts/wslpe-p1c-host-filter-pilot.py
"$PY" -m unittest -v \
    tests.test_wslpe_p1c_host_filter_pilot \
    tests.test_wslpe_isolation_policy \
    tests.test_wslpe_p1c_batch_review \
    tests.test_wslpe_https_auth_audit

echo '===== WSLPE READ-ONLY PRIVILEGED PREFLIGHT ====='
sudo -v

echo '===== AUTHENTICATED HTTPS MANAGEMENT RECHECK ====='
"$PY" scripts/wslpe-https-auth-audit.py \
    --expected-thumbprint C773EC26D02940F559FE715B83628FEDAE2AA92D

echo '===== WSLPE FILTER PREVIEW — NOT APPLIED ====='
"$PY" scripts/wslpe-p1c-host-filter-pilot.py

echo '[PASS] WSLPE bounded firewall candidate ready for operator review'
echo '[NOT VERIFIED] Timed pilot runtime, nft drop behavior, L2/NAT isolation'
echo '[NO CHANGES] NORTH, guest, VMware, nftables, NAT and host routing unchanged'
