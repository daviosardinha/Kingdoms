"""Focused lifecycle tests; no VMware, root privileges or GOAD dependencies."""
import ast
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def load_method(file, name, namespace):
    tree = ast.parse((ROOT / file).read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[method], type_ignores=[]), file, 'exec'), namespace)
    return namespace[name]


def class_field(file, name):
    tree = ast.parse((ROOT / file).read_text())
    return next(ast.literal_eval(n.value) for n in ast.walk(tree)
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))


class RouterStartup(unittest.TestCase):
    def setUp(self):
        self.process = Mock()
        self.process.run.return_value = subprocess.CompletedProcess([], 0)
        self.process.TimeoutExpired = subprocess.TimeoutExpired
        self.clock = Mock()
        self.clock.monotonic.side_effect = [0, 0, 181]
        self.method = load_method('goad/provider/vagrant/vmware_kingdoms.py', '_bring_up_router', {
            'subprocess': self.process, 'time': self.clock, 'Log': Mock(),
        })
        self.provider = Mock()
        self.provider.path = '/instance/provider'
        self.provider.get_runtime_mode.return_value = 'exercise'
        self.provider._vmx_path.return_value = '/instance/router.vmx'
        self.provider._running_instance_vms.return_value = []
        self.provider._script.side_effect = lambda name: str(ROOT / 'scripts' / name)
        self.provider._provider_env.return_value = {}

    def test_installed_router_uses_vmrun_and_management(self):
        self.assertTrue(self.method(self.provider))
        commands = [c.args[0] for c in self.process.run.call_args_list]
        self.assertEqual(commands[0], ['vmrun', '-T', 'ws', 'start', '/instance/router.vmx', 'nogui'])
        self.assertIn('router-ssh.sh', commands[-1][1])
        self.provider.command.run_vagrant.assert_not_called()

    def test_running_router_is_not_powered_on_again(self):
        self.provider._running_instance_vms.return_value = ['GOAD-ROUTER']
        self.assertTrue(self.method(self.provider))
        self.assertFalse(any(c.args[0][0] == 'vmrun' for c in self.process.run.call_args_list))

    def test_fresh_router_retains_provisioning(self):
        self.provider.get_runtime_mode.return_value = 'unknown'
        self.provider.command.run_vagrant.return_value = True
        self.assertTrue(self.method(self.provider))
        self.provider.command.run_vagrant.assert_called_once_with(['up', 'GOAD-ROUTER'], self.provider.path)
        self.process.run.assert_not_called()

    def test_missing_vmx_fails_without_recreation(self):
        self.provider._vmx_path.return_value = None
        self.assertFalse(self.method(self.provider))
        self.provider.command.run_vagrant.assert_not_called()
        self.process.run.assert_not_called()

    def test_failed_power_on_stops_before_ssh(self):
        self.process.run.return_value = subprocess.CompletedProcess([], 1)
        self.assertFalse(self.method(self.provider))
        self.assertEqual(self.process.run.call_count, 1)

    def test_unreachable_management_has_no_nat_fallback(self):
        self.process.run.side_effect = [subprocess.CompletedProcess([], 0)] * 3 + [subprocess.CompletedProcess([], 255)]
        self.assertFalse(self.method(self.provider))
        self.provider.command.run_vagrant.assert_not_called()

    def test_failed_network_validation_stops_before_ssh(self):
        self.process.run.side_effect = [subprocess.CompletedProcess([], 0)] * 2 + [subprocess.CompletedProcess([], 1)]
        self.assertFalse(self.method(self.provider))
        self.assertEqual(self.process.run.call_count, 3)


