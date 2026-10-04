#!/usr/bin/env bash
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SOURCE_GATE="${ROOT}/scripts/verify-test-source.sh"
cd "${ROOT}"

fail() {
    echo "[FAIL] $*" >&2
    exit 1
}

pass() {
    echo "[PASS] $*"
}

warn() {
    echo "[WARN] $*"
}

require_file() {
    [[ -f "$1" ]] || fail "missing required file: $1"
}

# Git is the source of truth for GOAD Kingdoms. Refuse to validate a local
# repair, dirty checkout, unpushed commit, stale branch, or divergent branch.
# An exact detached candidate can be tested by exporting
# GOAD_KINGDOMS_EXPECTED_COMMIT=<sha> before running this preflight.
[[ -f "${SOURCE_GATE}" ]] || fail "source-of-truth gate is missing: ${SOURCE_GATE}"
bash "${SOURCE_GATE}"
pass "Git source-of-truth gate"

for file in \
    goad_nomad.py \
    goad/provisioner/ansible/ansible.py \
    goad/provider/provider_factory.py \
    goad/provider/vagrant/vmware_kingdoms.py \
    goad/provider/vagrant/vmware_nomad.py \
    scripts/lab-mode.sh \
    scripts/provisioning-routes.sh \
    scripts/setup-vmware-networks.sh \
    scripts/check-vmware-networks.sh \
    scripts/check-vmware-instance-conflicts.sh \
    scripts/verify-test-source.sh \
    scripts/validate-network-segmentation.sh \
    scripts/validate-network-segmentation-runtime.sh \
    scripts/validate-network-segmentation-source.sh \
    scripts/validate-ws01-source.sh \
    scripts/validate-ws01-runtime.sh \
    ad/GOAD/providers/vmware/router/provision.sh \
    ad/GOAD/providers/vmware/router/nftables/provisioning.nft \
    ad/GOAD/providers/vmware/router/nftables/exercise.nft \
    ansible/roles/child_domain/tasks/main.yml
 do
    require_file "${file}"
 done
pass "required network-segmentation source files are present"

# lab-mode.sh and setup-vmware-networks.sh are user-facing entry points and must
# retain their executable bits in Git. Supporting helpers are deliberately
# invoked through bash by the project so archive/copy operations cannot break
# them solely by stripping mode bits.
[[ -x scripts/lab-mode.sh ]] || fail "scripts/lab-mode.sh is not executable"
[[ -x scripts/setup-vmware-networks.sh ]] || fail "scripts/setup-vmware-networks.sh is not executable"
pass "user-facing lifecycle script executable bits"

for file in \
    scripts/lab-mode.sh \
    scripts/provisioning-routes.sh \
    scripts/setup-vmware-networks.sh \
    scripts/check-vmware-networks.sh \
    scripts/check-vmware-instance-conflicts.sh \
    scripts/verify-test-source.sh \
    scripts/validate-network-segmentation.sh \
    scripts/validate-network-segmentation-runtime.sh \
    scripts/validate-network-segmentation-source.sh \
    scripts/validate-ws01-source.sh \
    scripts/validate-ws01-runtime.sh \
    ad/GOAD/providers/vmware/router/provision.sh
 do
    bash -n "${file}"
 done
pass "shell syntax"

python3 -m py_compile \
    goad/config.py \
    goad_nomad.py \
    goad/provider/provider_factory.py \
    goad/provider/vagrant/vmware.py \
    goad/provider/vagrant/vmware_kingdoms.py \
    goad/provider/vagrant/vmware_nomad.py \
    goad/provisioner/ansible/ansible.py
pass "Python syntax"

# The deterministic segmented MACs are intentionally stable within one lab so
# IP/NIC validation remains reproducible. Two lab instances must therefore never
# be allowed to run those identities on the same VMware vmnets concurrently.
conflict_tmp="$(mktemp -d)"
trap 'rm -rf "${conflict_tmp}"' EXIT
mkdir -p "${conflict_tmp}/current" "${conflict_tmp}/other"
printf 'ethernet1.address = "00:50:56:20:20:10"\n' > "${conflict_tmp}/current/current.vmx"
printf 'ethernet1.address = "00:50:56:20:20:10"\n' > "${conflict_tmp}/other/conflict.vmx"

