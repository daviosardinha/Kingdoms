#!/usr/bin/env bash
# Phase 03 readiness contract: read-only prerequisite validation for
# "03 - Poison the Wells". This script does NOT start Responder, ntlmrelayx,
# mitm6, trigger coercion, relay credentials, or modify Active Directory.
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
DOMAIN_FQDN='north.sevenkingdoms.local'
WINTERFELL='10.4.10.11'
CASTELBLACK='10.4.10.22'
WS01='10.4.10.31'
KINGSLANDING='10.4.20.10'
MEEREEN='10.4.30.12'
STAMP="$(date +%Y%m%d-%H%M%S)"
EVIDENCE="${EVIDENCE:-$HOME/Kingdoms-evidence/phase03-readiness-$STAMP}"

mkdir -p "$EVIDENCE"
cd "$ROOT" || exit 1
export PATH="$HOME/.goad/.venv/bin:$PATH"

# Full GOAD remains the default. NORTH requires its exact reduced inventory;
# a GOAD/Essos inventory can produce false Phase 03 readiness results.
case "${KINGDOMS_PHASE03_PROFILE:-GOAD}" in
  GOAD)
    PHASE03_LAB_INVENTORY="$ROOT/ad/GOAD/data/inventory"
    PHASE03_INSTANCE_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"
    ;;
  NORTH)
    PHASE03_LAB_INVENTORY="$ROOT/ad/NORTH/data/inventory"
    PHASE03_INSTANCE_INVENTORY="$(dirname "$PROVIDER")/inventory"
    [[ -f "$ROOT/ad/NORTH/data/config.json" ]] || {
      echo '[FAIL] NORTH scenario config missing' >&2; exit 2;
    }
    ;;
  *)
    echo '[FAIL] KINGDOMS_PHASE03_PROFILE must be GOAD or NORTH' >&2
    exit 2
    ;;
esac
for required in "$PHASE03_LAB_INVENTORY" "$PHASE03_INSTANCE_INVENTORY"; do
  [[ -f "$required" ]] || {
    printf '[FAIL] Phase 03 inventory missing: %s\n' "$required" >&2
    exit 2
  }
done

PASS=0
WARN=0
FAIL=0
pass(){ PASS=$((PASS+1)); printf '[PASS] %s\n' "$*"; }
warn(){ WARN=$((WARN+1)); printf '[WARN] %s\n' "$*" >&2; }
fail(){ FAIL=$((FAIL+1)); printf '[FAIL] %s\n' "$*" >&2; }
info(){ printf '[INFO] %s\n' "$*"; }
section(){ printf '\n============================================================\n%s\n============================================================\n' "$*"; }
strip_ansi(){ sed -E 's/\x1B\[[0-9;?]*[ -\/]*[@-~]//g'; }
tcp_open(){ timeout 4 nc -z -w3 "$1" "$2" >/dev/null 2>&1; }

