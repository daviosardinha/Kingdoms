#!/usr/bin/env bash
# Sanitized diagnosis for the Phase 03 Rickon -> WS01 headless RDP session.
# Does not print the credential file contents or place the password in argv.
set -uo pipefail
umask 077

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
SERVICE='kingdoms-phase03-rickon.service'
TARGET_IP='10.4.10.31'
CREDENTIAL_FILE="${KINGDOMS_RICKON_RDP_SECRET_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kingdoms/rickon-rdp.password}"
CERT_FILE="${KINGDOMS_WS01_RDP_CERT_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kingdoms/ws01-rdp.sha256}"

cd "$ROOT" || exit 1

echo '===== RICKON USER SERVICE ====='
systemctl --user show "$SERVICE"   -p ActiveState -p SubState -p MainPID -p NRestarts -p ExecMainStatus -p Result   --no-pager 2>/dev/null || true

echo
echo '===== RICKON PROCESS TREE ====='
pgrep -af 'rickon-headless|xvfb-run|Xvfb|xfreerdp3' || true

echo
echo '===== WS01 RDP SOCKETS ====='
ss -H -ntp 2>/dev/null | grep "${TARGET_IP}:3389" || true

echo
echo '===== RECENT SERVICE JOURNAL ====='
# The service receives the password only through stdin, so it is not present in
# the committed unit or process argv. Still redact any accidental /p: token.
journalctl --user -u "$SERVICE" -n 120 --no-pager -o cat 2>/dev/null |
  sed -E 's#(/p:)[^[:space:]]+#\1[REDACTED]#g' || true

echo
echo '===== LOCAL SECRET / CERTIFICATE CONTRACT ====='
for item in "$CREDENTIAL_FILE" "$CERT_FILE"; do
  if [[ -f "$item" && ! -L "$item" && -r "$item" ]]; then
    printf 'FILE=%s OWNER=%s MODE=%s SIZE=%s\n'       "$item" "$(stat -c '%U' "$item")" "$(stat -c '%a' "$item")" "$(stat -c '%s' "$item")"
  else
    echo "FAIL: required file unavailable: $item"
  fi
done

command -v xfreerdp3 >/dev/null 2>&1 || {
  echo 'FAIL: xfreerdp3 not found'
  exit 1
}

help="$(xfreerdp3 /help 2>&1 || true)"
if ! grep -Fq '/auth-only' <<<"$help"; then
  echo
  echo 'INFO: this FreeRDP build does not expose /auth-only; skipping credential-only probe'
  exit 0
fi

[[ -f "$CREDENTIAL_FILE" && -r "$CREDENTIAL_FILE" && -s "$CREDENTIAL_FILE" ]] || {
  echo 'FAIL: credential file not usable for auth-only probe'
  exit 1
}
[[ -f "$CERT_FILE" && -r "$CERT_FILE" && -s "$CERT_FILE" ]] || {
  echo 'FAIL: certificate fingerprint file not usable for auth-only probe'
  exit 1
}

RDP_CERT_SHA256="$(tr -d '[:space:]:-' < "$CERT_FILE" | tr '[:upper:]' '[:lower:]')"
[[ "$RDP_CERT_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
  echo 'FAIL: stored WS01 certificate fingerprint is malformed'
  exit 1
}

if ss -H -nt state established 2>/dev/null | grep -Eq "[[:space:]]$TARGET_IP:3389([[:space:]]|$)"; then
  echo
  echo 'INFO: an established WS01 RDP session already exists; skipping auth-only probe'
  exit 0
fi

if systemctl --user is-active --quiet "$SERVICE" && [[ "${RICKON_DIAG_ALLOW_ACTIVE_AUTH:-0}" != "1" ]]; then
  echo
  echo 'INFO: Rickon service is still active; skipping parallel auth-only probe'
  exit 0
fi

echo
echo '===== FREERDP AUTH-ONLY PROBE ====='
set +e
probe="$({
  printf '%s\n' "/v:$TARGET_IP" '/d:NORTH' '/u:rickon.stark'
  printf '/p:'; cat -- "$CREDENTIAL_FILE"; printf '\n'
  printf '%s\n'     "/cert:fingerprint:sha256:$RDP_CERT_SHA256"     '/auth-only'     '/log-level:WARN'
} | timeout 20s xfreerdp3 /args-from:stdin 2>&1)"
rc=$?
set -e

printf '%s\n' "$probe" | sed -E 's#(/p:)[^[:space:]]+#\1[REDACTED]#g'
echo "PHASE03_RICKON_AUTH_ONLY_RC=$rc"

if (( rc == 0 )); then
  echo 'PHASE03_RICKON_AUTH_ONLY=PASS'
else
  echo 'PHASE03_RICKON_AUTH_ONLY=FAIL'
fi
