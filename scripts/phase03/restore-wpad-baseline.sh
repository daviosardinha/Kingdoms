#!/usr/bin/env bash
# Restore the exact pre-WPAD WS01 IPv6/DNS baseline.
#
# Rollback is state-driven: mutate only the NORTH-facing IPv6/DNS values that
# differ from the captured baseline, then require the existing exact verifier
# to pass. No reboot, adapter reset, IPv4 change, or lab lifecycle transition.
set -Eeuo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
ATTEMPTS="${WPAD_RESTORE_ATTEMPTS:-2}"
RESTORE_TIMEOUT_SECONDS="${WPAD_RESTORE_TIMEOUT_SECONDS:-60}"
VERIFY_TIMEOUT_SECONDS="${WPAD_VERIFY_TIMEOUT_SECONDS:-45}"
SETTLE_SECONDS="${WPAD_RESTORE_SETTLE_SECONDS:-3}"

DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"
RESTORE_PLAYBOOK="$ROOT/ansible/phase03-wpad-restore-baseline.yml"
VERIFY_SCRIPT="$ROOT/scripts/phase03/verify-wpad-reset.sh"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-wpad-baseline.json}"

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

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

cd "$ROOT"

[[ -f "$BASELINE" ]] || fail "captured WPAD baseline is missing: $BASELINE"
[[ -f "$RESTORE_PLAYBOOK" ]] || fail "WPAD restore playbook is missing: $RESTORE_PLAYBOOK"

if pgrep -af '(^|[ /])mitm6([ ]|$)' >/dev/null; then
  fail 'mitm6 is still active; stop the WPAD attack runtime before restoring WS01'
fi

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || fail 'ansible-playbook not found'

echo '===== PHASE 03 WPAD BASELINE RESTORE ====='
echo "Attempts:        $ATTEMPTS"
echo "Restore timeout: ${RESTORE_TIMEOUT_SECONDS}s"
echo "Verify timeout:  ${VERIFY_TIMEOUT_SECONDS}s"

echo
echo '===== CURRENT BASELINE STATE ====='
if timeout --kill-after=5 "$VERIFY_TIMEOUT_SECONDS" bash "$VERIFY_SCRIPT"; then
  echo '[PASS] WS01 already matches the captured WPAD baseline'
  echo 'PHASE03_WPAD_RESTORE_COMPLETE=True'
  exit 0
fi

for ((attempt=1; attempt<=ATTEMPTS; attempt++)); do
  echo
  echo "===== EXACT RESTORE ATTEMPT $attempt/$ATTEMPTS ====="
  echo '[*] restoring only NORTH-facing IPv6/DNS differences from captured baseline'

  set +e
  ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  timeout --kill-after=5 "$RESTORE_TIMEOUT_SECONDS" \
    "$ANSIBLE_PLAYBOOK" \
      -i "$DATA_INVENTORY" \
      -i "$PROVIDER_INVENTORY" \
      "$RESTORE_PLAYBOOK"
  restore_rc=$?
  set -e

  case "$restore_rc" in
    0)
      echo '[+] exact baseline mutation returned normally'
      ;;
    124|137)
      echo "[WARN] exact baseline mutation exceeded its bounded wait (rc=$restore_rc); verifying guest state directly"
      ;;
    *)
      echo "[WARN] exact baseline mutation returned rc=$restore_rc; exact verification remains authoritative"
      ;;
  esac

  sleep "$SETTLE_SECONDS"

  echo '[*] verifying exact captured IPv6/DNS baseline'
  if timeout --kill-after=5 "$VERIFY_TIMEOUT_SECONDS" bash "$VERIFY_SCRIPT"; then
    echo "[PASS] exact WPAD baseline restored on attempt $attempt"
    echo 'PHASE03_WPAD_RESTORE_COMPLETE=True'
    exit 0
  fi

  if (( attempt < ATTEMPTS )); then
    echo '[INFO] exact baseline has not converged yet; retrying the scoped restore once'
  fi
done

fail "WS01 did not return to the captured WPAD baseline after $ATTEMPTS exact restore attempts"
