#!/usr/bin/env bash
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Native Kingdoms profile. GOAD remains the reference default.
readonly KINGDOMS_VMWARE_LAB="${KINGDOMS_VMWARE_LAB:-GOAD}"
case "${KINGDOMS_VMWARE_LAB}" in
    GOAD)
        readonly ROUTES="${ROOT}/scripts/provisioning-routes.sh"
        readonly POLICY_DIR="${ROOT}/ad/GOAD/providers/vmware/router/nftables"
        readonly ROUTER_SSH="${ROOT}/scripts/router-ssh.sh"
        readonly NFTABLES_FORWARD_TABLE="goad_nomad"
        ;;
    NORTH)
        readonly ROUTES="${ROOT}/scripts/course1/provisioning-routes.sh"
        readonly POLICY_DIR="${ROOT}/ad/NORTH/providers/vmware/router/nftables"
        readonly ROUTER_SSH="${ROOT}/scripts/course1/router-ssh.sh"
        readonly NFTABLES_FORWARD_TABLE="kingdoms_north"
        ;;
    *)
        echo "[FAIL] Unsupported Kingdoms VMware profile: ${KINGDOMS_VMWARE_LAB}" >&2
        exit 1
        ;;
esac

readonly AD_READINESS_TIMEOUT_SECONDS=300
readonly AD_READINESS_PROBE_TIMEOUT_SECONDS=15
readonly AD_READINESS_RETRY_DELAY_SECONDS=5
readonly AD_REPAIR_TIMEOUT_SECONDS=90

# Keep the same patched Kingdoms AD/NT5DS readiness and isolation controller;
# only the selected instance's guest roster and network helper paths change.
if [[ "${KINGDOMS_VMWARE_LAB}" == "NORTH" ]]; then
    readonly DOMAIN_CONTROLLERS=( GOAD-DC01 GOAD-DC02 )
    readonly EXERCISE_DOMAIN_CONTROLLERS=( GOAD-DC02 GOAD-DC01 )
    readonly DOMAIN_MEMBERS=( GOAD-SRV02 GOAD-WS01 )
    readonly WINDOWS_VMS=( GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01 )
    declare -A DC_DOMAIN=(
        [GOAD-DC01]="sevenkingdoms.local"
        [GOAD-DC02]="north.sevenkingdoms.local"
    )
    declare -A DC_FQDN=(
        [GOAD-DC01]="kingslanding.sevenkingdoms.local"
        [GOAD-DC02]="winterfell.north.sevenkingdoms.local"
    )
    declare -A DC_TIME_PARENT_DOMAIN=( [GOAD-DC02]="sevenkingdoms.local" )
    declare -A DC_TIME_PARENT_SERVER=( [GOAD-DC02]="kingslanding.sevenkingdoms.local" )
    declare -A MEMBER_DOMAIN=(
        [GOAD-SRV02]="north.sevenkingdoms.local"
        [GOAD-WS01]="north.sevenkingdoms.local"
    )
    declare -A MEMBER_DC=(
        [GOAD-SRV02]="winterfell.north.sevenkingdoms.local"
        [GOAD-WS01]="winterfell.north.sevenkingdoms.local"
    )
    declare -A MEMBER_NETBIOS=(
        [GOAD-SRV02]="NORTH"
        [GOAD-WS01]="NORTH"
    )
else
    readonly DOMAIN_CONTROLLERS=(
        GOAD-DC01
        GOAD-DC02
        GOAD-DC03
    )

    # When entering exercise mode, restart the child DC before its parent so
    # WINTERFELL can initialize while KINGSLANDING is still fully online.
    readonly EXERCISE_DOMAIN_CONTROLLERS=(
        GOAD-DC02
        GOAD-DC03
        GOAD-DC01
    )

    readonly DOMAIN_MEMBERS=(
        GOAD-SRV02
        GOAD-SRV03
        GOAD-WS01
    )

    # Keep the canonical six-machine list explicit. Several source/runtime
    # validators consume this as a compatibility contract, while the grouped arrays
    # above control AD-aware transition ordering.
    readonly WINDOWS_VMS=(
        GOAD-DC01
        GOAD-DC02
        GOAD-DC03
        GOAD-SRV02
        GOAD-SRV03
        GOAD-WS01
    )

    declare -A DC_DOMAIN=(
        [GOAD-DC01]="sevenkingdoms.local"
        [GOAD-DC02]="north.sevenkingdoms.local"
        [GOAD-DC03]="essos.local"
    )

    declare -A DC_FQDN=(
        [GOAD-DC01]="kingslanding.sevenkingdoms.local"
        [GOAD-DC02]="winterfell.north.sevenkingdoms.local"
        [GOAD-DC03]="meereen.essos.local"
    )

    # Child-domain PDC emulators must follow the AD forest time hierarchy. NORTH's
    # PDC (WINTERFELL) therefore synchronizes from the forest-root PDC
    # (KINGSLANDING). Forest-root PDCs are intentionally not listed here.
    declare -A DC_TIME_PARENT_DOMAIN=(
        [GOAD-DC02]="sevenkingdoms.local"
    )

    declare -A DC_TIME_PARENT_SERVER=(
        [GOAD-DC02]="kingslanding.sevenkingdoms.local"
    )

    declare -A MEMBER_DOMAIN=(
        [GOAD-SRV02]="north.sevenkingdoms.local"
        [GOAD-SRV03]="essos.local"
        [GOAD-WS01]="north.sevenkingdoms.local"
    )

    declare -A MEMBER_DC=(
        [GOAD-SRV02]="winterfell.north.sevenkingdoms.local"
        [GOAD-SRV03]="meereen.essos.local"
        [GOAD-WS01]="winterfell.north.sevenkingdoms.local"
    )

    declare -A MEMBER_NETBIOS=(
        [GOAD-SRV02]="NORTH"
        [GOAD-SRV03]="ESSOS"
        [GOAD-WS01]="NORTH"
    )

fi

fail() {
    echo "[!] $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 ||
        fail "Required command not found: $1"
}

