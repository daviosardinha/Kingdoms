#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

fail() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }
pass() { printf '[PASS] %s\n' "$*"; }

printf '\n============================================================\n'
printf 'GOAD KINGDOMS — CLEAN-INSTALL SOURCE GATE\n'
printf '============================================================\n\n'

bash scripts/verify-test-source.sh
pass 'Git source-of-truth gate'

readonly REQUIRED=(
    goad.sh
    goad_nomad.py
    goad/provisioner/ansible/ansible.py
    goad/provider/provider_factory.py
    goad/provider/vagrant/vmware.py
    goad/provider/vagrant/vmware_kingdoms.py
    playbooks.yml
    ansible/ws01.yml
    ansible/phase01.yml
    ansible/ws01-lpe-install.yml
    ansible/kingdoms-health.yml
    ansible/kingdoms-health-final.yml
    ansible/roles/kingdoms_health/dc/tasks/main.yml
    ansible/roles/kingdoms_health/member/tasks/main.yml
    ansible/windows-lpe.yml
    ansible/roles/settings/enable_nat_adapter/tasks/main.yml
    ad/GOAD/data/config.json
    ad/GOAD/data/inventory
    ad/GOAD/providers/vmware/Vagrantfile
    ad/GOAD/providers/vmware/inventory
    scripts/lab-mode.sh
    scripts/preflight-goad-kingdoms-fresh-install.sh
    scripts/validate-network-segmentation-source.sh
    scripts/validate-ws01-source.sh
    scripts/validate-windows-lpe-framework-source.sh
)
for file in "${REQUIRED[@]}"; do
    [[ -f "${file}" ]] || fail "required clean-install source is missing: ${file}"
done
pass 'required GOAD Kingdoms clean-install source files'

bash -n scripts/validate-goad-kingdoms-install-source.sh
pass 'clean-install gate shell syntax'

bash -n scripts/preflight-goad-kingdoms-fresh-install.sh
pass 'fresh-install preflight shell syntax'

python3 - <<'PY'
import ast
from pathlib import Path
import re
import sys

try:
    import yaml
except Exception as exc:
    raise SystemExit(f'PyYAML is required to validate playbooks.yml: {exc}')


def fail(message):
    raise SystemExit(message)


def require_tokens(label, text, tokens):
    for token in tokens:
        if token not in text:
            fail(f'{label} missing contract: {token}')


# Parse the Python sources without writing __pycache__ into the working tree.
for source in (
    'goad_nomad.py',
    'goad/provider/vagrant/vmware.py',
    'goad/provider/vagrant/vmware_kingdoms.py',
):
    text = Path(source).read_text()
    try:
        compile(text, source, 'exec')
    except SyntaxError as exc:
        fail(f'Python syntax error in {source}: {exc}')

playbooks = yaml.safe_load(Path('playbooks.yml').read_text())
expected = [
    'build.yml',
    'ad-servers.yml',
    'ad-parent_domain.yml',
    'ad-child_domain.yml',
    'wait5m.yml',
    'ad-members.yml',
    'kingdoms-time-backoff.yml',
    'ad-trusts.yml',
    'ad-data.yml',
    'ws01.yml',
    'ad-gmsa.yml',
    'laps.yml',
    'ad-relations.yml',
    'adcs.yml',
    'ad-acl.yml',
    'servers.yml',
    'security.yml',
    'kingdoms-health.yml',
    'vulnerabilities.yml',
    'phase01.yml',
    'ws01-lpe-install.yml',
    'kingdoms-health-final.yml',
]
actual = playbooks.get('GOAD')
if actual != expected:
    fail(f'GOAD clean-install playbook sequence mismatch:\nexpected={expected}\nactual={actual}')
if actual.index('ws01.yml') <= actual.index('ad-data.yml'):
    fail('ws01.yml must run after ad-data.yml so NORTH\\rickon.stark exists')
