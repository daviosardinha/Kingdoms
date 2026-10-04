#!/usr/bin/env bash
# Finalize the Phase 03 mitm6/WPAD exercise.
# Validate the captured chain, then always restore WS01 network state.
# Evidence files are intentionally preserved by the rollback path.
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
VALIDATOR="$ROOT/scripts/phase03/validate-wpad-chain.sh"
ROLLBACK="$ROOT/scripts/phase03/rollback-wpad-runtime.sh"
VICTIM_CLEANUP="$ROOT/scripts/phase03/diagnostics/cleanup-wpad-rickon-session.sh"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
ACTIVE="${WPAD_ACTIVE_MARKER:-$STATE_HOME/kingdoms/phase03-wpad-active}"
LOCK="${WPAD_LOCK_FILE:-/tmp/kingdoms-phase03-wpad.lock}"
WATCHDOG_UNIT='kingdoms-phase03-wpad-watchdog'

cd "$ROOT" || exit 1

exec 9>"$LOCK"
echo 'Waiting for WPAD lifecycle lock...'
flock 9
echo 'WPAD lifecycle lock acquired'

[[ -x "$VALIDATOR" || -f "$VALIDATOR" ]] || {
  echo "FAIL: WPAD validator missing: $VALIDATOR" >&2
  exit 1
}

[[ -x "$ROLLBACK" || -f "$ROLLBACK" ]] || {
  echo "FAIL: WPAD rollback missing: $ROLLBACK" >&2
  exit 1
}

cleanup_attempted=0
cleanup_rc=0
victim_cleanup_rc=0

cleanup() {
  local original_rc=$?
  trap - EXIT INT TERM

  if (( cleanup_attempted == 0 )); then
    cleanup_attempted=1
    echo
    echo '===== AUTOMATIC WPAD NETWORK ROLLBACK ====='
    bash "$ROLLBACK"
    cleanup_rc=$?

    echo
    echo '===== AUTOMATIC WPAD VICTIM-SESSION CLEANUP ====='
    bash "$VICTIM_CLEANUP"
    victim_cleanup_rc=$?
  fi

  if (( cleanup_rc != 0 )); then
    echo 'FAIL: automatic WPAD rollback did not return WS01 to the captured baseline' >&2
    exit "$cleanup_rc"
  fi

  if (( victim_cleanup_rc != 0 )); then
    echo 'FAIL: automatic WPAD victim-session cleanup failed' >&2
    exit "$victim_cleanup_rc"
  fi

  # Removing the generation marker while holding the lifecycle lock makes any
  # already-queued watchdog harmless. Use non-blocking systemd cancellation so
  # completion can never deadlock waiting for a watchdog that is waiting here.
  rm -f -- "$ACTIVE"
  sudo systemctl stop --no-block "$WATCHDOG_UNIT.timer" "$WATCHDOG_UNIT.service" >/dev/null 2>&1 || true
  sudo systemctl reset-failed "$WATCHDOG_UNIT.timer" "$WATCHDOG_UNIT.service" >/dev/null 2>&1 || true
  echo 'PHASE03_WPAD_WATCHDOG_TIMER_CANCELLED=True'
  echo 'PHASE03_WPAD_WATCHDOG_DISARMED=True'

  if (( original_rc != 0 )); then
    echo 'FAIL: WPAD proof failed, but automatic rollback completed successfully' >&2
    exit "$original_rc"
  fi

  echo
  echo 'PHASE03_WPAD_EXERCISE_COMPLETE=True'
  exit 0
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo '===== VALIDATE MITM6 / WPAD EVIDENCE ====='
bash "$VALIDATOR"
