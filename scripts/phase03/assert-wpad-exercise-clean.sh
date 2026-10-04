#!/usr/bin/env bash
# Refuse later Phase 03 exercises while the mitm6/WPAD exercise owns temporary state.
set -euo pipefail

STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
ACTIVE="${WPAD_ACTIVE_MARKER:-$STATE_HOME/kingdoms/phase03-wpad-active}"
IFACE="${IFACE:-vmnet10}"
PACDIR="${PACDIR:-/tmp/kingdoms-wpad}"
PCAP="${PCAP:-/tmp/kingdoms-wpad.pcap}"

fail=0

if [[ -e "$ACTIVE" ]]; then
  echo "FAIL: Phase 03 WPAD exercise is still armed: $ACTIVE" >&2
  fail=1
fi

if pgrep -af "(^|[ /])mitm6[ ]+-i[ ]+${IFACE}([ ]|$)" >/dev/null; then
  echo 'FAIL: scoped mitm6 runtime is still active' >&2
  fail=1
fi

if pgrep -af "python3[ ]+-m[ ]+http[.]server[ ]+80[ ].*--directory[ ]+${PACDIR}([ ]|$)" >/dev/null; then
  echo 'FAIL: WPAD HTTP observer is still active' >&2
  fail=1
fi

if pgrep -af "tcpdump[ ].*-i[ ]+${IFACE}[ ].*-w[ ]+${PCAP//./[.]}" >/dev/null; then
  echo 'FAIL: WPAD packet capture is still active' >&2
  fail=1
fi

if (( fail != 0 )); then
  echo 'Run scripts/phase03/complete-wpad-exercise.sh or wait for the safety rollback before starting the next exercise.' >&2
  exit 1
fi

echo 'PASS: no active WPAD exercise state'
