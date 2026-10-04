#!/usr/bin/env bash
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROUTES="${ROOT}/scripts/provisioning-routes.sh"
readonly POLICY_DIR="${ROOT}/ad/GOAD/providers/vmware/router/nftables"

readonly AD_READINESS_TIMEOUT_SECONDS=300
readonly AD_READINESS_PROBE_TIMEOUT_SECONDS=15
readonly AD_READINESS_RETRY_DELAY_SECONDS=5
readonly AD_REPAIR_TIMEOUT_SECONDS=90

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
# VMware Guest Operations use the committed post-Vagrant domain administrator
# identities. WS01 intentionally reuses the NORTH credentials carried by srv02
# instead of introducing another credential literal.
declare -A GUESTOPS_INVENTORY_ALIAS=(
    [GOAD-DC01]="dc01"
    [GOAD-DC02]="dc02"
    [GOAD-DC03]="dc03"
    [GOAD-SRV02]="srv02"
    [GOAD-SRV03]="srv03"
    [GOAD-WS01]="srv02"
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

pin_vmware_management_nic_identity() {
    local vmx="$1"

    # ethernet0 is the Vagrant/management NAT NIC. VMware-generated addresses
    # are tied to VM identity and can be recomputed after lifecycle power
    # operations. Once VMware has created the guest, freeze the already-chosen
    # management MAC as a static VMX address so Windows keeps seeing the same
    # device across provisioning/exercise transitions.
    #
    # Fresh installs are safe: the first generated MAC becomes the permanent
    # management identity. Existing labs that have already drifted must first
    # restore the MAC Windows currently owns before this helper is allowed to
    # pin it; never invent a replacement identity here.
    if is_running "${vmx}"; then
        fail "refusing to pin VMware management NIC identity while VM is running: ${vmx}"
    fi

    python3 - "${vmx}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()

def get(key):
    match = re.search(
        rf'(?im)^\s*{re.escape(key)}\s*=\s*"([^"]*)"',
        text,
    )
    return match.group(1) if match else None

def set_value(data, key, value):
    pattern = rf'(?im)^\s*{re.escape(key)}\s*=.*$'
    line = f'{key} = "{value}"'
    if re.search(pattern, data):
        return re.sub(pattern, line, data)
    if not data.endswith("\n"):
        data += "\n"
    return data + line + "\n"

def remove_key(data, key):
    pattern = rf'(?im)^\s*{re.escape(key)}\s*=.*\n?'
    return re.sub(pattern, "", data)

address_type = (get("ethernet0.addresstype") or "").lower()
static_address = get("ethernet0.address")
generated_address = get("ethernet0.generatedAddress")

if address_type == "static":
    if not static_address:
        raise SystemExit(
            f"VMX ethernet0 is static but has no address: {path}"
        )
    pinned = static_address.lower()
    updated = text
elif address_type == "generated":
    if not generated_address:
        raise SystemExit(
            f"VMX ethernet0 is generated but has no generatedAddress: {path}"
        )
    pinned = generated_address.lower()
    updated = set_value(text, "ethernet0.addresstype", "static")
    updated = set_value(updated, "ethernet0.address", pinned)
    updated = remove_key(updated, "ethernet0.generatedAddress")
    updated = remove_key(updated, "ethernet0.generatedAddressOffset")
else:
    raise SystemExit(
        f"unsupported ethernet0.addressType={address_type!r}: {path}"
    )

# A generated VMware Workstation MAC uses the 00:0c:29 OUI. Once that exact
# guest-known identity is converted to static, Workstation's reserved-OUI
# validation must be disabled for this adapter or power-on may reject it.
updated = set_value(updated, "ethernet0.checkMACAddress", "FALSE")

# Keep the VM UUID stable as well, but the management MAC no longer depends on
# VMware deriving an address from that UUID.
updated = set_value(updated, "uuid.action", "keep")

if updated != text:
    path.write_text(updated)

print(
    f"KINGDOMS_VMWARE_MANAGEMENT_NIC_PINNED|ethernet0={pinned}|type=static"
)
PY
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


vmrun_named_device_action() {
    local vm="$1"
    local action="$2"
    local attempts="${3:-15}"
    local delay="${4:-2}"
    local vmx command output rc attempt desired_pattern

    vmx="$(vmx_for "${vm}")"

    case "${action}" in
        connect)
            command='connectNamedDevice'
            desired_pattern='already.*connected|already in desired state'
            ;;
        disconnect)
            command='disconnectNamedDevice'
            desired_pattern='already.*disconnected|not.*connected|already in desired state'
            ;;
        *)
            fail "Unknown VMware named-device action for ${vm}: ${action}"
            ;;
    esac

    for ((attempt=1; attempt<=attempts; attempt++)); do
        output=""
        if output="$(vmrun -T ws "${command}" "${vmx}" ethernet0 2>&1)"; then
            rc=0
        else
            rc=$?
        fi

        if (( rc == 0 )); then
            echo "        [+] ${vm} ethernet0 runtime ${action} request accepted (attempt ${attempt})"
            return 0
        fi

        if grep -Eqi "${desired_pattern}" <<<"${output}"; then
            echo "        [+] ${vm} ethernet0 already ${action}ed"
            return 0
        fi

        if (( attempt == 1 || attempt % 5 == 0 )); then
            echo "        [*] retrying ${vm} ethernet0 runtime ${action} (attempt ${attempt}/${attempts}); vmrun rc=${rc}" >&2
            [[ -n "${output}" ]] && printf '            %s\n' "${output}" >&2
        fi

        (( attempt < attempts )) && sleep "${delay}"
    done

    echo "        [!] ${vm}: vmrun could not ${action} ethernet0 after ${attempts} attempts" >&2
    [[ -n "${output:-}" ]] && printf '            last vmrun output: %s\n' "${output}" >&2
    return 1
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

        pin_vmware_management_nic_identity "${vmx}" ||
            fail "${vm}: could not preserve VMware management NIC identity"

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

    # Provisioning is an authenticated management state, not just a VMX flag.
    # A clean/failsafe checkpoint may legitimately leave guests powered off.
    # When provisioning requests persistent NAT ON + runtime connect, power the
    # guest on before any WinRM/AD readiness check. Exercise/failsafe paths with
    # desired=FALSE deliberately preserve an already powered-off guest.
    if [[ "${desired}" == "TRUE" && "${action}" == "connect" ]] &&
       ! is_running "${vmx}"; then
        echo "        [*] VM is powered off; starting it for provisioning readiness"

        pin_vmware_management_nic_identity "${vmx}" ||
            fail "${vm}: could not preserve VMware management NIC identity"

        vmrun -T ws start "${vmx}" nogui >/dev/null

        wait_started "${vmx}" ||
            fail "${vm} did not start for provisioning readiness."

        sleep 2
    fi

    if is_running "${vmx}"; then
        vmrun_named_device_action "${vm}" "${action}" 15 2 ||
            fail "${vm}: could not reconcile ethernet0 runtime state to ${action}"
    elif [[ "${desired}" == "TRUE" || "${action}" == "connect" ]]; then
        fail "${vm}: runtime connect requested while VM is powered off"
    fi

    printf '        [+] ethernet0 startConnected=%s, runtime=%s\n' \
        "${desired}" \
        "${action}"
}