resolve_provider() {
    if [[ -n "${GOAD_PROVIDER_DIR:-}" ]]; then
        [[ -d "${GOAD_PROVIDER_DIR}" ]] ||
            fail "GOAD_PROVIDER_DIR does not exist: ${GOAD_PROVIDER_DIR}"

        PROVIDER="${GOAD_PROVIDER_DIR}"
        return
    fi

    local -a ids=()

    mapfile -t ids < <(
        find "${ROOT}/workspace" \
            -type f \
            -path '*/provider/.vagrant/machines/GOAD-ROUTER/vmware_desktop/id' \
            -print 2>/dev/null
    )

    if [[ ${#ids[@]} -eq 0 ]]; then
        fail "No deployed GOAD-ROUTER Vagrant instance found."
    fi

    if [[ ${#ids[@]} -gt 1 ]]; then
        echo "[!] Multiple deployed provider instances found:" >&2
        printf '    %s\n' "${ids[@]}" >&2
        echo >&2
        echo "Set GOAD_PROVIDER_DIR explicitly." >&2
        exit 1
    fi

    PROVIDER="${ids[0]%%/.vagrant/*}"
}

vmx_for() {
    local vm="$1"
    local id_file="${PROVIDER}/.vagrant/machines/${vm}/vmware_desktop/id"

    [[ -f "${id_file}" ]] ||
        fail "Missing Vagrant VM id file for ${vm}"

    local vmx
    vmx="$(cat "${id_file}")"

    [[ -f "${vmx}" ]] ||
        fail "VMX does not exist for ${vm}: ${vmx}"

    printf '%s\n' "${vmx}"
}

is_running() {
    local vmx="$1"

    vmrun -T ws list 2>/dev/null |
        tail -n +2 |
        grep -Fxq "${vmx}"
}

wait_stopped() {
    local vmx="$1"

    for _ in {1..90}; do
        if ! is_running "${vmx}"; then
            return 0
        fi

        sleep 2
    done

    return 1
}

wait_started() {
    local vmx="$1"

    for _ in {1..60}; do
        if is_running "${vmx}"; then
            return 0
        fi

        sleep 2
    done

    return 1
}

get_start_connected() {
    local vmx="$1"
    local line

    line="$(
        grep -Ei \
            '^ethernet0\.startConnected[[:space:]]*=' \
            "${vmx}" |
            tail -n 1 || true
    )"

    if [[ -z "${line}" ]]; then
        echo "UNSET"
        return
    fi

    printf '%s\n' "${line}" |
        sed -E 's/.*"([^"]+)".*/\1/' |
        tr '[:lower:]' '[:upper:]'
}

set_start_connected() {
    local vmx="$1"
    local desired="$2"

    python3 - "${vmx}" "${desired}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
desired = sys.argv[2].upper()

if desired not in {"TRUE", "FALSE"}:
    raise SystemExit(f"Invalid startConnected value: {desired}")

text = path.read_text()

pattern = r'(?im)^\s*ethernet0\.startConnected\s*=.*$'
replacement = f'ethernet0.startConnected = "{desired}"'

if re.search(pattern, text):
    text = re.sub(pattern, replacement, text)
else:
    if not text.endswith("\n"):
        text += "\n"

    text += replacement + "\n"

path.write_text(text)
PY
}

verify_windows_layout() {
    local vm vmx

    for vm in "${WINDOWS_VMS[@]}"; do
        vmx="$(vmx_for "${vm}")"

        grep -Eiq \
            '^ethernet0\.connectiontype = "nat"' \
            "${vmx}" ||
            fail "${vm}: ethernet0 is not VMware NAT; refusing to continue."

        grep -Eiq \
            '^ethernet1\.connectiontype = "custom"' \
            "${vmx}" ||
            fail "${vm}: ethernet1 is not a custom exercise adapter."
    done
}

apply_router_policy() {
    local mode="$1"
    local policy="${POLICY_DIR}/${mode}.nft"

    [[ -f "${policy}" ]] ||
        fail "Missing router policy: ${policy}"

    echo "[*] Applying router ${mode} policy"

    (
        cd "${PROVIDER}"

        cat "${policy}" |
            GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROUTER_SSH}" '
                set -e

                cat > /tmp/goad-nomad-mode.nft

                sudo nft -c \
                    -f /tmp/goad-nomad-mode.nft

                sudo install \
                    -m 0644 \
                    /tmp/goad-nomad-mode.nft \
                    /etc/nftables.conf

                sudo systemctl restart nftables
            '
    )

    echo "[+] Router ${mode} policy active and persistent"
}

ensure_vm_nat_state() {
    local vm="$1"
    local desired="$2"
    local action="$3"

    local vmx
    local current
    local was_running=0

    vmx="$(vmx_for "${vm}")"
    current="$(get_start_connected "${vmx}")"

    printf '    %-12s persistent=%-5s -> %-5s ' \
        "${vm}" \
        "${current}" \
        "${desired}"

    if [[ "${current}" != "${desired}" ]]; then
        if is_running "${vmx}"; then
            was_running=1

            echo
            echo "        [*] stopping VM to update persistent NIC state"

            vmrun -T ws stop "${vmx}" soft >/dev/null

            wait_stopped "${vmx}" ||
                fail "${vm} did not stop cleanly."
        fi

        set_start_connected "${vmx}" "${desired}"

        current="$(get_start_connected "${vmx}")"

        [[ "${current}" == "${desired}" ]] ||
            fail "${vm}: failed to persist ethernet0.startConnected=${desired}"

        if [[ "${was_running}" -eq 1 ]]; then
            echo "        [*] starting VM"

            vmrun -T ws start "${vmx}" nogui >/dev/null

            wait_started "${vmx}" ||
                fail "${vm} did not start."

            sleep 2
        fi
    else
        echo
    fi

    if is_running "${vmx}"; then
        case "${action}" in
            connect)
                vmrun -T ws \
                    connectNamedDevice \
                    "${vmx}" \
                    ethernet0 >/dev/null 2>&1 || true
                ;;

            disconnect)
                vmrun -T ws \
                    disconnectNamedDevice \
                    "${vmx}" \
                    ethernet0 >/dev/null 2>&1 || true
                ;;

            *)
                fail "Unknown VMware device action: ${action}"
                ;;
        esac
    fi

    printf '        [+] ethernet0 startConnected=%s, runtime=%s\n' \
        "${desired}" \
        "${action}"
}

vagrant_powershell_ready() {
    local vm="$1"
    local script="$2"
    local timeout_seconds="$3"
    local encoded

    (( timeout_seconds > 0 )) || return 124

    encoded="$(
        printf '%s' "${script}" |
            iconv -f UTF-8 -t UTF-16LE |
            base64 -w0
    )"

    (
        cd "${PROVIDER}"
        timeout "${timeout_seconds}" vagrant winrm "${vm}" -c \
            "powershell.exe -NoProfile -NonInteractive -EncodedCommand ${encoded}"
    ) >/dev/null 2>&1
}

