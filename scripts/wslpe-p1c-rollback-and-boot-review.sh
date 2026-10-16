#!/usr/bin/env bash
# One WSLPE-only recovery timer / boot handoff source gate. READ ONLY.
# No mutation of NORTH, Windows, VMware, VMX, NAT, nft or systemd.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Existing GOAD Python venv missing'; exit 1; }

echo '===== WSLPE CONSOLIDATED RECOVERY + TIMER SAFETY REGRESSIONS ====='
"$PY" -m py_compile \
    kingdoms/wslpe_recovery_bundle.py \
    kingdoms/wslpe_rollback_worker.py \
    kingdoms/wslpe_rollback_timer_plan.py \
    scripts/wslpe-p1c-rollback-worker.py \
    scripts/wslpe-p1c-rollback-plan.py \
    tests/test_wslpe_rollback_timer_plan.py
"$PY" -m unittest -v \
    tests.test_wslpe_recovery_bundle \
    tests.test_wslpe_exact_restore \
    tests.test_wslpe_vmware_recover \
    tests.test_wslpe_rollback_timer_plan \
    tests.test_wslpe_boot_policy \
    tests.test_wslpe_north_cutover_parity \
    tests.test_wslpe_nat_readiness

echo '===== EXACT WSLPE LIVE REGISTRATION / TIMER PREVIEW ====='
"$PY" scripts/wslpe-p1c-rollback-plan.py

echo '===== BOOT GUARD CURRENT PORT VALIDATION (READ ONLY) ====='
sudo -v
"$PY" scripts/wslpe-p1c-boot-policy-preview.py

echo '[PASS] WSLPE_RECOVERY_TIMER_AND_BOOT_PREVIEW=TRUE'
echo '[NO CHANGES] NORTH, VMware, guest, VMX, NAT, nftables and systemd untouched'
echo '[RELEASE BLOCKED] Timer arming and real recovery worker are not yet enabled'
echo '[RELEASE BLOCKED] Boot-persistent firewall and Layer 2 isolation not proven'
