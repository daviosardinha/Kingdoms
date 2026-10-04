#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROVIDER="${GOAD_PROVIDER_DIR:-}"
readonly LOG_DIR="${GOAD_NOMAD_VALIDATION_LOG_DIR:-/tmp/goad-nomad-runtime-validation-$(date +%Y%m%d-%H%M%S)}"
readonly INVENTORY_DATA="${ROOT}/ad/GOAD/data/inventory"
readonly INVENTORY_PROVIDER="${ROOT}/ad/GOAD/providers/vmware/inventory"
readonly ANSIBLE_CFG="${ROOT}/ansible/ansible.cfg"
readonly RDP_BOT_MODE="${KINGDOMS_RDP_BOT_MODE:-legacy}"

readonly WINDOWS_VMS=(GOAD-DC01 GOAD-DC02 GOAD-DC03 GOAD-SRV02 GOAD-SRV03 GOAD-WS01)

declare -A EXPECTED_NAME=(
    [GOAD-DC01]=KINGSLANDING
    [GOAD-DC02]=WINTERFELL
    [GOAD-DC03]=MEEREEN
    [GOAD-SRV02]=CASTELBLACK
    [GOAD-SRV03]=BRAAVOS
    [GOAD-WS01]=WS01
)

declare -A NAT_IP=()

declare -i PASS_COUNT=0
declare -i FAIL_COUNT=0
declare -i WARN_COUNT=0
FINAL_EXERCISE=0

section() {
    echo
    echo "============================================================"
    echo "$*"
    echo "============================================================"
}

pass() {
    PASS_COUNT+=1
    echo "[PASS] $*"
}

warn() {
    WARN_COUNT+=1
    echo "[WARN] $*" >&2
}

fail() {
    FAIL_COUNT+=1
    echo "[FAIL] $*" >&2
    return 1
}

fatal() {
    fail "$*" || true
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fatal "required command not found: $1"
}

vmx_for() {
    local vm="$1"
    local id_file="${PROVIDER}/.vagrant/machines/${vm}/vmware_desktop/id"
    [[ -f "${id_file}" ]] || fatal "missing Vagrant id for ${vm}: ${id_file}"
    local vmx
    vmx="$(cat "${id_file}")"
    [[ -f "${vmx}" ]] || fatal "missing VMX for ${vm}: ${vmx}"
    printf '%s\n' "${vmx}"
}

router_cmd() {
    (
        cd "${PROVIDER}"
        GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/router-ssh.sh" "$1"
    )
}

vagrant_ps() {
    local vm="$1"
    local script encoded
    script="$(cat)"
    encoded="$(printf '%s' "${script}" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)"

    (
        cd "${PROVIDER}"
        timeout 240 vagrant winrm "${vm}" -c \
            "powershell.exe -NoProfile -NonInteractive -EncodedCommand ${encoded}"
    ) 2>&1 | tr -d '\r'
}

find_ansible_playbook() {
    local deploy_root
    deploy_root="$(dirname "$(dirname "$(dirname "${PROVIDER}")")")"

    local -a candidates=(
        "$(command -v ansible-playbook 2>/dev/null || true)"
        "${ROOT}/.venv/bin/ansible-playbook"
        "${ROOT}/venv/bin/ansible-playbook"
        "${deploy_root}/.venv/bin/ansible-playbook"
        "${deploy_root}/venv/bin/ansible-playbook"
        "${HOME}/.goad/.venv/bin/ansible-playbook"
        "${HOME}/.local/bin/ansible-playbook"
    )

    local candidate
    for candidate in "${candidates[@]}"; do
        [[ -n "${candidate}" && -x "${candidate}" ]] || continue
        printf '%s\n' "${candidate}"
        return 0
    done

    return 1
}

run_playbook() {
    local playbook="$1"
    local logfile="$2"

    echo "[*] Running ${playbook}"

    (
        cd "${ROOT}/ansible"
        ANSIBLE_CONFIG="${ANSIBLE_CFG}" \
        timeout 3600 "${ANSIBLE_PLAYBOOK}" \
            -i "${INVENTORY_DATA}" \
            -i "${INVENTORY_PROVIDER}" \
            "${playbook}"
    ) 2>&1 | tee "${logfile}"

    if grep -Eq 'failed=[1-9]|unreachable=[1-9]' "${logfile}"; then
        return 1
    fi
}

