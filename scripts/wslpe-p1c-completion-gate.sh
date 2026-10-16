#!/usr/bin/env bash
# Single consolidated WSLPE P1-C completion gate.
# READ ONLY: no VM lifecycle, NAT disconnect, firewall writes, Windows change
# or traffic to NORTH. Uses prior 38/38 IPv4 packet-proof acceptance.
set -euo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Existing GOAD Python venv missing'; exit 1; }

echo 'KINGDOMS WSLPE | ONE-PASS P1-C COMPLETION GATE'
echo '[NO CHANGES] Exact native WSLPE only, NORTH frozen, no NAT/network mutations'

echo '===== SOURCE AND SAFETY CONTRACTS ====='
"$PY" -m py_compile \
    kingdoms/wslpe_nat_readiness.py \
    scripts/wslpe-p1c-nat-readiness-audit.py
"$PY" -m unittest -v \
    tests.test_wslpe_nat_readiness \
    tests.test_wslpe_packet_acceptance \
    tests.test_wslpe_p1c_host_filter_pilot \
    tests.test_wslpe_remote_operator \
    tests.test_wslpe_isolation_policy \
    tests.test_wslpe_https_auth_audit \
    tests.test_wslpe_p1c_batch_review \
    tests.test_wslpe_p1c_topology_audit
echo '[PASS] WSLPE completion source/safety gate'

sudo -v

echo '===== COLLECT ALL REMAINING P1-C EVIDENCE ====='
FAIL=0

if bash scripts/wslpe-full-review.sh; then
    echo '[PASS] WSLPE existing host and guest full review'
else
    echo '[BLOCKED] Existing host and guest full review'
    FAIL=1
fi

if "$PY" scripts/wslpe-p1c-nat-readiness-audit.py; then
    echo '[PASS] Exact VMX/NAT/IPv4/IPv6/certificate/host persistence audit collected'
else
    echo '[BLOCKED] Exact VMX/NAT/IPv4/IPv6/certificate/host readiness audit'
    FAIL=1
fi

if "$PY" scripts/wslpe-p1c-host-filter-pilot.py --verify-rollback; then
    echo '[PASS] Prior WSLPE firewall pilot absent; authenticated HTTPS works'
else
    echo '[BLOCKED] Prior WSLPE filter removal or HTTPS not confirmed'
    FAIL=1
fi

echo
echo '===== FINAL CONSOLIDATED P1-C DECISION ====='
if [[ "$FAIL" -ne 0 ]]; then
    echo '[BLOCKED] Evidence collection incomplete: DO NOT disconnect NAT'
    echo '[NO CHANGES] NORTH, VMware, Windows and host rules untouched'
    exit 1
fi

echo '[PASS] WSLPE_P1C_CONSOLIDATED_EVIDENCE=COLLECTED'
echo '[PASS] Previous 38/38 controlled IPv4 packet filtering acceptance retained'
echo '[RELEASE BLOCKED] VMware NAT cutover still needs proven VMX-only rollback'
echo '[RELEASE BLOCKED] Persistent host/L2/IPv6 protection still unproven'
echo '[RELEASE BLOCKED] Local learner RDP and scenario acceptance pending'
echo '[NO CHANGES] WSLPE remains PROVIDED, NORTH frozen'