cat > "${conflict_tmp}/vmrun-current" <<EOF
#!/usr/bin/env bash
printf 'Total running VMs: 1\\n%s\\n' '${conflict_tmp}/current/current.vmx'
EOF
chmod +x "${conflict_tmp}/vmrun-current"

GOAD_KINGDOMS_VMRUN_BIN="${conflict_tmp}/vmrun-current" \
    bash scripts/check-vmware-instance-conflicts.sh "${conflict_tmp}/current" >/dev/null ||
    fail "collision guard rejects a VM belonging to the selected provider"

cat > "${conflict_tmp}/vmrun-conflict" <<EOF
#!/usr/bin/env bash
printf 'Total running VMs: 1\\n%s\\n' '${conflict_tmp}/other/conflict.vmx'
EOF
chmod +x "${conflict_tmp}/vmrun-conflict"

if GOAD_KINGDOMS_VMRUN_BIN="${conflict_tmp}/vmrun-conflict" \
    bash scripts/check-vmware-instance-conflicts.sh "${conflict_tmp}/current" >/dev/null 2>&1; then
    fail "collision guard allows an outside provider to reuse a segmented MAC"
fi
rm -rf "${conflict_tmp}"
trap - EXIT
pass "deterministic VMware MAC collision guard"

if command -v ruby >/dev/null 2>&1; then
    ruby -c ad/GOAD/providers/vmware/Vagrantfile >/dev/null
    ruby -c ad/GOAD/providers/vmware/router/Vagrantfile >/dev/null
    pass "VMware Vagrantfile syntax"
else
    warn "ruby not found; skipped Vagrantfile syntax check"
fi

if command -v nft >/dev/null 2>&1; then
    if sudo -n true >/dev/null 2>&1; then
        sudo nft -c -f ad/GOAD/providers/vmware/router/nftables/provisioning.nft
        sudo nft -c -f ad/GOAD/providers/vmware/router/nftables/exercise.nft
        pass "nftables syntax"
    else
        warn "passwordless sudo unavailable; run manually: sudo nft -c -f ad/GOAD/providers/vmware/router/nftables/provisioning.nft && sudo nft -c -f ad/GOAD/providers/vmware/router/nftables/exercise.nft"
    fi
else
    warn "nft not found; skipped nftables parser check"
fi

# A full Ansible run owns provider finalization. The console must not call the
# same finalizer again, otherwise a successful install enters exercise mode
# twice. Inspect executable Python with the AST so comments/docstrings cannot
# create false positives. The console also owns the legacy-compatible NOMAD
# human-readable elapsed timer and must not delegate to the upstream time.ctime
# wrapper. Internal NOMAD identifiers remain compatibility names during the
# public GOAD Kingdoms rename.
python3 - <<'PY'
import ast
from pathlib import Path

console_source = Path('goad_nomad.py').read_text()
ansible_source = Path('goad/provisioner/ansible/ansible.py').read_text()
console_tree = ast.parse(console_source)

method = None
for node in console_tree.body:
    if isinstance(node, ast.ClassDef) and node.name == 'GoadNomad':
        method = next(
            (
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == 'do_provision_lab'
            ),
            None,
        )
        break

if method is None:
    raise SystemExit('GOAD_NOMAD compatibility do_provision_lab not found')

finalize_calls = [
    node
    for node in ast.walk(method)
    if isinstance(node, ast.Call)
    and (
        (isinstance(node.func, ast.Name) and node.func.id == 'finalize_install')
        or (isinstance(node.func, ast.Attribute) and node.func.attr == 'finalize_install')
    )
]
if finalize_calls:
    raise SystemExit('GOAD_NOMAD compatibility do_provision_lab performs duplicate provider finalization')

legacy_super_calls = [
    node
    for node in ast.walk(method)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr == 'do_provision_lab'
    and isinstance(node.func.value, ast.Call)
    and isinstance(node.func.value.func, ast.Name)
    and node.func.value.func.id == 'super'
]
if legacy_super_calls:
    raise SystemExit('GOAD_NOMAD compatibility do_provision_lab delegates to legacy upstream timer')