ansible_ps_north() {
    local host="$1"
    local label="$2"
    local ps_file play_file log_file

    ps_file="${LOG_DIR}/${host}-${label}.ps1"
    play_file="${LOG_DIR}/${host}-${label}.yml"
    log_file="${LOG_DIR}/${host}-${label}.log"

    cat > "${ps_file}"

    python3 - "${host}" "${ps_file}" "${play_file}" <<'PY'
from pathlib import Path
import sys

host = sys.argv[1]
ps = Path(sys.argv[2]).read_text().splitlines()
out = Path(sys.argv[3])
indented = "\n".join("          " + line for line in ps)
out.write_text(
    f"""---
- name: GOAD_NOMAD runtime validation
  hosts: {host}
  gather_facts: false
  tasks:
    - name: Execute validation PowerShell
      ansible.windows.win_powershell:
        script: |
{indented}
      register: validation
    - name: Show validation output
      ansible.builtin.debug:
        var: validation.output
"""
)
PY

    (
        cd "${ROOT}/ansible"
        ANSIBLE_CONFIG="${ANSIBLE_CFG}" \
        timeout 600 "${ANSIBLE_PLAYBOOK}" \
            -i "${INVENTORY_DATA}" \
            -i "${INVENTORY_PROVIDER}" \
            "${play_file}"
    ) 2>&1 | tee "${log_file}"

    ! grep -Eq 'failed=[1-9]|unreachable=[1-9]' "${log_file}"
}

cleanup() {
    local rc=$?
    trap - EXIT INT TERM

    if [[ -n "${PROVIDER}" && -d "${PROVIDER}" && "${FINAL_EXERCISE}" -ne 1 ]]; then
        echo
        echo "[CLEANUP] Returning GOAD_NOMAD to exercise mode..."
        if ! GOAD_PROVIDER_DIR="${PROVIDER}" \
            bash "${ROOT}/scripts/lab-mode.sh" exercise; then
            echo "[CLEANUP] WARNING: normal exercise-mode recovery failed" >&2
            echo "[CLEANUP] Attempting network-isolation recovery..." >&2
            GOAD_PROVIDER_DIR="${PROVIDER}" \
                bash "${ROOT}/scripts/lab-mode.sh" exercise-failsafe || \
                echo "[CLEANUP] WARNING: network-isolation recovery also failed" >&2
        fi
    fi

    # set -e can terminate the validator on an unexpected command error before
    # one of the explicit fatal() paths has a chance to increment FAIL_COUNT.
    # Never print the contradictory FAIL: 0 / [FAILED] combination.
    if [[ "${rc}" -ne 0 && "${FAIL_COUNT}" -eq 0 ]]; then
        FAIL_COUNT=1
        echo "[FAIL] validator aborted on an unexpected command error (rc=${rc}); inspect the last emitted command/log" >&2
    fi

    echo
    echo "============================================================"
    echo "GOAD_NOMAD RUNTIME VALIDATION SUMMARY"
    echo "============================================================"
    echo "PASS: ${PASS_COUNT}"
    echo "WARN: ${WARN_COUNT}"
    echo "FAIL: ${FAIL_COUNT}"
    echo "Logs: ${LOG_DIR}"

    if [[ "${rc}" -eq 0 && "${FAIL_COUNT}" -eq 0 ]]; then
        echo
        echo "[READY] CLEAN-CHECKOUT NETWORK SEGMENTATION RUNTIME VALIDATION PASSED"
        exit 0
    fi

    echo
    echo "[FAILED] NETWORK SEGMENTATION RUNTIME VALIDATION DID NOT PASS"
    exit 1
}

trap cleanup EXIT INT TERM

mkdir -p "${LOG_DIR}"

section "1. PREREQUISITES / CLEAN-CHECKOUT IDENTITY"

case "${RDP_BOT_MODE}" in
    legacy|headless) ;;
    *) fatal "KINGDOMS_RDP_BOT_MODE must be legacy or headless (got: ${RDP_BOT_MODE})" ;;
esac

[[ -n "${PROVIDER}" ]] || fatal "GOAD_PROVIDER_DIR is not set"
[[ -d "${PROVIDER}" ]] || fatal "GOAD_PROVIDER_DIR does not exist: ${PROVIDER}"
[[ -d "${ROOT}/.git" ]] || fatal "run this validator from a Git clone"

for cmd in git bash python3 vmrun vagrant ip nc timeout iconv base64 sudo; do
    require_command "${cmd}"
done

sudo -v

HEAD_SHA="$(git -C "${ROOT}" rev-parse HEAD)"
echo "Source HEAD: ${HEAD_SHA}"
echo "Provider:    ${PROVIDER}"

if [[ -n "$(git -C "${ROOT}" status --porcelain)" ]]; then
    fatal "clean-checkout working tree is not clean"
fi
pass "clean Git working tree"

bash "${ROOT}/scripts/validate-network-segmentation-source.sh" | tee "${LOG_DIR}/source-preflight.log"
pass "source preflight"

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "${ANSIBLE_PLAYBOOK}" ]] || fatal "ansible-playbook not found in PATH or detected GOAD virtualenvs"
echo "Ansible: ${ANSIBLE_PLAYBOOK}"
pass "Ansible runtime located"