if actual.index('kingdoms-health.yml') <= actual.index('security.yml'):
    fail('pre-vulnerability Kingdoms health gate must run after security.yml')
if actual.index('kingdoms-health.yml') >= actual.index('vulnerabilities.yml'):
    fail('pre-vulnerability Kingdoms health gate must run before vulnerabilities.yml')
if actual.index('phase01.yml') <= actual.index('vulnerabilities.yml'):
    fail('phase01.yml must run after vulnerabilities.yml')
if actual.index('phase01.yml') >= actual.index('ws01-lpe-install.yml'):
    fail('phase01.yml must run before final WS01 LPE seeding')
if actual.index('kingdoms-health-final.yml') <= actual.index('ws01-lpe-install.yml'):
    fail('final Kingdoms health proof must run after WS01 LPE seeding')
if actual[-1] != 'kingdoms-health-final.yml':
    fail('final Kingdoms health proof must be the final GOAD Ansible stage')

health = Path('ansible/kingdoms-health.yml').read_text()
require_tokens(
    'Kingdoms pre-vulnerability health gate',
    health,
    (
        'hosts: dc',
        'hosts: server:workstation',
        'role: kingdoms_health/dc',
        'role: kingdoms_health/member',
        'kingdoms_health_domain_controller:',
        'kingdoms_health_repair: true',
    ),
)

final_health = Path('ansible/kingdoms-health-final.yml').read_text()
require_tokens(
    'Kingdoms final health proof',
    final_health,
    (
        'hosts: dc',
        'hosts: server:workstation',
        'kingdoms_health_domain_controller:',
        'kingdoms_health_repair: false',
    ),
)

member_health = Path('ansible/roles/kingdoms_health/member/tasks/main.yml').read_text()
require_tokens(
    'Kingdoms member health contract',
    member_health,
    (
        'Test-ComputerSecureChannel',
        'Reset-ComputerMachinePassword',
        'nltest.exe',
        'Resolve-DnsName',
        'w32tm.exe',
        'AllowRepair',
        'DomainController',
        'Wait-DomainDiscovery',
        'Invoke-Nltest',
        'KINGDOMS_MEMBER_DCLOCATOR_RETRY',
        '-Server $DomainController',
    ),
)

dc_health = Path('ansible/roles/kingdoms_health/dc/tasks/main.yml').read_text()
require_tokens(
    'Kingdoms domain controller health contract',
    dc_health,
    (
        "'NTDS', 'DNS', 'ADWS', 'Netlogon', 'Kdc', 'W32Time'",
        "'SYSVOL', 'NETLOGON'",
        'Get-ADDomain',
        'Resolve-DnsName',
        'nltest.exe',
    ),
)
if 'Reset-ComputerMachinePassword' in dc_health:
    fail('domain controller health gate must not auto-repair machine trust')
if 'Assert-DomainDiscovery' in member_health:
    fail('member health must not hard-fail on a single DC Locator miss before trust evaluation')
if member_health.index('$discoveryHealthy = Wait-DomainDiscovery') > member_health.index('$trustHealthy = Test-DirectSecureChannel'):
    fail('member health must record bounded locator state before evaluating trust independently')
if '-Server $DomainController' not in member_health:
    fail('member trust validation/repair must pin the known domain controller')

for label, health_script in (
    ('domain controller health contract', dc_health),
    ('member health contract', member_health),
):
    if '$DomainName:' in health_script:
        fail(f'{label} contains unsafe PowerShell interpolation before colon')

if '${DomainName}:' not in dc_health:
    fail('domain controller health contract must delimit DomainName before colon in PowerShell strings')

install_lpe = Path('ansible/ws01-lpe-install.yml').read_text()
require_tokens(
    'WS01 LPE clean-install playbook',
    install_lpe,
    (
        'hosts: ws01',
        'role: windows_lpe',
        'windows_lpe_action: apply',
        'windows_lpe_profile: full-lpe',
    ),
)
if 'windows_lpe_allow_candidate' in install_lpe:
    fail('promoted clean install must not require candidate opt-in')

