#!/usr/bin/env bash
# One-shot WSLPE owner-context VMware list and offline scratch restore gate.
# Uses a root-scheduled timer executing unprivileged VMX-owner code.
# NEVER powers VM, edits registered VMX, touches NORTH or changes firewall.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Expected Kingdoms Python unavailable'; exit 1; }

echo '===== WSLPE NORTH-REUSED OWNER RECOVERY SOURCE CONTRACTS ====='
"$PY" -m py_compile \
  kingdoms/wslpe_vmrun_recovery.py \
  scripts/wslpe-p1c-owner-vmrun-worker.py \
  scripts/wslpe-p1c-owner-recovery-check.py \
  tests/test_wslpe_vmrun_recovery.py
"$PY" -m unittest -v \
  tests.test_wslpe_vmrun_recovery \
  tests.test_wslpe_owner_recovery \
  tests.test_wslpe_north_cutover_parity \
  tests.test_wslpe_nat_readiness

echo '===== HOST-SIDE VMWARE OWNER PROOF + SCRATCH VMX RESTORE ====='
sudo -v
"$PY" scripts/wslpe-p1c-owner-recovery-check.py \
  --rehearse --vmrun-readonly

echo '[PASS] WSLPE_VMWARE_OWNER_RECOVERY_READONLY_GATE=TRUE'
echo '[NOT VERIFIED] Live VM shutdown/start, physical VMX replacement or independent recovery from failure'
echo '[RELEASE BLOCKED] NAT handoff, persistent host firewall and learner isolation'