section "2. ENTER / VERIFY PROVISIONING MODE"

GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/lab-mode.sh" provisioning | tee "${LOG_DIR}/provisioning-transition.log"
pass "provisioning transition"

GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/lab-mode.sh" status | tee "${LOG_DIR}/provisioning-status.log"
grep -Fq 'Recorded mode: provisioning' "${LOG_DIR}/provisioning-status.log" || fatal "recorded mode is not provisioning"
grep -Fq 'policy accept;' "${LOG_DIR}/provisioning-status.log" || fatal "router is not permissive in provisioning mode"
pass "provisioning state recorded and router policy accept"

ip route show 10.4.20.0/24 | grep -Fq 'via 10.4.10.1' || fatal "SevenKingdoms provisioning route missing"
ip route show 10.4.30.0/24 | grep -Fq 'via 10.4.10.1' || fatal "ESSOS provisioning route missing"
pass "provisioning-only host routes"

section "3. VAGRANT MANAGEMENT / NAT ADDRESS DISCOVERY"

for vm in "${WINDOWS_VMS[@]}"; do
    if ! out="$(vagrant_ps "${vm}" <<'PS'
$ErrorActionPreference = 'Stop'
Write-Output "COMPUTERNAME=$env:COMPUTERNAME"

# Do not key management discovery to a Windows display alias. The Server boxes
# currently expose the provisioning NIC as Ethernet0, while the Windows 10
# workstation exposes that same VMware NAT adapter as "Ethernet0 2". Discover
# it by network identity instead: a usable non-loopback/non-APIPA IPv4 address
# outside the deterministic 10.4.0.0/16 exercise networks.
$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
    Where-Object {
        $_.IPAddress -ne '127.0.0.1' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.IPAddress -notmatch '^10\.4\.'
    } |
    Sort-Object InterfaceIndex |
    Select-Object -First 1 -ExpandProperty IPAddress

if (-not $ip) {
    throw 'Provisioning NAT IPv4 address was not discovered by network identity'
}
Write-Output "NATIP=$ip"
PS
)"; then
        fatal "${vm} Vagrant management query failed during NAT address discovery"
    fi
    printf '%s\n' "${out}" | tee "${LOG_DIR}/${vm}-management.log"

    printf '%s\n' "${out}" | grep -Fq "COMPUTERNAME=${EXPECTED_NAME[$vm]}" || fatal "${vm} Vagrant management returned unexpected computer name"

    nat="$(printf '%s\n' "${out}" | sed -n 's/.*NATIP=\([0-9.]*\).*/\1/p' | tail -n 1)"
    [[ -n "${nat}" ]] || fatal "could not discover NAT IP for ${vm}"
    NAT_IP["${vm}"]="${nat}"

    printf '%-12s %-15s %s\n' "${vm}" "${nat}" "${EXPECTED_NAME[$vm]}"
done
pass "all six Vagrant management paths"

section "4. WS01 CLEAN FOUNDATION CONTRACT"

out="$(vagrant_ps GOAD-WS01 <<'PS'
$ErrorActionPreference = 'Stop'

$computer = Get-CimInstance Win32_ComputerSystem
if (-not $computer.PartOfDomain) { throw 'WS01 is not joined to a domain' }
if ($computer.Domain -ne 'north.sevenkingdoms.local') { throw "unexpected WS01 domain: $($computer.Domain)" }
if (-not (Test-ComputerSecureChannel)) { throw 'WS01 domain secure channel is unhealthy' }

$rdpUsers = @(
    Get-LocalGroupMember -Group 'Remote Desktop Users' |
        ForEach-Object { $_.Name.ToLowerInvariant() }
)
if ($rdpUsers.Count -ne 1 -or $rdpUsers -notcontains 'north\rickon.stark') {
    throw "WS01 RDP group must contain only Rickon: $($rdpUsers -join ',')"
}

$admins = @(
    Get-LocalGroupMember -Group 'Administrators' |
        ForEach-Object { $_.Name.ToLowerInvariant() }
)
if ($admins -contains 'north\rickon.stark') { throw 'Rickon is unexpectedly a local administrator' }

$uac = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System').EnableLUA
if ($uac -ne 1) { throw "UAC EnableLUA=$uac" }

$disabledProfiles = @(Get-NetFirewallProfile | Where-Object { -not $_.Enabled })
if ($disabledProfiles.Count -ne 0) {
    throw "disabled firewall profiles: $($disabledProfiles.Name -join ',')"
}

$defender = Get-MpComputerStatus
if (-not $defender.AntivirusEnabled) { throw 'Microsoft Defender antivirus is disabled' }
if (-not $defender.RealTimeProtectionEnabled) { throw 'Microsoft Defender real-time protection is disabled' }

