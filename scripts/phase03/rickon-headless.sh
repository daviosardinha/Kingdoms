#!/usr/bin/env bash
# Persistent Phase 03 NORTH victim session: Rickon Stark -> WS01.
# The user-level systemd unit supervises restarts. Credentials and the
# independently verified WS01 RDP certificate fingerprint stay outside Git.
set -Eeuo pipefail
umask 077

readonly TARGET_FQDN='ws01.north.sevenkingdoms.local'
readonly TARGET_IP='10.4.10.31'
readonly EXPECTED_INTERFACE='vmnet10'
readonly EXPECTED_SOURCE='10.4.10.254'
readonly CREDENTIAL_FILE="${KINGDOMS_RICKON_RDP_SECRET_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kingdoms/rickon-rdp.password}"
readonly CERT_FILE="${KINGDOMS_WS01_RDP_CERT_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kingdoms/ws01-rdp.sha256}"

fail() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -ne 0 ]] ||
  fail 'Run the Rickon victim session as the unprivileged Kali operator, never sudo.'

for cmd in ip stat ss getent awk xvfb-run xfreerdp3; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing prerequisite: $cmd"
done

resolved_ip="$(getent ahostsv4 "$TARGET_FQDN" 2>/dev/null | awk 'NR==1{print $1}')"
[[ "$resolved_ip" == "$TARGET_IP" ]] ||
  fail "WS01 name resolution changed: expected $TARGET_FQDN -> $TARGET_IP, got ${resolved_ip:-none}."

route="$(ip -4 route get "$TARGET_IP" 2>/dev/null)" ||
  fail 'Cannot find the NORTH route to WS01.'
[[ " $route " == *" dev $EXPECTED_INTERFACE "* &&
   " $route " == *" src $EXPECTED_SOURCE "* ]] ||
  fail 'NORTH route changed: expected WS01 via vmnet10 from 10.4.10.254.'

if ss -H -nt state established | grep -Eq "[[:space:]]$TARGET_IP:3389([[:space:]]|$)"; then
  fail 'A WS01 RDP connection already exists from this operator host; refusing a duplicate victim session.'
fi

validate_owner_only_file() {
  local path="$1"
  local label="$2"
  [[ -f "$path" && ! -L "$path" && -r "$path" ]] ||
    fail "$label must be a readable, non-symlink regular file: $path"
  [[ "$(stat -c '%u' -- "$path")" == "$(id -u)" ]] ||
    fail "$label must be owned by the operator account."
  local mode
  mode="$(stat -c '%a' -- "$path")" || fail "Cannot stat $label."
  (( (8#$mode & 8#077) == 0 )) ||
    fail "$label grants group/other access (use chmod 600)."
  [[ -s "$path" ]] || fail "$label is empty."
}

validate_owner_only_file "$CREDENTIAL_FILE" 'Credential file'
validate_owner_only_file "$CERT_FILE" 'Certificate fingerprint file'

RDP_CERT_SHA256="$(tr -d '[:space:]:-' < "$CERT_FILE" | tr '[:upper:]' '[:lower:]')"
[[ "$RDP_CERT_SHA256" =~ ^[0-9a-f]{64}$ ]] ||
  fail 'WS01 certificate fingerprint must contain exactly 64 SHA-256 hex characters.'

printf '[INFO] Starting NORTH\\rickon.stark headless session to WS01 with pinned SHA-256 certificate.\n'

{
  printf '%s\n' "/v:$TARGET_FQDN" '/d:NORTH' '/u:rickon.stark'
  printf '/p:'; cat -- "$CREDENTIAL_FILE"
  printf '\n'
  printf '%s\n'     "/cert:fingerprint:sha256:$RDP_CERT_SHA256"     '/size:1280x800'     '/audio-mode:2'     '-clipboard'     '/log-level:ERROR'
} | exec xvfb-run -a -s '-screen 0 1280x800x24 -nolisten tcp'       xfreerdp3 /args-from:stdin