vagrant_powershell_capture() {
    local vm="$1"
    local script="$2"
    local timeout_seconds="$3"
    local encoded

    (( timeout_seconds > 0 )) || return 124

    encoded="$(
        printf '%s' "${script}" |
            iconv -f UTF-8 -t UTF-16LE |
            base64 -w0
    )"

    (
        cd "${PROVIDER}"
        timeout "${timeout_seconds}" vagrant winrm "${vm}" -c \
            "powershell.exe -NoProfile -NonInteractive -EncodedCommand ${encoded}"
    ) 2>&1
}

ensure_child_dc_time_ready() {
    local vm="$1"
    local domain="${DC_DOMAIN[${vm}]}"
    local parent_domain="${DC_TIME_PARENT_DOMAIN[${vm}]:-}"
    local parent_server="${DC_TIME_PARENT_SERVER[${vm}]:-}"
    local probe_script
    local repair_script
    local output=""
    local marker=""
    local last_state="reason=transport"
    local consecutive_source_failures=0
    local repair_attempted=0
    [[ -n "${parent_domain}" && -n "${parent_server}" ]] || return 0

    probe_script="$(cat <<POWERSHELL
\$ErrorActionPreference = 'Continue'

\$source = (& w32tm.exe /query /source 2>\$null | Out-String).Trim().TrimEnd('.')
\$sourceRc = \$LASTEXITCODE
if (\$sourceRc -ne 0 -or -not \$source -or \$source -ine '${parent_server}') {
    \$sourceSafe = ((\$source -replace '[|\r\n]', ' ').Trim())
    if (-not \$sourceSafe) { \$sourceSafe = '<none>' }
    Write-Output "KINGDOMS_DC_TIME_NOT_READY|reason=source|source=\$sourceSafe|expected=${parent_server}"
    exit 0
}

\$locator = @(& nltest.exe '/dsgetdc:${domain}' /timeserv /force 2>&1 | ForEach-Object { "\$_" })
\$locatorRc = \$LASTEXITCODE
if (\$locatorRc -ne 0) {
    \$detail = ((\$locator -join ' ') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_DC_TIME_NOT_READY|reason=advertising|rc=\$locatorRc|detail=\$detail"
    exit 0
}

Write-Output "KINGDOMS_DC_TIME_READY|source=\$source|parent=${parent_server}"
POWERSHELL
)"

    repair_script="$(cat <<POWERSHELL
\$ErrorActionPreference = 'Continue'

# Prove that the authoritative parent-domain time source is discoverable.
\$parentLocator = @(& nltest.exe '/dsgetdc:${parent_domain}' /timeserv /force 2>&1 | ForEach-Object { "\$_" })
\$parentLocatorRc = \$LASTEXITCODE
if (\$parentLocatorRc -ne 0) {
    \$detail = ((\$parentLocator -join ' ') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_DC_TIME_REPAIR_FAILED|stage=parent_timeserv_locator|rc=\$parentLocatorRc|detail=\$detail"
    exit 0
}

# Prove UDP/123 reaches the expected forest-root PDC before changing W32Time.
\$strip = @(& w32tm.exe /stripchart /computer:${parent_server} /samples:2 /dataonly 2>&1 | ForEach-Object { "\$_" })
\$stripRc = \$LASTEXITCODE
if (\$stripRc -ne 0) {
    \$detail = ((\$strip -join ' ') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_DC_TIME_REPAIR_FAILED|stage=parent_ntp_path|rc=\$stripRc|detail=\$detail"
    exit 0
}

& w32tm.exe /config /syncfromflags:domhier /update | Out-Null
\$configRc = \$LASTEXITCODE
if (\$configRc -ne 0) {
    Write-Output "KINGDOMS_DC_TIME_REPAIR_FAILED|stage=config|rc=\$configRc"
    exit 0
}

try {
    Restart-Service W32Time -Force -ErrorAction Stop
    \$service = Get-Service W32Time -ErrorAction Stop
    \$service.WaitForStatus(
        [System.ServiceProcess.ServiceControllerStatus]::Running,
        [TimeSpan]::FromSeconds(10)
    )
}
catch {
    \$detail = ((\$_.Exception.Message -replace '[|\r\n]', ' ').Trim())
    Write-Output "KINGDOMS_DC_TIME_REPAIR_FAILED|stage=service|detail=\$detail"
    exit 0
}

Start-Sleep -Seconds 2

\$source = ''
\$sourceRc = -1
\$lastResyncRc = -1

for (\$syncAttempt = 1; \$syncAttempt -le 12; \$syncAttempt++) {
    if (\$syncAttempt -eq 1 -or ((\$syncAttempt - 1) % 3) -eq 0) {
        # Prime the parent-domain locator immediately before rediscovery. This
        # avoids waiting for W32Time's default 15-minute peer-resolution backoff.
        & nltest.exe '/dsgetdc:${parent_domain}' /timeserv /force | Out-Null
        & w32tm.exe /resync /rediscover /nowait | Out-Null
        \$lastResyncRc = \$LASTEXITCODE
    }

    Start-Sleep -Seconds 5

    \$source = (& w32tm.exe /query /source 2>\$null | Out-String).Trim().TrimEnd('.')
    \$sourceRc = \$LASTEXITCODE

    if (\$sourceRc -eq 0 -and \$source -ieq '${parent_server}') {
        # Once synchronized, wait until Netlogon exposes this child PDC as a
        # TIMESERV so local-domain members can discover it deterministically.
        \$advertise = @(& nltest.exe '/dsgetdc:${domain}' /timeserv /force 2>&1 | ForEach-Object { "\$_" })
        \$advertiseRc = \$LASTEXITCODE
        if (\$advertiseRc -eq 0) {
            Write-Output "KINGDOMS_DC_TIME_REPAIRED|source=\$source|sync_attempt=\$syncAttempt"
            exit 0
        }
    }
}

\$sourceSafe = ((\$source -replace '[|\r\n]', ' ').Trim())
if (-not \$sourceSafe) { \$sourceSafe = '<none>' }
Write-Output "KINGDOMS_DC_TIME_REPAIR_FAILED|stage=sync_or_advertising|resync_rc=\$lastResyncRc|source_rc=\$sourceRc|source=\$sourceSafe|expected=${parent_server}"
exit 0
POWERSHELL
)"

    local started="${SECONDS}"
    local elapsed=0
    local remaining="${AD_READINESS_TIMEOUT_SECONDS}"
    local probe_timeout="${AD_READINESS_PROBE_TIMEOUT_SECONDS}"
    local repair_timeout=0
    local next_report=30

    while (( SECONDS - started < AD_READINESS_TIMEOUT_SECONDS )); do
        elapsed=$((SECONDS - started))
        remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
        probe_timeout="${AD_READINESS_PROBE_TIMEOUT_SECONDS}"
        (( remaining < probe_timeout )) && probe_timeout="${remaining}"
        (( probe_timeout > 0 )) || break

        output=""
        marker=""

        if output="$(vagrant_powershell_capture "${vm}" "${probe_script}" "${probe_timeout}")"; then
            marker="$(
                printf '%s\n' "${output}" |
                    grep -E 'KINGDOMS_DC_TIME_(READY|NOT_READY)\|' |
                    tail -n 1 || true
            )"
        fi

        if [[ "${marker}" == KINGDOMS_DC_TIME_READY\|* ]]; then
            echo "        [+] ${vm} child-domain time hierarchy ready (${parent_server})"
            return 0
        fi

        if [[ "${marker}" == KINGDOMS_DC_TIME_NOT_READY\|* ]]; then
            last_state="${marker#KINGDOMS_DC_TIME_NOT_READY|}"
        else
            last_state="reason=transport"
        fi

        if [[ "${last_state}" == reason=source\|* ]]; then
            consecutive_source_failures=$((consecutive_source_failures + 1))
        else
            consecutive_source_failures=0
        fi

        if (( repair_attempted == 0 && consecutive_source_failures >= 6 )); then
            echo "        [!] ${vm} AD is ready but child-domain time stayed off the parent hierarchy for ~30s"
            echo "        [*] attempting one bounded child-PDC W32Time hierarchy recovery"
            repair_attempted=1

            elapsed=$((SECONDS - started))
            remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
            (( remaining > 0 )) || break
            repair_timeout="${AD_REPAIR_TIMEOUT_SECONDS}"
            (( remaining < repair_timeout )) && repair_timeout="${remaining}"

            output=""
            if output="$(vagrant_powershell_capture "${vm}" "${repair_script}" "${repair_timeout}")"; then
                marker="$(
                    printf '%s\n' "${output}" |
                        grep -E 'KINGDOMS_DC_TIME_(REPAIRED|REPAIR_FAILED)\|' |
                        tail -n 1 || true
                )"

                if [[ "${marker}" == KINGDOMS_DC_TIME_REPAIRED\|* ]]; then
                    echo "        [+] ${vm} child-domain time recovery completed: ${marker}"
                elif [[ "${marker}" == KINGDOMS_DC_TIME_REPAIR_FAILED\|* ]]; then
                    fail "${vm} child-domain time recovery failed: ${marker}"
                else
                    fail "${vm} child-domain time recovery returned without a terminal marker"
                fi
            else
                marker="$(
                    printf '%s\n' "${output}" |
                        grep -E 'KINGDOMS_DC_TIME_(REPAIRED|REPAIR_FAILED)\|' |
                        tail -n 1 || true
                )"
                fail "${vm} child-domain time recovery transport failed within remaining readiness budget: ${marker:-no marker}"
            fi

            consecutive_source_failures=0
        fi

        elapsed=$((SECONDS - started))
        remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
        (( remaining < 0 )) && remaining=0
        if (( elapsed >= next_report )); then
            echo "        [*] waiting for ${vm} child-domain time readiness (${elapsed}s elapsed, ${remaining}s remaining); ${last_state}"
            next_report=$((next_report + 30))
        fi

        (( remaining > 0 )) || break
        if (( remaining < AD_READINESS_RETRY_DELAY_SECONDS )); then
            sleep "${remaining}"
        else
            sleep "${AD_READINESS_RETRY_DELAY_SECONDS}"
        fi
    done
    fail "${vm} child-domain time hierarchy did not converge within 300s; ${last_state}; repair_attempted=${repair_attempted}"
}

