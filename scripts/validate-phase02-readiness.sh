#!/usr/bin/env bash
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
INSTANCE="${INSTANCE:-}"
PROVIDER="${PROVIDER:-${GOAD_PROVIDER_DIR:-}}"

if [[ -z "$PROVIDER" ]]; then
  if [[ -z "$INSTANCE" ]]; then
    echo 'FAIL: set INSTANCE, PROVIDER, or GOAD_PROVIDER_DIR explicitly' >&2
    exit 2
  fi
  PROVIDER="$ROOT/workspace/$INSTANCE/provider"
fi

if [[ -z "$INSTANCE" ]]; then
  INSTANCE="$(basename "$(dirname "$PROVIDER")")"
fi
DOMAIN_FQDN="north.sevenkingdoms.local"
DOMAIN_NB="NORTH"
WINTERFELL="10.4.10.11"
CASTELBLACK="10.4.10.22"
WS01="10.4.10.31"
STAMP="$(date +%Y%m%d-%H%M%S)"
EVIDENCE="${EVIDENCE:-$HOME/Kingdoms-evidence/phase02-readiness-$STAMP}"
RDP_BOT_MODE="${PHASE02_RDP_BOT_MODE:-legacy}"

mkdir -p "$EVIDENCE"
case "$RDP_BOT_MODE" in
  legacy|headless) ;;
  *)
    echo "PHASE02_RDP_BOT_MODE must be legacy or headless (got: $RDP_BOT_MODE)" >&2
    exit 2
    ;;
esac
cd "$ROOT" || exit 1
export PATH="$HOME/.goad/.venv/bin:$PATH"
export KINGDOMS_RDP_LOG_DIR="$EVIDENCE/rdp-contract"

# The legacy GOAD run remains the default. For the reduced NORTH course,
# bind the RDP policy audit to this instance's exact inventory and scenario;
# GOAD/Essos inventory data must not masquerade as NORTH release evidence.
case "${KINGDOMS_PHASE02_PROFILE:-GOAD}" in
  GOAD) ;;
  NORTH)
    export KINGDOMS_RDP_DATA_INVENTORY="$ROOT/ad/NORTH/data/inventory"
    export KINGDOMS_RDP_INVENTORY="$(dirname "$PROVIDER")/inventory"
    export KINGDOMS_RDP_SCENARIO_CONFIG="$ROOT/ad/NORTH/data/config.json"
    for required in "$KINGDOMS_RDP_DATA_INVENTORY" "$KINGDOMS_RDP_INVENTORY" "$KINGDOMS_RDP_SCENARIO_CONFIG"; do
      [[ -f "$required" ]] || { printf '[FAIL] NORTH RDP input missing: %s\n' "$required" >&2; exit 2; }
    done
    ;;
  *) echo '[FAIL] KINGDOMS_PHASE02_PROFILE must be GOAD or NORTH' >&2; exit 2 ;;
esac

PASS=0
FAIL=0
WARN=0

pass(){ PASS=$((PASS+1)); printf '[PASS] %s\n' "$*"; }
fail(){ FAIL=$((FAIL+1)); printf '[FAIL] %s\n' "$*" >&2; }
warn(){ WARN=$((WARN+1)); printf '[WARN] %s\n' "$*" >&2; }
section(){ printf '\n============================================================\n%s\n============================================================\n' "$*"; }
strip_ansi(){ sed -E 's/\x1B\[[0-9;?]*[ -\/]*[@-~]//g'; }
tcp_open(){ timeout 4 nc -z -w3 "$1" "$2" >/dev/null 2>&1; }

USERS=(hodor brandon.stark jon.snow samwell.tarly rickon.stark)
declare -A PASSWD=(
  [hodor]='hodor'
  [brandon.stark]='iseedeadpeople'
  [jon.snow]='iknownothing'
  [samwell.tarly]='Heartsbane'
  [rickon.stark]='Winter2022'
)

