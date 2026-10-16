#!/usr/bin/env bash
# WSLPE-only next-stage source and runtime preview.
# NEVER performs vmrun stop/start, writes a registered VMX, installs
# nftables, enables systemd services, changes NAT or contacts NORTH.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
PY="$HOME/.goad/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[BLOCKED] Existing GOAD Python venv missing'; exit 1; }

echo '===== P1-C RECOVERY AND DYNAMIC BOOT-GUARD SOURCE REGRESSIONS ====='
"$PY" -m py_compile \
  kingdoms/wslpe_exact_restore.py \
  kingdoms/wslpe_vmware_recover.py \
  kingdoms/wslpe_boot_policy.py \
  scripts/wslpe-p1c-boot-policy-preview.py
"$PY" -m unittest -v \
  tests.test_wslpe_exact_restore \
  tests.test_wslpe_vmware_recover \
  tests.test_wslpe_boot_policy \
  tests.test_wslpe_north_cutover_parity \
  tests.test_wslpe_nat_readiness

echo '===== LIVE EXACT WSLPE BOOT FIREWALL PREVIEW ====='
sudo -v
"$PY" scripts/wslpe-p1c-boot-policy-preview.py

echo '===== FINAL SOURCE CHECKPOINT ====='
echo '[PASS] WSLPE_P1C_RECOVERY_AND_BOOT_POLICY_PREVIEW=TRUE'
echo '[NO CHANGES] NORTH, VMware, Windows, NAT, host firewall and systemd'
echo '[RELEASE BLOCKED] No rollback timer wired to real VMX changes yet'
echo '[RELEASE BLOCKED] No boot-persistent policy installed or reboot-proven'
echo '[RELEASE BLOCKED] vmnet2 host/L2 isolation still unproven'
