#!/usr/bin/env bash
# Kingdoms Course 1: ONE offline source-to-preview acceptance command.
# Never provisions, starts, stops, resets, snapshots or configures a VM.
set -Eeuo pipefail

readonly ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
umask 077
export PYTHONDONTWRITEBYTECODE=1

REFERENCE_PROVIDER=""
SURVEY_HOST=0
PRIVATE_WORKDIR=""

usage() {
    cat <<'USAGE'
Usage:
  bash scripts/course1/validate-course1.sh [--reference-provider ABSOLUTE_PATH] [--survey-host]

Runs the complete offline Course 1 gate:
  1. Clean, pinned, upstream-matched Kingdoms Git source
  2. Course 1 source/topology, binding, artifact, lifecycle and isolation tests
  3. Existing lab-mode AD readiness source regression
  4. Bash syntax, four-VM generator preview, Ruby + Ansible artifact parsers
  5. Static lifecycle matrix for both reference and reduced profiles
  6. Ephemeral credential-protected preview: source-integrity verification
  7. Negative gate: reduced preview MUST be rejected by installed-instance binding
  8. Negative same-host cohosting gate: shared vmnets/MACs/IPs must be detected
  9. Optional read-only reference-instance startup/stop/reset planning
 10. Optional compact read-only VMware host survey (no network/VM changes)
 11. Optional three-zone proposal comparison with observed host identities

--reference-provider must point at an EXISTING six-VM Kingdoms instance
provider directory; it is inspected read-only and never operated on.
--survey-host queries ip address/routes, VMware network config and vmrun list.
Incomplete visibility stops with nonzero; no vmnets are allocated.
The temporary preview is automatically removed on success OR failure.
USAGE
}

fail() {
    printf '\n[FAIL] %s\n' "$*" >&2
    exit 1
}
step() {
    printf '\n===== KINGDOMS COURSE 1: %s =====\n' "$*"
}
cleanup() {
    if [[ -n "${PRIVATE_WORKDIR}" && -d "${PRIVATE_WORKDIR}" ]]; then
        rm -rf -- "${PRIVATE_WORKDIR}"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while [[ $# -gt 0 ]]; do
    case "$1" in
        --survey-host)
            SURVEY_HOST=1
            shift
            ;;
        --reference-provider)
            [[ $# -ge 2 && -n "$2" && "$2" == /* ]] ||
                fail "--reference-provider requires an existing absolute directory"
            REFERENCE_PROVIDER="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            fail "unknown option: $1"
            ;;
    esac
done

command -v git >/dev/null || fail "git is missing"
command -v python3 >/dev/null || fail "python3 is missing"
command -v ruby >/dev/null || fail "ruby is missing"
command -v mktemp >/dev/null || fail "mktemp is missing"

step "01 - Pin and verify committed Git source"
readonly HEAD_SHA="$(git rev-parse HEAD)"
bash scripts/verify-test-source.sh "${HEAD_SHA}"

step "02 - Complete offline contract regression suite"
python3 -m unittest \
    tests.test_course1_reduced_profile \
    tests.test_course1_runtime_contract \
    tests.test_course1_instance_binding \
    tests.test_course1_external_artifacts \
    tests.test_course1_lifecycle_plan \
    tests.test_course1_bound_lifecycle \
    tests.test_course1_source_gate \
    tests.test_course1_network_plan \
    tests.test_course1_host_fit \
    tests.test_course1_host_survey \
    tests.test_lab_mode_ad_readiness

step "03 - Bash syntax regression"
bash -n scripts/course1/validate-course1.sh \
        scripts/lab-mode.sh scripts/verify-test-source.sh
echo "[PASS] Bash syntax"

step "04 - Generated recipe and native Ruby/Ansible parsing"
python3 scripts/course1/generate-profile.py --check
python3 scripts/course1/check-rendered-artifacts.py --check

step "05 - Offline lifecycle matrix (two profiles x five actions)"
for profile in full-goad course1-fall-of-the-north; do
    for action in start stop reset provisioning exercise; do
        python3 -m goad.course1_lifecycle_plan --check \
            --profile "${profile}" --action "${action}" >/dev/null
    done
done
python3 -m goad.course1_lifecycle_plan --check \
    --profile course1-fall-of-the-north \
    --action start --machine GOAD-WS01 >/dev/null
echo "[PASS] All 11 static plans generated, activation still blocked"

step "06 - Private ephemeral preview, compared with canonical source"
PRIVATE_WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/kingdoms-course1-check.XXXXXXXX")"
readonly PREVIEW="${PRIVATE_WORKDIR}/preview"
python3 scripts/course1/generate-profile.py \
    --output "${PREVIEW}" --acknowledge-lab-credentials
python3 -m goad.course1_source_gate --check-preview "${PREVIEW}"

step "07 - Negative activation gate for four-guest candidate"
set +e
binding_output="$(python3 -m goad.course1_instance_binding \
    --check-provider "${PREVIEW}/instance-preview" 2>&1)"
binding_status=$?
set -e
if [[ ${binding_status} -eq 0 ||
      "${binding_output}" != *"reduced profile activation is blocked"* ]]; then
    fail "Four-VM preview was not rejected for the expected instance-binding reason"
fi
echo "[PASS] Four-VM preview cannot be activated as installed instance"

step "08 - Negative same-host network collision gate"
python3 -m goad.course1_network_plan --assert-preview-unsafe "${PREVIEW}"

step "08b - Nondeployable three-zone candidate source contract"
python3 -m goad.course1_host_fit \
    --check-proposal docs/course1-network-candidate.example.json

if [[ -n "${REFERENCE_PROVIDER}" ]]; then
    step "09 - Optional installed reference read-only binding"
    [[ -d "${REFERENCE_PROVIDER}" ]] ||
        fail "reference provider directory does not exist"
    for action in start stop reset provisioning exercise; do
        python3 -m goad.course1_bound_lifecycle \
            --check-provider "${REFERENCE_PROVIDER}" \
            --action "${action}" >/dev/null
    done
    echo "[PASS] Installed six-VM instance is bound to five static plans"
fi

if [[ "${SURVEY_HOST}" -eq 1 ]]; then
    step "10 - Read-only live VMware host survey"
    python3 -m goad.course1_host_survey --check --summary
    step "11 - Compare nondeployable proposal to observed host"
    python3 -m goad.course1_host_fit \
        --check-proposal docs/course1-network-candidate.example.json --inspect-host
fi

step "COMPLETE"
printf '[PASS] All offline Course 1 validation gates passed at %s\n' "${HEAD_SHA}"
echo "[BLOCKED] Four-VM installation/start/stop/reset still NOT authorized"
echo "[INFO] Ephemeral preview is deleted automatically; no guest was touched"
