#!/usr/bin/env bash
# WSLPE-only host owner recovery rehearsal in ONE command.
# No VMware lifecycle, NAT disconnect, VMX edit, Windows or nft modifications.
set -euo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Existing GOAD Python unavailable'; exit 1; }

echo '===== WSLPE OWNER-RECOVERY SOURCE GATE ====='
"$PY" -m py_compile \
  kingdoms/wslpe_owner_recovery.py \
  scripts/wslpe-p1c-owner-recovery-check.py \
  tests/test_wslpe_owner_recovery.py
"$PY" -m unittest -v \
  tests.test_wslpe_owner_recovery \
  tests.test_wslpe_north_cutover_parity \
  tests.test_wslpe_nat_readiness

echo '===== INDEPENDENT HOST TIMER REHEARSAL ====='
echo 'Creates one disposable /tmp sentinel as the exact WSLPE VMware owner.'
echo 'No NAT, guest, NORTH or firewall modifications are authorized.'
sudo -v
"$PY" scripts/wslpe-p1c-owner-recovery-check.py --rehearse
echo '[PASS] WSLPE_OWNER_RECOVERY_REHEARSAL=TRUE'
echo '[NOT VERIFIED] VMware owner vmrun stop/start and powered-off VMX restore'
echo '[RELEASE BLOCKED] NAT handoff and learner access remain locked'