foundation = Path('ansible/ws01.yml').read_text()
require_tokens(
    'WS01 clean foundation playbook',
    foundation,
    (
        'hosts: ws01',
        "role: 'settings/eval_rearm'",
        "role: 'commonwkstn'",
        "role: 'settings/adjust_rights'",
        "role: 'settings/user_rights'",
    ),
)

config = Path('ad/GOAD/data/config.json').read_text()
if '"ws01"' not in config or '"north\\\\rickon.stark"' not in config:
    fail('GOAD data does not define WS01 with Rickon foothold rights')

inventory = Path('ad/GOAD/data/inventory').read_text()
if not re.search(r'(?m)^ws01\s*$', inventory):
    fail('GOAD lab inventory does not include ws01')

provider_inventory = Path('ad/GOAD/providers/vmware/inventory').read_text().splitlines()
ws01_lines = [
    line.strip()
    for line in provider_inventory
    if re.match(r'^\s*ws01(?:\s|$)', line)
]
if len(ws01_lines) != 1:
    fail(f'Kingdoms VMware provider inventory must define exactly one ws01 entry: {ws01_lines}')

parts = ws01_lines[0].split()
ws01_vars = dict(
    token.split('=', 1)
    for token in parts[1:]
    if '=' in token
)

expected_ws01_vars = {
    'ansible_host': '10.4.10.31',
    'dns_domain': 'dc02',
    'dict_key': 'ws01',
}
for key, expected_value in expected_ws01_vars.items():
    actual_value = ws01_vars.get(key)
    if actual_value != expected_value:
        fail(
            f'Kingdoms VMware ws01 {key} mismatch: '
            f'expected={expected_value!r} actual={actual_value!r}'
        )

provider_factory = Path('goad/provider/provider_factory.py').read_text()
if 'GoadKingdomsVmwareProvider' not in provider_factory:
    fail('VMware provider factory is not wired to GOAD Kingdoms segmented provider')

console = Path('goad_nomad.py').read_text()
require_tokens(
    'GOAD Kingdoms unattended sudo lifecycle',
    console,
    (
        'def _start_install_sudo_keepalive(self, stop_event):',
        "['sudo', '-k']",
        "['sudo', '-v']",
        "['sudo', '-n', '-v']",
        "name='goad-kingdoms-sudo-keepalive'",
        'non-interactive keepalive active every 60s',
        'sudo_lost_event.is_set()',
        'refusing to report the install as successful',
    ),
)

vmware_provider = Path('goad/provider/vagrant/vmware.py').read_text()
require_tokens(
    'VMware Tools recoverable-transition logging',
    vmware_provider,
    (
        'VMware Tools install/reboot interrupted WinRM',
        'validating guest recovery before classifying it as a failure',
        'recovery reboot closed WinRM',
        'continuing with readiness validation',
    ),
)
if 'VMware Tools WinRM session interrupted for' in vmware_provider:
    fail('expected VMware Tools transport teardown must not use the old failure-like warning text')

kingdoms_provider = Path('goad/provider/vagrant/vmware_kingdoms.py').read_text()
require_tokens(
    'fresh-install pre-AD provisioning bootstrap',
    kingdoms_provider,
    (
        'def _fresh_install_bootstrap_pending(self):',
        "profile.get('status') == 'ansible_running'",
        "self.get_runtime_mode() == 'unknown'",
        'def prepare_provisioning(self):',
        "self._apply_router_policy('provisioning')",
        'self._enable_provisioning_routes()',
        'self._validate_management_plane()',
        'fresh install bootstrap before AD exists',
        'fresh pre-AD management plane ready',
    ),
)

