#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Keep the original GOAD invocation unchanged. NORTH explicitly selects the
# reduced Vagrantfile so its deterministic MAC roster comes from Course 1.
if [[ "${1:-}" == --north ]]; then
    shift
    readonly CANONICAL_VAGRANTFILE="${ROOT}/ad/NORTH/providers/vmware/Vagrantfile"
else
    readonly CANONICAL_VAGRANTFILE="${ROOT}/ad/GOAD/providers/vmware/Vagrantfile"
fi
readonly VMRUN_BIN="${GOAD_KINGDOMS_VMRUN_BIN:-$(command -v vmrun 2>/dev/null || true)}"

fail() {
    printf '[FAIL] %s\n' "$*" >&2
    exit 1
}

provider_dir="${1:-${GOAD_PROVIDER_DIR:-}}"
[[ -n "${provider_dir}" ]] || fail 'provider directory is required as argument 1 or GOAD_PROVIDER_DIR'
[[ -d "${provider_dir}" ]] || fail "provider directory does not exist: ${provider_dir}"
[[ -f "${CANONICAL_VAGRANTFILE}" ]] || fail "canonical GOAD VMware Vagrantfile is missing: ${CANONICAL_VAGRANTFILE}"
[[ -n "${VMRUN_BIN}" && -x "${VMRUN_BIN}" ]] || fail 'vmrun is required to inspect running VMware guests'

provider_real="$(realpath -m "${provider_dir}")"

mapfile -t protected_macs < <(
    grep -Eo ':mac[[:space:]]*=>[[:space:]]*"([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}"' "${CANONICAL_VAGRANTFILE}" \
        | sed -E 's/.*"(([[:xdigit:]]{2}:){5}[[:xdigit:]]{2})"/\1/' \
        | tr '[:upper:]' '[:lower:]' \
        | sort -u
)

[[ ${#protected_macs[@]} -gt 0 ]] || fail 'no deterministic segmented MAC identities were found in the canonical Vagrantfile'

declare -A protected=()
for mac in "${protected_macs[@]}"; do
    protected["${mac}"]=1
done

if ! running_output="$(${VMRUN_BIN} -T ws list 2>&1)"; then
    printf '%s\n' "${running_output}" >&2
    fail 'vmrun could not enumerate running VMware guests'
fi

conflicts=()
while IFS= read -r vmx; do
    [[ -n "${vmx}" ]] || continue
    vmx_real="$(realpath -m "${vmx}")"

    # VMs belonging to the selected provider are allowed to be already running.
    # This matters for idempotent start/recovery and focused WS01 provisioning.
    if [[ "${vmx_real}" == "${provider_real}/"* ]]; then
        continue
    fi

    [[ -f "${vmx_real}" ]] || fail "running VMX reported by vmrun is unreadable: ${vmx_real}"

    while IFS= read -r mac; do
        mac="${mac,,}"
        if [[ -n "${protected[${mac}]:-}" ]]; then
            conflicts+=("${mac}|${vmx_real}")
        fi
    done < <(
        sed -nE 's/^[Ee][Tt][Hh][Ee][Rr][Nn][Ee][Tt][0-9]+\.[Aa][Dd][Dd][Rr][Ee][Ss][Ss][[:space:]]*=[[:space:]]*"(([[:xdigit:]]{2}:){5}[[:xdigit:]]{2})".*/\1/p' "${vmx_real}"
    )
done < <(printf '%s\n' "${running_output}" | tail -n +2)

if [[ ${#conflicts[@]} -gt 0 ]]; then
    printf '\n[FAIL] Another running VMware guest is using GOAD Kingdoms deterministic segmented MAC identity/identities.\n' >&2
    printf 'Selected provider: %s\n' "${provider_real}" >&2
    printf '\nConflicts:\n' >&2
    for conflict in "${conflicts[@]}"; do
        mac="${conflict%%|*}"
        vmx="${conflict#*|}"
        printf '  MAC %-17s  %s\n' "${mac}" "${vmx}" >&2
    done
    printf '\nRunning two segmented GOAD Kingdoms instances on the same VMware vmnets causes duplicate MAC/IP registration and broken L2 connectivity.\n' >&2
    printf 'Stop the conflicting instance before install/start/ws01 continues.\n\n' >&2
    exit 1
fi

printf '[PASS] no conflicting running GOAD Kingdoms segmented instance detected\n'
printf '       provider=%s\n' "${provider_real}"
