#!/usr/bin/env bash
# Read-only preflight for the permanent WS01 HTTP -> LDAPS relay proof.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
TARGET="${TARGET:-10.4.10.11}"
TARGET_FQDN="${TARGET_FQDN:-winterfell.north.sevenkingdoms.local}"

find_ntlmrelayx() {
  local c
  for c in     "$(command -v impacket-ntlmrelayx 2>/dev/null || true)"     "$(command -v ntlmrelayx.py 2>/dev/null || true)"     /usr/share/doc/python3-impacket/examples/ntlmrelayx.py; do
    [[ -n "$c" && ( -f "$c" || -x "$c" ) ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

cd "$ROOT"

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

echo '===== HTTP -> LDAPS READ-ONLY RELAY PREFLIGHT ====='

bash scripts/verify-test-source.sh || {
  echo "FAIL: source checkout does not match its configured upstream" >&2
  exit 1
}

if pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|mitm6|Responder[.]py|responder)([ ]|$)' >/dev/null; then
  echo 'FAIL: conflicting Phase 03 runtime is active' >&2
  pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|mitm6|Responder[.]py|responder)([ ]|$)' || true
  exit 1
fi
echo 'PASS: neutral Phase 03 runtime'

route="$(ip route get "$TARGET" 2>/dev/null | head -n1 || true)"
printf '%s\n' "$route"
grep -Eq 'dev vmnet10([[:space:]]|$)' <<<"$route" || { echo "FAIL: $TARGET_FQDN does not route through vmnet10" >&2; exit 1; }

timeout 4 nc -z -w3 "$TARGET" 636 >/dev/null 2>&1 || { echo "FAIL: $TARGET_FQDN TCP/636 unreachable" >&2; exit 1; }
echo "PASS: $TARGET_FQDN TCP/636 reachable"

for port in 80 445; do
  if sudo ss -H -lnt 2>/dev/null | grep -Eq ":$port[[:space:]]"; then
    echo "FAIL: local TCP/$port is already in use" >&2
    sudo ss -H -lntp 2>/dev/null | grep -E ":$port[[:space:]]" || true
    exit 1
  fi
  echo "PASS: local TCP/$port is free"
done

command -v setsid >/dev/null 2>&1 || { echo 'FAIL: setsid not found' >&2; exit 1; }
echo "SETSID=$(command -v setsid)"

NTLMRELAYX="$(find_ntlmrelayx || true)"
[[ -n "$NTLMRELAYX" ]] || { echo 'FAIL: ntlmrelayx not found' >&2; exit 1; }

help="$("$NTLMRELAYX" -h 2>&1 || true)"
for opt in   '-t'   '--no-dump'   '--no-da'   '--no-acl'   '--no-smb-server'   '--no-wcf-server'   '--no-raw-server'; do
  grep -Fq -- "$opt" <<<"$help" || { echo "FAIL: ntlmrelayx missing expected option: $opt" >&2; exit 1; }
done

echo "NTLMRELAYX=$NTLMRELAYX"
echo 'PHASE03_HTTP_LDAPS_PREFLIGHT_COMPLETE=True'