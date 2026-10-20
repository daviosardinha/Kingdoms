#!/usr/bin/env bash
# Read-only managed-host policy audit. No password probes or lab reconfiguration.
set -Eeuo pipefail
readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_HOSTS='dc02:srv02:ws01'
REQUIRE_SESSIONS=false
PHASE01=false
SOURCE_ONLY=false
BOT_MODE=legacy
usage() {
    printf '%s\n' \
        'Usage: bash scripts/validate-rdp-runtime.sh [--source-only] [--host ws01] [--require-sessions] [--phase01] [--bot-mode legacy|headless]' \
        'Default: source gate, 3389 reachability, effective policy for all three NORTH hosts.' \
        '--require-sessions: also require observed Robb/CASTELBLACK and Rickon/WS01 RDP sessions.' \
        '--phase01: run the existing read-only Phase 01 validator unchanged.' \
        '--bot-mode: legacy requires WINTERFELL connect_bot healthy; headless requires it disabled.' \
        'No credential attempts are made. A policy PASS is not a fresh desktop-logon PASS.' \
        'Run from the configured Kingdoms management/operator host with NORTH connectivity.' \
        'Optional: KINGDOMS_RDP_ANSIBLE, KINGDOMS_RDP_INVENTORY, KINGDOMS_RDP_DATA_INVENTORY, KINGDOMS_RDP_SCENARIO_CONFIG, KINGDOMS_RDP_LOG_DIR.'
}
fail() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }
while [[ $# -gt 0 ]]; do
    case "$1" in
        --source-only) SOURCE_ONLY=true; shift ;;
        --host)
            [[ "${2:-}" == ws01 ]] || fail 'Only --host ws01 is supported; omit for all three hosts'
            TARGET_HOSTS=ws01; shift 2 ;;
        --require-sessions) REQUIRE_SESSIONS=true; shift ;;
        --phase01) PHASE01=true; shift ;;
        --bot-mode)
            [[ "${2:-}" == legacy || "${2:-}" == headless ]] || fail '--bot-mode must be legacy or headless'
            BOT_MODE="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; fail "Unknown argument: $1" ;;
    esac
done
if ${SOURCE_ONLY} && { ${REQUIRE_SESSIONS} || ${PHASE01} || [[ "${TARGET_HOSTS}" != 'dc02:srv02:ws01' ]] || [[ "${BOT_MODE}" != legacy ]]; }; then
    fail '--source-only cannot be combined with runtime options'
fi
cd "${ROOT}"
bash scripts/verify-test-source.sh
python3 -m unittest discover -s tests -p 'test_rdp_*.py'
if ${SOURCE_ONLY}; then
    printf '[PASS] RDP source contract only; Windows runtime has NOT been tested.\n'
    exit 0
fi
for command in timeout nc; do command -v "${command}" >/dev/null || fail "Missing ${command}"; done
ANSIBLE_PLAYBOOK="${KINGDOMS_RDP_ANSIBLE:-}"
if [[ -z "${ANSIBLE_PLAYBOOK}" ]]; then
    for candidate in "$(command -v ansible-playbook 2>/dev/null || true)" \
        "${ROOT}/.venv/bin/ansible-playbook" "${ROOT}/venv/bin/ansible-playbook" \
        "${HOME}/.goad/.venv/bin/ansible-playbook" "${HOME}/.local/bin/ansible-playbook"; do
        if [[ -n "${candidate}" && -x "${candidate}" ]]; then ANSIBLE_PLAYBOOK="${candidate}"; break; fi
    done
fi
[[ -n "${ANSIBLE_PLAYBOOK}" && -x "${ANSIBLE_PLAYBOOK}" ]] || fail 'Set KINGDOMS_RDP_ANSIBLE to ansible-playbook'
INVENTORY="${KINGDOMS_RDP_INVENTORY:-${ROOT}/ad/GOAD/providers/vmware/inventory}"
DATA_INVENTORY="${KINGDOMS_RDP_DATA_INVENTORY:-${ROOT}/ad/GOAD/data/inventory}"
SCENARIO_CONFIG="${KINGDOMS_RDP_SCENARIO_CONFIG:-}"
[[ -f "${INVENTORY}" ]] || fail "Inventory not found: ${INVENTORY}"
[[ -f "${DATA_INVENTORY}" ]] || fail "Data inventory not found: ${DATA_INVENTORY}"
SCENARIO_EXTRA=()
if [[ -n "${SCENARIO_CONFIG}" ]]; then
    [[ -f "${SCENARIO_CONFIG}" ]] || fail "Scenario JSON not found: ${SCENARIO_CONFIG}"
    # The legacy RDP playbook defaults to GOAD vars_files. Explicit scenario
    # extra-vars override that for the same NORTH profile without affecting GOAD.
    SCENARIO_EXTRA=(-e "@${SCENARIO_CONFIG}")
fi
readonly LOG_DIR="${KINGDOMS_RDP_LOG_DIR:-$(mktemp -d /tmp/kingdoms-rdp-validation.XXXXXX)}"
mkdir -p "${LOG_DIR}"
declare -a HOSTS=(WINTERFELL CASTELBLACK WS01)
declare -a IPS=(10.4.10.11 10.4.10.22 10.4.10.31)
if [[ "${TARGET_HOSTS}" == ws01 ]]; then HOSTS=(WS01); IPS=(10.4.10.31); fi
for index in "${!HOSTS[@]}"; do
    timeout 5 nc -zw3 "${IPS[$index]}" 3389 || fail "RDP unreachable: ${HOSTS[$index]} (not an authorization denial)"
done
(
    cd "${ROOT}/ansible"
    ANSIBLE_CONFIG="${ROOT}/ansible/ansible.cfg" timeout 900 "${ANSIBLE_PLAYBOOK}" \
        -i "${DATA_INVENTORY}" -i "${INVENTORY}" \
        validate-kingdoms-rdp.yml \
        -e "rdp_target_hosts=${TARGET_HOSTS}" -e "rdp_require_sessions=${REQUIRE_SESSIONS}" -e "rdp_bot_mode=${BOT_MODE}" \
        "${SCENARIO_EXTRA[@]}"
) 2>&1 | tee "${LOG_DIR}/rdp-policy.log"
for host in "${HOSTS[@]}"; do
    grep -Fq "RDP_POLICY_CONTRACT=${host}:PASS" "${LOG_DIR}/rdp-policy.log" || fail "Missing evidence for ${host}"
done
if ${PHASE01}; then
    python3 scripts/validate-phase01.py --out "${LOG_DIR}/phase01" 2>&1 | tee "${LOG_DIR}/phase01.log"
fi
printf '\n[PASS] Requested RDP policy checks completed. Logs: %s\n' "${LOG_DIR}"
printf '%s\n' \
    '[NOT RUN] Fresh desktop logins for the 15 user/host combinations.' \
    '[NOT RUN] Clean rebuild, migration/idempotence, reset and unrelated service acceptance tests.' \
    'Existing session evidence may predate a policy change; perform fresh logins for release acceptance.'