wait_domain_controller_ready() {
    local vm="$1"
    local domain="${DC_DOMAIN[${vm}]}"
    local fqdn="${DC_FQDN[${vm}]}"
    local script
    local basic_ready=0

    script="$(cat <<POWERSHELL
\$ErrorActionPreference = 'Stop'
\$Env:ADPS_LoadDefaultDrive = '0'

foreach (\$serviceName in @('NTDS','DNS','ADWS','Netlogon','Kdc','W32Time')) {
    \$service = Get-Service -Name \$serviceName -ErrorAction Stop
    if (\$service.Status -ne 'Running') {
        throw "\$serviceName is \$(\$service.Status)"
    }
}

foreach (\$shareName in @('SYSVOL','NETLOGON')) {
    if (-not (Get-SmbShare -Name \$shareName -ErrorAction SilentlyContinue)) {
        throw "\$shareName share is missing"
    }
}

Import-Module ActiveDirectory -ErrorAction Stop
Get-ADRootDSE -Server '${fqdn}' -ErrorAction Stop | Out-Null
Resolve-DnsName '_ldap._tcp.dc._msdcs.${domain}' -Server 127.0.0.1 -ErrorAction Stop | Out-Null

\$savedPreference = \$ErrorActionPreference
try {
    \$ErrorActionPreference = 'Continue'
    \$nltest = @(& nltest.exe '/dsgetdc:${domain}' /force 2>&1 | ForEach-Object { "\$_" })
    \$nltestRc = \$LASTEXITCODE
}
finally {
    \$ErrorActionPreference = \$savedPreference
}

if (\$nltestRc -ne 0) {
    throw "DC Locator is not ready: \$(\$nltest -join ' ')"
}

Write-Output 'KINGDOMS_DC_RUNTIME_READY'
POWERSHELL
)"

    local started="${SECONDS}"
    local elapsed=0
    local remaining="${AD_READINESS_TIMEOUT_SECONDS}"
    local probe_timeout="${AD_READINESS_PROBE_TIMEOUT_SECONDS}"
    local next_report=30

    while (( SECONDS - started < AD_READINESS_TIMEOUT_SECONDS )); do
        elapsed=$((SECONDS - started))
        remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
        probe_timeout="${AD_READINESS_PROBE_TIMEOUT_SECONDS}"
        (( remaining < probe_timeout )) && probe_timeout="${remaining}"
        (( probe_timeout > 0 )) || break

        if vagrant_powershell_ready "${vm}" "${script}" "${probe_timeout}"; then
            basic_ready=1
            break
        fi

        elapsed=$((SECONDS - started))
        remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
        (( remaining < 0 )) && remaining=0
        if (( elapsed >= next_report )); then
            echo "        [*] waiting for ${vm} AD runtime readiness (${elapsed}s elapsed, ${remaining}s remaining)"
            next_report=$((next_report + 30))
        fi

        (( remaining > 0 )) || break
        if (( remaining < AD_READINESS_RETRY_DELAY_SECONDS )); then
            sleep "${remaining}"
        else
            sleep "${AD_READINESS_RETRY_DELAY_SECONDS}"
        fi
    done
    (( basic_ready == 1 )) ||
        fail "${vm} did not regain AD/DC Locator readiness for ${domain} within 300s"

    ensure_child_dc_time_ready "${vm}"

    echo "        [+] ${vm} AD runtime ready (${fqdn})"
}