require_tokens(
    'GOAD Kingdoms failed Windows bring-up recovery',
    kingdoms_provider,
    (
        'def _wait_machine_stopped(self, machine, timeout=120):',
        'def _stop_failed_windows_guest_cleanly(self, machine):',
        'def _recover_failed_windows_vagrant_up(self, machine):',
        'def install(self):',
        "first_up = self.command.run_vagrant(['up', machine], self.path)",
        'tools_ready = self._ensure_vmware_tools(machine)',
        'def _authenticated_guest_recovery_ready(self, machine, timeout=60):',
        'if not first_up or not tools_ready:',
        'if not self._recover_failed_windows_vagrant_up(machine):',
        'shutdown.exe /s /t 0 /f',
        "['vmrun', '-T', 'ws', 'stop', vmx, 'soft']",
        "['halt', machine, '-f']",
        "['up', machine, '--provision']",
        'timeout=600',
        'if not self._ensure_vmware_tools(machine):',
        'starting a clean recovery provision cycle',
        'completed a clean failed-bring-up recovery provision cycle',
        "['sudo', '-n', '-v']",
        "['sudo', '-n', 'bash', route_script, 'enable']",
    ),
)
if 'forcing a clean provision cycle' in kingdoms_provider:
    fail('recovery logging still claims the now-graceful recovery cycle is forced')

preflight_call = kingdoms_provider.find('if not self.prepare_install():')
first_guest_start = kingdoms_provider.find('if not self._bring_up_router():')
if preflight_call == -1 or first_guest_start == -1 or preflight_call >= first_guest_start:
    fail('Kingdoms install must complete host-network preflight before starting GOAD-ROUTER')

lab_mode = Path('scripts/lab-mode.sh').read_text()
require_tokens(
    'AD-aware Kingdoms mode transition',
    lab_mode,
    (
        'DOMAIN_CONTROLLERS',
        'DOMAIN_MEMBERS',
        'EXERCISE_DOMAIN_CONTROLLERS',
        'wait_domain_controller_ready',
        'wait_domain_member_ready',
        'preflight_domain_health',
        'Get-ADRootDSE',
        'Test-ComputerSecureChannel -Server',
        'System.Security.Principal.NTAccount',
        'w32tm.exe /query /source',
        'configure_windows_nat_provisioning',
        'configure_windows_nat_exercise',
        'prove_isolated_guest_ready',
        'temporarily connecting runtime NAT for authenticated readiness',
        'authenticated post-reboot readiness proven; runtime NAT disconnected',
        'member/workstation guests first; domain controllers last',
        'domain controllers first with AD readiness; members second',
    ),
)
provisioning_transition = lab_mode[
    lab_mode.index('configure_windows_nat_provisioning()'):
    lab_mode.index('configure_windows_nat_exercise()')
]
if provisioning_transition.index('for vm in "${DOMAIN_CONTROLLERS[@]}"') > provisioning_transition.index('for vm in "${DOMAIN_MEMBERS[@]}"'):
    fail('provisioning mode must restart/validate domain controllers before dependent members')

exercise_transition = lab_mode[
    lab_mode.index('configure_windows_nat_exercise()'):
    lab_mode.index('verify_persistent_state()')
]
if exercise_transition.index('for vm in "${DOMAIN_MEMBERS[@]}"') > exercise_transition.index('for vm in "${EXERCISE_DOMAIN_CONTROLLERS[@]}"'):
    fail('exercise mode must restart members before domain controllers')
for token in (
    'ensure_vm_nat_state "${vm}" FALSE disconnect',
    'prove_isolated_guest_ready "${vm}" member',
    'prove_isolated_guest_ready "${vm}" dc',
):
    if token not in exercise_transition:
        fail(f'exercise mode missing post-reboot authenticated readiness contract: {token}')

runtime_validator = Path('scripts/validate-network-segmentation-runtime.sh').read_text()
if '${HOME}/.goad/.venv/bin/ansible-playbook' not in runtime_validator:
    fail('network runtime validator does not detect the canonical GOAD Ansible virtualenv')