guestops_credential_value() {
    local vm="$1"
    local key="$2"
    local alias="${GUESTOPS_INVENTORY_ALIAS[${vm}]:-}"
    local inventory="${ROOT}/ad/GOAD/data/inventory_disable_vagrant"
    local line value

    [[ -n "${alias}" ]] ||
        fail "No VMware Guest Operations inventory alias is defined for ${vm}"

    [[ -f "${inventory}" ]] ||
        fail "Post-Vagrant inventory is missing: ${inventory}"

    line="$(
        grep -E "^${alias}[[:space:]]" "${inventory}" |
            head -n 1 || true
    )"

    [[ -n "${line}" ]] ||
        fail "No post-Vagrant credential entry found for ${vm} (${alias})"

    case "${key}" in
        ansible_user)
            value="$(
                sed -nE 's/.*[[:space:]]ansible_user=([^[:space:]]+).*/\1/p' <<<"${line}"
            )"
            ;;
        ansible_password)
            value="$(
                sed -nE 's/.*[[:space:]]ansible_password=([^[:space:]]+).*/\1/p' <<<"${line}"
            )"
            ;;
        *)
            fail "Unsupported Guest Operations credential key: ${key}"
            ;;
    esac

    [[ -n "${value}" ]] ||
        fail "Missing ${key} for ${vm} (${alias})"

    printf '%s\n' "${value}"
}

guestops_error() {
    local stage="$1" rc="$2" detail="${3:-No diagnostic returned by VMware Tools}"
    local guest_user="${4:-}" guest_password="${5:-}"

    # vmrun diagnostics can repeat arguments. Never include credentials in the
    # captured readiness output, including passwords containing glob syntax.
    [[ -z "${guest_password}" ]] || detail="${detail//"${guest_password}"/[REDACTED]}"
    [[ -z "${guest_user}" ]] || detail="${detail//"${guest_user}"/[REDACTED]}"
    detail="${detail//$'\r'/ }"
    detail="${detail//$'\n'/ }"
    detail="${detail//|/ }"
    printf 'KINGDOMS_GUESTOPS_ERROR|stage=%s|rc=%s|detail=%s\n' \
        "${stage}" "${rc}" "${detail:0:1500}"
}