class ShellContracts(unittest.TestCase):
    def test_timer_health_states(self):
        text = (ROOT / 'scripts/check-vmware-networks.sh').read_text()
        block = text[text.index('timer_state='):text.index('\nif systemctl is-failed')]
        prefix = '''
failures=0
ok() { :; }
fail() { failures=$((failures + 1)); }
systemctl() {
  if [[ "$1" == is-active ]]; then return 0; fi
  case "$4" in
    SubState) echo "$TEST_TIMER" ;;
    NextElapseUSecMonotonic) echo "$TEST_NEXT" ;;
    ActiveState) echo "$TEST_SERVICE" ;;
  esac
}
HOSTADDR_TIMER=timer
HOSTADDR_SERVICE=service
'''
        for timer, next_run, service, expected in [
            ('waiting', '45s', 'inactive', 0),
            ('elapsed', '0', 'inactive', 1),
            ('waiting', '0', 'inactive', 1),
            ('running', 'infinity', 'activating', 0),
            ('running', 'infinity', 'failed', 1),
        ]:
            with self.subTest(timer=timer, next_run=next_run, service=service):
                result = subprocess.run(['bash', '-c', prefix + block + '\nexit "$failures"'],
                    env={**os.environ, 'TEST_TIMER': timer, 'TEST_NEXT': next_run, 'TEST_SERVICE': service})
                self.assertEqual(result.returncode, expected)

    def test_ssh_key_and_collision_handling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / 'provider/.vagrant/machines/GOAD-ROUTER/vmware_desktop'
            state.mkdir(parents=True)
            (state / 'id').write_text('/router.vmx')
            (state / 'private_key').write_text('test fixture, not a real key')
            bindir = root / 'bin'
            bindir.mkdir()
            (bindir / 'ip').write_text('#!/bin/bash\necho "1: vmnet99 inet ${TEST_ADDRESS}/24"\n')
            (bindir / 'ssh').write_text(
                '#!/bin/bash\n'
                'args="$*"\n'
                'if [[ -n "${TEST_REJECT_KEY:-}" && "$args" == *"${TEST_REJECT_KEY}"* ]]; then exit 255; fi\n'
                'printf "%s\\n" "$@"\n'
                'if [[ " $args " != *" -n "* ]]; then cat; fi\n'
            )
            for file in bindir.iterdir():
                file.chmod(0o755)
            env = {**os.environ, 'GOAD_PROVIDER_DIR': str(root / 'provider'),
                   'VAGRANT_HOME': str(root / 'vagrant'),
                   'XDG_CONFIG_HOME': str(root / 'config'),
                   'PATH': str(bindir) + ':' + os.environ['PATH'],
                   'TEST_ADDRESS': '10.4.99.254'}
            command = ['bash', str(ROOT / 'scripts/router-ssh.sh'), 'sudo nft list ruleset']
            result = subprocess.run(command, env=env, input='stdin preserved', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(state / 'private_key'), result.stdout)
            self.assertIn('vagrant@10.4.99.1', result.stdout)
            self.assertIn('stdin preserved', result.stdout)
            env['TEST_ADDRESS'] = '10.4.99.1'
            self.assertNotEqual(subprocess.run(command, env=env, capture_output=True).returncode, 0)
            env['TEST_ADDRESS'] = '10.4.99.254'
            (state / 'private_key').unlink()
            self.assertNotEqual(subprocess.run(command, env=env, capture_output=True).returncode, 0)
            fallback = root / 'vagrant/insecure_private_key'
            fallback.parent.mkdir()
            fallback.write_text('test fallback')
            result = subprocess.run(command, env=env, input='', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(fallback), result.stdout)

            # A stale per-instance key must not make management unrecoverable
            # when the router still accepts the standard Vagrant identity.
            (state / 'private_key').write_text('stale instance key')
            env['TEST_REJECT_KEY'] = str(state / 'private_key')
            result = subprocess.run(
                command,
                env=env,
                input='stdin preserved',
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(fallback), result.stdout)
            self.assertIn('recovered with fallback Vagrant key', result.stderr)
            self.assertIn('stdin preserved', result.stdout)

            stable = root / 'config/kingdoms/router-management-ed25519'
            stable.parent.mkdir(parents=True)
            stable.write_text('stable test fixture')
            env.pop('TEST_REJECT_KEY', None)
            result = subprocess.run(
                command,
                env=env,
                input='',
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(stable), result.stdout)