NXC=()
if command -v netexec >/dev/null 2>&1; then
  NXC=(netexec)
elif command -v nxc >/dev/null 2>&1; then
  NXC=(nxc)
elif command -v poetry >/dev/null 2>&1 && poetry run netexec --version >/dev/null 2>&1; then
  NXC=(poetry run netexec)
fi

run_nxc(){
  local logfile="$1"; shift
  local raw="${logfile}.raw"
  local nxc_path="$EVIDENCE/nxc"
  mkdir -p "$nxc_path"
  env NXC_PATH="$nxc_path" timeout 90 "${NXC[@]}" "$@" >"$raw" 2>&1
  local rc=$?
  strip_ansi <"$raw" >"$logfile"
  cat "$logfile"
  return "$rc"
}

auth_ok(){ grep -Fq '[+]' "$1"; }
share_line(){ grep -Ei "(^|[[:space:]])$2([[:space:]]|$)" "$1" | head -n 1; }
share_has(){ local line; line="$(share_line "$1" "$2")"; grep -Fq "$3" <<<"$line"; }

section 'KINGDOMS — 02 TEST THE GATES — STRICT PRE-LAB CONTRACT'
printf 'Instance : %s\nEvidence : %s\nRDP bot  : %s\nNetExec  : isolated under %s\n' "$INSTANCE" "$EVIDENCE" "$RDP_BOT_MODE" "$EVIDENCE/nxc"

section '1. REQUIRED OPERATOR TOOLS'
for c in git nc timeout curl getent python3; do
  command -v "$c" >/dev/null 2>&1 && pass "$c available" || fail "$c missing"