wait_domain_member_ready() {
    local vm="$1"
    local domain="${MEMBER_DOMAIN[${vm}]}"
    local dc="${MEMBER_DC[${vm}]}"
    local netbios="${MEMBER_NETBIOS[${vm}]}"
    local script
    local repair_script
    local output=""
    local marker=""
    local last_state="reason=transport"
    local consecutive_time_failures=0
    local time_repair_attempted=0

    script="$(cat <<POWERSHELL
\$ErrorActionPreference = 'Stop'

try {
    Resolve-DnsName '${dc}' -ErrorAction Stop | Out-Null
}
catch {
    Write-Output 'KINGDOMS_MEMBER_NOT_READY|reason=dns'
    exit 0
}

try {
    \$healthy = Test-ComputerSecureChannel -Server '${dc}' -ErrorAction Stop
}
catch {
    Write-Output 'KINGDOMS_MEMBER_NOT_READY|reason=secure_channel'
    exit 0
}

if (-not \$healthy) {
    Write-Output 'KINGDOMS_MEMBER_NOT_READY|reason=secure_channel'
    exit 0
}

try {
    \$account = New-Object System.Security.Principal.NTAccount('${netbios}', 'administrator')
    \$null = \$account.Translate([System.Security.Principal.SecurityIdentifier])
}
catch {
    Write-Output 'KINGDOMS_MEMBER_NOT_READY|reason=account_translation'
    exit 0
}

# Test-ComputerSecureChannel can succeed before Netlogon has fully established
# the domain session W32Time consumes for authenticated NT5DS discovery. Gate
# time readiness on the Netlogon control path itself.
\$savedPreference = \$ErrorActionPreference
try {
    \$ErrorActionPreference = 'Continue'
    \$scQuery = @(& nltest.exe '/sc_query:${domain}' 2>&1 | ForEach-Object { "\$_" })
    \$scQueryRc = \$LASTEXITCODE
}
finally {
    \$ErrorActionPreference = \$savedPreference
}

if (\$scQueryRc -ne 0) {
    \$detail = ((\$scQuery -join ' ') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_MEMBER_NOT_READY|reason=netlogon_session|rc=\$scQueryRc|detail=\$detail"
    exit 0
}

\$savedPreference = \$ErrorActionPreference
try {
    \$ErrorActionPreference = 'Continue'
    \$source = (& w32tm.exe /query /source 2>\$null | Out-String).Trim()
    \$sourceRc = \$LASTEXITCODE
}
finally {
    \$ErrorActionPreference = \$savedPreference
}

\$source = \$source.Trim().TrimEnd('.')
if (\$sourceRc -ne 0 -or -not \$source -or \$source -ine '${dc}') {
    \$sourceSafe = ((\$source -replace '[|\r\n]', ' ').Trim())
    if (-not \$sourceSafe) { \$sourceSafe = '<none>' }
    Write-Output "KINGDOMS_MEMBER_NOT_READY|reason=time|source=\$sourceSafe|expected=${dc}"
    exit 0
}

\$sourceSafe = ((\$source -replace '[|\r\n]', ' ').Trim())
Write-Output "KINGDOMS_MEMBER_RUNTIME_READY|time=\$sourceSafe|expected=${dc}"
POWERSHELL
)"

    repair_script="$(cat <<POWERSHELL
\$ErrorActionPreference = 'Continue'

# The normal readiness probe has already proved DNS, machine trust, account
# translation and the Netlogon secure session. Re-prove the Netlogon session
# immediately before touching W32Time so recovery never races early boot.
\$scQuery = @(& nltest.exe '/sc_query:${domain}' 2>&1 | ForEach-Object { "\$_" })
\$scQueryRc = \$LASTEXITCODE
if (\$scQueryRc -ne 0) {
    \$detail = ((\$scQuery -join ' ') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=netlogon_session|rc=\$scQueryRc|detail=\$detail"
    exit 0
}

\$locator = @(& nltest.exe '/dsgetdc:${domain}' /timeserv /force 2>&1 | ForEach-Object { "\$_" })
\$locatorRc = \$LASTEXITCODE
if (\$locatorRc -ne 0) {
    \$locatorSafe = ((\$locator -join ' ') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=timeserv_locator|rc=\$locatorRc|detail=\$locatorSafe"
    exit 0
}

# Prove UDP/123 to the authoritative domain DC before resetting W32Time.
\$strip = @(& w32tm.exe /stripchart /computer:${dc} /samples:2 /dataonly 2>&1 | ForEach-Object { "\$_" })
\$stripRc = \$LASTEXITCODE
if (\$stripRc -ne 0) {
    \$detail = ((\$strip -join ' ') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=ntp_path|rc=\$stripRc|detail=\$detail"
    exit 0
}

& w32tm.exe /config /syncfromflags:domhier /update | Out-Null
\$configRc = \$LASTEXITCODE
if (\$configRc -ne 0) {
    Write-Output "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=config|rc=\$configRc"
    exit 0
}

try {
    Restart-Service W32Time -Force -ErrorAction Stop
    \$service = Get-Service W32Time -ErrorAction Stop
    \$service.WaitForStatus(
        [System.ServiceProcess.ServiceControllerStatus]::Running,
        [TimeSpan]::FromSeconds(10)
    )
}
catch {
    \$detail = ((\$_.Exception.Message -replace '[|\r\n]', ' ').Trim())
    Write-Output "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=service|detail=\$detail"
    exit 0
}

Start-Sleep -Seconds 2

\$lastResyncRc = -1
\$source = ''
\$sourceRc = -1

for (\$repairAttempt = 1; \$repairAttempt -le 12; \$repairAttempt++) {
    if (\$repairAttempt -eq 1 -or ((\$repairAttempt - 1) % 3) -eq 0) {
        # Keep Netlogon/DC Locator warm immediately before each NT5DS
        # rediscovery request. No trust or machine-password state is rewritten.
        & nltest.exe '/sc_query:${domain}' | Out-Null
        \$scRefreshRc = \$LASTEXITCODE
        if (\$scRefreshRc -ne 0) {
            Write-Output "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=netlogon_session_lost|rc=\$scRefreshRc"
            exit 0
        }

        & nltest.exe '/dsgetdc:${domain}' /timeserv /force | Out-Null
        \$locatorRefreshRc = \$LASTEXITCODE
        if (\$locatorRefreshRc -ne 0) {
            Write-Output "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=timeserv_locator_lost|rc=\$locatorRefreshRc"
            exit 0
        }

        & w32tm.exe /resync /rediscover /nowait | Out-Null
        \$lastResyncRc = \$LASTEXITCODE
    }

    Start-Sleep -Seconds 5

    \$source = (& w32tm.exe /query /source 2>\$null | Out-String).Trim().TrimEnd('.')
    \$sourceRc = \$LASTEXITCODE

    if (
        \$sourceRc -eq 0 -and
        \$source -and
        \$source -ieq '${dc}'
    ) {
        Write-Output "KINGDOMS_MEMBER_TIME_REPAIRED|source=\$source|attempt=\$repairAttempt|netlogon_session=ready"
        exit 0
    }
}

\$sourceSafe = ((\$source -replace '[|\r\n]', ' ').Trim())
if (-not \$sourceSafe) { \$sourceSafe = '<none>' }
Write-Output "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=rediscover|resync_rc=\$lastResyncRc|source_rc=\$sourceRc|source=\$sourceSafe|expected=${dc}|netlogon_session=ready"
exit 0
POWERSHELL
)"

    local started="${SECONDS}"
    local elapsed=0
    local remaining="${AD_READINESS_TIMEOUT_SECONDS}"
    local probe_timeout="${AD_READINESS_PROBE_TIMEOUT_SECONDS}"
    local repair_timeout=0
    local next_report=30

    while (( SECONDS - started < AD_READINESS_TIMEOUT_SECONDS )); do
        elapsed=$((SECONDS - started))
        remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
        probe_timeout="${AD_READINESS_PROBE_TIMEOUT_SECONDS}"
        (( remaining < probe_timeout )) && probe_timeout="${remaining}"
        (( probe_timeout > 0 )) || break

        output=""
        marker=""

        if output="$(vagrant_powershell_capture "${vm}" "${script}" "${probe_timeout}")"; then
            marker="$(
                printf '%s\n' "${output}" |
                    grep -E 'KINGDOMS_MEMBER_(RUNTIME_READY|NOT_READY)\|' |
                    tail -n 1 || true
            )"
        fi

        if [[ "${marker}" == KINGDOMS_MEMBER_RUNTIME_READY\|* ]]; then
            echo "        [+] ${vm} domain runtime ready (${domain})"
            return 0
        fi

        if [[ "${marker}" == KINGDOMS_MEMBER_NOT_READY\|* ]]; then
            last_state="${marker#KINGDOMS_MEMBER_NOT_READY|}"
        else
            last_state="reason=transport"
        fi

        if [[ "${last_state}" == reason=time\|* ]]; then
            consecutive_time_failures=$((consecutive_time_failures + 1))
        else
            consecutive_time_failures=0
        fi

        # Only time recovery is automatic. Reaching reason=time proves DNS,
        # machine trust, domain account translation and the Netlogon secure
        # session all passed in this same probe. Never reset a machine password
        # or repair trust here.
        if (( time_repair_attempted == 0 && consecutive_time_failures >= 6 )); then
            echo "        [!] ${vm} identity checks are healthy but domain time stayed unsynchronized for ~30s"
            echo "        [*] attempting one bounded W32Time domain-hierarchy rediscovery/resync"
            time_repair_attempted=1

            elapsed=$((SECONDS - started))
            remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
            (( remaining > 0 )) || break
            repair_timeout="${AD_REPAIR_TIMEOUT_SECONDS}"
            (( remaining < repair_timeout )) && repair_timeout="${remaining}"

            output=""
            if output="$(vagrant_powershell_capture "${vm}" "${repair_script}" "${repair_timeout}")"; then
                marker="$(
                    printf '%s\n' "${output}" |
                        grep -E 'KINGDOMS_MEMBER_TIME_(REPAIRED|REPAIR_FAILED)\|' |
                        tail -n 1 || true
                )"

                if [[ "${marker}" == KINGDOMS_MEMBER_TIME_REPAIRED\|* ]]; then
                    echo "        [+] ${vm} bounded domain-time recovery completed: ${marker}"
                elif [[ "${marker}" == KINGDOMS_MEMBER_TIME_REPAIR_FAILED\|* ]]; then
                    fail "${vm} bounded domain-time recovery failed: ${marker}"
                else
                    fail "${vm} time-recovery command returned without a terminal marker"
                fi
            else
                marker="$(
                    printf '%s\n' "${output}" |
                        grep -E 'KINGDOMS_MEMBER_TIME_(REPAIRED|REPAIR_FAILED)\|' |
                        tail -n 1 || true
                )"
                fail "${vm} bounded domain-time recovery transport failed within remaining readiness budget: ${marker:-no marker}"
            fi

            consecutive_time_failures=0
        fi

        elapsed=$((SECONDS - started))
        remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
        (( remaining < 0 )) && remaining=0
        if (( elapsed >= next_report )); then
            echo "        [*] waiting for ${vm} domain runtime readiness (${elapsed}s elapsed, ${remaining}s remaining); ${last_state}"
            next_report=$((next_report + 30))
        fi

        (( remaining > 0 )) || break
        if (( remaining < AD_READINESS_RETRY_DELAY_SECONDS )); then
            sleep "${remaining}"
        else
            sleep "${AD_READINESS_RETRY_DELAY_SECONDS}"
        fi
    done
    fail "${vm} did not regain domain identity readiness for ${domain} within 300s; ${last_state}; time_repair_attempted=${time_repair_attempted}"
}

