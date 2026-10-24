"""Failure-path tests with simulated Vagrant/WinRM; no VMs or root required."""
import ast
from functools import partial
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from goad.install_profile import new_install_profile, save_install_profile


def load_class(file, name, namespace):
    tree = ast.parse((ROOT / file).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), file, 'exec'), namespace)
    return namespace[name]


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        class Base:
            def install(self):
                return self.command.run_vagrant(['up', 'GOAD-SRV02'], self.path)

        self.log = Mock()
        cls = load_class('goad/provider/vagrant/vmware_kingdoms_profile.py',
            'ProfiledGoadKingdomsVmwareProvider', {
                'Path': Path, 'time': time, 'Log': self.log,
                'new_install_profile': new_install_profile,
                'save_install_profile': save_install_profile,
                'GoadKingdomsVmwareProvider': Base,
            })
        self.provider = cls()
        self.provider.lab_name = 'GOAD'
        self.provider.path = self.root / 'provider'
        self.provider.command = SimpleNamespace(run_vagrant=Mock(return_value=True))

    def records(self):
        return [json.loads(p.read_text()) for p in sorted((self.root / 'install-timings').glob('*.json'))]

    def test_first_creation_is_classified_before_vagrant_creates_state(self):
        def up(*args):
            state = self.provider.path / '.vagrant/machines/GOAD-SRV02/vmware_desktop'
            state.mkdir(parents=True)
            (state / 'id').write_text('/guest.vmx')
            return False
        original = self.provider.command.run_vagrant
        original.side_effect = up
        self.assertFalse(self.provider.install())
        self.assertIs(self.provider.command.run_vagrant, original)
        original.side_effect = None
        self.assertTrue(self.provider.install())
        rows = self.records()
        self.assertEqual(len(rows), 2)
        failed = next(row for row in rows if row['status'] == 'failed')
        resumed = next(row for row in rows if row['status'] == 'awaiting_ansible')
        self.assertEqual(failed['phases'][0]['label'], 'Vagrant first creation GOAD-SRV02')
        self.assertEqual(failed['phases'][0]['outcome'], 'failed')
        self.assertEqual(resumed['phases'][0]['label'], 'Vagrant up existing VM GOAD-SRV02')
        self.assertNotEqual(failed['attempt_id'], resumed['attempt_id'])
        self.assertNotIn('started', failed)  # process-specific monotonic timestamp
        self.assertFalse(failed['partial'])
        self.assertTrue(resumed['partial'])

    def test_partial_state_is_not_called_first_creation(self):
        state = self.provider.path / '.vagrant/machines/GOAD-SRV02/vmware_desktop'
        state.mkdir(parents=True)
        self.assertEqual(self.provider._vagrant_profile_label(['up', 'GOAD-SRV02']),
                         'Vagrant up partial state GOAD-SRV02')

    def test_interruption_and_exception_restore_vagrant_and_preserve_failure(self):
        for exc, expected in [(KeyboardInterrupt(), 'interrupted'), (RuntimeError(), 'failed')]:
            with self.subTest(exception=type(exc).__name__):
                original = self.provider.command.run_vagrant
                original.side_effect = exc
                with self.assertRaises(type(exc)):
                    self.provider.install()
                self.assertIs(self.provider.command.run_vagrant, original)
                self.assertFalse(self.provider._kingdoms_install_profile_active)
                self.assertEqual(self.provider._kingdoms_install_profile['status'], expected)
        self.assertEqual(len(self.records()), 2)

    def test_timing_storage_failure_does_not_fail_installation(self):
        (self.root / 'install-timings').write_text('not a directory')
        self.assertTrue(self.provider.install())
        self.assertEqual(self.log.warning.call_count, 1)

    def test_atomic_replace_failure_keeps_previous_checkpoint(self):
        profile = new_install_profile(self.provider.path)
        warn = Mock()
        self.assertTrue(save_install_profile(profile, warn))
        before = Path(profile['_path']).read_text()
        profile['status'] = 'failed'
        with patch('goad.install_profile.os.replace', side_effect=OSError('disk unavailable')):
            self.assertFalse(save_install_profile(profile, warn))
        self.assertEqual(Path(profile['_path']).read_text(), before)
        self.assertEqual(len(list((self.root / 'install-timings').iterdir())), 1)

    def test_other_labs_do_not_get_profile_state_or_files(self):
        self.provider.lab_name = 'GOAD-Light'
        self.assertTrue(self.provider.install())
        self.assertFalse(hasattr(self.provider, '_kingdoms_install_profile'))
        self.assertFalse((self.root / 'install-timings').exists())


class AnsibleProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        profile = new_install_profile(Path(self.temp.name) / 'provider')
        profile.update(status='awaiting_ansible', provider_success=True, provider_elapsed=1)
        base = load_class('goad/provisioner/ansible/ansible.py', 'Ansible', {
            'Provisioner': object, 'Log': Mock(), 'time': time, 'os': os,
        })
        local = load_class('goad/provisioner/ansible/local.py', 'LocalAnsibleProvisionerCmd', {
            'Ansible': base, 'Log': Mock(), 'PROVISIONING_LOCAL': 'local',
            'os': os, 'Path': Path, 'partial': partial,
        })
        self.ansible = local()
        self.ansible.lab_name = 'GOAD'
        self.ansible.provider_name = 'vmware'
        self.ansible.path = '/ansible'
        self.ansible.provider = SimpleNamespace(
            _kingdoms_install_profile=profile,
            _save_install_profile=lambda: save_install_profile(profile, Mock()),
        )
        self.ansible.command = SimpleNamespace(run_ansible=Mock(return_value=True))
        self.ansible.get_inventory = Mock(return_value=['inventory'])
        self.ansible.get_playbook_list = Mock(return_value=['servers.yml'])
        self.ansible._prepare_provider_provisioning = Mock(return_value=True)
        self.ansible._finalize_provider_provisioning = Mock(return_value=True)
        self.profile = profile

    def test_north_reuses_existing_profiling_and_pre_ad_ansible_bootstrap(self):
        self.ansible.lab_name = 'NORTH'
        self.assertIs(self.ansible._kingdoms_install_profile(), self.profile)
        self.assertTrue(self.ansible.run())
        self.assertEqual(self.profile['status'], 'completed')
        self.ansible._prepare_provider_provisioning.assert_called_once_with()
        self.ansible._finalize_provider_provisioning.assert_called_once_with()
        self.ansible.command.run_ansible.assert_called_once()

    def test_north_failed_or_finished_provider_profile_is_not_bootstrap(self):
        self.ansible.lab_name = 'NORTH'
        self.profile['status'] = 'failed'
        self.assertIsNone(self.ansible._kingdoms_install_profile())
        self.profile['status'] = 'completed'
        self.assertIsNone(self.ansible._kingdoms_install_profile())

    def test_north_manifest_resume_skips_completed_ad_build_and_finalizes(self):
        self.ansible.lab_name = 'NORTH'
        self.ansible.get_playbook_list.return_value = [
            'build.yml', 'ad-servers.yml', 'ad-parent_domain.yml',
            'kingdoms-health.yml', 'vulnerabilities.yml', 'phase01.yml',
            'ws01-lpe-install.yml', 'kingdoms-health-final.yml',
        ]
        self.assertTrue(self.ansible.run_from('vulnerabilities.yml'))
        executed = [call.args[0] for call in
                    self.ansible.command.run_ansible.call_args_list]
        self.assertEqual(executed, [
            '-i inventory vulnerabilities.yml',
            '-i inventory phase01.yml',
            '-i inventory ws01-lpe-install.yml',
            '-i inventory kingdoms-health-final.yml',
        ])
        self.ansible._prepare_provider_provisioning.assert_called_once()
        self.ansible._finalize_provider_provisioning.assert_called_once()
        self.assertNotIn('build.yml', ' '.join(executed))
        self.assertEqual(self.profile['status'], 'awaiting_ansible')

    def test_retry_attempts_have_individual_outcomes_and_isolated_task_files(self):
        self.ansible.command.run_ansible.side_effect = [False, True]
        original_env = dict(os.environ)
        self.assertTrue(self.ansible.run())
        attempts = [p for p in self.profile['ansible_phases'] if p['kind'] == 'playbook_attempt']
        self.assertEqual([p['outcome'] for p in attempts], ['failed', 'succeeded'])
        self.assertTrue(attempts[0]['label'].endswith('#1'))
        self.assertTrue(attempts[1]['label'].endswith('#2'))
        paths = [c.kwargs['env']['GOAD_INSTALL_TASK_TIMINGS']
                 for c in self.ansible.command.run_ansible.call_args_list]
        self.assertNotEqual(paths[0], paths[1])
        self.assertEqual(dict(os.environ), original_env)
        self.assertEqual(self.profile['status'], 'completed')
        self.assertIsNone(self.ansible._active_install_profile)
        saved = json.loads(Path(self.profile['_path']).read_text())
        self.assertFalse(saved['partial'])
        self.assertGreaterEqual(saved['recorded_elapsed'], saved['ansible_elapsed'])
        self.ansible._finalize_provider_provisioning.assert_called_once()

    def test_failed_retries_preserve_existing_limit_and_do_not_finalize(self):
        self.ansible.command.run_ansible.return_value = False
        self.assertFalse(self.ansible.run())
        self.assertEqual(self.ansible.command.run_ansible.call_count, 4)
        self.assertEqual(self.profile['status'], 'failed')
        self.ansible._finalize_provider_provisioning.assert_not_called()

    def test_preparation_interruption_is_persisted_and_propagated(self):
        self.ansible._prepare_provider_provisioning.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.ansible.run()
        self.assertEqual(self.profile['status'], 'interrupted')
        self.assertEqual(self.profile['ansible_phases'][0]['outcome'], 'interrupted')
        self.assertIsNone(self.ansible._active_install_profile)
        self.ansible.command.run_ansible.assert_not_called()

    def test_failed_finalization_cannot_report_completed(self):
        self.ansible._finalize_provider_provisioning.return_value = False
        self.assertFalse(self.ansible.run())
        self.assertEqual(self.profile['status'], 'failed')
        self.assertEqual(self.profile['ansible_phases'][-1]['outcome'], 'failed')

    def test_standalone_playbook_does_not_consume_pending_install_profile(self):
        self.assertTrue(self.ansible.run('servers.yml'))
        self.assertEqual(self.profile['status'], 'awaiting_ansible')
        self.assertEqual(self.profile['ansible_phases'], [])
        self.ansible.command.run_ansible.assert_called_once_with('-i inventory servers.yml', '/ansible')

    def test_completed_profile_is_not_reused_by_later_runs(self):
        self.assertTrue(self.ansible.run())
        before = Path(self.profile['_path']).read_text()
        self.assertTrue(self.ansible.run())
        self.assertEqual(Path(self.profile['_path']).read_text(), before)