done
[[ ${#NXC[@]} -gt 0 ]] && pass "NetExec available: ${NXC[*]}" || fail 'NetExec/nxc unavailable'
if command -v xfreerdp3 >/dev/null 2>&1 || command -v xfreerdp >/dev/null 2>&1; then
  pass 'FreeRDP client available'
else
  fail 'FreeRDP client missing'
fi
MSSQLCLIENT=''
if command -v impacket-mssqlclient >/dev/null 2>&1; then
  MSSQLCLIENT="$(command -v impacket-mssqlclient)"
elif command -v mssqlclient.py >/dev/null 2>&1; then
  MSSQLCLIENT="$(command -v mssqlclient.py)"
fi
if [[ -n "$MSSQLCLIENT" ]] && timeout 15 env PATH=/usr/bin:/bin "$MSSQLCLIENT" -h >/dev/null 2>&1; then
  pass "Impacket MSSQL client functional with system Python"
else
  fail 'Impacket MSSQL client missing or broken with system Python'
fi

HTTP_AUTH_CLIENT=''
if curl --version 2>/dev/null | grep -qi 'NTLM'; then
  HTTP_AUTH_CLIENT='curl'
  pass 'curl has NTLM support'
elif /usr/bin/python3 -c 'import requests, requests_ntlm' >/dev/null 2>&1; then
  HTTP_AUTH_CLIENT='requests-ntlm'
  pass 'Python requests-ntlm available for the HTTP Windows-auth gate'
else
  fail 'No working NTLM HTTP client: curl lacks NTLM and python3 requests-ntlm is unavailable'
fi

section '2. INSTANCE / EXERCISE STATE'
[[ -d "$PROVIDER" ]] && pass 'provider directory exists' || fail "provider missing: $PROVIDER"
if [[ -f "$PROVIDER/.goad-nomad-mode" ]]; then
  MODE="$(tr -d '[:space:]' < "$PROVIDER/.goad-nomad-mode")"
  [[ "$MODE" == exercise ]] && pass 'lab mode = exercise' || fail "lab mode=$MODE (expected exercise)"
else
  fail 'runtime mode marker missing'
fi

section '3. COURSE NAME RESOLUTION'
for rec in \
  "winterfell.north.sevenkingdoms.local:$WINTERFELL" \
  "castelblack.north.sevenkingdoms.local:$CASTELBLACK" \
  "ws01.north.sevenkingdoms.local:$WS01"
do
  fqdn="${rec%%:*}"; ip="${rec##*:}"
  if getent ahostsv4 "$fqdn" 2>/dev/null | awk '{print $1}' | grep -Fxq "$ip"; then
    pass "$fqdn resolves to $ip"
  else
    fail "$fqdn does not resolve to $ip from the student host"
  fi
done

section '4. PHASE 01 REGRESSION + EXACT RDP CONTRACT'
set +e
bash scripts/validate-rdp-runtime.sh --phase01 --bot-mode "$RDP_BOT_MODE" 2>&1 | tee "$EVIDENCE/rdp-phase01.log"
RDP_RC=${PIPESTATUS[0]}
set +e
if [[ $RDP_RC -eq 0 ]]; then
  pass 'Phase 01 regression + Phase 02 RDP runtime contract'
else
  fail "existing validator failed rc=$RDP_RC"
fi
for host in WINTERFELL CASTELBLACK WS01; do
  grep -Fq "RDP_POLICY_CONTRACT=${host}:PASS" "$EVIDENCE/rdp-phase01.log" \
    && pass "$host exact RDP policy" \
    || fail "$host RDP policy marker missing"
done

section '5. REQUIRED GATE REACHABILITY'
for rec in \
  "WINTERFELL:$WINTERFELL:445:SMB" \
  "CASTELBLACK:$CASTELBLACK:445:SMB" \
  "WS01:$WS01:445:SMB" \
  "WINTERFELL:$WINTERFELL:3389:RDP" \
  "CASTELBLACK:$CASTELBLACK:3389:RDP" \
  "WS01:$WS01:3389:RDP" \
  "CASTELBLACK:$CASTELBLACK:1433:MSSQL" \
  "CASTELBLACK:$CASTELBLACK:80:HTTP"
do
  IFS=: read -r name ip port svc <<<"$rec"
  tcp_open "$ip" "$port" && pass "$name $svc TCP/$port reachable" || fail "$name $svc TCP/$port unreachable"
done

for rec in "WINTERFELL:$WINTERFELL" "CASTELBLACK:$CASTELBLACK" "WS01:$WS01"; do
  name="${rec%%:*}"; ip="${rec##*:}"
  if tcp_open "$ip" 5985; then
    pass "$name WinRM TCP/5985 reachable for the documented command path"
  elif tcp_open "$ip" 5986; then
    fail "$name exposes only WinRM/HTTPS 5986; documented NetExec command needs correction before the lab"
  else
    fail "$name WinRM is unreachable on both 5985 and 5986"
  fi
done

section '6. FIVE RECOVERED CREDENTIALS — SMB AUTHENTICATION'
if [[ ${#NXC[@]} -gt 0 ]]; then
  for target in "WINTERFELL:$WINTERFELL" "CASTELBLACK:$CASTELBLACK"; do
    name="${target%%:*}"; ip="${target##*:}"
    for user in "${USERS[@]}"; do
      log="$EVIDENCE/smb-${name,,}-$user.log"
      run_nxc "$log" smb "$ip" -d "$DOMAIN_FQDN" -u "$user" -p "${PASSWD[$user]}" --shares >/dev/null 2>&1
      if auth_ok "$log"; then
        pass "$name accepts NORTH\\$user over SMB"
      else
        fail "$name did not accept NORTH\\$user over SMB"
        continue
      fi

      if [[ "$name" == WINTERFELL ]]; then
        for share in 'IPC$' NETLOGON SYSVOL; do
          share_has "$log" "$share" READ \
            && pass "$name $user has expected READ on $share" \
            || fail "$name $user missing expected READ on $share"
        done
        for share in 'ADMIN$' 'C$'; do
          if share_has "$log" "$share" READ || share_has "$log" "$share" WRITE; then
            fail "$name $user unexpectedly has file access on $share"
          else
            pass "$name $user has no unexpected access on $share"
          fi
        done
      else
        for share in all public; do
          if share_has "$log" "$share" READ && share_has "$log" "$share" WRITE; then
            pass "$name $user has expected READ,WRITE on $share"
          else
            fail "$name $user does not have expected READ,WRITE on $share"
          fi
        done
        for share in 'ADMIN$' 'C$'; do
          if share_has "$log" "$share" READ || share_has "$log" "$share" WRITE; then
            fail "$name $user unexpectedly has administrative-share access on $share"
          else
            pass "$name $user has no unexpected administrative-share access on $share"
          fi
        done
      fi
    done
  done
else
  fail 'SMB credential/authorization matrix not run because NetExec is unavailable'
fi

section '7. WINRM — NO SURPRISE FOOTHOLD'
if [[ ${#NXC[@]} -gt 0 ]]; then
  for target in "WINTERFELL:$WINTERFELL" "CASTELBLACK:$CASTELBLACK" "WS01:$WS01"; do
    name="${target%%:*}"; ip="${target##*:}"
    if ! tcp_open "$ip" 5985; then
      fail "$name WinRM authorization test cannot use the documented TCP/5985 path"
      continue
    fi
    for user in "${USERS[@]}"; do
      log="$EVIDENCE/winrm-${name,,}-$user.log"
      run_nxc "$log" winrm "$ip" -d "$DOMAIN_FQDN" -u "$user" -p "${PASSWD[$user]}" >/dev/null 2>&1
      if auth_ok "$log"; then
        fail "$name unexpectedly gives NORTH\\$user a WinRM-capable session"
      else
        pass "$name does not give NORTH\\$user an unexpected WinRM foothold"
      fi
    done
  done
else
  fail 'WinRM matrix not run because NetExec is unavailable'
fi

section '8. MSSQL — EXACT WINDOWS LOGIN CONTRACT'
if [[ ${#NXC[@]} -gt 0 ]]; then
  declare -A SQL_EXPECT=(
    [hodor]=allow
    [brandon.stark]=allow
    [jon.snow]=allow
    [samwell.tarly]=allow
    [rickon.stark]=allow
  )
  for user in "${USERS[@]}"; do
    log="$EVIDENCE/mssql-$user.log"
    run_nxc "$log" mssql "$CASTELBLACK" -d "$DOMAIN_FQDN" -u "$user" -p "${PASSWD[$user]}" >/dev/null 2>&1
    if auth_ok "$log"; then observed=allow; else observed=deny; fi
    if [[ "$observed" == "${SQL_EXPECT[$user]}" ]]; then
      pass "MSSQL $user = $observed as designed"
    else
      fail "MSSQL $user = $observed, expected ${SQL_EXPECT[$user]}"
    fi
  done
else
  fail 'MSSQL login matrix not run because NetExec is unavailable'
fi

section '9. MSSQL — SERVER ROLE CONTRACT'
if [[ -n "$MSSQLCLIENT" ]]; then
  for user in hodor brandon.stark jon.snow samwell.tarly rickon.stark; do
    log="$EVIDENCE/mssql-role-$user.log"
    printf "SELECT SYSTEM_USER;\nSELECT IS_SRVROLEMEMBER('sysadmin');\nexit\n" | \
      timeout 45 env PATH=/usr/bin:/bin "$MSSQLCLIENT" "$DOMAIN_NB/$user:${PASSWD[$user]}@$CASTELBLACK" -windows-auth \
      >"$log" 2>&1
    rc=$?
    cat "$log"
    if [[ $rc -ne 0 ]] || ! grep -Eqi "${user//./\\.}" "$log"; then
      fail "Could not query MSSQL context for $user"
      continue
    fi
    if [[ "$user" == jon.snow ]]; then
      grep -Eq '(^|[[:space:]])1([[:space:]]|$)' "$log" \
        && pass 'jon.snow is MSSQL sysadmin as designed' \
        || fail 'jon.snow is not MSSQL sysadmin as designed'
    else
      grep -Eq '(^|[[:space:]])0([[:space:]]|$)' "$log" \
        && pass "$user is a non-sysadmin MSSQL login as designed" \
        || fail "$user MSSQL sysadmin state does not match the course contract"
    fi
  done
else
  fail 'MSSQL role checks not run: Impacket mssqlclient missing'
fi

section '10. IIS WINDOWS AUTHENTICATION — EXACT COURSE BOUNDARY'
url="http://castelblack.north.sevenkingdoms.local/internal/"
unauth="$EVIDENCE/http-unauth.headers"
code="$(curl --noproxy '*' -sS --max-time 15 -D "$unauth" -o /dev/null -w '%{http_code}' "$url" 2>"$EVIDENCE/http-unauth.err")"
if [[ "$code" == 401 ]] && grep -Eqi '^WWW-Authenticate:.*Negotiate' "$unauth" && grep -Eqi '^WWW-Authenticate:.*NTLM' "$unauth"; then
  pass '/internal/ unauthenticated boundary = 401 + Negotiate + NTLM'
else
  fail "/internal/ unauthenticated boundary mismatch (HTTP ${code:-ERROR})"
fi

for user in "${USERS[@]}"; do
  headers="$EVIDENCE/http-$user.headers"
  body="$EVIDENCE/http-$user.body"
  if [[ "$HTTP_AUTH_CLIENT" == 'curl' ]]; then
    code="$(curl --noproxy '*' --ntlm -sS --max-time 15 -D "$headers" -o "$body" -w '%{http_code}' \
        -u "$DOMAIN_NB\\$user:${PASSWD[$user]}" "$url" 2>"$EVIDENCE/http-$user.err")"
  elif [[ "$HTTP_AUTH_CLIENT" == 'requests-ntlm' ]]; then
    code="$(PHASE02_HTTP_USER="$DOMAIN_NB\\$user" PHASE02_HTTP_PASS="${PASSWD[$user]}" PHASE02_HTTP_URL="$url" \
      /usr/bin/python3 - <<'PY'
import os
import requests
from requests_ntlm import HttpNtlmAuth
s = requests.Session()
s.trust_env = False
r = s.get(
    os.environ["PHASE02_HTTP_URL"],
    auth=HttpNtlmAuth(os.environ["PHASE02_HTTP_USER"], os.environ["PHASE02_HTTP_PASS"]),
    timeout=15,
)
print(r.status_code)
PY
    )"
  else
    code='ERROR'
  fi
  if [[ "$code" =~ ^2[0-9][0-9]$ ]]; then
    pass "/internal/ accepts NORTH\\$user (HTTP $code)"
  else
    fail "/internal/ does not accept NORTH\\$user as planned (HTTP ${code:-ERROR})"
  fi
done

section '11. FINAL PHASE 02 FOOTHOLD CONTRACT'
if tcp_open "$WS01" 3389 && grep -Fq 'RDP_POLICY_CONTRACT=WS01:PASS' "$EVIDENCE/rdp-phase01.log"; then
  pass 'Rickon -> WS01 RDP low-privilege foothold is ready'
else
  fail 'Rickon -> WS01 foothold contract is not ready'
fi

section 'FINAL RESULT'
printf 'PASS: %d\nWARN: %d\nFAIL: %d\nEvidence: %s\n' "$PASS" "$WARN" "$FAIL" "$EVIDENCE"
if [[ $FAIL -eq 0 ]]; then
  cat <<'READY'

[READY] 02 — TEST THE GATES PRE-LAB CONTRACT PASSED
The current Kingdoms instance matches the intended Phase 02 path.
No known access-right/service mismatch should force a curriculum stop.
READY
  exit 0
fi

cat <<'NOTREADY'

[NOT READY] 02 — TEST THE GATES HAS A CONTRACT MISMATCH
Fix every [FAIL] before restarting the chapter. Do not work around it mid-lab.
NOTREADY
exit 1