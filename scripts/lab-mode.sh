#!/usr/bin/env bash
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROUTES="${ROOT}/scripts/provisioning-routes.sh"
# GOAD keeps the exact original six-guest behavior. NORTH reuses this same
# controller with the reduced profile selected explicitly by the provider.
readonly GOAD_LAB_PROFILE="${GOAD_LAB_PROFILE:-GOAD}"
case "${GOAD_LAB_PROFILE}" in
    GOAD|NORTH) ;;
    *) echo "[BLOCKED] Unknown Kingdoms profile: ${GOAD_LAB_PROFILE}" >&2; exit 2 ;;
esac
readonly POLICY_DIR="${ROOT}/ad/${GOAD_LAB_PROFILE}/providers/vmware/router/nftables"

# Explicitly enabled only by the failed-start NORTH recovery controller.
# Normal exercise transitions still require every guest's AD readiness.
EXERCISE_ALLOW_STOPPED_MEMBERS=0
# Only requested by the parent provider after a complete, successful NORTH
# installed cold-start readiness chain (four guests, not a single-VM start).
EXERCISE_VALIDATED_COLD_START=0

readonly AD_READINESS_TIMEOUT_SECONDS=300
readonly AD_READINESS_PROBE_TIMEOUT_SECONDS=15
# Only NORTH/DC02 uses direct HTTPS WinRM; its existing 15s probe was
# shorter than the proven 30s/45s operation/read timeout pair.
readonly NORTH_DC02_DIRECT_PROBE_TIMEOUT_SECONDS=75
readonly AD_READINESS_RETRY_DELAY_SECONDS=5
readonly AD_REPAIR_TIMEOUT_SECONDS=90

# An explicit profile selection controls only the two Essos Windows guests.
# Ordering is identical to the proven six-guest GOAD lifecycle.
if [[ "${GOAD_LAB_PROFILE}" == NORTH ]]; then
    EXTRA_DOMAIN_CONTROLLERS=()
    EXTRA_DOMAIN_MEMBERS=()
else
    EXTRA_DOMAIN_CONTROLLERS=(GOAD-DC03)
    EXTRA_DOMAIN_MEMBERS=(GOAD-SRV03)
fi

readonly DOMAIN_CONTROLLERS=(
    GOAD-DC01
    GOAD-DC02
    "${EXTRA_DOMAIN_CONTROLLERS[@]}"
)

# Exercise restarts child DCs before the root PDC to preserve the time chain.
readonly EXERCISE_DOMAIN_CONTROLLERS=(
    GOAD-DC02
    "${EXTRA_DOMAIN_CONTROLLERS[@]}"
    GOAD-DC01
)

readonly DOMAIN_MEMBERS=(
    GOAD-SRV02
    "${EXTRA_DOMAIN_MEMBERS[@]}"
    GOAD-WS01
)

readonly WINDOWS_VMS=(
    GOAD-DC01
    GOAD-DC02
    "${EXTRA_DOMAIN_CONTROLLERS[@]}"
    GOAD-SRV02
    "${EXTRA_DOMAIN_MEMBERS[@]}"
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
            GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/router-ssh.sh" '
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

extract_dc02_time_marker() {
    local vm="$1"
    local kinds="$2"
    local output="$3"

    if [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]]; then
        # pywinrm can prepend PowerShell CLIXML progress without a newline:
        # </Objs>KINGDOMS_DC_TIME_READY|source=... .
        # Extract the marker instead of requiring the line to begin with it.
        # Caller also requires a successful authenticated WinRM return code.
        printf '%s\n' "${output}" |
            grep -oE "KINGDOMS_DC_TIME_(${kinds})\|[^<]*" |
            tail -n 1 || true
    else
        # Preserve original KINGDOMS/GOAD matching.
        printf '%s\n' "${output}" |
            grep -E "KINGDOMS_DC_TIME_(${kinds})\|" |
            tail -n 1 || true
    fi
}

north_direct_dc02_capture() {
    local vm="$1"
    local script="$2"
    local timeout_seconds="$3"
    local python="${HOME}/.goad/.venv/bin/python"

    [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]] ||
        fail "Direct DC02 transport is only supported for NORTH"
    [[ -x "${python}" ]] ||
        fail "Missing KINGDOMS management Python runtime: ${python}"

    # Reuse direct WinRM/NTLM already proven by installed NORTH startup.
    printf '%s' "${script}" |
        timeout "${timeout_seconds}" "${python}" "${ROOT}/scripts/north-exercise-winrm.py" \
            --machine "${vm}" --provider "${PROVIDER}" --timeout "${timeout_seconds}"
}

