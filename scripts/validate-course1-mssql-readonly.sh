#!/usr/bin/env bash
# Kingdoms Course 1 - read-only CASTELBLACK -> BRAAVOS MSSQL evidence.
# Runs from the operator's Kali (or a host with NORTH SQL reachability).
# No VM lifecycle, routing, service, identity, or SQL configuration is changed.
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_FILE="$ROOT/scripts/mssql/course1-linked-readonly.sql"
HOST="castelblack.north.sevenkingdoms.local"
IP="10.4.10.22"
EVIDENCE_DIR="${EVIDENCE_DIR:-$HOME/Kingdoms-evidence/course1-mssql-readonly}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$EVIDENCE_DIR/castelblack-braavos-$STAMP.log"

fail() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }
pass() { printf '[PASS] %s\n' "$*"; }
info() { printf '[INFO] %s\n' "$*"; }

[[ -f "$SQL_FILE" ]] || fail "Missing SQL probe: $SQL_FILE"
command -v timeout >/dev/null 2>&1 || fail 'GNU timeout is required'
command -v tee >/dev/null 2>&1 || fail 'tee is required'
command -v grep >/dev/null 2>&1 || fail 'grep is required'
VERIFY_LOG=''
if (($# > 0)); then
  [[ $# -eq 2 && "$1" == '--verify-log' ]] || fail 'Usage: script [--verify-log EXISTING_LOG]'
  VERIFY_LOG="$2"
  [[ -f "$VERIFY_LOG" && -r "$VERIFY_LOG" ]] || fail "Evidence log not readable: $VERIFY_LOG"
fi
if [[ -z "$VERIFY_LOG" ]]; then
  CLIENT="$(command -v impacket-mssqlclient 2>/dev/null || true)"
  if [[ -z "$CLIENT" ]]; then
    CLIENT="$(command -v mssqlclient.py 2>/dev/null || true)"
  fi
  [[ -n "$CLIENT" ]] || fail 'Impacket MSSQL client not found in PATH'
  mkdir -p -- "$EVIDENCE_DIR"
  chmod 700 -- "$EVIDENCE_DIR"
fi

printf '\n===== KINGDOMS COURSE 1: MSSQL LINKED SERVER READ-ONLY AUDIT =====\n'
info "Source instance: $HOST ($IP):1433"
info 'Remote target: BRAAVOS, reached ONLY through CASTELBLACK SQL linked server'
if [[ -n "$VERIFY_LOG" ]]; then
  LOG="$VERIFY_LOG"
  info 'Mode: verify existing evidence only (no connection or password prompt)'
else
  info 'Authentication: NORTH\\jon.snow (password entered interactively)'
fi
info 'The remote instance is NOT accessed directly from Kali'
info "Private evidence file: $LOG"
info 'No configuration, privilege, route, firewall, or VM changes'
printf '\n'

# Impacket reads the password from the terminal. Never pass it via CLI, shell
# environment, or repository files. The -file option executes ONLY the fixed
# read-only statements in course1-linked-readonly.sql.
if [[ -n "$VERIFY_LOG" ]]; then
  client_rc=0
else
  set +e
  timeout --foreground -k 5 180 \
    "$CLIENT" -windows-auth -target-ip "$IP" -port 1433 \
    -file "$SQL_FILE" "NORTH/jon.snow@$HOST" \
    2>&1 | tee "$LOG"
  client_rc=${PIPESTATUS[0]}
  set -e
fi

printf '\n===== RESULT =====\n'
if ((client_rc != 0)); then
  fail "MSSQL client exited with code $client_rc (or timed out). See $LOG"
fi

# Check evidence from result ROWS only. Never match the SQL> echoed command;
# otherwise a failed OPENQUERY could be falsely reported as a successful test.
if grep -aqE "^[[:space:]]*(b'KINGDOMS_LOCAL_PROOF_OK'|KINGDOMS_LOCAL_PROOF_OK)[[:space:]]" "$LOG"; then
  pass 'CASTELBLACK SQL login and local SELECT succeeded'
else
  fail "No successful CASTELBLACK result row. See $LOG"
fi

if grep -aqE "^[[:space:]]*(b'KINGDOMS_REMOTE_PROOF_OK'|KINGDOMS_REMOTE_PROOF_OK)[[:space:]]" "$LOG"; then
  pass 'CASTELBLACK -> BRAAVOS OPENQUERY returned a remote SQL result row'
  info 'Inspect the remote login and sysadmin values in the output above'
  info "Evidence verified: $LOG"
  exit 0
fi

fail "BRAAVOS linked-server query did not return a remote result row. Check SQL errors in $LOG. No guest or network changes were made."
