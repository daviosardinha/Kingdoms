#!/usr/bin/env bash
# Live acceptance test for the Phase 03 unattended WPAD safety rollback.
# Uses a short validation-only timer; the production launcher still defaults to 15m.
set -Eeuo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
ACTIVE="${WPAD_ACTIVE_MARKER:-$STATE_HOME/kingdoms/phase03-wpad-active}"
WATCHDOG_UNIT='kingdoms-phase03-wpad-watchdog'
WATCHDOG_DELAY="${WPAD_WATCHDOG_VALIDATION_DELAY:-120s}"
WAIT_SECONDS="${WPAD_WATCHDOG_VALIDATION_WAIT_SECONDS:-210}"
DRIFT_ATTEMPTS="${WPAD_WATCHDOG_DRIFT_ATTEMPTS:-4}"
DRIFT_POLL_SECONDS="${WPAD_WATCHDOG_DRIFT_POLL_SECONDS:-5}"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"
TRIGGER_PLAYBOOK="$ROOT/ansible/phase03-trigger-ws01-renew6.yml"
DRIFT_PLAYBOOK="$ROOT/ansible/phase03-wpad-drift-check.yml"
LOG_DIR="${WPAD_WATCHDOG_VALIDATION_LOG_DIR:-/tmp/kingdoms-wpad-watchdog-validation-$(date +%Y%m%d-%H%M%S)}"
RICKON_SERVICE='kingdoms-phase03-rickon.service'

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
  return 1
}

cleanup_on_exit() {
  local rc=$?
  trap - EXIT INT TERM

  if (( rc != 0 )) && [[ -f "$ACTIVE" ]]; then
    echo
    echo '[RECOVERY] validation aborted while WPAD was armed; invoking managed completion cleanup' >&2
    bash "$ROOT/scripts/phase03/complete-wpad-exercise.sh" >/dev/null 2>&1 || true
  fi

  exit "$rc"
}

trap cleanup_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$ROOT"
mkdir -p "$LOG_DIR"

echo '============================================================'
echo 'PHASE 03 WPAD WATCHDOG LIVE ACCEPTANCE'
echo '============================================================'
echo "Validation timer: $WATCHDOG_DELAY"
echo "Logs:             $LOG_DIR"

[[ ! -e "$ACTIVE" ]] || fail "WPAD exercise is already armed: $ACTIVE"
bash scripts/phase03/assert-wpad-exercise-clean.sh

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || fail 'ansible-playbook not found'

START_EPOCH="$(date +%s)"

echo
echo '===== ARM REAL EXERCISE WITH VALIDATION-ONLY WATCHDOG DELAY ====='
WPAD_WATCHDOG_DELAY="$WATCHDOG_DELAY" \
  bash scripts/phase03/start-wpad-exercise.sh |
  tee "$LOG_DIR/start.log"

[[ -f "$ACTIVE" ]] || fail 'launcher returned without an active WPAD generation marker'
sudo systemctl is-active --quiet "$WATCHDOG_UNIT.timer" ||
  fail 'real systemd watchdog timer is not active after launcher success'

grep -Fq "watchdog_delay=$WATCHDOG_DELAY" "$ACTIVE" ||
  fail 'active generation does not record the validation watchdog delay'

echo
echo '===== INDUCE REAL WS01 DHCPV6 DRIFT ====='
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
"$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$TRIGGER_PLAYBOOK" |
  tee "$LOG_DIR/renew6.log"

echo
echo '===== PROVE WS01 ACTUALLY DIFFERS FROM CAPTURED BASELINE ====='
drift_seen=0
for ((attempt=1; attempt<=DRIFT_ATTEMPTS; attempt++)); do
  drift_log="$LOG_DIR/drift-$attempt.log"

  ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  "$ANSIBLE_PLAYBOOK" \
    -i "$DATA_INVENTORY" \
    -i "$PROVIDER_INVENTORY" \
    "$DRIFT_PLAYBOOK" 2>&1 |
    tee "$drift_log"

  if grep -Fq 'PHASE03_WPAD_DRIFT=True' "$drift_log"; then
    drift_seen=1
    echo "PASS: real WS01 IPv6/DNS drift observed on attempt $attempt"
    break
  fi

  if (( attempt < DRIFT_ATTEMPTS )); then
    echo "INFO: drift not visible yet; retriggering DHCPv6 before attempt $((attempt + 1))"
    ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
    "$ANSIBLE_PLAYBOOK" \
      -i "$DATA_INVENTORY" \
      -i "$PROVIDER_INVENTORY" \
      "$TRIGGER_PLAYBOOK" >/dev/null
    sleep "$DRIFT_POLL_SECONDS"
  fi
done

(( drift_seen == 1 )) ||
  fail 'real WS01 WPAD drift was not observed before watchdog acceptance window'

echo
echo '===== WAIT FOR UNATTENDED SYSTEMD WATCHDOG ====='
elapsed=0
while [[ -f "$ACTIVE" && "$elapsed" -lt "$WAIT_SECONDS" ]]; do
  if (( elapsed == 0 || elapsed % 20 == 0 )); then
    echo "INFO: watchdog generation still armed; elapsed=${elapsed}s"
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done

[[ ! -f "$ACTIVE" ]] ||
  fail "watchdog did not disarm its generation within ${WAIT_SECONDS}s"

# Give the oneshot a moment to finish after it removes the generation marker.
for _ in {1..10}; do
  if ! sudo systemctl is-active --quiet "$WATCHDOG_UNIT.service" &&
     ! sudo systemctl is-active --quiet "$WATCHDOG_UNIT.timer"; then
    break
  fi
  sleep 1
done

if sudo systemctl is-active --quiet "$WATCHDOG_UNIT.service" ||
   sudo systemctl is-active --quiet "$WATCHDOG_UNIT.timer"; then
  fail 'watchdog generation marker cleared but its systemd unit is still active'
fi

echo
echo '===== WATCHDOG JOURNAL EVIDENCE ====='
SINCE="$(date -d "@$START_EPOCH" '+%Y-%m-%d %H:%M:%S')"
sudo journalctl -u "$WATCHDOG_UNIT.service" --since "$SINCE" --no-pager |
  tee "$LOG_DIR/watchdog-journal.log"

grep -Fq 'PHASE03_WPAD_WATCHDOG_ROLLBACK_COMPLETE=True' "$LOG_DIR/watchdog-journal.log" ||
  fail 'watchdog journal does not contain the successful rollback marker'

echo
echo '===== PROVE POST-WATCHDOG NEUTRAL STATE ====='
bash scripts/phase03/assert-wpad-exercise-clean.sh |
  tee "$LOG_DIR/clean.log"

bash scripts/phase03/verify-wpad-reset.sh |
  tee "$LOG_DIR/reset.log"

systemctl --user is-active --quiet "$RICKON_SERVICE" ||
  fail "shared Rickon fixture is not active after watchdog cleanup"

[[ -f /tmp/kingdoms-wpad.pcap ]] ||
  fail 'operator WPAD packet-capture evidence was unexpectedly removed'

echo
echo 'PHASE03_WPAD_WATCHDOG_LIVE_ACCEPTANCE=True'
echo "PHASE03_WPAD_WATCHDOG_VALIDATION_LOGS=$LOG_DIR"

trap - EXIT INT TERM
exit 0
