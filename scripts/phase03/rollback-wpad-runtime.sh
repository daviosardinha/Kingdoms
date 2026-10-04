#!/usr/bin/env bash
# Deterministically restore WS01 networking after the Phase 03 mitm6/WPAD exercise.
# This wrapper never reboots, resets, or disables the Windows adapter.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-wpad-baseline.json}"
PLAYBOOK="$ROOT/ansible/phase03-wpad-rollback.yml"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"

find_ansible_playbook() {
  local candidate
  for candidate in \
    "$(command -v ansible-playbook 2>/dev/null || true)" \
    "$ROOT/.venv/bin/ansible-playbook" \
    "$ROOT/venv/bin/ansible-playbook" \
    "$HOME/.goad/.venv/bin/ansible-playbook" \
    "$HOME/.local/bin/ansible-playbook"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    printf '%s\n' "$candidate"
    return 0
  done
  return 1
}

cd "$ROOT"

[[ -f "$BASELINE" ]] || {
  echo "FAIL: WPAD baseline missing: $BASELINE" >&2
  echo 'Run scripts/phase03/check-wpad-permanent-prereqs.sh before the exercise.' >&2
  exit 1
}

[[ -f "$PLAYBOOK" ]] || {
  echo "FAIL: rollback playbook missing: $PLAYBOOK" >&2
  exit 1
}

if [[ "${WPAD_SKIP_LOCAL_STOP:-0}" != "1" ]]; then
  echo '===== STOP TEMPORARY MITM6 / WPAD RUNTIME ====='
  bash scripts/phase03/diagnostics/stop-wpad-runtime.sh
else
  echo '===== LOCAL WPAD RUNTIME CLEANUP ALREADY PERFORMED ====='
fi

if pgrep -af '(^|[ /])mitm6([ ]|$)' >/dev/null; then
  echo 'FAIL: mitm6 is still active. Refusing to restore DHCPv6 state while the rogue server is running.' >&2
  exit 1
fi
echo 'PASS: mitm6 is stopped before network rollback'

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || {
  echo 'FAIL: ansible-playbook not found' >&2
  exit 1
}

echo
echo '===== RESTORE WS01 IPV6 / DNS STATE ====='
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$PLAYBOOK"

echo
echo '===== VERIFY EXACT CAPTURED BASELINE ====='
bash scripts/phase03/verify-wpad-reset.sh

echo
echo 'PHASE03_WPAD_DETERMINISTIC_ROLLBACK_COMPLETE=True'