Write-Output 'WS01_DOMAIN=PASS'
Write-Output 'WS01_RICKON_RDP=PASS'
Write-Output 'WS01_RICKON_LOW_PRIV=PASS'
Write-Output 'WS01_UAC=PASS'
Write-Output 'WS01_FIREWALL=PASS'
Write-Output 'WS01_DEFENDER=PASS'
PS
)"
printf '%s\n' "${out}" | tee "${LOG_DIR}/ws01-foundation.log"
for check in \
    WS01_DOMAIN \
    WS01_RICKON_RDP \
    WS01_RICKON_LOW_PRIV \
    WS01_UAC \
    WS01_FIREWALL \
    WS01_DEFENDER
do
    printf '%s\n' "${out}" | grep -Fq "${check}=PASS" || fatal "${check} validation failed"
done
pass "WS01 domain, foothold, low-privilege and native security baseline"

section "5. REPLAY COMMITTED CHILD-DOMAIN / DNS SOURCE"

run_playbook ad-child_domain.yml "${LOG_DIR}/ad-child-domain-pass1.log" || fatal "first ad-child_domain.yml replay failed"
pass "child-domain/DNS source replay #1"

run_playbook ad-child_domain.yml "${LOG_DIR}/ad-child-domain-pass2.log" || fatal "second ad-child_domain.yml replay failed"

child_status="$(awk '
/TASK \[child_domain : add child domain to parent domain\]/{seen=1; next}
seen && /^(ok|changed|fatal): \[dc02\]/{print; exit}
' "${LOG_DIR}/ad-child-domain-pass2.log")"

echo "Second-run child-domain task: ${child_status:-not-found}"
[[ "${child_status}" == ok:* ]] || fatal "child-domain promotion task was not idempotent on second run"
pass "child-domain promotion idempotency"

run_playbook ad-trusts.yml "${LOG_DIR}/ad-trusts.log" || fatal "ad-trusts.yml replay failed"
pass "trust/DNS source replay"

section "6. POST-REPLAY DNS STATE"

out="$(vagrant_ps GOAD-DC02 <<'PS'
$ErrorActionPreference = 'Stop'

if ((Get-WindowsFeature DNS).InstallState -ne 'Installed') { throw 'DNS Server role is not installed' }

$binding = Get-NetAdapterBinding -Name 'Ethernet0' -ComponentID ms_tcpip6
if ($binding.Enabled) { throw 'IPv6 is still enabled on Ethernet0 provisioning NIC' }

$zone = Get-DnsServerZone -Name 'north.sevenkingdoms.local'
if (-not $zone.IsDsIntegrated) { throw 'north.sevenkingdoms.local is not AD integrated' }

# Conditional forwarders are exposed by Get-DnsServerZone with
# ZoneType=Forwarder. Validate the forwarding relationship itself rather than
# assuming a particular AD-integration/replication scope.
$parent = Get-DnsServerZone -Name 'sevenkingdoms.local' -ErrorAction Stop
if ($parent.ZoneType.ToString() -ne 'Forwarder') { throw "sevenkingdoms.local is not a forwarder: $($parent.ZoneType)" }
$parentMasters = @($parent.MasterServers | ForEach-Object { $_.ToString() })
if ($parentMasters -notcontains '10.4.20.10') { throw "parent forwarder incorrect: $($parentMasters -join ',')" }

$essos = Get-DnsServerZone -Name 'essos.local' -ErrorAction Stop
if ($essos.ZoneType.ToString() -ne 'Forwarder') { throw "essos.local is not a forwarder: $($essos.ZoneType)" }
$essosMasters = @($essos.MasterServers | ForEach-Object { $_.ToString() })
if ($essosMasters -notcontains '10.4.30.12') { throw "ESSOS forwarder incorrect: $($essosMasters -join ',')" }

$a = @(Resolve-DnsName winterfell.north.sevenkingdoms.local -Type A -Server 10.4.10.11 -DnsOnly |
    Where-Object Type -eq 'A' |
    Select-Object -ExpandProperty IPAddress -Unique)
if ($a.Count -ne 1 -or $a[0] -ne '10.4.10.11') { throw "Winterfell authoritative A records incorrect: $($a -join ',')" }

Write-Output 'WINTERFELL_DNS=PASS'
Write-Output "PARENT_FORWARDER=$($parentMasters -join ',')"
Write-Output "ESSOS_FORWARDER=$($essosMasters -join ',')"
PS
)"
printf '%s\n' "${out}" | tee "${LOG_DIR}/winterfell-dns.log"
printf '%s\n' "${out}" | grep -Fq 'WINTERFELL_DNS=PASS' || fatal "Winterfell DNS validation failed"
pass "Winterfell DNS hardening / forwarders"

