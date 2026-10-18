"""Source-only, no-Windows tests for the explicit #28 pilot."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/wslpe45-single-pilot.py'
spec = importlib.util.spec_from_file_location('wslpe45_single_pilot', SCRIPT)
assert spec and spec.loader
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class SinglePilotTests(unittest.TestCase):
    def test_exact_only_candidate(self):
        self.assertEqual(pilot.PILOTS, {'app_paths_registry_hijack': 28})
        with patch.object(pilot.batch, 'source_readiness') as lookup:
            with self.assertRaises(pilot.batch.BatchBlocked):
                pilot.source_gate('scm_create_service_acl')
            lookup.assert_not_called()

    def test_single_row_source_gate_not_whole_batch(self):
        row = dict(number=28, id='app_paths_registry_hijack', status='candidate',
                   source_ci='passed')
        with patch.object(pilot.batch, 'source_readiness', return_value=(
            [row], ['#25 msi_repair_custom_action: pending'])):
            self.assertIs(pilot.source_gate('app_paths_registry_hijack'), row)
        with patch.object(pilot.batch, 'source_readiness', return_value=(
            [row], ['#28 app_paths_registry_hijack: unsafe source'])):
            with self.assertRaises(pilot.batch.BatchBlocked):
                pilot.source_gate('app_paths_registry_hijack')

    def test_plan_cannot_contact_native_guest(self):
        row = dict(number=28, id='app_paths_registry_hijack', status='candidate',
                   source_ci='passed')
        with patch.object(pilot, 'source_gate', return_value=row), \
             patch.object(pilot.batch, 'trusted_safety') as native, \
             patch.object(pilot.subprocess, 'run') as command:
            self.assertEqual(pilot.main([]), 0)
            native.assert_not_called()
            command.assert_not_called()

    def test_preflight_explicit_read_only_and_fail_closed(self):
        plays = yaml.safe_load(pilot.PREFLIGHT.read_text(encoding='utf-8'))
        self.assertEqual([p['hosts'] for p in plays], ['localhost', 'wslpe'])
        tasks = plays[1]['tasks']
        self.assertEqual(len(tasks), 1)
        self.assertFalse(tasks[0]['changed_when'])
        source = tasks[0]['ansible.windows.win_powershell']['script']
        for required in ('WSLPE-WS01', 'lpe.trainee', 'app_paths_registry_hijack',
                         'Kingdom45AppPathsConsumer', 'Kingdom45AppPathsProbe.exe',
                         'msi_repair_custom_action', 'Kingdom40LocalRpcServer.exe',
                         'WSLPE45_PILOT28_CLEAN=PASS'):
            self.assertIn(required, source)
        for disallowed in ('Remove-Item', 'Set-Acl', 'New-Item',
                           'Register-ScheduledTask', 'Start-Process'):
            self.assertNotIn(disallowed, source)

    def test_snapshot_gate_passes_loaded_preflight_to_existing_guard(self):
        stage = SimpleNamespace(load_preflight=Mock(return_value=object()),
                                verify_vm_snapshot=Mock())
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))
        with patch.object(pilot.importlib.util, 'spec_from_file_location', return_value=spec), \
             patch.object(pilot.importlib.util, 'module_from_spec', return_value=stage):
            pilot.snapshot_gate()
        stage.load_preflight.assert_called_once_with()
        stage.verify_vm_snapshot.assert_called_once_with(stage.load_preflight.return_value)

    def test_read_only_preflight_stops_before_live_journal(self):
        source = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('modes.add_argument("--preflight", action="store_true")', source)
        self.assertIn('modes.add_argument("--execute", action="store_true")', source)
        self.assertLess(source.index('if args.preflight:'),
                        source.index('report = {"schema":'))
        self.assertLess(source.index('if args.preflight:'),
                        source.index('sentinel, os.O_CREAT'))
        self.assertIn('[PASS] #28 read-only guest preflight; no scenario writes', source)

    def test_pilot_preserves_batch_recovery_and_no_auto_reset(self):
        script = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('.wslpe45-recovery-required', script)
        self.assertIn('.wslpe45-single-run.lock', script)
        self.assertIn('snapshot_gate()', script)
        self.assertIn('base.check_inventory(', script)
        self.assertIn('learner_proof', script)
        self.assertNotIn('shell=True', script)
        self.assertNotIn('sentinel.unlink()\n                return 2', script)


if __name__ == '__main__':
    unittest.main()