vmware_guest_powershell_capture() {
    local vm="$1"
    local script="$2"
    local timeout_seconds="$3"
    local vmx guest_user guest_password wrapper wrapper_encoded
    local guest_output guest_script host_output host_script guest_file
    local upload_rc=1 run_rc=0 copy_rc=1 attempt
    local list_output="" list_rc=0 upload_detail="" run_detail="" copy_detail=""
    local started="${SECONDS}" remaining="${timeout_seconds}"

    (( timeout_seconds > 0 )) || return 124

    vmx="$(vmx_for "${vm}")" || return
    if list_output="$(timeout --kill-after=1 "${remaining}" vmrun -T ws list 2>&1)"; then
        :
    else
        list_rc=$?
        guestops_error list "${list_rc}" "${list_output}"
        (( SECONDS - started < timeout_seconds )) || return 124
        return "${list_rc}"
    fi
    if ! tail -n +2 <<<"${list_output}" | grep -Fxq "${vmx}"; then
        guestops_error state 125 "${vm} is not listed as running"
        return 125
    fi

    guest_user="$(guestops_credential_value "${vm}" ansible_user)" || return
    guest_password="$(guestops_credential_value "${vm}" ansible_password)" || return

    guest_script="C:\\Windows\\Temp\\kingdoms-guestops-${vm}-$$-${RANDOM}.ps1"
    guest_output="C:\\Windows\\Temp\\kingdoms-guestops-${vm}-$$-${RANDOM}.txt"
    host_script="$(mktemp "/tmp/kingdoms-guestops-${vm}.script.XXXXXX")"
    host_output="$(mktemp "/tmp/kingdoms-guestops-${vm}.output.XXXXXX")"
    printf '%s\n' "${script}" >"${host_script}"

    # Do not pass the readiness payload through vmrun argv. Large encoded
    # repair scripts can exceed VMware Workstation's internal argument buffer
    # and fail with "Buffer too small". Upload the script through Guest
    # Operations and keep runProgramInGuest limited to a small fixed wrapper.
    remaining=$((timeout_seconds - (SECONDS - started)))
    if (( remaining <= 0 )); then
        rm -f "${host_script}" "${host_output}"
        guestops_error prepare 124 "Probe deadline expired before guest script upload"
        return 124
    fi

    if upload_detail="$(timeout --kill-after=1 "${remaining}" vmrun -T ws \
        -gu "${guest_user}" \
        -gp "${guest_password}" \
        copyFileFromHostToGuest \
        "${vmx}" \
        "${host_script}" \
        "${guest_script}" 2>&1)"; then
        upload_rc=0
    else
        upload_rc=$?
    fi

    if (( upload_rc != 0 )); then
        rm -f "${host_script}" "${host_output}"
        guestops_error upload "${upload_rc}" "${upload_detail}" "${guest_user}" "${guest_password}"
        (( SECONDS - started < timeout_seconds )) || return 124
        return 126
    fi

    wrapper="$(cat <<POWERSHELL
\$result = '${guest_output}'
\$scriptPath = '${guest_script}'
\$stdout = "\${result}.stdout"
\$stderr = "\${result}.stderr"
\$arguments = @(
    '-NoProfile',
    '-NonInteractive',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    \$scriptPath
)
try {
    \$start = @{
        FilePath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
        ArgumentList = \$arguments
        RedirectStandardOutput = \$stdout
        RedirectStandardError = \$stderr
        Wait = \$true
        PassThru = \$true
        ErrorAction = 'Stop'
    }
    \$child = Start-Process @start

    \$parts = @()
    if (Test-Path \$stdout) {
        \$parts += Get-Content -Raw -Path \$stdout -ErrorAction SilentlyContinue
    }
    if (Test-Path \$stderr) {
        \$parts += Get-Content -Raw -Path \$stderr -ErrorAction SilentlyContinue
    }

    [System.IO.File]::WriteAllText(
        \$result,
        ((\$parts | Where-Object { \$_ }) -join [Environment]::NewLine),
        [System.Text.Encoding]::UTF8
    )

    exit \$child.ExitCode
}
catch {
    [System.IO.File]::WriteAllText(
        \$result,
        "KINGDOMS_GUESTOPS_WRAPPER_ERROR|\$((\$_.Exception.Message -replace '[|\\r\\n]', ' ').Trim())",
        [System.Text.Encoding]::UTF8
    )
    exit 1
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue \$stdout, \$stderr
}
POWERSHELL
)"

    wrapper_encoded="$(
        printf '%s' "${wrapper}" |
            iconv -f UTF-8 -t UTF-16LE |
            base64 -w0
    )"

    remaining=$((timeout_seconds - (SECONDS - started)))
    if (( remaining <= 0 )); then
        rm -f "${host_script}" "${host_output}"
        guestops_error prepare 124 "Probe deadline expired before guest execution"
        return 124
    fi

    if run_detail="$(timeout --kill-after=1 "${remaining}" vmrun -T ws \
        -gu "${guest_user}" \
        -gp "${guest_password}" \
        runProgramInGuest \
        "${vmx}" \
        'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' \
        -NoProfile \
        -NonInteractive \
        -EncodedCommand "${wrapper_encoded}" 2>&1)"; then
        run_rc=0
    else
        run_rc=$?
    fi

    for attempt in {1..5}; do
        remaining=$((timeout_seconds - (SECONDS - started)))
        (( remaining > 0 )) || break

        if copy_detail="$(timeout --kill-after=1 "${remaining}" vmrun -T ws \
            -gu "${guest_user}" \
            -gp "${guest_password}" \
            copyFileFromGuestToHost \
            "${vmx}" \
            "${guest_output}" \
            "${host_output}" 2>&1)"; then
            copy_rc=0
            break
        else
            copy_rc=$?
        fi

        (( run_rc == 0 )) || break

        remaining=$((timeout_seconds - (SECONDS - started)))
        (( remaining > 0 )) || break
        sleep 1
    done

    if (( copy_rc == 0 )); then
        cat "${host_output}"
    fi

    # Guest cleanup is best effort within the same deadline. Remove both the
    # uploaded script and its result; host-side temp files are always removed.
    for guest_file in "${guest_output}" "${guest_script}"; do
        remaining=$((timeout_seconds - (SECONDS - started)))
        (( remaining > 0 )) || break
        timeout --kill-after=1 "${remaining}" vmrun -T ws \
            -gu "${guest_user}" \
            -gp "${guest_password}" \
            deleteFileInGuest \
            "${vmx}" \
            "${guest_file}" >/dev/null 2>&1 || true
    done
    rm -f "${host_script}" "${host_output}"

    if (( run_rc != 0 )); then
        guestops_error run "${run_rc}" "${run_detail}" "${guest_user}" "${guest_password}"
        (( SECONDS - started < timeout_seconds )) || return 124
        return "${run_rc}"
    fi
    if (( copy_rc != 0 )); then
        guestops_error copy "${copy_rc}" "${copy_detail}" "${guest_user}" "${guest_password}"
        (( SECONDS - started < timeout_seconds )) || return 124
        return 126
    fi
    return "${run_rc}"
}
guestops_check() (
    local vm="${1:-GOAD-DC02}" vmx output rc
    [[ -n "${GUESTOPS_INVENTORY_ALIAS[${vm}]:-}" ]] ||
        fail "No Guest Operations inventory alias is defined for ${vm}"
    vmx="$(vmx_for "${vm}")" || exit
    [[ "$(get_start_connected "${vmx}")" == "FALSE" ]] ||
        fail "${vm}: GuestOps check requires persistent NAT to remain FALSE"

    echo "[*] ${vm}: one GuestOps output-capture probe (15s budget)"
    READINESS_TRANSPORT=guestops
    if output="$(powershell_capture "${vm}" \
        "Write-Output 'KINGDOMS_GUESTOPS_CAPTURE=PASS'" \
        "${AD_READINESS_PROBE_TIMEOUT_SECONDS}")"; then
        printf '%s\n' "${output}"
        grep -Fq 'KINGDOMS_GUESTOPS_CAPTURE=PASS' <<<"${output}" ||
            fail "${vm}: guest execution returned without the output-capture marker"
        echo "[+] ${vm} GuestOps execution and output capture passed"
    else
        rc=$?
        printf '%s\n' "${output}" >&2
        fail "${vm}: GuestOps output-capture probe failed (rc=${rc})"
    fi
)