out="$(vagrant_ps GOAD-DC01 <<'PS'
$ErrorActionPreference = 'Stop'
$essos = Get-DnsServerZone -Name 'essos.local' -ErrorAction Stop
if ($essos.ZoneType.ToString() -ne 'Forwarder') { throw "essos.local is not a forwarder on Kingslanding: $($essos.ZoneType)" }
$masters = @($essos.MasterServers | ForEach-Object { $_.ToString() })
if ($masters -notcontains '10.4.30.12') { throw "Kingslanding ESSOS forwarder incorrect: $($masters -join ',')" }
Write-Output 'KINGSLANDING_ESSOS_FORWARDER=PASS'
PS
)"
printf '%s\n' "${out}" | tee "${LOG_DIR}/kingslanding-forwarder.log"
printf '%s\n' "${out}" | grep -Fq 'KINGSLANDING_ESSOS_FORWARDER=PASS' || fatal "Kingslanding ESSOS forwarder validation failed"
pass "forest-replicated ESSOS forwarder"

section "7. TRUST / BOT / LINKED-SQL HEALTH IN PROVISIONING MODE"

out="$(vagrant_ps GOAD-DC02 <<'PS'
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
$dc = nltest /dsgetdc:sevenkingdoms.local /force | Out-String
if ($dc -notmatch '10\.4\.20\.10') { throw 'Kingslanding discovery failed' }
$t = Get-ADTrust -Identity sevenkingdoms.local
if ($t.Direction.ToString() -ne 'BiDirectional') { throw "parent/child trust direction: $($t.Direction)" }
Write-Output 'PARENT_CHILD_TRUST=PASS'
PS
)"
printf '%s\n' "${out}" | tee "${LOG_DIR}/parent-child-trust.log"
printf '%s\n' "${out}" | grep -Fq 'PARENT_CHILD_TRUST=PASS' || fatal "parent/child trust validation failed"
pass "parent/child trust"

out="$(vagrant_ps GOAD-DC01 <<'PS'
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
$dc = nltest /dsgetdc:essos.local /force | Out-String
if ($dc -notmatch '10\.4\.30\.12') { throw 'Meereen discovery failed' }
$t = Get-ADTrust -Identity essos.local
if ($t.Direction.ToString() -ne 'BiDirectional') { throw "forest trust direction: $($t.Direction)" }
Write-Output 'FOREST_TRUST=PASS'
PS
)"
printf '%s\n' "${out}" | tee "${LOG_DIR}/forest-trust.log"
printf '%s\n' "${out}" | grep -Fq 'FOREST_TRUST=PASS' || fatal "forest trust validation failed"
pass "SevenKingdoms/ESSOS forest trust"

# ntlm_bot and responder_bot remain traffic-generator health requirements in
# every runtime mode. connect_bot is validated by the RDP contract below
# because its expected state differs between legacy and headless.
#
# A Scheduled Task sampled while it is executing can report State=Running and
# LastTaskResult=0x00041301 (SCHED_S_TASK_RUNNING). That value is scheduler
# state, not a completed task failure. Wait for each short-lived bot to settle,
# then require the completed Ready/0 contract. Always persist probe output so a
# real task or WinRM failure remains diagnosable.
if ! out="$(vagrant_ps GOAD-DC02 <<'PS'
$ErrorActionPreference = 'Stop'

foreach ($name in 'ntlm_bot','responder_bot') {
    try {
        $deadline = (Get-Date).AddSeconds(30)

        while ($true) {
            $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
            $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction Stop
            $state = $task.State.ToString()
            $last = [int64]$info.LastTaskResult
            $lastHex = '0x{0:X8}' -f ([uint32]$info.LastTaskResult)

            Write-Output (
                "BOT_SAMPLE|NAME=$name|STATE=$state|LAST=$last|LAST_HEX=$lastHex" +
                "|LAST_RUN=$($info.LastRunTime.ToString('o'))" +
                "|NEXT_RUN=$($info.NextRunTime.ToString('o'))"
            )

            if ($state -eq 'Running') {
                if ((Get-Date) -ge $deadline) {
                    Write-Output "$name=FAIL|STATE=$state|LAST=$last|REASON=did-not-settle"
                    break
                }

                Start-Sleep -Seconds 2
                continue
            }

            if ($state -ne 'Ready') {
                Write-Output "$name=FAIL|STATE=$state|LAST=$last|REASON=unexpected-state"
                break
            }

            if ($last -ne 0) {
                Write-Output "$name=FAIL|STATE=$state|LAST=$last|REASON=completed-result"
                break
            }

            Write-Output "$name=PASS|STATE=Ready|LAST=0"
            break
        }
    }
    catch {
        Write-Output "$name=FAIL|REASON=query-error|ERROR=$($_.Exception.Message)"
    }
}
PS
)"; then
    printf '%s\n' "${out}" | tee "${LOG_DIR}/bots.log"
    fatal "WINTERFELL traffic-generator bot query failed"
