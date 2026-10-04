#!/usr/bin/env bash
# Restore the exact pre-WPAD WS01 IPv6/DNS baseline.
#
# The DHCPv6 renewal playbook can outlive the guest-side ipconfig /renew6
# operation. Therefore the renewal command's exit status is diagnostic only:
# exact baseline verification is the success criterion.
set -Eeuo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
ATTEMPTS="${WPAD_RESTORE_ATTEMPTS:-3}"
RENEW_TIMEOUT_SECONDS="${WPAD_RENEW_TIMEOUT_SECONDS:-45}"
VERIFY_TIMEOUT_SECONDS="${WPAD_VERIFY_TIMEOUT_SECONDS:-45}"
SETTLE_SECONDS="${WPAD_RESTORE_SETTLE_SECONDS:-5}"

DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"
RENEW_PLAYBOOK="$ROOT/ansible/phase03-trigger-ws01-renew6.yml"
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

if pgrep -af '(^|[ /])mitm6([ ]|$)' >/dev/null; then
  fail 'mitm6 is still active; stop the WPAD attack runtime before restoring WS01'
fi

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || fail 'ansible-playbook not found'

echo '===== PHASE 03 WPAD BASELINE RESTORE ====='
echo "Attempts:       $ATTEMPTS"
echo "Renew timeout:  ${RENEW_TIMEOUT_SECONDS}s"
echo "Verify timeout: ${VERIFY_TIMEOUT_SECONDS}s"

echo
echo '===== CURRENT BASELINE STATE ====='
if timeout --kill-after=5 "$VERIFY_TIMEOUT_SECONDS" bash "$VERIFY_SCRIPT"; then
  echo '[PASS] WS01 already matches the captured WPAD baseline'
  echo 'PHASE03_WPAD_RESTORE_COMPLETE=True'
  exit 0
fi

for ((attempt=1; attempt<=ATTEMPTS; attempt++)); do
  echo
  echo "===== RESTORE ATTEMPT $attempt/$ATTEMPTS ====="
  echo '[*] requesting scoped WS01 DHCPv6 renewal'

  set +e
  ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  timeout --kill-after=5 "$RENEW_TIMEOUT_SECONDS" \
    "$ANSIBLE_PLAYBOOK" \
      -i "$DATA_INVENTORY" \
      -i "$PROVIDER_INVENTORY" \
      "$RENEW_PLAYBOOK"
  renew_rc=$?
  set -e

  case "$renew_rc" in
    0)
      echo '[+] renewal playbook returned normally'
      ;;
    124|137)
      echo "[INFO] renewal control path exceeded its bounded wait (rc=$renew_rc); verifying guest state directly"
      ;;
    *)
      echo "[WARN] renewal playbook returned rc=$renew_rc; exact baseline verification remains authoritative"
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
    echo '[INFO] WS01 has not converged yet; another bounded renewal will be attempted'
  fi
done

fail "WS01 did not return to the captured WPAD baseline after $ATTEMPTS bounded restore attempts"
