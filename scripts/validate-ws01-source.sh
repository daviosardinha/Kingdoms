#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

fail() {
    printf '[FAIL] %s\n' "$*" >&2
    exit 1
}

pass() {
    printf '[PASS] %s\n' "$*"
}

bash scripts/verify-test-source.sh
pass "Git source-of-truth gate"

for file in \
    ad/GOAD/data/config.json \
    ad/GOAD/data/inventory \
    ad/GOAD/data/inventory_disable_vagrant \
    ad/GOAD/providers/vmware/Vagrantfile \
    ad/GOAD/providers/vmware/inventory \
    ansible/ad-servers.yml \
    ansible/ws01.yml \
    goad_nomad.py \
    goad/provider/vagrant/vmware.py \
    goad/provider/vagrant/vmware_nomad.py \
    scripts/lab-mode.sh \
    scripts/validate-ws01-runtime.sh \
    scripts/validate-network-segmentation-runtime.sh \
    extensions/ws01/extension.json
do
    [[ -f "${file}" ]] || fail "missing required WS01 source file: ${file}"
done
pass "required WS01 source files"

bash -n scripts/lab-mode.sh
bash -n scripts/validate-ws01-runtime.sh
bash -n scripts/validate-network-segmentation-runtime.sh
python3 -m py_compile \
    goad_nomad.py \
    goad/provider/vagrant/vmware.py \
    goad/provider/vagrant/vmware_nomad.py
pass "shell and Python syntax"

python3 - <<'PY'
import ast
import json
from pathlib import Path
import re
import subprocess


def fail(message):
    raise SystemExit(message)


def section_items(text, section):
    match = re.search(
        rf'(?ms)^\[{re.escape(section)}\]\s*\n(.*?)(?=^\[|\Z)',
        text,
    )
    if match is None:
        fail(f'missing inventory section: [{section}]')
    return [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip() and not line.lstrip().startswith((';', '#'))
    ]


config = json.loads(Path('ad/GOAD/data/config.json').read_text())
ws01 = config['lab']['hosts'].get('ws01')
if ws01 is None:
    fail('ws01 host is missing from GOAD config')
if 'local_admin_password' in ws01:
    fail('WS01 must inherit the existing NORTH lab credential instead of publishing a new password')

expected = {
    'hostname': 'ws01',
    'type': 'workstation',
    'domain': 'north.sevenkingdoms.local',
    'path': 'DC=north,DC=sevenkingdoms,DC=local',
}
for key, value in expected.items():
    if ws01.get(key) != value:
        fail(f'ws01 {key} must be {value!r}, got {ws01.get(key)!r}')

rdp_users = ws01.get('local_groups', {}).get('Remote Desktop Users', [])
if rdp_users != ['north\\rickon.stark']:
    fail(f'WS01 RDP foothold must be exactly NORTH\\rickon.stark: {rdp_users!r}')
if ws01.get('exact_local_groups') != ['Remote Desktop Users']:
    fail('WS01 RDP membership must be reconciled exactly, including existing deployments')

admins = [
    value.lower()
    for value in ws01.get('local_groups', {}).get('Administrators', [])
]
if 'north\\rickon.stark' in admins:
    fail('NORTH\\rickon.stark must not be a WS01 local administrator')

if ws01.get('vulns') or ws01.get('security'):
    fail('WS01 foundation commit must not plant LPE scenarios or alter security yet')

vagrant = Path('ad/GOAD/providers/vmware/Vagrantfile').read_text()
block_match = re.search(
    r'(?ms)^  # GOAD Kingdoms M2 first-class NORTH workstation\.\n'
    r'(.*?)(?=^  # GOAD_NOMAD routing plane\.)',
    vagrant,
)
if block_match is None:
    fail('canonical GOAD-WS01 Vagrant block is missing')

block = block_match.group(1)
for token in (
    ':name => "GOAD-WS01"',
    ':ip => "10.4.10.31"',
    ':lab_gateway => "10.4.10.1"',
    ':lab_mac => "00:50:56:20:10:31"',
    ':box => "mayfly/windows10"',
    ':box_version => "2024.01.06"',
    ':vnet => "vmnet10"',
    ':skip_private_network => true',
):
    if token not in block:
        fail(f'GOAD-WS01 Vagrant contract is missing {token}')

provider_inventory = Path('ad/GOAD/providers/vmware/inventory').read_text()
provider_line = 'ws01 ansible_host=10.4.10.31 dns_domain=dc02 dict_key=ws01'
if provider_line not in provider_inventory:
    fail('WS01 provider inventory endpoint is incorrect')

disabled_inventory = Path('ad/GOAD/data/inventory_disable_vagrant').read_text()
if 'ws01 ansible_host=' in disabled_inventory:
    fail('canonical WS01 post-Vagrant inventory must not duplicate a plaintext credential')