fi

printf '%s\n' "${out}" | tee "${LOG_DIR}/bots.log"
for bot in ntlm_bot responder_bot; do
    printf '%s\n' "${out}" | grep -Fq "${bot}=PASS|STATE=Ready|LAST=0" ||
        fatal "${bot} validation failed; inspect ${LOG_DIR}/bots.log"
done
pass "GOAD traffic-generator bot health"

# Preserve the complete NORTH RDP policy contract. connect_bot has two explicit
# accepted runtime contracts: legacy requires Ready/Running; headless requires
# Disabled while preserving the Robb run-as SID for rollback integrity.
bash "${ROOT}/scripts/validate-rdp-runtime.sh" --bot-mode "${RDP_BOT_MODE}" ||
    fatal "NORTH RDP/connect_bot contract failed in ${RDP_BOT_MODE} mode"
pass "NORTH RDP/connect_bot ${RDP_BOT_MODE} contract"

out="$(vagrant_ps GOAD-SRV02 <<'PS'
$ErrorActionPreference = 'Stop'
$cs = 'Server=127.0.0.1,1433;User ID=sa;Password=Sup1_sa_P@ssw0rd!;Encrypt=False;TrustServerCertificate=True'
$conn = New-Object System.Data.SqlClient.SqlConnection $cs
try {
    $conn.Open()
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = @"
EXECUTE AS LOGIN = N'NORTH\jon.snow';
EXEC ('SELECT @@SERVERNAME AS RemoteServer, SUSER_SNAME() AS RemoteLogin') AT [BRAAVOS];
REVERT;
"@
    $ds = New-Object System.Data.DataSet
    $da = New-Object System.Data.SqlClient.SqlDataAdapter $cmd
    [void]$da.Fill($ds)
    $row = $ds.Tables[0].Rows[0]
    if ($row.RemoteServer -ne 'BRAAVOS\SQLEXPRESS' -or $row.RemoteLogin -ne 'sa') { throw "unexpected linked result: $($row.RemoteServer) / $($row.RemoteLogin)" }
    Write-Output 'CASTELBLACK_TO_BRAAVOS=PASS'
} finally { $conn.Close() }
PS
)"
printf '%s\n' "${out}" | tee "${LOG_DIR}/sql-castelblack-braavos.log"
printf '%s\n' "${out}" | grep -Fq 'CASTELBLACK_TO_BRAAVOS=PASS' || fatal "Castelblack -> Braavos linked SQL failed"
pass "Castelblack -> Braavos linked SQL"

out="$(vagrant_ps GOAD-SRV03 <<'PS'
$ErrorActionPreference = 'Stop'
$cs = 'Server=127.0.0.1,1433;User ID=sa;Password=sa_P@ssw0rd!Ess0s;Encrypt=False;TrustServerCertificate=True'
$conn = New-Object System.Data.SqlClient.SqlConnection $cs
try {
    $conn.Open()
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = @"
EXECUTE AS LOGIN = N'ESSOS\khal.drogo';
EXEC ('SELECT @@SERVERNAME AS RemoteServer, SUSER_SNAME() AS RemoteLogin') AT [CASTELBLACK];
REVERT;
"@
    $ds = New-Object System.Data.DataSet
    $da = New-Object System.Data.SqlClient.SqlDataAdapter $cmd
    [void]$da.Fill($ds)
    $row = $ds.Tables[0].Rows[0]
    if ($row.RemoteServer -ne 'CASTELBLACK\SQLEXPRESS' -or $row.RemoteLogin -ne 'sa') { throw "unexpected linked result: $($row.RemoteServer) / $($row.RemoteLogin)" }
    Write-Output 'BRAAVOS_TO_CASTELBLACK=PASS'
} finally { $conn.Close() }
PS
)"
printf '%s\n' "${out}" | tee "${LOG_DIR}/sql-braavos-castelblack.log"
printf '%s\n' "${out}" | grep -Fq 'BRAAVOS_TO_CASTELBLACK=PASS' || fatal "Braavos -> Castelblack linked SQL failed"
pass "Braavos -> Castelblack linked SQL"

section "8. RETURN TO EXERCISE MODE"

GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/lab-mode.sh" exercise | tee "${LOG_DIR}/exercise-transition.log"
FINAL_EXERCISE=1
pass "exercise transition"

GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/lab-mode.sh" status | tee "${LOG_DIR}/exercise-status.log"
grep -Fq 'Recorded mode: exercise' "${LOG_DIR}/exercise-status.log" || fatal "recorded mode is not exercise"
grep -Fq 'policy drop;' "${LOG_DIR}/exercise-status.log" || fatal "router is not deny-by-default"
pass "exercise mode / deny-by-default router"

section "9. FINAL PERSISTENT NAT ISOLATION"

