#!/usr/bin/env bash
# Release WPAD ownership of the shared permanent Rickon victim fixture.
# Attacks 13/14 may ensure this service is healthy, but must never tear it down:
# later Phase 03 exercises reuse the same Rickon -> WS01 session.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
SERVICE='kingdoms-phase03-rickon.service'
MARKER="${WPAD_RICKON_MARKER:-/tmp/kingdoms-wpad-rickon-started}"

cd "$ROOT"

if [[ -f "$MARKER" ]]; then
  owner="$(cat "$MARKER" 2>/dev/null || true)"
  if [[ "$owner" != 'started-by-wpad' && "$owner" != 'ensured-by-wpad' ]]; then
    echo "FAIL: unexpected WPAD Rickon ownership marker: $MARKER" >&2
    exit 1
  fi
  rm -f -- "$MARKER"
fi

# Rickon is a shared permanent Phase 03 fixture. Ensure the user service
# remains supervised after WPAD cleanup instead of stopping it.
if ! systemctl --user is-active --quiet "$SERVICE"; then
  systemctl --user start "$SERVICE"
fi

echo 'PASS: WPAD released Rickon ownership without stopping the shared victim fixture'
echo 'PHASE03_WPAD_RICKON_PRESERVED=True'
