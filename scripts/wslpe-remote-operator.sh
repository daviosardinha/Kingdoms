#!/usr/bin/env bash
# WSLPE-only remote SSH firewall operator workflow.
# Default: short-lived /run systemd timer smoke preflight; no nft installation.
# --execute: confirmed, bounded 120-second firewall test.
# --verify: check table removal and HTTPS after reconnecting.
set -euo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Existing Kingdoms Python missing'; exit 1; }

MODE="--preflight"
if [[ $# -gt 0 ]]; then MODE="$1"; fi
if [[ $# -gt 1 ]]; then
    echo '[BLOCKED] Use --preflight, --execute or --verify only'
    exit 1
fi
case "$MODE" in
    --preflight|--execute|--verify) ;;
    *) echo '[BLOCKED] Unknown WSLPE remote workflow mode'; exit 1 ;;
esac

if [[ ! -v SSH_CONNECTION ]] || [[ -z "$SSH_CONNECTION" ]]; then
    echo '[BLOCKED] Remote SSH session with SSH_CONNECTION is required'
    exit 1
fi

echo 'KINGDOMS WSLPE | SAFE REMOTE OPERATOR WORKFLOW'
echo 'NORTH frozen; no VMware, NAT, routing or Windows lifecycle changes'
sudo -v

if [[ "$MODE" == "--verify" ]]; then
    echo '===== CHECK HOST-SIDE ROLLBACK AND AUTHENTICATED HTTPS ====='
    "$PY" scripts/wslpe-p1c-host-filter-pilot.py --verify-rollback
    exit $?
fi

echo '===== WSLPE SOURCE REGRESSION ====='
"$PY" -m py_compile \
    kingdoms/wslpe_remote_operator.py \
    scripts/wslpe-p1c-host-filter-pilot.py
"$PY" -m unittest -v \
    tests.test_wslpe_remote_operator \
    tests.test_wslpe_p1c_host_filter_pilot \
    tests.test_wslpe_isolation_policy \
    tests.test_wslpe_https_auth_audit

echo '===== CERTIFICATE-VERIFIED WSLPE HTTPS ====='
"$PY" scripts/wslpe-https-auth-audit.py \
    --expected-thumbprint C773EC26D02940F559FE715B83628FEDAE2AA92D

if [[ "$MODE" == "--preflight" ]]; then
    echo '===== REMOTE SSH ROUTE + INDEPENDENT HOST TIMER SELF-TEST ====='
    "$PY" scripts/wslpe-p1c-host-filter-pilot.py --remote-preflight
    echo '[PASS] WSLPE_REMOTE_OPERATOR_PREFLIGHT=TRUE'
    echo '[NO FIREWALL CHANGES] No nft rule installed or NAT modification'
    exit 0
fi

echo '===== CONFIRM TIME-LIMITED HOST FIREWALL CHANGE ====='
echo 'This affects WSLPE vmnet only and runs 120 seconds.'
echo 'An independent host-side rollback is armed BEFORE applying any rule.'
echo 'If SSH disconnects, reconnect and run this script with --verify.'
printf 'Type PILOT WSLPE HOST FILTER to continue: '
CONFIRM=''
IFS= read -r CONFIRM </dev/tty || {
    echo '[BLOCKED] Interactive SSH TTY required for state-changing operation'
    exit 1
}
if [[ "$CONFIRM" != "PILOT WSLPE HOST FILTER" ]]; then
    echo '[CANCELLED] No firewall rules installed'
    exit 1
fi

echo '===== VERIFIED-ROLLBACK REMOTE WSLPE FIREWALL PILOT ====='
"$PY" scripts/wslpe-p1c-host-filter-pilot.py \
    --pilot --remote --seconds 120 \
    --confirm "PILOT WSLPE HOST FILTER"

echo '===== ALLOW HOST-SIDE TIMER TO REMOVE SCOPED TABLE ====='
sleep 140
"$PY" scripts/wslpe-p1c-host-filter-pilot.py --verify-rollback
echo '[PASS] WSLPE_REMOTE_PILOT_ROLLBACK_AND_HTTPS=TRUE'
echo '[RELEASE BLOCKED] Guest NAT/L2 isolation and learner RDP still unverified'