for vm in "${WINDOWS_VMS[@]}"; do
    vmx="$(vmx_for "${vm}")"
    grep -Eiq '^ethernet0\.startConnected[[:space:]]*=[[:space:]]*"FALSE"' "${vmx}" || fatal "${vm} startConnected is not FALSE"

    ip="${NAT_IP[$vm]}"
    printf '%-12s %-15s ' "${vm}" "${ip}"
    if timeout 3 nc -zw2 "${ip}" 5985 2>/dev/null; then
        fatal "${vm} NAT WinRM remains reachable in exercise mode"
    fi
    echo '[PASS] isolated'
done
pass "all six Windows NAT paths persistently isolated"

[[ -z "$(ip route show 10.4.20.0/24)" ]] || fatal "SevenKingdoms provisioning route remains in exercise mode"
[[ -z "$(ip route show 10.4.30.0/24)" ]] || fatal "ESSOS provisioning route remains in exercise mode"
pass "protected-zone host routes removed"

section "10. STUDENT-SIDE NETWORK BOUNDARY"

# lab-mode exercise may stop/start Windows guests when persisting the NAT NIC
# as disconnected. VMware reporting power=running only means the VM process is
# running; it does not guarantee that Windows networking/services are ready.
# Wait on the actual NORTH-side services required by the exercise instead of
# racing guest boot or depending on Windows ICMP firewall behavior.
wait_north_service() {
    local label="$1"
    local host="$2"
    local port="$3"
    local timeout_s="${4:-300}"
    local start now elapsed next_notice

    start="$(date +%s)"
    next_notice=30

    while true; do
        if timeout 3 nc -zw2 "$host" "$port" >/dev/null 2>&1; then
            now="$(date +%s)"
            elapsed=$((now - start))
            echo "[READY] ${label} (${host}:${port}) after ${elapsed}s"
            return 0
        fi

        now="$(date +%s)"
        elapsed=$((now - start))

        if (( elapsed >= timeout_s )); then
            echo "[TIMEOUT] ${label} (${host}:${port}) not ready after ${elapsed}s" >&2
            return 1
        fi

        if (( elapsed >= next_notice )); then
            echo "[WAIT] ${label} (${host}:${port}) still starting after ${elapsed}s"
            next_notice=$((next_notice + 30))
        fi

        sleep 5
    done
}

wait_north_service "Winterfell SMB"   10.4.10.11 445  300 || fatal "Winterfell SMB did not recover after exercise transition"
wait_north_service "Castelblack SMB"  10.4.10.22 445  300 || fatal "Castelblack SMB did not recover after exercise transition"
wait_north_service "WS01 RDP"         10.4.10.31 3389 300 || fatal "WS01 RDP did not recover after exercise transition"

# The next section executes Ansible directly over the isolated NORTH network,
# so also wait for WinRM rather than allowing another post-reboot race.
wait_north_service "Winterfell WinRM"  10.4.10.11 5986 300 || fatal "Winterfell WinRM did not recover after exercise transition"

# WinRM can become available before the domain controller is operational.
# The ActiveDirectory PowerShell provider requires Active Directory Web
# Services, so wait for ADWS TCP/9389 before executing the exercise trust gate.
wait_north_service "Winterfell ADWS"   10.4.10.11 9389 300 || fatal "Winterfell ADWS did not recover after exercise transition"

wait_north_service "Castelblack WinRM" 10.4.10.22 5986 300 || fatal "Castelblack WinRM did not recover after exercise transition"
wait_north_service "WS01 WinRM"        10.4.10.31 5986 300 || fatal "WS01 WinRM did not recover after exercise transition"

pass "NORTH services stabilized and remain directly reachable"

if timeout 3 nc -zw2 10.4.20.10 445 2>/dev/null; then
    fatal "SevenKingdoms is directly reachable from student/host side"
fi
if timeout 3 nc -zw2 10.4.30.12 445 2>/dev/null; then
    fatal "ESSOS is directly reachable from student/host side"
fi
pass "direct SevenKingdoms / ESSOS access blocked"

section "11. EXERCISE-PATH DNS / TRUST / SQL FROM NORTH"

ansible_ps_north dc02 exercise-dns-trust <<'PS'
$ErrorActionPreference = 'Stop'

# Importing the ActiveDirectory module normally creates an implicit AD: drive.
# That provider initialization performs its own default-server discovery and
# can fail during post-boot convergence even after TCP/9389 starts listening.
# This validator never uses AD:, so suppress that side effect and probe the
# exact directory server and trust cmdlet path that section 11 requires.
$Env:ADPS_LoadDefaultDrive = '0'
Import-Module ActiveDirectory -ErrorAction Stop

Clear-DnsClientCache
try { Clear-DnsServerCache -Force -ErrorAction Stop } catch { }