guestops_time_check() (
    local vm="${1:-GOAD-DC02}"
    local domain="${DC_DOMAIN[${vm}]:-}"
    local parent_server="${DC_TIME_PARENT_SERVER[${vm}]:-}"
    local vmx output rc probe_script

    [[ -n "${domain}" ]] ||
        fail "${vm}: GuestOps time check requires a domain controller target"
    [[ -n "${parent_server}" ]] ||
        fail "${vm}: no child-domain parent time source is defined"

    vmx="$(vmx_for "${vm}")" || exit
    [[ "$(get_start_connected "${vmx}")" == "FALSE" ]] ||
        fail "${vm}: GuestOps time check requires persistent NAT to remain FALSE"

    probe_script="$(cat <<POWERSHELL
\$ErrorActionPreference = 'Continue'

\$source = (& w32tm.exe /query /source 2>\$null | Out-String).Trim().TrimEnd('.')
\$sourceRc = \$LASTEXITCODE
Write-Output "KINGDOMS_TIME_DIAG|stage=source|rc=\$sourceRc|source=\$source"

if (\$sourceRc -ne 0 -or -not \$source -or \$source -ine '${parent_server}') {
    \$sourceSafe = ((\$source -replace '[|\r\n]', ' ').Trim())
    if (-not \$sourceSafe) { \$sourceSafe = '<none>' }
    Write-Output "KINGDOMS_DC_TIME_NOT_READY|reason=source|source=\$sourceSafe|expected=${parent_server}"
    exit 0
}

\$locator = @(& nltest.exe '/dsgetdc:${domain}' /timeserv /force 2>&1 | ForEach-Object { "\$_" })
\$locatorRc = \$LASTEXITCODE
Write-Output "KINGDOMS_TIME_DIAG|stage=locator|rc=\$locatorRc"
if (\$locatorRc -ne 0) {
    \$detail = ((\$locator -join ' ') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_DC_TIME_NOT_READY|reason=advertising|rc=\$locatorRc|detail=\$detail"
    exit 0
}

Write-Output "KINGDOMS_DC_TIME_READY|source=\$source|parent=${parent_server}"
POWERSHELL
)"

    echo "[*] ${vm}: one exact child-domain time probe through GuestOps (15s budget)"
    READINESS_TRANSPORT=guestops
    output=""
    if output="$(powershell_capture "${vm}" "${probe_script}" "${AD_READINESS_PROBE_TIMEOUT_SECONDS}")"; then
        printf '%s\n' "${output}"
        marker="$(
            last_marker_line "${output}"                 'KINGDOMS_DC_TIME_READY|'                 'KINGDOMS_DC_TIME_NOT_READY|'
        )"
        if [[ -n "${marker}" ]]; then
            echo "[+] ${vm} GuestOps child-time probe returned a readiness marker"
        else
            fail "${vm}: GuestOps child-time probe returned without a readiness marker"
        fi
    else
        rc=$?
        printf '%s\n' "${output}" >&2
        fail "${vm}: GuestOps child-time probe failed (rc=${rc})"
    fi
)
powershell_capture() {
    local vm="$1"
    local script="$2"
    local timeout_seconds="$3"

    case "${READINESS_TRANSPORT:-vagrant}" in
        vagrant)
            vagrant_powershell_capture "${vm}" "${script}" "${timeout_seconds}"
            ;;
        guestops)
            vmware_guest_powershell_capture "${vm}" "${script}" "${timeout_seconds}"
            ;;
        *)
            fail "Unknown readiness transport: ${READINESS_TRANSPORT}"
            ;;
    esac
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
last_marker_line() {
    local text="$1"
    shift
    local line prefix
    local marker=""

    while IFS= read -r line; do
        for prefix in "$@"; do
            case "${line}" in
                *"${prefix}"*)
                    marker="${prefix}${line#*"${prefix}"}"
                    ;;
            esac
        done
    done <<<"${text}"

    printf '%s\n' "${marker}"
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
    local capture_rc=0
    local transport_marker=""
    local last_state="reason=transport"
    local consecutive_source_failures=0
    local consecutive_transport_failures=0
    local repair_attempted=0
    local repair_deferred=0
    local repair_invocations=0
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