# Remove the function docstring before text checks so explanatory prose cannot
# satisfy or invalidate executable-code assertions.
body = list(method.body)
if (
    body
    and isinstance(body[0], ast.Expr)
    and isinstance(body[0].value, ast.Constant)
    and isinstance(body[0].value.value, str)
):
    body = body[1:]
executable = '\n'.join(ast.unparse(node) for node in body)

if 'get_current_instance_provisioner().run()' not in executable:
    raise SystemExit('GOAD_NOMAD compatibility do_provision_lab does not invoke the provisioner directly')
if 'set_status(READY)' not in executable:
    raise SystemExit('GOAD_NOMAD compatibility do_provision_lab does not set READY after successful finalization')
if '_format_elapsed' not in executable:
    raise SystemExit('GOAD_NOMAD compatibility do_provision_lab does not use the human-readable timer')
if 'return self._finalize_provider_provisioning()' not in ansible_source:
    raise SystemExit('Ansible full-lab run no longer owns provider finalization')
PY
pass "single final-isolation owner and human-readable install timer"

grep -Fq 'GoadKingdomsVmwareProvider' goad/provider/provider_factory.py ||
    fail "provider factory does not select the guarded GOAD Kingdoms VMware provider"
grep -Fq '_check_segmented_instance_conflicts' goad/provider/vagrant/vmware_kingdoms.py ||
    fail "GOAD Kingdoms VMware provider has no collision preflight"
grep -Fq 'check-vmware-instance-conflicts.sh' goad/provider/vagrant/vmware_kingdoms.py ||
    fail "GOAD Kingdoms VMware provider does not invoke the collision guard"
grep -Fq 'return super().prepare_install()' goad/provider/vagrant/vmware_kingdoms.py ||
    fail "collision preflight does not return to the validated M1 prepare_install lifecycle"
python3 - <<'PY'
import ast
from pathlib import Path

source = Path('goad/provider/vagrant/vmware_kingdoms.py').read_text()
tree = ast.parse(source)
provider = next(
    node
    for node in tree.body
    if isinstance(node, ast.ClassDef) and node.name == 'GoadKingdomsVmwareProvider'
)
install = next(
    node
    for node in provider.body
    if isinstance(node, ast.FunctionDef) and node.name == 'install'
)

preflight_line = None
first_vagrant_line = None
for node in ast.walk(install):
    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == 'self'
            and node.func.attr == 'prepare_install'
        ):
            preflight_line = node.lineno
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == 'run_vagrant'
        ):
            first_vagrant_line = min(first_vagrant_line or node.lineno, node.lineno)

if preflight_line is None:
    raise SystemExit('Kingdoms install does not invoke the host-network preflight')
if first_vagrant_line is None:
    raise SystemExit('Kingdoms install contains no Vagrant bring-up call')
if preflight_line >= first_vagrant_line:
    raise SystemExit('Kingdoms host-network preflight runs after guest bring-up')
PY
pass "GOAD Kingdoms provider owns fail-closed pre-start collision policy"

grep -Fq 'name: DNS' ansible/roles/child_domain/tasks/main.yml ||
    fail "child-domain role does not explicitly install DNS"
grep -Fq 'include_management_tools: yes' ansible/roles/child_domain/tasks/main.yml ||
    fail "child-domain role does not install DNS management tools"
grep -Fq -- '-InstallDns:$true' ansible/roles/child_domain/tasks/main.yml ||
    fail "child-domain promotion does not explicitly install DNS"
grep -Fq 'ms_tcpip6' ansible/roles/child_domain/tasks/main.yml ||
    fail "child-domain role does not harden IPv6 on the provisioning NIC"
grep -Fq 'Get-DnsServerZone' ansible/roles/child_domain/tasks/main.yml ||
    fail "child-domain role does not validate the AD-integrated child DNS zone"
grep -Fq 'name: ADWS' ansible/roles/child_domain/tasks/main.yml ||
    fail "child-domain role does not manage Active Directory Web Services"
grep -Fq 'state: started' ansible/roles/child_domain/tasks/main.yml ||
    fail "child-domain role does not ensure required Windows services are started"
pass "Winterfell DNS / ADWS hardening is present"

