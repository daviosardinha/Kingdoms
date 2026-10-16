#!/usr/bin/env bash
# One-shot WSLPE-only packet-path evidence; safe baseline is default.
# --execute explicitly authorizes only previously reviewed 180s nft pilot.
set -euo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Existing WSLPE Python environment missing'; exit 1; }
MODE="--baseline"
if [[ $# -gt 0 ]]; then MODE="$1"; fi
if [[ $# -gt 1 || "$MODE" != "--baseline" && "$MODE" != "--execute" ]]; then
  echo '[BLOCKED] Use --baseline (default) or --execute'; exit 1
fi

echo '===== WSLPE PACKET-PATH REGRESSION ====='
"$PY" -m py_compile \
  kingdoms/wslpe_packet_path.py \
  scripts/wslpe-p1c-packet-acceptance.py
"$PY" -m unittest -v \
  tests.test_wslpe_packet_acceptance \
  tests.test_wslpe_p1c_host_filter_pilot \
  tests.test_wslpe_remote_operator \
  tests.test_wslpe_isolation_policy

echo '===== WSLPE OPERATOR PRIVILEGED READ-ONLY GATE ====='
sudo -v

echo '===== WSLPE CONTROLLED PACKET-PATH PROOF ====='
if [[ "$MODE" == "--baseline" ]]; then
  "$PY" scripts/wslpe-p1c-packet-acceptance.py --baseline
  echo '[PASS] Source + guest-to-owned-host baseline complete; no firewall applied'
  exit 0
fi

if [[ -n "${SSH_CONNECTION:-}" ]]; then
  echo '[INFO] SSH operator detected: remote route and rollback checks required'
else
  [[ -t 0 && -t 1 ]] || {
    echo '[BLOCKED] Local execution requires an interactive Kali console'
    exit 1
  }
  echo '[INFO] Kali local operator: independent host timer check required'
fi
echo 'The confirmed pilot temporarily filters WSLPE-only vmnet2 for 180s.'
echo 'Continue only with host-side recovery available.'
printf 'Type PROVE WSLPE PACKET ISOLATION to continue: '
CONFIRM=''
IFS= read -r CONFIRM </dev/tty || {
  echo '[BLOCKED] Interactive SSH confirmation required'; exit 1
}
[[ "$CONFIRM" == "PROVE WSLPE PACKET ISOLATION" ]] || {
  echo '[CANCELLED] No firewall changes'; exit 1
}

"$PY" scripts/wslpe-p1c-packet-acceptance.py --execute \
  --confirm 'PROVE WSLPE PACKET ISOLATION'
echo '[PASS] WSLPE-only packet acceptance finished'