class Compatibility(unittest.TestCase):
    def test_old_workspace_migration_is_idempotent(self):
        method = load_method('goad/provider/vagrant/vmware.py', '_sync_goad_nomad_vagrantfile_compatibility', {
            'os': os, 're': re, 'Log': Mock(),
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Vagrantfile'
            # Existing current layout, before offline box settings were added.
            text = ('Vagrant.configure("2") do |config|\n' +
                    (ROOT / 'ad/GOAD/providers/vmware/Vagrantfile').read_text() +
                    '\n        v.vmx["numvcpus"] = box[:cpus]\n' +
                    'v.enable_vmrun_ip_lookup = false\n' +
                    'v.vmx["ethernet0.startConnected"] = "TRUE"\nend\n')
            path.write_text(text)
            provider = Mock(path=directory)
            self.assertTrue(method(provider))
            first = path.read_text()
            self.assertIn('config.vm.box_check_update = false', first)
            self.assertTrue(method(provider))
            self.assertEqual(path.read_text(), first)


class InstalledWindows(unittest.TestCase):
    def setUp(self):
        self.process = Mock()
        self.process.TimeoutExpired = subprocess.TimeoutExpired
        self.process.run.return_value = subprocess.CompletedProcess([], 0)
        self.clock = Mock()
        self.clock.monotonic.return_value = 0
        self.method = load_method('goad/provider/vagrant/vmware_kingdoms.py', '_start_existing_instance', {
            'subprocess': self.process, 'time': self.clock, 'Log': Mock(),
        })
        self.provider = Mock()
        self.provider.get_runtime_mode.return_value = 'exercise'
        self.provider.goad_nomad_windows = ['GOAD-DC01', 'GOAD-DC02']
        self.provider.management_hosts = {
            'GOAD-DC01': '10.4.20.10',
            'GOAD-DC02': '10.4.10.11',
        }
        self.provider._vmx_path.side_effect = lambda name: f'/instance/{name}.vmx'
        self.provider._running_instance_vms.return_value = []
        self.provider._wait_lab_winrm_ready.return_value = True
        self.provider._wait_installed_ad_ready.return_value = True

    def test_direct_power_is_serialized_by_ad_readiness(self):
        events = []

        def run(command, **kwargs):
            if command[:4] == ['vmrun', '-T', 'ws', 'start']:
                events.append(('power', Path(command[4]).stem))
            return subprocess.CompletedProcess([], 0)

        def winrm(machine, host, timeout):
            events.append(('winrm', machine))
            return True

        def ad_ready(machine, host, timeout):
            events.append(('ad', machine))
            return True

        self.process.run.side_effect = run
        self.provider._wait_lab_winrm_ready.side_effect = winrm
        self.provider._wait_installed_ad_ready.side_effect = ad_ready

        self.assertTrue(self.method(self.provider))
        self.assertEqual(
            events,
            [
                ('power', 'GOAD-DC01'),
                ('winrm', 'GOAD-DC01'),
                ('ad', 'GOAD-DC01'),
                ('power', 'GOAD-DC02'),
                ('winrm', 'GOAD-DC02'),
                ('ad', 'GOAD-DC02'),
            ],
        )
        self.provider.command.run_vagrant.assert_not_called()
        self.provider._ensure_vmware_tools.assert_not_called()
        self.assertGreaterEqual(self.provider._enable_provisioning_routes.call_count, 3)

    def test_parent_ad_failure_prevents_dependent_power_on(self):
        self.provider._wait_installed_ad_ready.side_effect = [False]

        self.assertFalse(self.method(self.provider))
        self.assertEqual(self.process.run.call_count, 1)
        self.assertIn('GOAD-DC01', self.process.run.call_args.args[0][4])
        self.provider._wait_installed_ad_ready.assert_called_once()
        self.assertFalse(
            any('GOAD-DC02' in call.args[0][4] for call in self.process.run.call_args_list)
        )

    def test_running_dependency_is_still_validated_before_child_start(self):
        self.provider._running_instance_vms.return_value = ['GOAD-DC01']

        self.assertTrue(self.method(self.provider))
        self.assertEqual(self.process.run.call_count, 1)
        self.assertIn('GOAD-DC02', self.process.run.call_args.args[0][4])
        self.provider._wait_lab_winrm_ready.assert_any_call(
            'GOAD-DC01', '10.4.20.10', timeout=300
        )
        self.provider._wait_installed_ad_ready.assert_any_call(
            'GOAD-DC01', '10.4.20.10', timeout=300
        )

    def test_unknown_mode_cannot_reprovision(self):
        self.provider.get_runtime_mode.return_value = 'unknown'
        self.assertFalse(self.method(self.provider))
        self.provider._bring_up_router.assert_not_called()
        self.process.run.assert_not_called()

    def test_missing_guest_prevents_any_power_on(self):
        self.provider._vmx_path.side_effect = lambda name: None if name == 'GOAD-DC02' else '/vm.vmx'
        self.assertFalse(self.method(self.provider))
        self.provider._bring_up_router.assert_not_called()
        self.process.run.assert_not_called()

    def test_policy_failure_prevents_windows_power_on(self):
        self.provider._apply_router_policy.return_value = False
        self.assertFalse(self.method(self.provider))
        self.process.run.assert_not_called()

    def test_failed_winrm_does_not_invoke_nat_recovery(self):
        self.provider._wait_lab_winrm_ready.return_value = False
        self.assertFalse(self.method(self.provider))
        self.provider.command.run_vagrant.assert_not_called()
        self.provider._ensure_vmware_tools.assert_not_called()
        self.provider._wait_installed_ad_ready.assert_not_called()

    def test_total_dependency_readiness_budget(self):
        self.clock.monotonic.side_effect = [0, 901]
        self.assertFalse(self.method(self.provider))
        self.assertEqual(self.process.run.call_count, 1)
        self.provider._wait_lab_winrm_ready.assert_not_called()
        self.provider._wait_installed_ad_ready.assert_not_called()

    def test_each_real_machine_start_includes_required_ad_dependencies(self):
        names = class_field('goad/provider/vagrant/vmware.py', 'goad_nomad_windows')
        hosts = class_field('goad/provider/vagrant/vmware_nomad.py', 'management_hosts')
        expected = {
            'GOAD-DC01': ['GOAD-DC01'],
            'GOAD-DC02': ['GOAD-DC01', 'GOAD-DC02'],
            'GOAD-DC03': ['GOAD-DC03'],
            'GOAD-SRV02': ['GOAD-DC01', 'GOAD-DC02', 'GOAD-SRV02'],
            'GOAD-SRV03': ['GOAD-DC03', 'GOAD-SRV03'],
            'GOAD-WS01': ['GOAD-DC01', 'GOAD-DC02', 'GOAD-WS01'],
            'GOAD-ROUTER': [],
        }

        self.assertEqual(set(names), set(hosts))
        for selected in names + ['GOAD-ROUTER']:
            with self.subTest(selected=selected):
                self.setUp()
                self.provider.goad_nomad_windows = names
                self.provider.management_hosts = hosts

                self.assertTrue(self.method(self.provider, selected))
                self.provider._bring_up_router.assert_called_once()

                chain = expected[selected]
                if selected == 'GOAD-ROUTER':
                    self.process.run.assert_not_called()
                    self.provider._wait_lab_winrm_ready.assert_not_called()
                    self.provider._wait_installed_ad_ready.assert_not_called()
                    self.provider._apply_router_policy.assert_not_called()
                else:
                    powered = [
                        Path(call.args[0][4]).stem
                        for call in self.process.run.call_args_list
                    ]
                    self.assertEqual(powered, chain)
                    self.assertEqual(
                        [call.args[0] for call in self.provider._wait_lab_winrm_ready.call_args_list],
                        chain,
                    )
                    self.assertEqual(
                        [call.args[0] for call in self.provider._wait_installed_ad_ready.call_args_list],
                        chain,
                    )
                self.provider.command.run_vagrant.assert_not_called()

    def test_installed_members_receive_time_policy_before_ad_readiness(self):
        self.provider.goad_nomad_windows = ['GOAD-DC01', 'GOAD-DC02', 'GOAD-SRV02']
        self.provider.management_hosts = {
            'GOAD-DC01': '10.4.20.10',
            'GOAD-DC02': '10.4.10.11',
            'GOAD-SRV02': '10.4.10.22',
        }
        events = []

        def winrm(machine, host, timeout):
            events.append(('winrm', machine))
            return True

        def time_policy(machine, host):
            events.append(('time-policy', machine))
            return True

        def ad_ready(machine, host, timeout):
            events.append(('ad', machine))
            return True

        self.provider._wait_lab_winrm_ready.side_effect = winrm
        self.provider._ensure_installed_member_time_policy.side_effect = time_policy
        self.provider._wait_installed_ad_ready.side_effect = ad_ready

        self.assertTrue(self.method(self.provider, 'GOAD-SRV02'))
        self.assertIn(('time-policy', 'GOAD-SRV02'), events)
        self.assertLess(
            events.index(('winrm', 'GOAD-SRV02')),
            events.index(('time-policy', 'GOAD-SRV02')),
        )
        self.assertLess(
            events.index(('time-policy', 'GOAD-SRV02')),
            events.index(('ad', 'GOAD-SRV02')),
        )
        self.assertFalse(
            any(event[0] == 'time-policy' and event[1].startswith('GOAD-DC') for event in events)
        )

    def test_installed_member_time_policy_is_retry_only_not_trust_repair(self):
        text = (
            ROOT / 'goad/provider/vagrant/vmware_kingdoms.py'
        ).read_text(encoding='utf-8')
        fn = text[
            text.index('    def _ensure_installed_member_time_policy('):
            text.index('    def _wait_installed_ad_ready(')
        ]

        for token in (
            'ResolvePeerBackoffMinutes',
            'ResolvePeerBackoffMaxTimes',
            "expected NT5DS",
            'w32tm.exe /config /update',
            'KINGDOMS_NT5DS_BACKOFF_READY',
        ):
            self.assertIn(token, fn)

        self.assertIn('if ($changed)', fn)
        self.assertIn("$reloadState = 'not-required'", fn)
        self.assertIn("for ($attempt = 1; $attempt -le 12; $attempt++)", fn)
        self.assertIn("reload={1}", fn)

        for forbidden in (
            'Reset-ComputerMachinePassword',
            '/sc_reset:',
            'netdom resetpwd',
            '/manualpeerlist:',
        ):
            self.assertNotIn(forbidden, fn)
    def test_invalid_selection_has_no_side_effects(self):
        self.assertFalse(self.method(self.provider, 'OTHER-VM'))
        self.provider._bring_up_router.assert_not_called()
        self.process.run.assert_not_called()

    def test_installed_ad_gate_is_validation_only(self):
        text = (
            ROOT / 'goad/provider/vagrant/vmware_kingdoms.py'
        ).read_text(encoding='utf-8')
        fn = text[
            text.index('    def _wait_installed_ad_ready('):
            text.index('    def _start_existing_instance(')
        ]

        for token in (
            "nltest.exe '/dsgetdc:",
            "nltest.exe '/sc_query:",
            'Test-ComputerSecureChannel',
            'w32tm.exe /query /source',
            'KINGDOMS_INSTALLED_AD_READY',
        ):
            self.assertIn(token, fn)

        for forbidden in (
            'Reset-ComputerMachinePassword',
            '/sc_reset:',
            'netdom resetpwd',
            'Restart-Service W32Time',
            'w32tm.exe /config',
            'Set-ItemProperty',
        ):
            self.assertNotIn(forbidden, fn)


class StartIsolation(unittest.TestCase):
    def test_success_failure_interrupt_and_restore_failure(self):
        for outcome, restoration in [(True, True), (False, True), (KeyboardInterrupt(), True), (True, False)]:
            with self.subTest(outcome=outcome, restoration=restoration):
                process = Mock()
                process.run.return_value = subprocess.CompletedProcess([], 0)
                clock = Mock()
                clock.monotonic.return_value = 0
                method = load_method('goad/provider/vagrant/vagrant.py', 'start', {
                    'subprocess': process, 'threading': threading, 'time': clock, 'Log': Mock(),
                })
                provider = Mock()
                provider.is_goad_nomad_segmented.return_value = True
                provider.get_runtime_mode.return_value = 'exercise'
                provider.set_runtime_mode.return_value = restoration
                if isinstance(outcome, BaseException):
                    provider._start_existing_instance.side_effect = outcome
                    with self.assertRaises(KeyboardInterrupt):
                        method(provider)
                else:
                    provider._start_existing_instance.return_value = outcome
                    self.assertEqual(method(provider), outcome and restoration)
                provider.set_runtime_mode.assert_called_once_with('exercise')
                provider.install.assert_not_called()

    def test_single_guest_uses_same_restoration_on_failure(self):
        process = Mock()
        process.run.return_value = subprocess.CompletedProcess([], 0)
        clock = Mock()
        clock.monotonic.return_value = 0
        method = load_method('goad/provider/vagrant/vagrant.py', 'start', {
            'subprocess': process, 'threading': threading, 'time': clock, 'Log': Mock(),
        })
        provider = Mock()
        provider.get_runtime_mode.return_value = 'exercise'
        provider._start_existing_instance.return_value = False
        self.assertFalse(method(provider, 'GOAD-WS01'))
        provider._start_existing_instance.assert_called_once_with('GOAD-WS01')
        provider.set_runtime_mode.assert_called_once_with('exercise')
        provider.install.assert_not_called()


class LocalShutdown(unittest.TestCase):
    def setUp(self):
        self.process = Mock()
        self.process.TimeoutExpired = subprocess.TimeoutExpired
        self.process.run.return_value = subprocess.CompletedProcess([], 0, '', '')
        self.namespace = {'subprocess': self.process, 'Log': Mock()}
        self.stop = load_method('goad/provider/vagrant/vmware_kingdoms.py', 'stop', self.namespace)
        self.stop_vm = load_method('goad/provider/vagrant/vmware_kingdoms.py', 'stop_vm', self.namespace)
        self.start_vm = load_method('goad/provider/vagrant/vmware_kingdoms.py', 'start_vm', self.namespace)
        self.helper = load_method('goad/provider/vagrant/vmware_kingdoms.py', '_stop_machine_via_vmware', self.namespace)
        self.provider = Mock()
        self.provider.lab_name = 'GOAD'
        self.provider.goad_nomad_windows = class_field('goad/provider/vagrant/vmware.py', 'goad_nomad_windows')
        self.provider._last_bounded_vagrant_reaped = True
        self.names = self.provider.goad_nomad_windows + ['GOAD-ROUTER']

    def test_windows_first_router_last_without_vagrant(self):
        self.provider._running_instance_vms.side_effect = [self.names, ['GOAD-ROUTER'], []]
        self.assertTrue(self.stop(self.provider))
        actual = [c.args[0] for c in self.provider._stop_machine_via_vmware.call_args_list]
        self.assertEqual(actual, list(reversed(self.names[:-1])) + ['GOAD-ROUTER'])
        self.provider._run_vagrant_bounded.assert_not_called()
        self.provider.command.run_vagrant.assert_not_called()

    def test_failed_windows_shutdown_preserves_router(self):
        self.provider._running_instance_vms.side_effect = [self.names, ['GOAD-DC01', 'GOAD-ROUTER']]
        self.assertFalse(self.stop(self.provider))
        actual = [c.args[0] for c in self.provider._stop_machine_via_vmware.call_args_list]
        self.assertNotIn('GOAD-ROUTER', actual)

    def test_already_stopped_is_noop(self):
        self.provider._running_instance_vms.return_value = []
        self.assertTrue(self.stop(self.provider))
        self.assertTrue(self.stop_vm(self.provider, 'GOAD-WS01'))
        self.provider._stop_machine_via_vmware.assert_not_called()

    def test_unknown_vmware_state_fails_without_shutdown(self):
        self.provider._running_instance_vms.return_value = None
        self.assertFalse(self.stop(self.provider))
        self.provider._stop_machine_via_vmware.assert_not_called()

    def test_single_stop_targets_only_requested_guest(self):
        self.provider._running_instance_vms.return_value = self.names
        self.provider._stop_machine_via_vmware.return_value = True
        self.assertTrue(self.stop_vm(self.provider, 'GOAD-WS01'))
        self.provider._stop_machine_via_vmware.assert_called_once_with('GOAD-WS01')
        self.assertFalse(self.stop_vm(self.provider, 'GOAD-ROUTER'))
        self.assertFalse(self.stop_vm(self.provider, 'OTHER-VM'))
        self.assertEqual(self.provider._stop_machine_via_vmware.call_count, 1)

    def test_single_start_dispatch_and_invalid_name(self):
        self.provider.start.return_value = True
        self.assertTrue(self.start_vm(self.provider, 'GOAD-WS01'))
        self.provider.start.assert_called_once_with(vm_name='GOAD-WS01')
        self.assertFalse(self.start_vm(self.provider, 'OTHER-VM'))
        self.assertEqual(self.provider.start.call_count, 1)

    def test_unreaped_controller_blocks_local_shutdown(self):
        self.provider._last_bounded_vagrant_reaped = False
        self.assertFalse(self.stop(self.provider))
        self.assertFalse(self.stop_vm(self.provider, 'GOAD-WS01'))
        self.provider._running_instance_vms.assert_not_called()

    def test_soft_success_never_hard_powers_off(self):
        self.provider._vmx_path.return_value = '/instance/ws.vmx'
        self.provider._wait_machine_stopped.return_value = True
        self.assertTrue(self.helper(self.provider, 'GOAD-WS01'))
        self.assertEqual(self.process.run.call_count, 1)
        self.assertEqual(self.process.run.call_args.args[0][-1], 'soft')

    def test_soft_timeout_still_waits_for_guest(self):
        self.process.run.side_effect = subprocess.TimeoutExpired('vmrun', 45)
        self.provider._wait_machine_stopped.return_value = True
        self.assertTrue(self.helper(self.provider, 'GOAD-WS01'))
        self.assertEqual(self.process.run.call_count, 1)

    def test_hard_fallback_requires_proven_running_state(self):
        self.provider._wait_machine_stopped.side_effect = [False, True]
        self.provider._running_instance_vms.return_value = ['GOAD-WS01']
        self.assertTrue(self.helper(self.provider, 'GOAD-WS01'))
        self.assertEqual([c.args[0][-1] for c in self.process.run.call_args_list], ['soft', 'hard'])

    def test_unknown_state_prevents_hard_fallback(self):
        self.provider._wait_machine_stopped.return_value = False
        self.provider._running_instance_vms.return_value = None
        self.assertFalse(self.helper(self.provider, 'GOAD-WS01'))
        self.assertEqual(self.process.run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