lab_inventory = Path('ad/GOAD/data/inventory').read_text()
for section in ('domain', 'workstation', 'no_update'):
    if 'ws01' not in section_items(lab_inventory, section):
        fail(f'ws01 missing from [{section}]')
for section in ('server', 'dc', 'defender_on', 'defender_off', 'laps_workstation'):
    if 'ws01' in section_items(lab_inventory, section):
        fail(f'ws01 must not be in [{section}]')

provider_source = Path('goad/provider/vagrant/vmware.py').read_text()
vmware_tree = ast.parse(provider_source)
vmware_class = next(
    node for node in vmware_tree.body
    if isinstance(node, ast.ClassDef) and node.name == 'VmwareProvider'
)
windows_assignment = next(
    node for node in vmware_class.body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == 'goad_nomad_windows' for target in node.targets)
)
windows = ast.literal_eval(windows_assignment.value)
expected_windows = [
    'GOAD-DC01', 'GOAD-DC02', 'GOAD-DC03',
    'GOAD-SRV02', 'GOAD-SRV03', 'GOAD-WS01',
]
if windows != expected_windows:
    fail(f'VMware lifecycle Windows list mismatch: {windows!r}')

nomad_tree = ast.parse(Path('goad/provider/vagrant/vmware_nomad.py').read_text())
nomad_class = next(
    node for node in nomad_tree.body
    if isinstance(node, ast.ClassDef) and node.name == 'GoadNomadVmwareProvider'
)
management_assignment = next(
    node for node in nomad_class.body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == 'management_hosts' for target in node.targets)
)
management = ast.literal_eval(management_assignment.value)
if management.get('GOAD-WS01') != '10.4.10.31' or len(management) != 6:
    fail(f'management readiness contract mismatch: {management!r}')

lab_mode = Path('scripts/lab-mode.sh').read_text()
# The shared lifecycle now defines one full GOAD roster and omits only the
# two Essos guests for NORTH. A static whitespace split would incorrectly
# treat the Bash array expansion as a literal Windows VM name. Evaluate only
# the declaration block (no main(), host operations, sudo or Vagrant).
try:
    roster_start = lab_mode.index('# An explicit profile selection controls only')
    roster_end = lab_mode.index('\ndeclare -A DC_DOMAIN=(', roster_start)
except ValueError:
    fail('lab-mode profile roster declaration missing')
roster_source = lab_mode[roster_start:roster_end]
if 'readonly WINDOWS_VMS=(' not in roster_source:
    fail('lab-mode Windows VM list missing')

north_windows = [vm for vm in expected_windows
                 if vm not in ('GOAD-DC03', 'GOAD-SRV03')]
for profile, expected_roster in (
    ('GOAD', expected_windows),
    ('NORTH', north_windows),
):
    try:
        completed = subprocess.run(
            ['bash', '-c', roster_source + '\necho "${WINDOWS_VMS[*]}"\n'],
            env={'GOAD_LAB_PROFILE': profile, 'PATH': '/usr/bin:/bin'},
            capture_output=True, text=True, check=False, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        fail(f'lab-mode {profile} roster evaluation failed: {exc}')
    if completed.returncode != 0:
        fail(f'lab-mode {profile} roster evaluation failed: {completed.stderr.strip()}')
    actual_roster = completed.stdout.strip().split()
    if actual_roster != expected_roster:
        fail(f'lab-mode {profile} Windows roster mismatch: {actual_roster!r}')

runtime = Path('scripts/validate-network-segmentation-runtime.sh').read_text()
focused_runtime = Path('scripts/validate-ws01-runtime.sh').read_text()
runtime_match = re.search(r'^readonly WINDOWS_VMS=\(([^)]*)\)', runtime, re.MULTILINE)
if runtime_match is None or runtime_match.group(1).split() != expected_windows:
    fail('runtime validation Windows list does not match the six-machine contract')
if '[GOAD-WS01]=WS01' not in runtime:
    fail('runtime validation does not verify the WS01 hostname')
for token in (
    'WS01_DOMAIN=PASS',
    'WS01_RICKON_RDP=PASS',
    'WS01_RICKON_LOW_PRIV=PASS',
    'WS01_UAC=PASS',
    'WS01_FIREWALL=PASS',
    'WS01_DEFENDER=PASS',
):
    if token not in runtime:
        fail(f'WS01 runtime foundation check missing: {token}')
if 'WS01_FOUNDATION=PASS' not in focused_runtime:
    fail('focused WS01 runtime validator is missing its success contract')
for token in (
    'readonly WS01_IP="10.4.10.31"',
    'wait_for_tcp "${WS01_IP}" 3389',
    'wait_for_tcp "${WS01_IP}" 5986',
):
    if token not in focused_runtime:
        fail(f'focused WS01 runtime validator missing bounded service reachability contract: {token}')
if 'timeout 3 nc -zw2 "${host}" "${port}"' not in focused_runtime:
    fail('focused WS01 runtime validator wait_for_tcp helper does not perform bounded TCP probes')
if re.search(r'ping\s+[^\n]*10\.4\.10\.31', focused_runtime):
    fail('focused WS01 runtime validator must not require ICMP echo while Windows Firewall remains enabled')

playbook = Path('ansible/ws01.yml').read_text()
ad_servers = Path('ansible/ad-servers.yml').read_text()
for token in (
    "hosts: ws01",
    "role: 'commonwkstn'",
    "role: 'settings/adjust_rights'",
    "role: 'settings/user_rights'",
):
    if token not in playbook:
        fail(f'WS01 foundation playbook missing: {token}')
for forbidden in ('vulnerabilities', 'windows_lpe', 'disable_firewall', 'defender_off'):
    if forbidden in playbook:
        fail(f'WS01 foundation playbook contains premature weakening: {forbidden}')
if 'default(lab.domains[lab.hosts[dict_key].domain].domain_password)' not in ad_servers:
    fail('full GOAD provisioning does not provide the WS01 inherited local-admin credential')

console = Path('goad_nomad.py').read_text()
for token in (
    "def do_ws01(",
    "run('ws01.yml')",
    'provider.finalize_install()',
    "elif args.task == 'ws01':",
):
    if token not in console:
        fail(f'GOAD-WS01 controller integration missing: {token}')

console_tree = ast.parse(console)
console_class = next(
    node for node in console_tree.body
    if isinstance(node, ast.ClassDef) and node.name == 'GoadNomad'
)
ws01_method = next(
    node for node in console_class.body
    if isinstance(node, ast.FunctionDef) and node.name == '_do_ws01'
)
fail_closed_try = next(
    (
        node for node in ast.walk(ws01_method)
        if isinstance(node, ast.Try)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == 'install'
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == 'provider'
            for statement in node.body
            for call in ast.walk(statement)
        )
    ),
    None,
)
if fail_closed_try is None:
    fail('WS01 provider bring-up is not owned by a fail-closed try/finally')