preflight_domain_health() {
    local vm

    echo "[*] Proving AD identity health before isolation restarts"

    for vm in "${DOMAIN_CONTROLLERS[@]}"; do
        wait_domain_controller_ready "${vm}"
    done

    for vm in "${DOMAIN_MEMBERS[@]}"; do
        wait_domain_member_ready "${vm}"
    done

    echo "[+] AD identity preflight passed"
}

preflight_exercise_time_dependencies() {
    local vm

    echo "[*] Proving child-domain time authorities before member isolation"

    for vm in "${EXERCISE_DOMAIN_CONTROLLERS[@]}"; do
        [[ -n "${DC_TIME_PARENT_DOMAIN[${vm}]:-}" ]] || continue
        prove_isolated_guest_ready "${vm}" dc
    done

    echo "[+] Child-domain time authority preflight passed"
}

configure_windows_nat_provisioning() {
    local vm

    # DCs must be fully advertising before any dependent member is rebooted.
    # Merely seeing the VM process or WinRM is not enough for Netlogon.
    for vm in "${DOMAIN_CONTROLLERS[@]}"; do
        ensure_vm_nat_state "${vm}" TRUE connect
        wait_domain_controller_ready "${vm}"
    done

    for vm in "${DOMAIN_MEMBERS[@]}"; do
        ensure_vm_nat_state "${vm}" TRUE connect
        wait_domain_member_ready "${vm}"
    done
}

