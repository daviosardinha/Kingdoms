#!/usr/bin/env bash
# Atomically arm the Phase 03 mitm6/WPAD exercise and its 15-minute safety rollback.
set -Eeuo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
STATE_DIR="$STATE_HOME/kingdoms"
ACTIVE="${WPAD_ACTIVE_MARKER:-$STATE_DIR/phase03-wpad-active}"
LOCK="${WPAD_LOCK_FILE:-/tmp/kingdoms-phase03-wpad.lock}"
WATCHDOG_UNIT='kingdoms-phase03-wpad-watchdog'
WATCHDOG_DELAY="${WPAD_WATCHDOG_DELAY:-15m}"
TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"

cd "$ROOT"
install -d -m 700 "$STATE_DIR"

exec 9>"$LOCK"
flock 9

bash scripts/phase03/assert-wpad-exercise-clean.sh

cleanup_on_error() {
  local rc=$?
  trap - ERR INT TERM
  echo
  echo '===== WPAD STARTUP FAILED: CLEANING PARTIAL STATE =====' >&2
  bash scripts/phase03/diagnostics/stop-wpad-runtime.sh || true
  WPAD_SKIP_LOCAL_STOP=1 bash scripts/phase03/rollback-wpad-runtime.sh || true
  bash scripts/phase03/diagnostics/cleanup-wpad-rickon-session.sh || true
  sudo systemctl stop "$WATCHDOG_UNIT.timer" "$WATCHDOG_UNIT.service" >/dev/null 2>&1 || true
  sudo systemctl reset-failed "$WATCHDOG_UNIT.timer" "$WATCHDOG_UNIT.service" >/dev/null 2>&1 || true
  rm -f -- "$ACTIVE"
  exit "$rc"
}
trap cleanup_on_error ERR INT TERM

echo '===== WPAD BASELINE / PREREQUISITES ====='
bash scripts/phase03/check-wpad-permanent-prereqs.sh

echo
echo '===== WPAD PAC / VICTIM SESSION ====='
bash scripts/phase03/diagnostics/wpad-preflight.sh

echo
echo '===== START SCOPED MITM6 ====='
bash scripts/phase03/diagnostics/start-mitm6-ws01.sh 9>&-

echo
echo '===== START WPAD OBSERVERS ====='
bash scripts/phase03/diagnostics/start-wpad-observers.sh 9>&-

cat >"$ACTIVE" <<EOF
status=armed
token=$TOKEN
started_at_epoch=$(date +%s)
watchdog_delay=$WATCHDOG_DELAY
interface=vmnet10
target=WS01
EOF
chmod 600 "$ACTIVE"

echo
echo '===== ARM 15-MINUTE SAFETY ROLLBACK ====='
sudo systemctl stop "$WATCHDOG_UNIT.timer" "$WATCHDOG_UNIT.service" >/dev/null 2>&1 || true
sudo systemctl reset-failed "$WATCHDOG_UNIT.timer" "$WATCHDOG_UNIT.service" >/dev/null 2>&1 || true

sudo systemd-run   --unit="$WATCHDOG_UNIT"   --on-active="$WATCHDOG_DELAY"   --timer-property=AccuracySec=1s   --collect   --property=Type=oneshot   /usr/bin/bash "$ROOT/scripts/phase03/watchdog-wpad-exercise-root.sh"   "$(id -un)" "$HOME" "$ROOT" "$ACTIVE" "$LOCK"

sudo systemctl is-active --quiet "$WATCHDOG_UNIT.timer" || {
  echo 'FAIL: WPAD safety watchdog timer did not arm' >&2
  exit 1
}

trap - ERR INT TERM

# The lifecycle lock is startup-only from this point. Long-lived runtime
# children were launched with fd 9 closed, so releasing it here cannot be
# kept alive accidentally by mitm6, HTTP, or tcpdump.
flock -u 9
exec 9>&-

echo
echo 'PHASE03_WPAD_EXERCISE_ARMED=True'
echo "PHASE03_WPAD_WATCHDOG_DELAY=$WATCHDOG_DELAY"
echo 'NEXT: run scripts/phase03/diagnostics/trigger-ws01-renew6.sh'
echo 'FINISH: run scripts/phase03/complete-wpad-exercise.sh'
