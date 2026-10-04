#!/usr/bin/env bash
# Ensure the Phase 03 Rickon victim session exists for deterministic WPAD discovery.
# If this helper starts the shared service, it records that WPAD ensured it.
# Cleanup releases only that marker; the permanent Rickon fixture stays active
# for later Phase 03 exercises.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
SERVICE='kingdoms-phase03-rickon.service'
MARKER="${WPAD_RICKON_MARKER:-/tmp/kingdoms-wpad-rickon-started}"
WS01='10.4.10.31'

cd "$ROOT"

# Refresh the local pin from two agreeing observations before we inspect or
# start the headless session. This is local trust-state maintenance only.
bash scripts/phase03/sync-ws01-rdp-pin.sh

wait_for_healthy_session() {
  local attempt output
  for attempt in $(seq 1 12); do
    if output="$(bash scripts/phase03/validate-rickon-session.sh 2>&1)"; then
      printf '%s\n' "$output"
      return 0
    fi
    if (( attempt < 12 )); then
      echo "INFO: Rickon RDP transport is up but Windows session is not ready yet (attempt $attempt/12)"
      sleep 5
    fi
  done
  printf '%s\n' "$output" >&2
  return 1
}

if systemctl --user is-active --quiet "$SERVICE"; then
  if [[ -f "$MARKER" && "$(cat "$MARKER" 2>/dev/null || true)" == 'ensured-by-wpad' ]]; then
    echo 'PASS: Rickon victim service is already active and remains owned by this WPAD exercise'
  else
    echo 'PASS: Rickon victim service was already active before this WPAD exercise'
  fi
  wait_for_healthy_session
  exit 0
fi

systemctl --user cat "$SERVICE" >/dev/null 2>&1 || {
  echo "FAIL: $SERVICE is not installed for the operator user" >&2
  echo 'Install the existing Kingdoms Phase 03 Rickon user service before running this exercise.' >&2
  exit 1
}

bash scripts/phase03/check-rickon-prereqs.sh

rm -f -- "$MARKER"
systemctl --user start "$SERVICE"
printf '%s\n' ensured-by-wpad > "$MARKER"
chmod 600 "$MARKER"

echo 'Waiting for the Rickon -> WS01 interactive victim session...'
if ! wait_for_healthy_session; then
  echo 'FAIL: Rickon victim session did not become healthy within 60 seconds' >&2
  echo
  echo '===== RICKON FAILURE DIAGNOSTICS BEFORE STOP =====' >&2
  bash scripts/phase03/diagnostics/diagnose-rickon-session.sh >&2 || true

  systemctl --user stop "$SERVICE" >/dev/null 2>&1 || true
  rm -f -- "$MARKER"

  echo
  echo '===== RICKON AUTHENTICATION DIAGNOSTIC AFTER STOP =====' >&2
  bash scripts/phase03/diagnostics/diagnose-rickon-session.sh >&2 || true
  exit 1
fi

echo 'PHASE03_WPAD_RICKON_ENSURED_BY_EXERCISE=True'