# Do not gate W32Time recovery on a generic nltest parent-domain lookup.
# DsGetDcName can transiently return 1355 after lifecycle transitions even when
# the routed parent path, DNS records and expected PDC are already healthy.
# Prove the deterministic parent PDC through DNS instead, then prove NTP reachability.
\$parentPdcQuery = '_ldap._tcp.pdc._msdcs.${parent_domain}'
\$parentPdcRecords = @(
    Resolve-DnsName -Name \$parentPdcQuery -Server 127.0.0.1 -Type SRV -ErrorAction SilentlyContinue |
        Where-Object { \$_.Type -eq 'SRV' }
)

if (\$parentPdcRecords.Count -eq 0) {
    Write-Output "KINGDOMS_DC_TIME_REPAIR_DEFERRED|stage=parent_pdc_dns|detail=no SRV answer for \$parentPdcQuery"
    exit 0
}

\$parentPdcTargets = @(
    \$parentPdcRecords |
        ForEach-Object { "\$($_.NameTarget)".TrimEnd('.') }
)

if (-not (\$parentPdcTargets | Where-Object { \$_ -ieq '${parent_server}' })) {
    \$detail = ((\$parentPdcTargets -join ',') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_DC_TIME_REPAIR_DEFERRED|stage=parent_pdc_dns|detail=expected ${parent_server}; got \$detail"
    exit 0
}
# Prove UDP/123 reaches the expected forest-root PDC before changing W32Time.
# A temporarily unavailable NTP path is also a prerequisite wait condition.
\$strip = @(& w32tm.exe /stripchart /computer:${parent_server} /samples:2 /dataonly 2>&1 | ForEach-Object { "\$_" })
\$stripRc = \$LASTEXITCODE
if (\$stripRc -ne 0) {
    \$detail = ((\$strip -join ' ') -replace '[|\r\n]', ' ').Trim()
    Write-Output "KINGDOMS_DC_TIME_REPAIR_DEFERRED|stage=parent_ntp_path|rc=\$stripRc|detail=\$detail"
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
        # Prime DC Locator best-effort immediately before rediscovery. A transient
        # 1355 here is not a hard prerequisite: DNS already proved the expected
        # forest-root PDC and stripchart proved the NTP path.
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
        transport_marker=""
        capture_rc=0

        if output="$(powershell_capture "${vm}" "${probe_script}" "${probe_timeout}")"; then
            capture_rc=0
        else
            capture_rc=$?
        fi

        # Parse the guest result independently from the wrapper exit status.
        # Each GuestOps result path is unique per invocation, so a marker copied
        # from this probe is current evidence rather than stale output.
        marker="$(
            last_marker_line "${output}"                 'KINGDOMS_DC_TIME_READY|'                 'KINGDOMS_DC_TIME_NOT_READY|'
        )"

        if [[ "${marker}" == KINGDOMS_DC_TIME_READY\|* ]]; then
            echo "        [+] ${vm} child-domain time hierarchy ready (${parent_server})"
            return 0
        fi

        if [[ "${marker}" == KINGDOMS_DC_TIME_NOT_READY\|* ]]; then
            consecutive_transport_failures=0
            last_state="${marker#KINGDOMS_DC_TIME_NOT_READY|}"
        else
            transport_marker="$(
                last_marker_line "${output}" 'KINGDOMS_GUESTOPS_ERROR|'
            )"
            consecutive_transport_failures=$((consecutive_transport_failures + 1))

            if [[ -n "${transport_marker}" ]]; then
                last_state="reason=transport|capture_rc=${capture_rc}|${transport_marker}"
            elif (( capture_rc != 0 )); then
                last_state="reason=transport|capture_rc=${capture_rc}|detail=no_guestops_marker"
            else
                last_state="reason=no_time_marker|capture_rc=0"
            fi

            if [[ "${READINESS_TRANSPORT:-vagrant}" == "guestops" ]] &&
               (( consecutive_transport_failures >= 3 )); then
                echo "        [!] ${vm} child-time GuestOps probe failed repeatedly; ${last_state}" >&2
                if [[ -n "${output}" ]]; then
                    echo "        [!] last GuestOps child-time output follows:" >&2
                    printf '%s\n' "${output}" | tail -80 >&2
                fi
                fail "${vm} child-domain time probe transport failed 3 consecutive times after AD readiness"
            fi
        fi

        if [[ "${last_state}" == reason=source\|* ]]; then
            consecutive_source_failures=$((consecutive_source_failures + 1))
        else
            consecutive_source_failures=0
        fi

        if (( repair_attempted == 0 && consecutive_source_failures >= 6 )); then
            echo "        [!] ${vm} AD is ready but child-domain time stayed off the parent hierarchy for ~30s"
            echo "        [*] checking parent time prerequisites before bounded W32Time recovery"
            repair_invocations=$((repair_invocations + 1))

            elapsed=$((SECONDS - started))
            remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
            (( remaining > 0 )) || break
            repair_timeout="${AD_REPAIR_TIMEOUT_SECONDS}"
            (( remaining < repair_timeout )) && repair_timeout="${remaining}"

            output=""
            marker=""
            transport_marker=""
            capture_rc=0

            if output="$(powershell_capture "${vm}" "${repair_script}" "${repair_timeout}")"; then
                capture_rc=0
            else
                capture_rc=$?
            fi

            marker="$(
                last_marker_line "${output}"                     'KINGDOMS_DC_TIME_REPAIRED|'                     'KINGDOMS_DC_TIME_REPAIR_DEFERRED|'                     'KINGDOMS_DC_TIME_REPAIR_FAILED|'
            )"

            if [[ "${marker}" == KINGDOMS_DC_TIME_REPAIRED\|* ]]; then
                repair_attempted=1
                echo "        [+] ${vm} child-domain time recovery completed: ${marker}"
            elif [[ "${marker}" == KINGDOMS_DC_TIME_REPAIR_DEFERRED\|* ]]; then
                repair_deferred=$((repair_deferred + 1))
                last_state="reason=repair_deferred|${marker#KINGDOMS_DC_TIME_REPAIR_DEFERRED|}"
                echo "        [*] ${vm} child-domain time repair deferred; parent prerequisite is not ready yet"
                echo "            ${marker}"
            elif [[ "${marker}" == KINGDOMS_DC_TIME_REPAIR_FAILED\|* ]]; then
                repair_attempted=1
                fail "${vm} child-domain time recovery failed after prerequisites were proven: ${marker}"
            elif (( capture_rc != 0 )); then
                transport_marker="$(
                    last_marker_line "${output}" 'KINGDOMS_GUESTOPS_ERROR|'
                )"
                fail "${vm} child-domain time recovery transport failed (rc=${capture_rc}): ${transport_marker:-no GuestOps marker}"
            else
                fail "${vm} child-domain time recovery returned without a terminal marker"
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
    fail "${vm} child-domain time hierarchy did not converge within 300s; ${last_state}; repair_attempted=${repair_attempted}; repair_deferred=${repair_deferred}; repair_invocations=${repair_invocations}"
}