class ToolsReportingTests(unittest.TestCase):
    def setUp(self):
        class Base:
            def _ensure_vmware_tools(self, machine):
                return self.ensure_behavior()

            def _wait_guest_ip(self, vmx, timeout):
                return 'inherited'

        self.process = Mock()
        self.process.TimeoutExpired = subprocess.TimeoutExpired
        self.process.run.return_value = subprocess.CompletedProcess([], 0,
            '5985 (guest) => 2207 (host)\n', '')
        self.clock = SimpleNamespace(now=0)
        self.clock.monotonic = lambda: self.clock.now
        self.clock.sleep = lambda seconds: setattr(self.clock, 'now', self.clock.now + seconds)
        cls = load_class('goad/provider/vagrant/vmware_kingdoms.py', 'GoadKingdomsVmwareProvider', {
            'GoadNomadVmwareProvider': Base, 'Log': Mock(), 'os': os, 're': re,
            'ipaddress': ipaddress, 'subprocess': self.process, 'time': self.clock,
        })
        self.provider = cls()
        self.provider.lab_name = 'GOAD'
        self.provider.goad_nomad_windows = ['GOAD-SRV02']
        self.provider.path = '/instance/provider'
        self.provider.command = SimpleNamespace(vagrant_bin='vagrant')
        self.session = Mock()
        self.session.run_ps.return_value = SimpleNamespace(status_code=0, std_out=b'GOAD_VMTOOLS_RESTARTED')
        self.provider._winrm_session = Mock(return_value=self.session)
        self.provider._guest_tools_healthy = Mock(return_value=True)

    def test_one_restart_limit_survives_repeated_polling_failures(self):
        self.provider._poll_guest_ip_bounded = Mock(return_value=False)
        self.provider._restart_tools_reporting = Mock(return_value=False)
        def check():
            self.assertFalse(self.provider._wait_guest_ip('/guest.vmx', 1))
            return self.provider._wait_guest_ip('/guest.vmx', 1)
        self.provider.ensure_behavior = check
        self.assertFalse(self.provider._ensure_vmware_tools('GOAD-SRV02'))
        self.provider._restart_tools_reporting.assert_called_once_with('GOAD-SRV02', '/guest.vmx')
        self.assertIsNone(self.provider._tools_reporting_context)

    def test_healthy_reporting_does_not_restart_any_service(self):
        self.provider._authenticated_guest_install_ready = Mock(return_value=True)
        self.provider._vmx_path = Mock(return_value='/guest.vmx')
        self.provider._poll_guest_ip_bounded = Mock(return_value=True)
        self.provider._restart_tools_reporting = Mock()

        self.assertTrue(self.provider._ensure_vmware_tools('GOAD-SRV02'))

        self.provider._authenticated_guest_install_ready.assert_called_once_with(
            'GOAD-SRV02'
        )
        self.provider._poll_guest_ip_bounded.assert_called_once_with(
            '/guest.vmx', 10
        )
        self.provider._restart_tools_reporting.assert_not_called()

    def test_guest_health_does_not_bypass_failed_vagrant_provisioning(self):
        self.provider.prepare_install = Mock(return_value=True)
        self.provider._sync_goad_nomad_inventories = Mock(return_value=True)
        self.provider._sync_goad_nomad_vagrantfile_compatibility = Mock(return_value=True)
        self.provider._bring_up_router = Mock(return_value=True)
        self.provider.command.run_vagrant = Mock(return_value=False)
        self.provider._ensure_vmware_tools = Mock(return_value=True)
        self.provider._recover_failed_windows_vagrant_up = Mock(return_value=False)
        self.assertFalse(self.provider.install())
        self.provider._recover_failed_windows_vagrant_up.assert_called_once_with('GOAD-SRV02')
        self.process.run.assert_not_called()

    def test_failed_first_up_can_recover_before_canonical_ip_exists(self):
        self.provider.prepare_install = Mock(return_value=True)
        self.provider._sync_goad_nomad_inventories = Mock(return_value=True)
        self.provider._sync_goad_nomad_vagrantfile_compatibility = Mock(return_value=True)
        self.provider._bring_up_router = Mock(return_value=True)
        self.provider.command.run_vagrant = Mock(return_value=False)
        self.provider._ensure_vmware_tools = Mock(return_value=False)
        self.provider._authenticated_guest_recovery_ready = Mock(return_value=True)
        self.provider._recover_failed_windows_vagrant_up = Mock(return_value=False)

        self.assertFalse(self.provider.install())

        self.provider._authenticated_guest_recovery_ready.assert_called_once_with('GOAD-SRV02')
        self.provider._recover_failed_windows_vagrant_up.assert_called_once_with('GOAD-SRV02')

    def test_failed_first_up_still_fails_closed_without_recovery_readiness(self):
        self.provider.prepare_install = Mock(return_value=True)
        self.provider._sync_goad_nomad_inventories = Mock(return_value=True)
        self.provider._sync_goad_nomad_vagrantfile_compatibility = Mock(return_value=True)
        self.provider._bring_up_router = Mock(return_value=True)
        self.provider.command.run_vagrant = Mock(return_value=False)
        self.provider._ensure_vmware_tools = Mock(return_value=False)
        self.provider._authenticated_guest_recovery_ready = Mock(return_value=False)
        self.provider._recover_failed_windows_vagrant_up = Mock()

        self.assertFalse(self.provider.install())

        self.provider._recover_failed_windows_vagrant_up.assert_not_called()

    def test_resumed_partial_guest_recovers_even_when_vagrant_up_returns_success(self):
        """A running APIPA guest must rerun provisioners instead of being trusted."""
        self.provider.prepare_install = Mock(return_value=True)
        self.provider._sync_goad_nomad_inventories = Mock(return_value=True)
        self.provider._sync_goad_nomad_vagrantfile_compatibility = Mock(return_value=True)
        self.provider._bring_up_router = Mock(return_value=True)
        self.provider.command.run_vagrant = Mock(return_value=True)
        self.provider._ensure_vmware_tools = Mock(return_value=False)
        self.provider._authenticated_guest_recovery_ready = Mock(return_value=True)
        self.provider._recover_failed_windows_vagrant_up = Mock(return_value=False)

        self.assertFalse(self.provider.install())

        self.provider._authenticated_guest_recovery_ready.assert_called_once_with(
            'GOAD-SRV02'
        )
        self.provider._recover_failed_windows_vagrant_up.assert_called_once_with(
            'GOAD-SRV02'
        )

    def test_preprovision_recovery_contract_matches_srv02_failure_state(self):
        """Forwarded WinRM + VMware Tools may recover before the lab IP exists."""
        self.provider._winrm_forwarded_port = Mock(return_value=2207)
        self.provider._wait_winrm_ready = Mock(return_value=True)
        self.session.run_ps.return_value = SimpleNamespace(
            status_code=0,
            std_out=b'GOAD_KINGDOMS_RECOVERY_READY',
        )

        self.assertTrue(
            self.provider._authenticated_guest_recovery_ready('GOAD-SRV02')
        )

        script = self.session.run_ps.call_args.args[0]
        self.assertIn('VMTools', script)
        self.assertIn('vmtoolsd', script)
        self.assertIn(r'C:\Program Files\VMware\VMware Tools\vmtoolsd.exe', script)
        self.assertNotIn('Get-NetIPAddress', script)
        self.assertNotIn('10.4.10.22', script)
        self.provider._wait_winrm_ready.assert_called_once_with(2207, 60)

    def test_preprovision_recovery_does_not_weaken_final_kingdoms_ip_gate(self):
        """The temporary recovery state must never count as installed readiness."""
        self.provider.management_hosts = {'GOAD-SRV02': '10.4.10.22'}
        self.provider._winrm_forwarded_port = Mock(return_value=2207)
        self.provider._wait_winrm_ready = Mock(return_value=True)

        self.session.run_ps.side_effect = [
            SimpleNamespace(
                status_code=0,
                std_out=b'GOAD_KINGDOMS_RECOVERY_READY',
            ),
            SimpleNamespace(status_code=0, std_out=b''),
        ]

        self.assertTrue(
            self.provider._authenticated_guest_recovery_ready('GOAD-SRV02')
        )
        self.assertFalse(
            self.provider._authenticated_guest_install_ready('GOAD-SRV02')
        )

        recovery_script = self.session.run_ps.call_args_list[0].args[0]
        final_script = self.session.run_ps.call_args_list[1].args[0]
        self.assertNotIn('Get-NetIPAddress', recovery_script)
        self.assertIn('Get-NetIPAddress', final_script)
        self.assertIn('10.4.10.22', final_script)

    def test_recovery_cycle_must_reach_strict_readiness_after_provision(self):
        """A successful --provision command alone cannot complete recovery."""
        self.provider._stop_failed_windows_guest_cleanly = Mock(return_value=True)
        self.provider._run_vagrant_bounded = Mock(return_value=True)
        self.provider._ensure_vmware_tools = Mock(return_value=False)

        self.assertFalse(
            self.provider._recover_failed_windows_vagrant_up('GOAD-SRV02')
        )

        self.provider._run_vagrant_bounded.assert_called_once_with(
            ['up', 'GOAD-SRV02', '--provision'],
            timeout=600,
        )
        self.provider._ensure_vmware_tools.assert_called_once_with('GOAD-SRV02')

    def test_recovery_cycle_succeeds_only_after_strict_readiness_returns(self):
        self.provider._stop_failed_windows_guest_cleanly = Mock(return_value=True)
        self.provider._run_vagrant_bounded = Mock(return_value=True)
        self.provider._ensure_vmware_tools = Mock(return_value=True)

        self.assertTrue(
            self.provider._recover_failed_windows_vagrant_up('GOAD-SRV02')
        )

        self.provider._run_vagrant_bounded.assert_called_once_with(
            ['up', 'GOAD-SRV02', '--provision'],
            timeout=600,
        )
        self.provider._ensure_vmware_tools.assert_called_once_with('GOAD-SRV02')

    def test_authenticated_guest_state_wins_over_broken_vmrun_reporting(self):
        """Healthy authenticated guest must survive stale VIX telemetry."""
        self.provider.management_hosts = {'GOAD-SRV02': '10.4.10.22'}
        self.provider._winrm_forwarded_port = Mock(return_value=2207)
        self.provider._wait_winrm_ready = Mock(return_value=True)
        self.provider._vmx_path = Mock(return_value='/guest.vmx')
        self.provider._poll_guest_ip_bounded = Mock(return_value=False)

        self.session.run_ps.return_value = SimpleNamespace(
            status_code=0,
            std_out=b'GOAD_KINGDOMS_GUEST_READY',
        )

        self.provider.ensure_behavior = Mock(
            side_effect=AssertionError(
                'inherited recovery must not run for a proven healthy guest'
            )
        )

        self.assertTrue(self.provider._ensure_vmware_tools('GOAD-SRV02'))

        self.provider.ensure_behavior.assert_not_called()
        self.provider._wait_winrm_ready.assert_called_once_with(2207, 60)
        self.provider._poll_guest_ip_bounded.assert_called_once_with(
            '/guest.vmx', 10
        )

    def test_authenticated_guest_state_requires_expected_kingdoms_ip(self):
        """Working NAT WinRM alone must not satisfy KINGDOMS readiness."""
        self.provider.management_hosts = {'GOAD-SRV02': '10.4.10.22'}
        self.provider._winrm_forwarded_port = Mock(return_value=2207)
        self.provider._wait_winrm_ready = Mock(return_value=True)

        self.session.run_ps.return_value = SimpleNamespace(
            status_code=0,
            std_out=b'',
        )

        self.provider.ensure_behavior = Mock(return_value=False)

        self.assertFalse(self.provider._ensure_vmware_tools('GOAD-SRV02'))
        self.provider.ensure_behavior.assert_called_once()

    def test_healthy_tools_and_nat_winrm_cannot_bypass_missing_lab_ip(self):
        """Inherited Tools success is not final Kingdoms readiness."""
        self.provider.management_hosts = {'GOAD-SRV02': '10.4.10.22'}
        self.provider._winrm_forwarded_port = Mock(return_value=2207)
        self.provider._wait_winrm_ready = Mock(return_value=True)
        self.session.run_ps.return_value = SimpleNamespace(
            status_code=0,
            std_out=b'',
        )
        self.provider.ensure_behavior = Mock(return_value=True)

        self.assertFalse(self.provider._ensure_vmware_tools('GOAD-SRV02'))
        self.provider.ensure_behavior.assert_called_once()
        self.assertEqual(self.session.run_ps.call_count, 2)

    def test_non_goad_uses_inherited_readiness_without_repair_context(self):
        self.provider.lab_name = 'GOAD-Light'
        self.provider.ensure_behavior = lambda: self.provider._wait_guest_ip('/guest.vmx')
        self.assertEqual(self.provider._ensure_vmware_tools('GOAD-SRV02'), 'inherited')
        self.assertFalse(hasattr(self.provider, '_tools_reporting_context'))

    def test_recovery_scope_is_removed_on_interrupt(self):
        self.provider.ensure_behavior = Mock(side_effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.provider._ensure_vmware_tools('GOAD-SRV02')
        self.assertIsNone(self.provider._tools_reporting_context)
        self.assertEqual(self.provider._wait_guest_ip('/guest.vmx'), 'inherited')

    def test_restart_requires_authenticated_success_and_host_confirmation(self):
        self.provider._poll_guest_ip_bounded = Mock(return_value=True)
        self.assertTrue(self.provider._restart_tools_reporting('GOAD-SRV02', '/guest.vmx'))
        self.provider._winrm_session.assert_called_once_with(2207)
        self.assertEqual(self.process.run.call_args.kwargs['timeout'], 15)
        self.provider._poll_guest_ip_bounded.return_value = False
        self.assertFalse(self.provider._restart_tools_reporting('GOAD-SRV02', '/guest.vmx'))

    def test_failed_authentication_or_service_command_cannot_recover(self):
        self.provider._poll_guest_ip_bounded = Mock()
        self.session.run_ps.side_effect = RuntimeError('authentication failed')
        self.assertFalse(self.provider._restart_tools_reporting('GOAD-SRV02', '/guest.vmx'))
        self.provider._poll_guest_ip_bounded.assert_not_called()
        self.session.run_ps.side_effect = None
        self.session.run_ps.return_value = SimpleNamespace(status_code=1, std_out=b'')
        self.assertFalse(self.provider._restart_tools_reporting('GOAD-SRV02', '/guest.vmx'))
        self.provider._poll_guest_ip_bounded.assert_not_called()

    def test_polling_bounds_hung_vmrun_calls_and_total_window(self):
        def hang(*args, **kwargs):
            self.clock.now += kwargs['timeout']
            raise subprocess.TimeoutExpired('vmrun', kwargs['timeout'])
        self.process.run.side_effect = hang
        self.assertFalse(self.provider._poll_guest_ip_bounded('/guest.vmx', 25))
        self.assertEqual(self.clock.now, 25)
        self.assertEqual(self.process.run.call_count, 2)
        self.assertTrue(all(c.kwargs['timeout'] <= 10 for c in self.process.run.call_args_list))

    def test_apipa_is_not_healthy_guest_reporting(self):
        self.process.run.return_value = subprocess.CompletedProcess([], 0, '169.254.246.88', '')
        self.assertFalse(self.provider._poll_guest_ip_bounded('/guest.vmx', 5))
        self.process.run.return_value = subprocess.CompletedProcess([], 0, '192.168.213.139', '')
        self.assertTrue(self.provider._poll_guest_ip_bounded('/guest.vmx', 5))


if __name__ == '__main__':
    unittest.main()