prove_isolated_guest_ready() (
    local vm="$1"
    local kind="$2"
    local vmx
    local persistent

    vmx="$(vmx_for "${vm}")"
    persistent="$(get_start_connected "${vmx}")"

    [[ "${persistent}" == "FALSE" ]] ||
        fail "${vm}: exercise readiness probe requires persistent NAT to remain FALSE"

    echo "        [*] temporarily connecting runtime NAT for authenticated readiness"

    vmrun -T ws connectNamedDevice "${vmx}" ethernet0 >/dev/null 2>&1 ||
        fail "${vm}: could not temporarily connect runtime NAT for readiness"

    cleanup_runtime_nat() {
        vmrun -T ws disconnectNamedDevice "${vmx}" ethernet0 >/dev/null 2>&1 || true
    }
    trap cleanup_runtime_nat EXIT

    case "${kind}" in
        member)
            wait_domain_member_ready "${vm}"
            ;;
        dc)
            wait_domain_controller_ready "${vm}"
            ;;
        *)
            fail "Unknown isolated readiness kind for ${vm}: ${kind}"
            ;;
    esac

    cleanup_runtime_nat
    trap - EXIT

    persistent="$(get_start_connected "${vmx}")"
    [[ "${persistent}" == "FALSE" ]] ||
        fail "${vm}: readiness probe changed persistent NAT isolation"

    echo "        [+] ${vm} authenticated post-reboot readiness proven; runtime NAT disconnected"
)

configure_windows_nat_exercise() {
    local vm

    # Members reboot first while their DCs are still healthy. Every restarted
    # guest keeps ethernet0.startConnected=FALSE. The management NIC is then
    # connected only long enough to prove authenticated Windows/domain
    # readiness through Vagrant WinRM and is immediately disconnected again.
    for vm in "${DOMAIN_MEMBERS[@]}"; do
        ensure_vm_nat_state "${vm}" FALSE disconnect
        prove_isolated_guest_ready "${vm}" member
    done

    # Keep parent/child dependencies available while DCs are restarted. The
    # child DC is validated before KINGSLANDING is cycled; MEEREEN is
    # independent; KINGSLANDING is restarted last.
    for vm in "${EXERCISE_DOMAIN_CONTROLLERS[@]}"; do
        ensure_vm_nat_state "${vm}" FALSE disconnect
        prove_isolated_guest_ready "${vm}" dc
    done
}

verify_persistent_state() {
    local desired="$1"
    local vm vmx current
    local failed=0

    echo
    echo "=== PERSISTENT WINDOWS NAT STATE ==="

    for vm in "${WINDOWS_VMS[@]}"; do
        vmx="$(vmx_for "${vm}")"
        current="$(get_start_connected "${vmx}")"

        printf '%-12s ethernet0.startConnected=%s' \
            "${vm}" \
            "${current}"

        if [[ "${current}" == "${desired}" ]]; then
            echo " [OK]"
        else
            echo " [FAIL]"
            failed=1
        fi
    done

    [[ "${failed}" -eq 0 ]] ||
        fail "Persistent Windows NAT state is inconsistent."
}

set_state() {
    printf '%s\n' "$1" > "${PROVIDER}/.goad-nomad-mode"
}