if not any(
    isinstance(call, ast.Call)
    and isinstance(call.func, ast.Attribute)
    and call.func.attr == 'finalize_install'
    for statement in fail_closed_try.finalbody
    for call in ast.walk(statement)
):
    fail('WS01 provider failure does not guarantee final exercise isolation')

tools_method = next(
    node for node in vmware_class.body
    if isinstance(node, ast.FunctionDef) and node.name == '_install_vmware_tools'
)
recovery_reboots = [
    call
    for handler in (
        node for node in ast.walk(tools_method)
        if isinstance(node, ast.ExceptHandler)
    )
    for call in ast.walk(handler)
    if isinstance(call, ast.Call)
    and isinstance(call.func, ast.Attribute)
    and call.func.attr == 'run_ps'
    and call.args
    and isinstance(call.args[0], ast.Constant)
    and 'shutdown.exe /r' in str(call.args[0].value)
]
if not recovery_reboots:
    fail('interrupted VMware Tools installation has no controlled recovery reboot')
if 'VMware Tools recovery reboot completed' not in provider_source:
    fail('VMware Tools recovery reboot lacks a validated success contract')

dispatch = next(
    node for node in console_tree.body
    if isinstance(node, ast.FunctionDef) and node.name == '_dispatch_task'
)
ws01_dispatch_calls = [
    node for node in ast.walk(dispatch)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr == 'do_ws01'
]
if len(ws01_dispatch_calls) != 1:
    fail('WS01 non-interactive dispatch must call do_ws01 exactly once')
if not any(
    isinstance(node, ast.If)
    and any(call is ws01_dispatch_calls[0] for call in ast.walk(node.test))
    and any(
        isinstance(child, ast.Return)
        and isinstance(child.value, ast.Constant)
        and child.value.value == 1
        for statement in node.body
        for child in ast.walk(statement)
    )
    for node in ast.walk(dispatch)
):
    fail('WS01 non-interactive dispatch does not propagate a failed task exit status')

extension = json.loads(Path('extensions/ws01/extension.json').read_text())
if 'GOAD' in extension.get('compatibility', []):
    fail('legacy ws01 extension still conflicts with first-class GOAD-WS01')

for token in (
    '_sync_goad_nomad_inventories',
    'added the committed GOAD-WS01 definition',
    'an incompatible GOAD-WS01 definition',
    'cannot derive the WS01 post-Vagrant inventory',
):
    if token not in provider_source:
        fail(f'existing-instance migration contract missing: {token}')
PY
pass "WS01 topology, identity, security and lifecycle contract"

git diff --check
pass "Git whitespace check"

printf '\n[READY] GOAD Kingdoms WS01 source validation passed.\n'
