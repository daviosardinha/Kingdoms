#!/usr/bin/env bash
# Root-owned 15-minute emergency cleanup for an abandoned Phase 03 WPAD exercise.
set -uo pipefail

OWNER="${1:?operator user required}"
OWNER_HOME="${2:?operator home required}"
ROOT="${3:?repository root required}"
ACTIVE="${4:?active marker required}"
LOCK="${5:?lock file required}"
TOKEN="${6:?exercise token required}"
BASELINE="$OWNER_HOME/.config/kingdoms/phase03-wpad-baseline.json"

exec 9>"$LOCK"
flock 9

if [[ ! -f "$ACTIVE" ]]; then
  echo 'PASS: WPAD watchdog fired after normal completion; no active marker remains'
  exit 0
fi

if ! grep -Fxq "token=$TOKEN" "$ACTIVE"; then
  echo 'PASS: stale WPAD watchdog generation does not own the current exercise'
  exit 0
fi

echo '===== PHASE 03 WPAD 15-MINUTE SAFETY ROLLBACK ====='

bash "$ROOT/scripts/phase03/diagnostics/stop-wpad-runtime.sh"
local_rc=$?

runuser -u "$OWNER" -- env   HOME="$OWNER_HOME"   ROOT="$ROOT"   BASELINE="$BASELINE"   WPAD_SKIP_LOCAL_STOP=1   bash "$ROOT/scripts/phase03/rollback-wpad-runtime.sh"
network_rc=$?

uid="$(id -u "$OWNER")"
runuser -u "$OWNER" -- env   HOME="$OWNER_HOME"   XDG_RUNTIME_DIR="/run/user/$uid"   DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus"   bash "$ROOT/scripts/phase03/diagnostics/cleanup-wpad-rickon-session.sh"
victim_rc=$?

if (( local_rc == 0 && network_rc == 0 && victim_rc == 0 )); then
  rm -f -- "$ACTIVE"
  echo 'PHASE03_WPAD_WATCHDOG_ROLLBACK_COMPLETE=True'
  exit 0
fi

echo "FAIL: WPAD watchdog cleanup incomplete local=$local_rc network=$network_rc victim=$victim_rc" >&2
echo "FAIL: active marker retained: $ACTIVE" >&2
exit 1