find_ansible_playbook(){
  local c
  for c in \
    "$(command -v ansible-playbook 2>/dev/null || true)" \
    "$ROOT/.venv/bin/ansible-playbook" \
    "$ROOT/venv/bin/ansible-playbook" \
    "$HOME/.goad/.venv/bin/ansible-playbook" \
    "$HOME/.local/bin/ansible-playbook"; do
    [[ -n "$c" && -x "$c" ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

NXC=()
if command -v netexec >/dev/null 2>&1; then
  NXC=(netexec)
elif command -v nxc >/dev/null 2>&1; then
  NXC=(nxc)
elif command -v poetry >/dev/null 2>&1 && poetry run netexec --version >/dev/null 2>&1; then
  NXC=(poetry run netexec)
fi

MSSQLCLIENT=''
if command -v impacket-mssqlclient >/dev/null 2>&1; then
  MSSQLCLIENT="$(command -v impacket-mssqlclient)"
elif command -v mssqlclient.py >/dev/null 2>&1; then
  MSSQLCLIENT="$(command -v mssqlclient.py)"
fi

LDAP_CHECKER=''
for c in \
  /usr/share/doc/python3-impacket/examples/CheckLDAPStatus.py \
  /usr/share/doc/python3-impacket/examples/CheckLDAPStatus.py.gz; do
  [[ -f "$c" ]] || continue
  LDAP_CHECKER="$c"
  break
done
if [[ -z "$LDAP_CHECKER" ]] && command -v dpkg >/dev/null 2>&1; then
  LDAP_CHECKER="$(dpkg -L python3-impacket 2>/dev/null | grep '/CheckLDAPStatus.py$' | head -n1 || true)"
fi

section 'KINGDOMS — 03 POISON THE WELLS — READ-ONLY READINESS CONTRACT'
printf 'Instance : %s\nEvidence : %s\n' "$INSTANCE" "$EVIDENCE"
printf '%s\n' '[INFO] No poisoning, relay, coercion, directory modification, capture or credential dumping is performed.'

section '0. SOURCE / INSTANCE / TOOL PRECHECK'
if bash scripts/verify-test-source.sh 2>&1 | tee "$EVIDENCE/source-gate.log"; then
  pass 'Git source gate passed'
else
  fail 'Git source gate failed'
fi

[[ -d "$PROVIDER" ]] && pass "provider exists: $PROVIDER" || fail "provider missing: $PROVIDER"
if [[ -f "$PROVIDER/.goad-nomad-mode" ]]; then
  MODE="$(tr -d '[:space:]' < "$PROVIDER/.goad-nomad-mode")"
  [[ "$MODE" == exercise ]] && pass 'instance is recorded in exercise mode' || fail "instance mode=$MODE (expected exercise)"
else
  fail 'exercise-mode marker missing'
fi

for c in git ip nc timeout grep awk sed python3 ss nslookup; do
  command -v "$c" >/dev/null 2>&1 && pass "tool available: $c" || fail "tool missing: $c"
done
[[ ${#NXC[@]} -gt 0 ]] && pass "NetExec available: ${NXC[*]}" || fail 'NetExec/nxc unavailable'
[[ -n "$MSSQLCLIENT" ]] && pass "MSSQL client available: $MSSQLCLIENT" || fail 'Impacket mssqlclient unavailable'
[[ -n "$LDAP_CHECKER" && "$LDAP_CHECKER" != *.gz ]] && pass "CheckLDAPStatus.py available: $LDAP_CHECKER" || fail 'CheckLDAPStatus.py unavailable as a directly executable Python source file'
ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] && pass "ansible-playbook available: $ANSIBLE_PLAYBOOK" || fail 'ansible-playbook unavailable'

for tool in responder impacket-ntlmrelayx mitm6 hashcat; do
  if command -v "$tool" >/dev/null 2>&1; then pass "Phase 03 operator tool available: $tool"; else warn "Phase 03 operator tool not found in PATH: $tool"; fi
done
if command -v coercer >/dev/null 2>&1 || command -v Coercer >/dev/null 2>&1 || command -v Coercer.py >/dev/null 2>&1; then
  pass 'Coercer tooling available'
else
  warn 'Coercer tooling not found in PATH; PrinterBug/PetitPotam can still be tested with specialist scripts later'
fi

section '1. NORTH ATTACK-SIDE NETWORK POSITION'
ROUTE_LINE="$(ip route get "$WINTERFELL" 2>/dev/null | head -n1 || true)"
printf '%s\n' "$ROUTE_LINE" | tee "$EVIDENCE/route-winterfell.log"
NORTH_IF="$(awk '{for(i=1;i<=NF;i++) if($i=="dev") {print $(i+1); exit}}' <<<"$ROUTE_LINE")"
NORTH_SRC="$(awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}' <<<"$ROUTE_LINE")"
if [[ -n "$NORTH_IF" && -n "$NORTH_SRC" ]]; then
  pass "NORTH route is direct through $NORTH_IF from $NORTH_SRC"
else
  fail 'could not determine the student-side NORTH interface/source address'
fi
if ip route show 10.4.10.0/24 | grep -Eq '(^|[[:space:]])10\.4\.10\.0/24([[:space:]]|$)' ; then
  pass '10.4.10.0/24 is present as the student-side NORTH network'
else
  fail '10.4.10.0/24 route is missing'
fi

for rec in "WINTERFELL:$WINTERFELL" "CASTELBLACK:$CASTELBLACK" "WS01:$WS01"; do
  name="${rec%%:*}"; ip="${rec##*:}"
  tcp_open "$ip" 445 && pass "$name SMB reachable directly from the student side" || fail "$name SMB unreachable from the student side"
done

if tcp_open "$KINGSLANDING" 445; then fail 'SevenKingdoms is directly reachable from the student side; segmentation contract broken'; else pass 'SevenKingdoms remains directly blocked from the student side'; fi
if tcp_open "$MEEREEN" 445; then fail 'ESSOS is directly reachable from the student side; segmentation contract broken'; else pass 'ESSOS remains directly blocked from the student side'; fi

section '2. SMB SIGNING / RELAY TARGET DISCOVERY'
if [[ ${#NXC[@]} -gt 0 ]]; then
  SMB_LOG="$EVIDENCE/netexec-smb-north.log"
  timeout 90 "${NXC[@]}" smb 10.4.10.0/24 >"$SMB_LOG.raw" 2>&1
  SMB_RC=$?
  strip_ansi <"$SMB_LOG.raw" >"$SMB_LOG"
  cat "$SMB_LOG"
  [[ $SMB_RC -eq 0 ]] || warn "NetExec SMB fingerprint returned rc=$SMB_RC; parsing evidence anyway"
  grep -Ei "${WINTERFELL}.*signing:True" "$SMB_LOG" >/dev/null && pass 'WINTERFELL requires SMB signing' || fail 'WINTERFELL SMB signing=True was not observed'
  grep -Ei "${CASTELBLACK}.*signing:False" "$SMB_LOG" >/dev/null && pass 'CASTELBLACK does not require SMB signing' || fail 'CASTELBLACK SMB signing=False was not observed'
  grep -Ei "${WS01}.*signing:False" "$SMB_LOG" >/dev/null && pass 'WS01 does not require SMB signing' || fail 'WS01 SMB signing=False was not observed'

  RELAY_LIST="$EVIDENCE/smb-relay-targets.txt"
  timeout 90 "${NXC[@]}" smb 10.4.10.0/24 --gen-relay-list "$RELAY_LIST" >"$EVIDENCE/netexec-relay-list.raw" 2>&1
  strip_ansi <"$EVIDENCE/netexec-relay-list.raw" >"$EVIDENCE/netexec-relay-list.log"
  if [[ -s "$RELAY_LIST" ]] && grep -Fxq "$CASTELBLACK" "$RELAY_LIST"; then pass 'CASTELBLACK is generated as an SMB relay target'; else fail 'CASTELBLACK missing from generated SMB relay targets'; fi
  if [[ -s "$RELAY_LIST" ]] && grep -Fxq "$WS01" "$RELAY_LIST"; then pass 'WS01 is generated as an SMB relay target'; else fail 'WS01 missing from generated SMB relay targets'; fi
  if [[ -s "$RELAY_LIST" ]] && grep -Fxq "$WINTERFELL" "$RELAY_LIST"; then fail 'WINTERFELL was incorrectly generated as an SMB relay target'; else pass 'WINTERFELL correctly excluded from SMB relay targets'; fi
else
  fail 'SMB signing/relay-list validation skipped because NetExec is unavailable'
fi

section '3. WINDOWS-SIDE POISONING / BOT / IPV6 / COERCION PREREQUISITES'
if [[ -n "$ANSIBLE_PLAYBOOK" ]]; then
  PLAYBOOK="$EVIDENCE/phase03-readonly.yml"
  cat >"$PLAYBOOK" <<'YAML'
---
- name: Phase 03 read-only prerequisite inventory
  hosts: dc02:srv02:ws01
  gather_facts: false
  tasks:
    - name: Collect Phase 03 runtime facts without changing state
      ansible.windows.win_powershell:
        script: |
          $ErrorActionPreference = 'Stop'
          $name = $env:COMPUTERNAME.ToUpperInvariant()
          Write-Output "PHASE03_HOST=$name"

          $spooler = Get-Service Spooler -ErrorAction SilentlyContinue
          if ($null -ne $spooler) {
              Write-Output ('PHASE03_SPOOLER={0}:{1}:{2}' -f $name, $spooler.Status, $spooler.StartType)
          }

          if ($name -eq 'WINTERFELL') {
              $llmnr = (Get-ItemProperty 'HKLM:\Software\Policies\Microsoft\Windows NT\DNSClient' -Name EnableMulticast -ErrorAction Stop).EnableMulticast
              Write-Output "PHASE03_LLMNR=$llmnr"

              $cfg = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object { $_.IPAddress -contains '10.4.10.11' } | Select-Object -First 1
              if ($null -eq $cfg) { throw 'Could not identify WINTERFELL segmented adapter' }
              Write-Output "PHASE03_NBTNS=$($cfg.TcpipNetbiosOptions)"

              foreach ($taskName in 'responder_bot','ntlm_bot') {
                  $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
                  $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction Stop
                  $args = ($task.Actions | Select-Object -First 1).Arguments
                  $user = $task.Principal.UserId
                  $interval = ($task.Triggers | Select-Object -First 1).Repetition.Interval
                  Write-Output "PHASE03_BOT=$taskName|STATE=$($task.State)|LAST=$($info.LastTaskResult)|USER=$user|INTERVAL=$interval|ARGS=$args"
              }

              Import-Module ActiveDirectory -ErrorAction Stop
              $domain = Get-ADDomain -Identity 'north.sevenkingdoms.local' -ErrorAction Stop
              $root = Get-ADObject -Identity $domain.DistinguishedName -Properties 'ms-DS-MachineAccountQuota' -ErrorAction Stop
              Write-Output "PHASE03_MAQ=$($root.'ms-DS-MachineAccountQuota')"

              $ldapIntegrity = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\NTDS\Parameters' -Name LDAPServerIntegrity -ErrorAction SilentlyContinue).LDAPServerIntegrity
              $cbt = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\NTDS\Parameters' -Name LdapEnforceChannelBindings -ErrorAction SilentlyContinue).LdapEnforceChannelBindings
              if ($null -eq $ldapIntegrity) { $ldapIntegrity = '<unset>' }
              if ($null -eq $cbt) { $cbt = '<unset>' }
              Write-Output "PHASE03_LDAP_REGISTRY=LDAPServerIntegrity:$ldapIntegrity|LdapEnforceChannelBindings:$cbt"
          }

          if ($name -eq 'WS01') {
              $v4 = Get-NetIPAddress -AddressFamily IPv4 -IPAddress '10.4.10.31' -ErrorAction Stop
              $alias = $v4.InterfaceAlias
              $binding = Get-NetAdapterBinding -Name $alias -ComponentID ms_tcpip6 -ErrorAction Stop
              $v6 = @(Get-NetIPAddress -InterfaceAlias $alias -AddressFamily IPv6 -ErrorAction SilentlyContinue)
              Write-Output "PHASE03_WS01_IPV6=ALIAS:$alias|ENABLED:$($binding.Enabled)|COUNT:$($v6.Count)"
          }

          if ($name -eq 'CASTELBLACK') {
              $sql = Get-CimInstance Win32_Service | Where-Object { $_.Name -like 'MSSQL*' -and $_.State -eq 'Running' } | Select-Object -First 1
              if ($null -eq $sql) { throw 'No running MSSQL service found on CASTELBLACK' }
              Write-Output "PHASE03_MSSQL_SERVICE=NAME:$($sql.Name)|ACCOUNT:$($sql.StartName)|STATE:$($sql.State)"
          }
      changed_when: false
      register: phase03_facts

    - name: Emit Phase 03 markers for the validator
      ansible.builtin.debug:
        msg: "{{ phase03_facts.output | default([]) }}"
      changed_when: false
YAML

  ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  timeout 600 "$ANSIBLE_PLAYBOOK" \
    -i "$PHASE03_LAB_INVENTORY" \
    -i "$PHASE03_INSTANCE_INVENTORY" \
    "$PLAYBOOK" 2>&1 | tee "$EVIDENCE/windows-prereqs.log"
  ANSIBLE_RC=${PIPESTATUS[0]}
  [[ $ANSIBLE_RC -eq 0 ]] && pass 'read-only Windows prerequisite collection completed' || fail "Windows prerequisite collection failed rc=$ANSIBLE_RC"

  grep -Fq 'PHASE03_LLMNR=1' "$EVIDENCE/windows-prereqs.log" && pass 'WINTERFELL LLMNR is enabled' || fail 'WINTERFELL LLMNR is not explicitly enabled'
  if grep -Eq 'PHASE03_NBTNS=(0|1)' "$EVIDENCE/windows-prereqs.log"; then pass 'WINTERFELL NetBIOS-over-TCP/IP is not explicitly disabled'; else fail 'WINTERFELL NBT-NS posture does not match the lab prerequisite'; fi

  BOT_RESP="$(grep -F 'PHASE03_BOT=responder_bot|' "$EVIDENCE/windows-prereqs.log" | tail -n1 || true)"
  if grep -Fqi 'USER=robb.stark' <<<"$BOT_RESP" && grep -Fqi 'Bravos' <<<"$BOT_RESP" && grep -Fqi 'private' <<<"$BOT_RESP" && grep -Fqi 'INTERVAL=PT2M' <<<"$BOT_RESP"; then
    pass 'responder_bot = Robb -> \\Bravos\private every 2 minutes'
  else
    fail 'responder_bot runtime contract does not match the intended Robb poisoning trigger'
  fi

  BOT_NTLM="$(grep -F 'PHASE03_BOT=ntlm_bot|' "$EVIDENCE/windows-prereqs.log" | tail -n1 || true)"
  if grep -Fqi 'USER=eddard.stark' <<<"$BOT_NTLM" && grep -Fqi 'Meren' <<<"$BOT_NTLM" && grep -Fqi 'Private' <<<"$BOT_NTLM" && grep -Fqi 'INTERVAL=PT5M' <<<"$BOT_NTLM"; then
    pass 'ntlm_bot = Eddard -> \\Meren\Private every 5 minutes'
  else
    fail 'ntlm_bot runtime contract does not match the intended Eddard relay trigger'
  fi

  grep -Eq 'PHASE03_MAQ=([1-9][0-9]*)' "$EVIDENCE/windows-prereqs.log" && pass 'NORTH MachineAccountQuota is non-zero for an RBCD lab candidate' || warn 'NORTH MachineAccountQuota is zero/unavailable; add-computer RBCD path will need a different design'
  grep -Eq 'PHASE03_WS01_IPV6=.*ENABLED:True.*COUNT:[1-9]' "$EVIDENCE/windows-prereqs.log" && pass 'WS01 NORTH adapter has IPv6 enabled and at least one IPv6 address' || warn 'WS01 IPv6 prerequisite is not ready for a mitm6 lab'
  if MSSQL_MARKER="$(grep -F 'PHASE03_MSSQL_SERVICE=' "$EVIDENCE/windows-prereqs.log" | tail -n1 || true)" && grep -Fqi 'ACCOUNT:north.sevenkingdoms.local' <<<"$MSSQL_MARKER" && grep -Fqi 'sql_svc' <<<"$MSSQL_MARKER" && grep -Fqi 'STATE:Running' <<<"$MSSQL_MARKER"; then
    pass 'CASTELBLACK MSSQL runs as the NORTH sql_svc domain identity'
  else
    fail 'CASTELBLACK MSSQL service account is not the expected NORTH sql_svc identity'
  fi

  if grep -Eq 'PHASE03_SPOOLER=WINTERFELL:Running:' "$EVIDENCE/windows-prereqs.log"; then pass 'WINTERFELL Print Spooler is running (PrinterBug candidate surface)'; else warn 'WINTERFELL Print Spooler is not running; PrinterBug against the DC is not currently a candidate'; fi
else
  fail 'Windows-side prerequisites not collected because ansible-playbook is unavailable'
fi

section '4. DNS-MISS PREREQUISITES FOR THE TWO BUILT-IN BOTS'
for typo in bravos meren; do
  DNS_LOG="$EVIDENCE/dns-${typo}.log"
  if nslookup "${typo}.${DOMAIN_FQDN}" "$WINTERFELL" >"$DNS_LOG" 2>&1; then
    if grep -Eqi 'NXDOMAIN|Non-existent domain|server can.t find' "$DNS_LOG"; then
      pass "$typo is absent from NORTH DNS and can fall through to local name resolution"
    else
      fail "$typo unexpectedly resolves in NORTH DNS"
    fi
  else
    if grep -Eqi 'NXDOMAIN|Non-existent domain|server can.t find' "$DNS_LOG"; then
      pass "$typo is absent from NORTH DNS and can fall through to local name resolution"
    else
      fail "could not prove expected DNS miss for $typo"
    fi
  fi
done

section '5. LDAP / LDAPS RELAY TARGET POSTURE'
for port in 389 636; do
  tcp_open "$WINTERFELL" "$port" && pass "WINTERFELL TCP/$port reachable" || fail "WINTERFELL TCP/$port unreachable"
done

LDAP_POSTURE_PROVED=0
if [[ ${#NXC[@]} -gt 0 ]]; then
  LDAP_NXC_LOG="$EVIDENCE/netexec-ldap-status.log"
  timeout 90 "${NXC[@]}" ldap "$WINTERFELL" -u '' -p '' >"$LDAP_NXC_LOG.raw" 2>&1
  LDAP_NXC_RC=$?
  strip_ansi <"$LDAP_NXC_LOG.raw" >"$LDAP_NXC_LOG"
  cat "$LDAP_NXC_LOG"
  [[ $LDAP_NXC_RC -eq 0 ]] || warn "NetExec LDAP posture probe returned rc=$LDAP_NXC_RC; parsing evidence anyway"

  if grep -Eqi 'signing:(None|False)' "$LDAP_NXC_LOG"; then
    pass 'WINTERFELL external LDAP probe does not observe signing enforcement'
  else
    fail 'NetExec LDAP probe did not show the expected non-enforced signing posture'
  fi

  if grep -Eqi 'channel binding:(Never|None|False)' "$LDAP_NXC_LOG"; then
    pass 'WINTERFELL external LDAP probe does not observe LDAPS channel-binding enforcement'
    LDAP_POSTURE_PROVED=1
  else
    fail 'NetExec LDAP probe did not show the expected non-enforced channel-binding posture'
  fi
else
  fail 'NetExec unavailable for LDAP relay-posture probe'
fi

# Optional corroboration with Impacket's CheckLDAPStatus.py.  Do not make a
# missing Python dependency look like a lab failure; the NetExec probe above
# is the primary external contract.
if [[ -n "$LDAP_CHECKER" && "$LDAP_CHECKER" != *.gz ]]; then
  LDAP_PY=''
  for py in "$HOME/.goad/.venv/bin/python" python3 /usr/bin/python3; do
    [[ -n "$py" ]] || continue
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import dns.resolver, impacket' >/dev/null 2>&1; then
      LDAP_PY="$(command -v "$py")"
      break
    fi
  done
  if [[ -n "$LDAP_PY" ]]; then
    LDAP_LOG="$EVIDENCE/ldap-status-impacket.log"
    timeout 90 "$LDAP_PY" "$LDAP_CHECKER" -domain "$DOMAIN_FQDN" -dc-ip "$WINTERFELL" >"$LDAP_LOG" 2>&1
    LDAP_RC=$?
    cat "$LDAP_LOG"
    if [[ $LDAP_RC -eq 0 ]] && grep -Eqi 'LDAP Signing Required:[[:space:]]*False' "$LDAP_LOG" && grep -Eqi 'LDAPS Channel Binding Status:[[:space:]]*Never' "$LDAP_LOG"; then
      pass 'CheckLDAPStatus.py independently corroborates signing=False and channel binding=Never'
    else
      warn 'CheckLDAPStatus.py did not corroborate the posture; NetExec evidence remains the primary Phase 03 gate'
    fi
  else
    info 'CheckLDAPStatus.py present but no local Python interpreter has its dns/impacket dependencies; NetExec is used as the primary probe'
  fi
fi

section '6. MSSQL AUTHENTICATION-COERCION PREREQUISITE'
if [[ -n "$MSSQLCLIENT" ]]; then
  SQL_LOG="$EVIDENCE/mssql-coercion-prereq.log"
  printf "SELECT SYSTEM_USER;\nSELECT servicename, service_account FROM sys.dm_server_services;\nEXEC master.sys.xp_dirtree 'C:\\Windows',1,0;\nexit\n" | \
    timeout 60 env PATH=/usr/bin:/bin "$MSSQLCLIENT" 'NORTH/jon.snow:iknownothing@castelblack.north.sevenkingdoms.local' -windows-auth \
    >"$SQL_LOG" 2>&1
  SQL_RC=$?
  cat "$SQL_LOG"
  if [[ $SQL_RC -eq 0 ]] && grep -Eqi 'NORTH\\jon\.snow' "$SQL_LOG"; then pass 'Jon can establish the documented Windows-authenticated MSSQL context'; else fail 'Jon MSSQL context failed'; fi
  grep -Eqi '(NORTH|north\.sevenkingdoms\.local)\\sql_svc' "$SQL_LOG" && pass 'MSSQL reports the expected NORTH sql_svc domain identity' || fail 'MSSQL service identity was not observed as the expected NORTH sql_svc identity'
  if [[ $SQL_RC -eq 0 ]] && ! grep -Eqi 'ERROR|permission.*denied|not.*permission' "$SQL_LOG"; then pass 'xp_dirtree executes with a local path; outbound UNC coercion can be lab-tested next without changing SQL configuration'; else fail 'xp_dirtree prerequisite did not execute cleanly'; fi
else
  fail 'MSSQL coercion prerequisite skipped because mssqlclient is unavailable'
fi

section '7. LOCAL LISTENER / TOOL CONFLICTS'
LISTEN_LOG="$EVIDENCE/local-listeners.log"
ss -H -lntup 2>/dev/null | tee "$LISTEN_LOG" || true
for port in 80 445; do
  if grep -Eq "(^|[^0-9]):${port}([^0-9]|$)" "$LISTEN_LOG"; then
    fail "local TCP/$port is already in use; Responder/ntlmrelayx listener ownership must be resolved before the relay lab"
  else
    pass "local TCP/$port is free for Phase 03 listeners"
  fi
done
# mitm6 needs the lab-facing interface, so a DNS listener bound only to
# loopback is not a conflict. Wildcard or non-loopback binds are.
for port in 53 547; do
  PORT_LINES="$(grep -E "(^|[^0-9]):${port}([^0-9]|$)" "$LISTEN_LOG" || true)"
  if [[ -z "$PORT_LINES" ]]; then
    pass "local port $port has no current listener conflict"
    continue
  fi

  NON_LOOPBACK="$(printf '%s\n' "$PORT_LINES" | grep -Ev '(^|[[:space:]])127\.0\.0\.1:' | grep -Ev '(^|[[:space:]])\[::1\]:' || true)"
  if [[ -n "$NON_LOOPBACK" ]]; then
    warn "local port $port has a non-loopback listener; inspect before starting mitm6"
  else
    pass "local port $port is bound only on loopback and does not conflict with the NORTH lab interface"
  fi
done

section '8. DELIBERATELY NOT EXECUTED YET'
printf '%s\n' \
  '[NOT RUN] Responder poisoning / NetNTLMv2 capture.' \
  '[NOT RUN] ntlmrelayx relay to CASTELBLACK or WS01.' \
  '[NOT RUN] SAM/LSASS/DPAPI dumping.' \
  '[NOT RUN] PrinterBug, PetitPotam, Coercer, or MSSQL UNC outbound authentication.' \
  '[NOT RUN] mitm6 / DHCPv6 / WPAD poisoning.' \
  '[NOT RUN] LDAP/LDAPS relay, RBCD, Shadow Credentials, or Drop-The-MIC.' \
  '[INFO] Those become technique-specific apply/prove/reset tests only after this prerequisite gate is understood.'

section 'FINAL PHASE 03 READINESS RESULT'
printf 'PASS: %d\nWARN: %d\nFAIL: %d\nEvidence: %s\n' "$PASS" "$WARN" "$FAIL" "$EVIDENCE"
if [[ $FAIL -eq 0 ]]; then
  cat <<'READY'

[READY] 03 — POISON THE WELLS BASELINE PREREQUISITES PASSED
The current instance supports the core NORTH poisoning/relay starting conditions.
Warnings identify optional/advanced paths that still require a focused runtime proof.
READY
  exit 0
fi

cat <<'NOTREADY'

[NOT READY] 03 — POISON THE WELLS HAS A BASELINE CONTRACT MISMATCH
Do not change the curriculum yet. Use the evidence above to decide whether the
lab or the planned Phase 03 path should be adapted.
NOTREADY
exit 1