wait_domain_controller_ready() {
    local vm="$1"
    local domain="${DC_DOMAIN[${vm}]}"
    local fqdn="${DC_FQDN[${vm}]}"
    local script
    local basic_ready=0
    local output=""
    local last_state="reason=transport"

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

        output=""
        if output="$(powershell_capture "${vm}" "${script}" "${probe_timeout}")"; then
            if grep -Fq 'KINGDOMS_DC_RUNTIME_READY' <<<"${output}"; then
                basic_ready=1
                break
            fi
            last_state="reason=guest_probe_no_ready_marker"
        else
            if [[ -n "${output}" ]]; then
                last_state="reason=guest_probe_failure"
            else
                last_state="reason=transport"
            fi
        fi

        elapsed=$((SECONDS - started))
        remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))
        (( remaining < 0 )) && remaining=0
        if (( elapsed >= next_report )); then
            echo "        [*] waiting for ${vm} AD runtime readiness (${elapsed}s elapsed, ${remaining}s remaining); ${last_state}"
            if [[ "${READINESS_TRANSPORT:-vagrant}" == "vagrant" ]]; then
                echo "        [*] re-requesting ${vm} ethernet0 runtime connection as a bounded VMware transport self-heal"
                vmrun_named_device_action "${vm}" connect 3 2 || true
            fi
            next_report=$((next_report + 30))
        fi

        (( remaining > 0 )) || break
        if (( remaining < AD_READINESS_RETRY_DELAY_SECONDS )); then
            sleep "${remaining}"
        else
            sleep "${AD_READINESS_RETRY_DELAY_SECONDS}"
        fi
    done
    if (( basic_ready != 1 )); then
        echo "        [!] ${vm} AD readiness timed out; last_state=${last_state}" >&2
        if [[ -n "${output}" ]]; then
            echo "        [!] last PowerShell readiness output follows:" >&2
            printf '%s\n' "${output}" | tail -80 >&2
        fi
        fail "${vm} did not regain AD/DC Locator readiness for ${domain} within 300s; ${last_state}"
    fi

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

        if output="$(powershell_capture "${vm}" "${script}" "${probe_timeout}")"; then
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
            if output="$(powershell_capture "${vm}" "${repair_script}" "${repair_timeout}")"; then
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

    is_running "${vmx}" ||
        fail "${vm}: authenticated exercise-readiness probe requires the VM to be powered on"

    echo "        [*] proving authenticated readiness through VMware Guest Operations"
    echo "            ethernet0 remains persistently OFF and runtime disconnected"

    READINESS_TRANSPORT=guestops

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

    persistent="$(get_start_connected "${vmx}")"
    [[ "${persistent}" == "FALSE" ]] ||
        fail "${vm}: readiness probe changed persistent NAT isolation"

    echo "        [+] ${vm} authenticated post-reboot readiness proven through VMware Guest Operations"
)
configure_windows_nat_exercise() {
    local vm

    # Members reboot first while their DCs are still healthy. Every restarted
    # guest keeps ethernet0.startConnected=FALSE. Authenticated Windows/domain
    # readiness is proven through VMware Guest Operations with the management
    # NIC still disconnected.
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

    local router_status=0
    local router_output=''

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

    if router_output="$(
        cd "${PROVIDER}"
        GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/router-ssh.sh" \
            'sudo nft list chain inet goad_nomad forward' 2>&1
    )"; then
        printf '%s\n' "${router_output}"
    else
        echo "[UNAVAILABLE] router management/policy query failed"
        printf '%s\n' "${router_output}"
        router_status=1
    fi

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

    return "${router_status}"
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