nat_enable = Path('ansible/roles/settings/enable_nat_adapter/tasks/main.yml').read_text()
require_tokens(
    'NAT adapter WinRM-safe transition',
    nat_enable,
    (
        'Start-Sleep -Seconds 5',
        'netsh interface set interface',
        'async: 60',
        'poll: 0',
        'ansible.builtin.meta: reset_connection',
        'ansible.builtin.wait_for_connection:',
        'timeout: 300',
        "if ($adapter.AdminStatus -ne 'Up')",
        'until: nat_adapter_enable_check.rc == 0',
    ),
)
if 'enable_adpter_interface' in nat_enable:
    fail('NAT adapter enable still retries the expected WinRM transport teardown as a task failure')

# A failed first bring-up must no longer hard-power Windows off as the primary
# recovery action. Older Server 2016 boxes have demonstrated a fully booted
# desktop with dead VMware Tools/WSMan after an unconditional halt -f. Require
# the recovery path to call the graceful-stop controller before the bounded
# Vagrant provisioning cycle. Forced halt remains only as the final fallback.
recovery_match = re.search(
    r'(?ms)^    def _recover_failed_windows_vagrant_up\(self, machine\):.*?(?=^    def install\(self\):)',
    kingdoms_provider,
)
if recovery_match is None:
    fail('cannot isolate GOAD Kingdoms failed-bring-up recovery implementation')
recovery = recovery_match.group(0)
if 'self._stop_failed_windows_guest_cleanly(machine)' not in recovery:
    fail('failed-bring-up recovery must invoke graceful Windows shutdown controller')
if "self._run_vagrant_bounded(['up', machine, '--provision'], timeout=600)" not in recovery:
    fail('failed-bring-up recovery must use a bounded Vagrant --provision cycle')

# Check the actual dispatch, rather than banning every Tools override by name.
# A scoped service-reporting repair is legitimate, but failed first-up recovery
# must remain an independent, mandatory decision in install().
provider_class = next(n for n in ast.parse(kingdoms_provider).body
                      if isinstance(n, ast.ClassDef) and n.name == 'GoadKingdomsVmwareProvider')
methods = {n.name: n for n in provider_class.body if isinstance(n, ast.FunctionDef)}

def matches(node, expression):
    return ast.dump(node) == ast.dump(ast.parse(expression, mode='eval').body)

guest_loop = next((n for n in methods['install'].body
                   if isinstance(n, ast.For) and matches(n.iter, 'self.goad_nomad_windows')), None)
if guest_loop is None:
    fail('cannot find the independent Windows install loop')
creation = next((i for i, n in enumerate(guest_loop.body)
                 if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'first_up' for t in n.targets)
                 and matches(n.value, "self.command.run_vagrant(['up', machine], self.path)")), -1)
readiness = next((i for i, n in enumerate(guest_loop.body)
                  if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'tools_ready' for t in n.targets)
                  and matches(n.value, 'self._ensure_vmware_tools(machine)')), -1)
recovery_probe = next((i for i, n in enumerate(guest_loop.body)
                       if isinstance(n, ast.If) and matches(n.test, 'not tools_ready')), -1)
dispatch = next((i for i, n in enumerate(guest_loop.body)
                 if isinstance(n, ast.If)
                 and matches(n.test, 'not first_up or not tools_ready')), -1)
if not 0 <= creation < readiness < recovery_probe < dispatch:
    fail(
        'Windows recovery must evaluate first-up result, strict Kingdoms readiness, '
        'pre-provision recovery readiness, then recovery dispatch in that order'
    )

probe_block = guest_loop.body[recovery_probe]
probe_assignment = next((n for n in probe_block.body
                         if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == 'recovery_ready'
                                 for t in n.targets)
                         and matches(
                             n.value,
                             'self._authenticated_guest_recovery_ready(machine)',
                         )), None)
