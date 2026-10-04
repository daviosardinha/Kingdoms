#!/usr/bin/env bash
# Read-only prerequisite gate for the permanent Phase 03 Rickon victim client.
set -uo pipefail

TARGET_FQDN='ws01.north.sevenkingdoms.local'
TARGET_IP='10.4.10.31'
EXPECTED_INTERFACE='vmnet10'
EXPECTED_SOURCE='10.4.10.254'
CREDENTIAL_FILE="${KINGDOMS_RICKON_RDP_SECRET_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kingdoms/rickon-rdp.password}"
CERT_FILE="${KINGDOMS_WS01_RDP_CERT_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kingdoms/ws01-rdp.sha256}"

PASS=0
FAIL=0
pass(){ PASS=$((PASS+1)); printf '[PASS] %s\n' "$*"; }
fail(){ FAIL=$((FAIL+1)); printf '[FAIL] %s\n' "$*" >&2; }

for executable in xfreerdp3 xvfb-run Xvfb xauth ip stat ss getent awk; do
  if command -v "$executable" >/dev/null 2>&1; then
    pass "$executable: $(command -v "$executable")"
  else
    fail "Missing $executable"
  fi
done

resolved_ip="$(getent ahostsv4 "$TARGET_FQDN" 2>/dev/null | awk 'NR==1{print $1}')"
if [[ "$resolved_ip" == "$TARGET_IP" ]]; then
  pass "$TARGET_FQDN resolves to $TARGET_IP"
else
  fail "$TARGET_FQDN must resolve to $TARGET_IP, got ${resolved_ip:-none}"
fi

route="$(ip -4 route get "$TARGET_IP" 2>&1 || true)"
printf '[INFO] WS01 route: %s\n' "$route"
if [[ " $route " == *" dev $EXPECTED_INTERFACE "* &&
      " $route " == *" src $EXPECTED_SOURCE "* ]]; then
  pass "WS01 route uses $EXPECTED_INTERFACE from $EXPECTED_SOURCE"
else
  fail "WS01 route must use $EXPECTED_INTERFACE from $EXPECTED_SOURCE"
fi

if ss -H -nt state established | grep -Eq "[[:space:]]$TARGET_IP:3389([[:space:]]|$)"; then
  fail 'WS01 already has an RDP connection from this operator host'
else
  pass 'No duplicate WS01 RDP connection is currently present'
fi

check_file() {
  local path="$1" label="$2"
  if [[ ! -f "$path" || -L "$path" || ! -r "$path" ]]; then
    fail "$label unavailable: $path"
    return
  fi
  if [[ "$(stat -c '%u' -- "$path")" != "$(id -u)" ]]; then
    fail "$label is not owned by the operator"
    return
  fi
  local mode
  mode="$(stat -c '%a' -- "$path" 2>/dev/null || true)"
  if [[ -z "$mode" ]] || (( (8#$mode & 8#077) != 0 )); then
    fail "$label must deny group/other access"
    return
  fi
  pass "$label owner/mode contract"
}

check_file "$CREDENTIAL_FILE" 'Rickon credential file'
check_file "$CERT_FILE" 'WS01 certificate fingerprint file'

if [[ -r "$CERT_FILE" ]]; then
  cert="$(tr -d '[:space:]:-' < "$CERT_FILE" | tr '[:upper:]' '[:lower:]')"
  [[ "$cert" =~ ^[0-9a-f]{64}$ ]] &&
    pass 'WS01 fingerprint format is valid SHA-256' ||
    fail 'WS01 fingerprint format is not 64 hex characters'
fi

if command -v xfreerdp3 >/dev/null 2>&1; then
  help_text="$(xfreerdp3 /help 2>&1 || true)"
  [[ "$help_text" == *"/args-from"* ]] &&
    pass 'FreeRDP supports /args-from' ||
    fail 'FreeRDP /args-from support not confirmed'
  [[ "$help_text" == *"fingerprint"* ]] &&
    pass 'FreeRDP supports certificate fingerprint pinning' ||
    fail 'FreeRDP certificate fingerprint support not confirmed'
fi

printf '\nPASS: %d\nFAIL: %d\n' "$PASS" "$FAIL"
(( FAIL == 0 ))