enter_exercise_failsafe() {
    echo "============================================================"
    echo "ENTERING GOAD_NOMAD FAIL-CLOSED EXERCISE RECOVERY"
    echo "============================================================"

    sudo -v
    verify_windows_layout

    # Mark the deployment degraded before touching state. Only a fully verified
    # router + host isolation contract may promote this marker back to exercise.
    set_state recovery-required

    echo
    echo "[*] Removing host provisioning routes first"
    sudo bash "${ROUTES}" disable

    echo
    echo "[*] Restoring persistent Windows NAT isolation without claiming guest readiness"

    local vm
    local failed=0
    local router_output=''

    for vm in "${DOMAIN_MEMBERS[@]}" "${EXERCISE_DOMAIN_CONTROLLERS[@]}"; do
        if ! ( ensure_vm_nat_state "${vm}" FALSE disconnect ); then
            echo "        [!] failsafe NAT isolation failed for ${vm}" >&2
            failed=1
        fi
    done

    if ! ( verify_persistent_state FALSE ); then
        failed=1
    fi

    if (( failed != 0 )); then
        fail "Fail-closed recovery could not prove host routes/NAT isolation; mode remains recovery-required."
    fi

    echo
    echo "[+] Host-side provisioning paths are isolated."
    echo "[*] Applying and verifying router exercise policy"

    if ! apply_router_policy exercise; then
        echo "[!] Router exercise policy could not be applied." >&2
        fail "Host isolation is proven, but router policy is unverified; mode remains recovery-required."
    fi

    if ! router_output="$(
        cd "${PROVIDER}"
        GOAD_PROVIDER_DIR="${PROVIDER}" bash "${ROOT}/scripts/router-ssh.sh" \
            'sudo nft list chain inet goad_nomad forward' 2>&1
    )"; then
        printf '%s\n' "${router_output}" >&2
        fail "Host isolation is proven, but router policy verification failed; mode remains recovery-required."
    fi

    printf '%s\n' "${router_output}" | grep -Fq 'policy drop;' ||
        fail "Router is reachable but deny-by-default policy is not active; mode remains recovery-required."

    set_state exercise

    echo
    echo "[+] FAIL-CLOSED network isolation restored and router policy verified."
    echo "    IMPORTANT: this path does not claim AD/domain readiness."
    echo "    Run the normal exercise lifecycle/readiness validation before continuing the lab."
}