if probe_assignment is None:
    fail(
        'missing authenticated pre-provision recovery probe for a guest that '
        'has not reached strict Kingdoms readiness'
    )
probe_fail_closed = next((n for n in probe_block.body
                          if isinstance(n, ast.If)
                          and matches(n.test, 'not recovery_ready')), None)
if probe_fail_closed is None or not any(
        isinstance(n, ast.Return) and matches(n.value, 'False')
        for n in probe_fail_closed.body
):
    fail('pre-provision recovery readiness must fail closed')

recovery_guard = next((n for n in guest_loop.body[dispatch].body if isinstance(n, ast.If)
                       and matches(n.test, 'not self._recover_failed_windows_vagrant_up(machine)')), None)
if recovery_guard is None or not any(isinstance(n, ast.Return) and matches(n.value, 'False')
                                     for n in recovery_guard.body):
    fail(
        'failed first-up OR incomplete strict Kingdoms readiness must enter the '
        'bounded recovery path and fail closed if recovery fails'
    )

recovery_method = methods.get('_recover_failed_windows_vagrant_up')
if recovery_method is None:
    fail('missing failed Windows bring-up recovery method')
post_recovery_readiness = next((
    n for n in ast.walk(recovery_method)
    if isinstance(n, ast.If)
    and matches(n.test, 'not self._ensure_vmware_tools(machine)')
), None)
if post_recovery_readiness is None or not any(
        isinstance(n, ast.Return) and matches(n.value, 'False')
        for n in post_recovery_readiness.body
):
    fail(
        'recovery must re-prove strict Kingdoms readiness after --provision '
        'before installation may continue'
    )

tools_override = methods.get('_ensure_vmware_tools')
if tools_override is not None and any(
        isinstance(n, ast.Call) and matches(n, 'self._recover_failed_windows_vagrant_up(machine)')
        for n in ast.walk(tools_override)):
    fail('failed-up recovery must not be hidden inside VMware Tools readiness')

provisioner = Path('goad/provisioner/ansible/ansible.py').read_text()
for token in ('_prepare_provider_provisioning', '_finalize_provider_provisioning', 'get_playbook_list'):
    if token not in provisioner:
        fail(f'Ansible clean-install lifecycle missing provider hook: {token}')
PY
pass 'GOAD clean-install orchestration + unattended lifecycle contract'

readonly ANSIBLE_PLAYBOOK="${HOME}/.goad/.venv/bin/ansible-playbook"
if [[ -x "${ANSIBLE_PLAYBOOK}" ]]; then
    ANSIBLE_CONFIG="${ROOT}/ansible/ansible.cfg" \
        "${ANSIBLE_PLAYBOOK}" -i 'ws01,' "${ROOT}/ansible/ws01.yml" --syntax-check >/dev/null
    ANSIBLE_CONFIG="${ROOT}/ansible/ansible.cfg" \
        "${ANSIBLE_PLAYBOOK}" -i 'ws01,' "${ROOT}/ansible/ws01-lpe-install.yml" --syntax-check >/dev/null
    pass 'WS01 foundation and install LPE Ansible syntax'
else
    printf '[INFO] GOAD Ansible runtime not installed yet; syntax checks deferred to bootstrap/runtime\n'
fi

bash scripts/validate-network-segmentation-source.sh
pass 'segmented VMware/provider source contract'

bash scripts/validate-ws01-source.sh
pass 'WS01 source contract'

bash scripts/validate-windows-lpe-framework-source.sh
pass '20-technique Windows LPE source contract'

git diff --check
pass 'Git whitespace check'

printf '\n[READY] GOAD Kingdoms clean-install source gate passed.\n'
printf 'A fresh GOAD/VMware install is wired for unattended sudo continuity, segmented provisioning, WS01 foundation, and all 20 LPE scenarios.\n'