#!/usr/bin/env bash
# Read-only preflight for the Phase 03 SMB -> LDAPS relay proof.
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
TARGET="${TARGET:-10.4.10.11}"
TARGET_FQDN="${TARGET_FQDN:-winterfell.north.sevenkingdoms.local}"

PASS=0
FAIL=0
pass(){ PASS=$((PASS+1)); printf '[PASS] %s\n' "$*"; }
fail(){ FAIL=$((FAIL+1)); printf '[FAIL] %s\n' "$*" >&2; }

find_ntlmrelayx() {
  local c
  for c in     "$(command -v impacket-ntlmrelayx 2>/dev/null || true)"     "$(command -v ntlmrelayx.py 2>/dev/null || true)"     /usr/share/doc/python3-impacket/examples/ntlmrelayx.py; do
    [[ -n "$c" && -f "$c" || -x "$c" ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

cd "$ROOT" || exit 1

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

echo '===== SOURCE ====='
if bash scripts/verify-test-source.sh; then
  pass 'Git source gate passed'
else
  fail 'source checkout does not match its configured upstream'
fi

echo
echo '===== TARGET ====='
route="$(ip route get "$TARGET" 2>/dev/null | head -n1 || true)"
printf '%s\n' "$route"
grep -Eq 'dev vmnet10([[:space:]]|$)' <<<"$route" &&
  pass "$TARGET_FQDN routes through vmnet10" ||
  fail "$TARGET_FQDN does not route through vmnet10"

for port in 389 636; do
  if timeout 4 nc -z -w3 "$TARGET" "$port" >/dev/null 2>&1; then
    pass "$TARGET_FQDN TCP/$port reachable"
  else
    fail "$TARGET_FQDN TCP/$port unreachable"
  fi
done

echo
echo '===== NTLMRELAYX CAPABILITY ====='
NTLMRELAYX="$(find_ntlmrelayx || true)"
if [[ -z "$NTLMRELAYX" ]]; then
  fail 'ntlmrelayx not found'
else
  pass "ntlmrelayx: $NTLMRELAYX"
  help="$("$NTLMRELAYX" -h 2>&1 || true)"
  for opt in     '-t'     '--no-dump'     '--no-da'     '--no-acl'     '-smb2support'     '--no-http-server'     '--no-wcf-server'     '--no-raw-server'; do
    grep -Fq -- "$opt" <<<"$help" &&
      pass "ntlmrelayx supports $opt" ||
      fail "ntlmrelayx missing expected option: $opt"
  done
fi

echo
echo '===== LOCAL LISTENER OWNERSHIP ====='
listeners="$(ss -H -lnt 2>/dev/null || true)"
if grep -Eq '(^|[[:space:]])[^[:space:]]*:445[[:space:]]' <<<"$listeners"; then
  fail 'local TCP/445 is already in use'
  ss -H -lntp 2>/dev/null | grep -E '(^|[[:space:]])[^[:space:]]*:445[[:space:]]' || true
else
  pass 'local TCP/445 is free for ntlmrelayx'
fi

if pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py)([ ]|$)' >/dev/null; then
  fail 'an ntlmrelayx process is already running'
  pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py)([ ]|$)' || true
else
  pass 'no existing ntlmrelayx process'
fi

if pgrep -af '(^|[ /])responder([ ]|$)' >/dev/null; then
  fail 'Responder is running; stop it before the deterministic SQL->SMB relay trigger'
  pgrep -af '(^|[ /])responder([ ]|$)' || true
else
  pass 'Responder is not running'
fi

echo
echo '===== RESULT ====='
printf 'PASS: %d\nFAIL: %d\n' "$PASS" "$FAIL"
(( FAIL == 0 ))