guestops_readiness_check() (
    local vm="${1:-GOAD-DC02}"
    local kind=""

    if [[ -n "${DC_DOMAIN[${vm}]:-}" ]]; then
        kind="dc"
    elif [[ -n "${MEMBER_DOMAIN[${vm}]:-}" ]]; then
        kind="member"
    else
        fail "Unknown Windows VM for GuestOps readiness check: ${vm}"
    fi

    echo "============================================================"
    echo "TARGETED VMWARE GUESTOPS READINESS"
    echo "============================================================"
    echo "VM:   ${vm}"
    echo "Kind: ${kind}"

    prove_isolated_guest_ready "${vm}" "${kind}"

    echo
    echo "[+] ${vm} targeted GuestOps readiness passed"
)
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
    require_command vmrun
    require_command vagrant
    require_command python3
    require_command ip
    require_command timeout
    require_command iconv
    require_command base64
    require_command mktemp

    [[ -f "${ROUTES}" ]] ||
        fail "${ROUTES} is missing."

    [[ -d "${POLICY_DIR}" ]] ||
        fail "${POLICY_DIR} is missing."

    resolve_provider

    case "${1:-status}" in
        exercise)
            enter_exercise_mode
            ;;

        exercise-failsafe)
            enter_exercise_failsafe
            ;;

        provisioning)
            enter_provisioning_mode
            ;;

        status)
            show_status
            ;;

        guestops-check)
            guestops_check "${2:-GOAD-DC02}"
            ;;

        guestops-readiness-check)
            guestops_readiness_check "${2:-GOAD-DC02}"
            ;;

        guestops-time-check)
            guestops_time_check "${2:-GOAD-DC02}"
            ;;

        *)
            echo "Usage: $0 {exercise|exercise-failsafe|provisioning|status|guestops-check [VM]|guestops-readiness-check [VM]|guestops-time-check [VM]}" >&2
            exit 2
            ;;
    esac
}

main "$@"