vagrant_powershell_ready() {
    local vm="$1"
    local script="$2"
    local timeout_seconds="$3"
    local encoded

    (( timeout_seconds > 0 )) || return 124

    if [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]]; then
        north_direct_dc02_capture "${vm}" "${script}" "${timeout_seconds}" >/dev/null 2>&1
        return $?
    fi

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

    if [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]]; then
        north_direct_dc02_capture "${vm}" "${script}" "${timeout_seconds}" 2>&1
        return $?
    fi

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
    local probe_rc=0
    local transport_detail=""
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
        if [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]]; then
            probe_timeout="${NORTH_DC02_DIRECT_PROBE_TIMEOUT_SECONDS}"
        fi
        (( remaining < probe_timeout )) && probe_timeout="${remaining}"
        (( probe_timeout > 0 )) || break

        output=""
        marker=""
        probe_rc=0

        if output="$(vagrant_powershell_capture "${vm}" "${probe_script}" "${probe_timeout}")"; then
            marker="$(
                extract_dc02_time_marker "${vm}" "READY|NOT_READY" "${output}"
            )"
        else
            probe_rc=$?
        fi

        if [[ "${marker}" == KINGDOMS_DC_TIME_READY\|* ]]; then
            echo "        [+] ${vm} child-domain time hierarchy ready (${parent_server})"
            return 0
        fi

        if [[ "${marker}" == KINGDOMS_DC_TIME_NOT_READY\|* ]]; then
            last_state="${marker#KINGDOMS_DC_TIME_NOT_READY|}"
        else
            last_state="reason=transport"
            if [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]]; then
                # NORTH-only failure evidence; never print arbitrary remote
                # PowerShell output or potentially sensitive response content.
                transport_detail="$(printf '%s\n' "${output}" |
                    grep -E '^NORTH_DIRECT_WINRM_ERROR machine=GOAD-DC02 ' |
                    tail -n 1 | cut -c 1-500 || true)"
                printf '        [DIAG] NORTH DC02 probe rc=%s, output_bytes=%s; %s\n' \
                    "${probe_rc}" "${#output}" "${transport_detail:-no recognized WinRM error or time-readiness marker}"
            fi
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
                    extract_dc02_time_marker "${vm}" "REPAIRED|REPAIR_FAILED" "${output}"
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
                    extract_dc02_time_marker "${vm}" "REPAIRED|REPAIR_FAILED" "${output}"
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
        if [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]]; then
            probe_timeout="${NORTH_DC02_DIRECT_PROBE_TIMEOUT_SECONDS}"
        fi
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

    if [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 && "${kind}" == dc ]]; then
        # Do not reconnect DC02's isolated NAT adapter just to repeat a probe.
        echo "        [*] NORTH GOAD-DC02: validating directly over owned lab WinRM"
        wait_domain_controller_ready "${vm}"
        echo "        [+] GOAD-DC02 authenticated direct readiness proven; NAT unchanged"
        return 0
    fi

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

require_north_validated_cold_start() {
    # The provider has already proven all four guests' authenticated AD/time
    # contracts. Only a full, previously isolated NORTH cold start may avoid
    # repeating the same probes through a now-unreliable Vagrant NAT path.
    [[ "${GOAD_LAB_PROFILE}" == NORTH &&
       "${EXERCISE_VALIDATED_COLD_START}" == 1 &&
       "${EXERCISE_ALLOW_STOPPED_MEMBERS}" == 0 &&
       "$(cat "${PROVIDER}/.goad-nomad-mode" 2>/dev/null || true)" == exercise ]] ||
        fail "NORTH validated cold-start isolation scope is not satisfied"

    local vm vmx
    for vm in "${WINDOWS_VMS[@]}"; do
        vmx="$(vmx_for "${vm}")"
        [[ "$(get_start_connected "${vmx}")" == FALSE ]] ||
            fail "${vm}: validated cold-start cannot change a persistent NAT adapter"
        is_running "${vmx}" ||
            fail "${vm}: validated cold-start requires all previously verified guests running"
    done
}