$localDc = 'winterfell.north.sevenkingdoms.local'
$deadline = (Get-Date).AddMinutes(5)
$lastAdError = 'no functional Active Directory probe completed'
$t = $null

while ((Get-Date) -lt $deadline) {
    try {
        $rootDse = Get-ADRootDSE -Server $localDc -ErrorAction Stop
        if ($rootDse.defaultNamingContext -ne 'DC=north,DC=sevenkingdoms,DC=local') {
            throw "unexpected Winterfell naming context: $($rootDse.defaultNamingContext)"
        }

        $t = Get-ADTrust -Identity 'sevenkingdoms.local' -Server $localDc -ErrorAction Stop
        if ($t.Direction.ToString() -ne 'BiDirectional') {
            throw "parent/child trust direction: $($t.Direction)"
        }

        $lastAdError = $null
        break
    } catch {
        $lastAdError = $_.Exception.Message
        Start-Sleep -Seconds 5
    }
}

if ($null -ne $lastAdError) {
    throw "Winterfell AD cmdlets were not functional within 300 seconds: $lastAdError"
}

$parent = nltest /dsgetdc:sevenkingdoms.local /force | Out-String
if ($parent -notmatch '10\.4\.20\.10') { throw 'parent DC discovery failed in exercise mode' }

$essos = Resolve-DnsName '_ldap._tcp.dc._msdcs.essos.local' -Type SRV -ErrorAction Stop
if (($essos | Where-Object NameTarget -match '^meereen\.essos\.local\.?$').Count -lt 1) { throw 'ESSOS SRV resolution did not return Meereen' }

Write-Output 'EXERCISE_AD_FUNCTIONAL_READY=PASS'
Write-Output 'EXERCISE_PARENT_CHILD=PASS'
Write-Output 'EXERCISE_ESSOS_DNS=PASS'
PS
pass "exercise-mode parent/child trust + cross-forest DNS from Winterfell"

ansible_ps_north srv02 exercise-linked-sql <<'PS'
$ErrorActionPreference = 'Stop'
$cs = 'Server=127.0.0.1,1433;User ID=sa;Password=Sup1_sa_P@ssw0rd!;Encrypt=False;TrustServerCertificate=True'
$conn = New-Object System.Data.SqlClient.SqlConnection $cs
try {
    $conn.Open()
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = @"
EXECUTE AS LOGIN = N'NORTH\jon.snow';
EXEC ('SELECT @@SERVERNAME AS RemoteServer, SUSER_SNAME() AS RemoteLogin') AT [BRAAVOS];
REVERT;
"@
    $ds = New-Object System.Data.DataSet
    $da = New-Object System.Data.SqlClient.SqlDataAdapter $cmd
    [void]$da.Fill($ds)
    $row = $ds.Tables[0].Rows[0]
    if ($row.RemoteServer -ne 'BRAAVOS\SQLEXPRESS' -or $row.RemoteLogin -ne 'sa') { throw 'exercise linked SQL result incorrect' }
    Write-Output 'EXERCISE_CASTELBLACK_TO_BRAAVOS=PASS'
} finally { $conn.Close() }
PS
pass "exercise-mode Castelblack -> Braavos linked SQL"

section "12. FINAL FIREWALL EVIDENCE"

router_cmd 'sudo nft list chain inet goad_nomad forward' | tee "${LOG_DIR}/final-firewall.log"

packets_for_rule() {
    local pattern="$1"
    grep -F "${pattern}" "${LOG_DIR}/final-firewall.log" |
        sed -n 's/.*counter packets \([0-9][0-9]*\).*/\1/p' |
        head -n 1
}

p_parent="$(packets_for_rule 'ip saddr 10.4.10.11 ip daddr 10.4.20.10')"
p_dns="$(packets_for_rule 'ip saddr 10.4.10.11 ip daddr 10.4.30.12 udp dport 53')"
p_sql="$(packets_for_rule 'ip saddr 10.4.10.22 ip daddr 10.4.30.23 tcp dport 1433')"

[[ "${p_parent:-0}" -gt 0 ]] || fatal "parent/child firewall rule did not record traffic"
[[ "${p_dns:-0}" -gt 0 ]] || fatal "Winterfell -> Meereen DNS firewall rule did not record traffic"
[[ "${p_sql:-0}" -gt 0 ]] || fatal "Castelblack -> Braavos SQL firewall rule did not record traffic"
pass "required exercise firewall paths recorded traffic"

section "13. FINAL STATE"

GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/lab-mode.sh" status | tee "${LOG_DIR}/final-status.log"
grep -Fq 'Recorded mode: exercise' "${LOG_DIR}/final-status.log" || fatal "final mode is not exercise"
grep -Fq 'policy drop;' "${LOG_DIR}/final-status.log" || fatal "final router policy is not drop"
pass "lab left in final exercise state"

exit 0