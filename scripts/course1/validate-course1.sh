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
     (stage 08c renders a private isolated three-NIC VMware/router preview)
 10. Optional single VMware host and registered VMX read-only survey
 11. Optional proposal comparison with running and registered VM identities
 12. Staged four-host Ansible + read-only topology dependency audit
 13. Immutable candidate integrity + future instance layout; Vagrant blocked
 14. Read-only VMware pre/post allocation stage detection; no host writes
 15. Mocked transactional VMware apply/rollback regressions (NO live changes)
 16. NORTH-only host-address helper/timer source and isolated status tests

--reference-provider must point at an EXISTING six-VM Kingdoms instance
provider directory; it is inspected read-only and never operated on.
--survey-host queries ip address/routes, VMware network config, vmrun list,
and ~/.vmware/inventory.vmls for registered (including powered-off) VMX identities.
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
    tests.test_kingdoms_vmware_profile \
    tests.test_kingdoms_north_mode_source \
    tests.test_kingdoms_foundation \
    tests.test_course1_lab_registry \
    tests.test_course1_instance_binding \
    tests.test_course1_external_artifacts \
    tests.test_course1_lifecycle_plan \
    tests.test_course1_bound_lifecycle \
    tests.test_course1_source_gate \
    tests.test_course1_network_plan \
    tests.test_course1_host_fit \
    tests.test_course1_vmware_candidate \
    tests.test_course1_install_stage \
    tests.test_course1_isolated_native_artifacts \
    tests.test_course1_dependency_audit \
    tests.test_course1_host_survey \
    tests.test_course1_vmware_registry \
    tests.test_course1_vmnet_maintenance \
    tests.test_course1_vmnet_transaction \
    tests.test_course1_north_host_addresses \
    tests.test_lab_mode_ad_readiness

step "02b - Native NORTH Vagrant/router source parsers"
ruby -c ad/NORTH/providers/vmware/Vagrantfile
bash -n ad/NORTH/providers/vmware/router/provision.sh
echo "[PASS] Native NORTH recipe parses; release gate still enforced"

step "03 - Bash syntax regression"
# Bash -n parses only the first file; subsequent arguments are parameters.
# Run a distinct syntax validation for each maintenance/lifecycle script.
for shell_file in \
    scripts/course1/validate-course1.sh \
    scripts/course1/maintain-vmware-networks.sh \
    scripts/course1/manage-north-hostaddrs.sh \
    scripts/course1/kingdoms-north-vmnet-hostaddrs \
    scripts/course1/provisioning-routes.sh \
    scripts/course1/router-ssh.sh \
    scripts/lab-mode.sh \
    scripts/verify-test-source.sh; do
    bash -n "${shell_file}" || fail "Bash syntax invalid: ${shell_file}"
done
echo "[PASS] Bash syntax (all four scripts checked independently)"

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

step "08c - Render isolated three-NIC VMware/router candidate (preview only)"
readonly CANDIDATE="${PRIVATE_WORKDIR}/isolated-vmware"
python3 -m goad.course1_vmware_candidate \
    --proposal docs/course1-network-candidate.example.json \
    --output "${CANDIDATE}"
bash -n "${CANDIDATE}/router/provision.sh"
ruby -c "${CANDIDATE}/instance-preview/Vagrantfile"
if grep -Eiq '(GOAD-DC03|GOAD-SRV03|ESSOS|vmnet30|10\.4\.)' \
    "${CANDIDATE}/instance-preview/Vagrantfile" \
    "${CANDIDATE}/router/provision.sh"; then
    fail "Course 1 isolated VMware/router preview retained reference network identities"
fi
echo "[PASS] Three custom router NICs; new Vagrant/router syntax; no ESSOS"

step "08d - Native isolated Ansible inventories + WinRM endpoint scope"
python3 scripts/course1/check-isolated-artifacts.py \
    --candidate "${CANDIDATE}" \
    --proposal docs/course1-network-candidate.example.json

step "08e - Batch audit of hardcoded six-VM topology dependencies"
python3 -m goad.course1_dependency_audit --check --limit 8

step "08f - Strict source integrity and future instance-layout plan"
python3 -m goad.course1_install_stage \
    --check-candidate "${CANDIDATE}" \
    --proposal docs/course1-network-candidate.example.json \
    --instance-id kingdoms-c1-regress01
echo "[BLOCKED] Private VMware/Ansible candidate is verified but NOT installable"

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
    step "10 - Single read-only VMware host + registered-VM survey"
    readonly HOST_SNAPSHOT="${PRIVATE_WORKDIR}/host-snapshot.json"
    python3 -m goad.course1_host_survey --check --json-only > "${HOST_SNAPSHOT}"
    [[ -s "${HOST_SNAPSHOT}" ]] || fail "VMware host survey did not return evidence"
    step "11 - Pre/post allocation VMware evidence and registered VM collisions"
    python3 -m goad.course1_vmnet_phase \
        --proposal docs/course1-network-candidate.example.json \
        --snapshot "${HOST_SNAPSHOT}"
    echo "[BLOCKED] New NORTH .254 host address persistence and live runtime remain separate gates"
fi

step "COMPLETE"
printf '[PASS] All offline Course 1 validation gates passed at %s\n' "${HEAD_SHA}"
echo "[BLOCKED] Four-VM installation/start/stop/reset still NOT authorized"
echo "[INFO] Ephemeral preview is deleted automatically; no guest was touched"