show_status() {
    echo "============================================================"
    echo "GOAD_NOMAD LAB MODE"
    echo "============================================================"

    echo
    printf 'Provider: %s\n' "${PROVIDER}"

    if [[ -f "${PROVIDER}/.goad-nomad-mode" ]]; then
        printf 'Recorded mode: %s\n' \
            "$(cat "${PROVIDER}/.goad-nomad-mode")"
    else
        echo "Recorded mode: unknown / not yet managed"
    fi

    echo
    echo "=== HOST PROVISIONING ROUTES ==="
    bash "${ROUTES}" status

    echo
    echo "=== ROUTER FORWARD POLICY ==="

    (
        cd "${PROVIDER}"

        GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROUTER_SSH}" \
            "sudo nft list chain inet ${NFTABLES_FORWARD_TABLE} forward"
    )

    echo
    echo "=== WINDOWS VM NETWORK STATE ==="

    local vm vmx current runtime

    for vm in "${WINDOWS_VMS[@]}"; do
        vmx="$(vmx_for "${vm}")"
        current="$(get_start_connected "${vmx}")"

        if is_running "${vmx}"; then
            runtime="running"
        else
            runtime="powered-off"
        fi

        echo "--- ${vm} ---"
        echo "power=${runtime}"
        echo "ethernet0.startConnected=${current}"

        grep -Ei \
            '^ethernet(0|1)\.(connectionType|vnet|present)' \
            "${vmx}" || true
    done
}

enter_exercise_mode() {
    echo "============================================================"
    echo "ENTERING GOAD_NOMAD EXERCISE MODE"
    echo "============================================================"

    sudo -v

    verify_windows_layout

    # On a provisioning -> exercise transition, prove the full domain contract.
    # On a cold start of an already-recorded exercise range, persistent NAT is
    # intentionally still FALSE, so probe only the child-DC time dependency
    # with temporary runtime NAT before checking members.
    if [[ "$(cat "${PROVIDER}/.goad-nomad-mode" 2>/dev/null || true)" != "exercise" ]]; then
        preflight_domain_health
    else
        preflight_exercise_time_dependencies
    fi

    #
    # Close routing first so there is never an intermediate
    # state where the host can freely reach protected zones.
    #
    apply_router_policy exercise

    echo
    sudo bash "${ROUTES}" disable

    echo
    echo "[*] Persisting and disconnecting Windows NAT adapters"
    echo "    member/workstation guests first; domain controllers last"

    configure_windows_nat_exercise

    verify_persistent_state FALSE

    set_state exercise

    echo
    echo "[+] GOAD_NOMAD is now in EXERCISE mode."
    echo "    Windows NAT adapters: persistent OFF + disconnected"
    echo "    Protected-zone host routes: removed"
    echo "    Router forwarding: deny-by-default"
}

enter_provisioning_mode() {
    echo "============================================================"
    echo "ENTERING GOAD_NOMAD PROVISIONING MODE"
    echo "============================================================"

    sudo -v

    verify_windows_layout

    #
    # Rebuild the Windows provisioning management plane first.
    #
    echo "[*] Persisting and connecting Windows NAT adapters"
    echo "    domain controllers first with AD readiness; members second"

    configure_windows_nat_provisioning

    verify_persistent_state TRUE

    echo
    apply_router_policy provisioning

    echo
    sudo bash "${ROUTES}" enable

    set_state provisioning

    echo
    echo "[+] GOAD_NOMAD is now in PROVISIONING mode."
    echo "    Windows NAT adapters: persistent ON + connected"
    echo "    Protected-zone host routes: enabled"
    echo "    Router forwarding: temporarily permissive"
}

main() {
    # Offline contract view used by the consolidated Kingdoms regression suite.
    # Does not enumerate, modify or power on guests; never grants deployment.
    if [[ "${1:-}" == "--describe-profile" ]]; then
        printf 'profile=%s\n' "${KINGDOMS_VMWARE_LAB}"
        printf 'windows=%s\n' "${WINDOWS_VMS[*]}"
        printf 'domain_controllers=%s\n' "${DOMAIN_CONTROLLERS[*]}"
        printf 'members=%s\n' "${DOMAIN_MEMBERS[*]}"
        printf 'routes=%s\n' "${ROUTES}"
        printf 'router_ssh=%s\n' "${ROUTER_SSH}"
        printf 'router_policy=%s\n' "${POLICY_DIR}"
        printf 'nftables_table=%s\n' "${NFTABLES_FORWARD_TABLE}"
        printf 'deployment_authorized=false\n'
        return 0
    fi
    require_command vmrun
    require_command vagrant
    require_command python3
    require_command ip
    require_command timeout
    require_command iconv
    require_command base64

    [[ -f "${ROUTES}" ]] ||
        fail "${ROUTES} is missing."

    [[ -d "${POLICY_DIR}" ]] ||
        fail "${POLICY_DIR} is missing."

    # NORTH always requires an explicit instance; never auto-select GOAD.
    if [[ "${KINGDOMS_VMWARE_LAB}" == "NORTH" ]]; then
        [[ -n "${GOAD_PROVIDER_DIR:-}" ]] ||
            fail "NORTH requires explicit GOAD_PROVIDER_DIR; no auto-discovery"
    fi

    resolve_provider

    if [[ "${KINGDOMS_VMWARE_LAB}" == "NORTH" ]]; then
        [[ -f "${PROVIDER}/Vagrantfile" && ! -L "${PROVIDER}/Vagrantfile" ]] ||
            fail "NORTH provider Vagrantfile is missing or unsafe"
        for vmnet in vmnet11 vmnet12 vmnet13; do
            grep -Fq ":vnet => \"${vmnet}\"" "${PROVIDER}/Vagrantfile" ||
                fail "NORTH provider is not bound to ${vmnet}"
        done
        if grep -Eq ':name => "(GOAD-DC03|GOAD-SRV03)"' "${PROVIDER}/Vagrantfile"; then
            fail "NORTH provider unexpectedly includes ESSOS guests"
        fi
    fi

    # Never interpret a Course 1 four-VM preview as a legacy six-VM range.
    # This is read-only and executes before status/provisioning/exercise paths.
    PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
        python3 -m goad.course1_instance_binding --check-provider "${PROVIDER}" ||
        fail "Refusing GOAD mode operation: instance profile binding is not approved"

    case "${1:-status}" in
        exercise)
            enter_exercise_mode
            ;;

        provisioning)
            enter_provisioning_mode
            ;;

        status)
            show_status
            ;;

        *)
            echo "Usage: $0 {exercise|provisioning|status}" >&2
            exit 2
            ;;
    esac
}

main "$@"