grep -Fq 'pin_vmware_management_nic_identity()' scripts/lab-mode.sh ||
    fail "lifecycle does not preserve VMware management NIC identity before direct power cycles"
grep -Fq 'ethernet0.addresstype' scripts/lab-mode.sh ||
    fail "lifecycle does not inspect VMware management NIC address type"
grep -Fq 'ethernet0.address' scripts/lab-mode.sh ||
    fail "lifecycle does not pin VMware management NIC to a static address"
grep -Fq 'ethernet0.checkMACAddress' scripts/lab-mode.sh ||
    fail "lifecycle does not allow the preserved VMware-generated OUI as a static address"
grep -Fq 'KINGDOMS_VMWARE_MANAGEMENT_NIC_PINNED' scripts/lab-mode.sh ||
    fail "lifecycle does not emit VMware management NIC identity evidence"
pass "VMware management NIC identity is static across lifecycle power cycles"

python3 - <<'PY'
from pathlib import Path

text = Path('scripts/lab-mode.sh').read_text()
start = text.index('prove_isolated_guest_ready() (')
end = text.index('configure_windows_nat_exercise() {', start)
fn = text[start:end]

required = (
    'READINESS_TRANSPORT=guestops',
    'proving authenticated readiness through VMware Guest Operations',
    'ethernet0 remains persistently OFF and runtime disconnected',
    'authenticated post-reboot readiness proven through VMware Guest Operations',
)
for token in required:
    if token not in fn:
        raise SystemExit(f'exercise readiness missing Guest Operations contract: {token}')

for forbidden in (
    'connectNamedDevice',
    'disconnectNamedDevice',
    'vmrun_named_device_action',
):
    if forbidden in fn:
        raise SystemExit(f'exercise readiness still hot-plugs management NAT: {forbidden}')

for token in (
    'guestops_credential_value()',
    'vmware_guest_powershell_capture()',
    'copyFileFromHostToGuest',
    'runProgramInGuest',
    'copyFileFromGuestToHost',
    'deleteFileInGuest',
    'guest_script',
    'host_script',
    'powershell_capture()',
):
    if token not in text:
        raise SystemExit(f'Guest Operations transport missing: {token}')

capture_start = text.index('vmware_guest_powershell_capture() {')
capture_end = text.index('guestops_check() (', capture_start)
capture = text[capture_start:capture_end]
if 'inner_encoded' in capture:
    raise SystemExit('GuestOps payload regressed to nested encoded argv transport')

expected_functions = (
    'vmware_guest_powershell_capture() {',
    'guestops_time_check() (',
    'powershell_capture() {',
)
for function in expected_functions:
    if text.count('\n' + function) != 1:
        raise SystemExit(
            f'Guest Operations helper boundary is corrupted or duplicated: {function}'
        )

if 'vmware_guest_guestops_time_check' in text:
    raise SystemExit('Guest Operations helper names were accidentally merged')

for function in (
    'last_marker_line() {',
    'ensure_child_dc_time_ready() {',
):
    if text.count('\n' + function) != 1:
        raise SystemExit(
            f'child-time parser boundary is corrupted or duplicated: {function}'
        )

if "grep -E 'KINGDOMS_DC_TIME_" in text:
    raise SystemExit('child-time marker parsing regressed to regex matching')
PY
pass "exercise readiness uses VMware Guest Operations without runtime NAT hot-plug"

grep -Fq 'policy drop;' ad/GOAD/providers/vmware/router/nftables/exercise.nft ||
    fail "exercise policy is not deny-by-default"
grep -Fq '10.4.10.22 ip daddr 10.4.30.23 tcp dport 1433' ad/GOAD/providers/vmware/router/nftables/exercise.nft ||
    fail "Castelblack -> Braavos linked-SQL rule is missing"
grep -Fq '10.4.10.11 ip daddr 10.4.30.12 udp dport 53' ad/GOAD/providers/vmware/router/nftables/exercise.nft ||
    fail "Winterfell -> Meereen conditional-DNS rule is missing"
pass "validated exercise firewall relationships are present"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git diff --check
    pass "git whitespace check"
fi

echo
echo "[READY] GOAD Kingdoms network-segmentation source preflight passed."