configure_windows_nat_exercise() {
    local vm

    if [[ "${EXERCISE_VALIDATED_COLD_START:-0}" == 1 ]]; then
        # Only after require_north_validated_cold_start has verified every VM,
        # and after the provider's complete direct authenticated readiness
        # chain. NICs remain persistently FALSE: no reboots, Vagrant WinRM,
        # NAT re-connections, or duplicate AD/time repairs.
        for vm in "${DOMAIN_MEMBERS[@]}" "${EXERCISE_DOMAIN_CONTROLLERS[@]}"; do
            ensure_vm_nat_state "${vm}" FALSE disconnect
        done
        echo "[+] NORTH: all four guests were authenticated before isolation; NAT disconnected without Vagrant or restart"
        return 0
    fi

    # Members reboot first while their DCs are still healthy. Every restarted
    # guest keeps ethernet0.startConnected=FALSE. The management NIC is then
    # connected only long enough to prove authenticated Windows/domain
    # readiness through Vagrant WinRM and is immediately disconnected again.
    for vm in "${DOMAIN_MEMBERS[@]}"; do
        ensure_vm_nat_state "${vm}" FALSE disconnect
        if [[ "${EXERCISE_ALLOW_STOPPED_MEMBERS}" == 1 ]]; then
            local vmx vm_list
            vmx="$(vmx_for "${vm}")"
            [[ "$(get_start_connected "${vmx}")" == FALSE ]] ||
                fail "${vm}: offline skip requires persistent NAT isolation"
            vm_list="$(vmrun -T ws list)" ||
                fail "${vm}: VMware power inventory unavailable; cannot skip"
            [[ "${vm_list}" == "Total running VMs:"* ]] ||
                fail "${vm}: VMware power inventory ambiguous; cannot skip"
            if ! printf '%s\n' "${vm_list}" | grep -Fxq "${vmx}"; then
                echo "    [SKIP] ${vm} powered off; NAT persistently disabled; no AD readiness claimed"
                continue
            fi
        fi
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
    if [[ "${GOAD_LAB_PROFILE}" == NORTH ]]; then
        # NORTH ownership evidence is private root-owned state under /run.
        # Use read-only privileged inspection; unprivileged Path.exists()
        # cannot traverse its 0700 directory and misreports an owned route.
        sudo -n bash "${ROUTES}" --north status --provider-dir "${PROVIDER}"
    else
        bash "${ROUTES}" status
    fi

    echo
    echo "=== ROUTER FORWARD POLICY ==="

    (
        cd "${PROVIDER}"

        GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/router-ssh.sh" \
            'sudo nft list chain inet goad_nomad forward'
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
    if [[ "${EXERCISE_VALIDATED_COLD_START}" == 1 ]]; then
        require_north_validated_cold_start
        echo "[+] NORTH: authenticated full installed-start guest readiness reused for isolation"
    elif [[ "$(cat "${PROVIDER}/.goad-nomad-mode" 2>/dev/null || true)" != "exercise" ]]; then
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
    if [[ "${GOAD_LAB_PROFILE}" == NORTH ]]; then
        sudo bash "${ROUTES}" --north disable --provider-dir "${PROVIDER}"
    else
        sudo bash "${ROUTES}" disable
    fi

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
    if [[ "${GOAD_LAB_PROFILE}" == NORTH ]]; then
        sudo bash "${ROUTES}" --north enable --provider-dir "${PROVIDER}"
    else
        sudo bash "${ROUTES}" enable
    fi

    set_state provisioning

    echo
    echo "[+] GOAD_NOMAD is now in PROVISIONING mode."
    echo "    Windows NAT adapters: persistent ON + connected"
    echo "    Protected-zone host routes: enabled"
    echo "    Router forwarding: temporarily permissive"
}

main() {
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

    resolve_provider

    if [[ "$#" -eq 2 ]]; then
        [[ "${1}" == exercise && "${GOAD_LAB_PROFILE}" == NORTH &&
           "$(cat "${PROVIDER}/.goad-nomad-mode" 2>/dev/null || true)" == exercise ]] ||
            fail "NORTH restoration flags require already-recorded exercise mode"
        case "${2}" in
            --allow-stopped-members)
                EXERCISE_ALLOW_STOPPED_MEMBERS=1
                ;;
            --validated-cold-start)
                EXERCISE_VALIDATED_COLD_START=1
                ;;
            *)
                fail "Unknown NORTH exercise restoration flag"
                ;;
        esac
    elif [[ "$#" -gt 2 ]]; then
        fail "Unexpected mode controller arguments"
    fi

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