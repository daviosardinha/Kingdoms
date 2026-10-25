"""Fresh-install bootstrap must not require AD before Ansible creates it."""

import ast
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def load_provider(base):
    source = (ROOT / 'goad/provider/vagrant/vmware_kingdoms.py').read_text()
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == 'GoadKingdomsVmwareProvider'
    )
    namespace = {
        'GoadNomadVmwareProvider': base,
        'Log': Mock(),
    }
    exec(
        compile(ast.Module(body=[node], type_ignores=[]),
                'goad/provider/vagrant/vmware_kingdoms.py', 'exec'),
        namespace,
    )
    return namespace['GoadKingdomsVmwareProvider']


class BaseProvider:
    def __init__(self):
        self.base_prepare_calls = 0

    def prepare_provisioning(self):
        self.base_prepare_calls += 1
        return 'BASE_AD_AWARE_PATH'

    def finalize_install(self):
        self.base_finalize_calls = getattr(self, 'base_finalize_calls', 0) + 1
        return 'BASE_EXERCISE_PATH'


class FreshInstallBootstrapTests(unittest.TestCase):
    def make_provider(self, mode='unknown', status='ansible_running',
                      provider_success=True):
        cls = load_provider(BaseProvider)
        provider = cls()
        provider.lab_name = 'GOAD'
        # The NORTH host-network ownership attestation is independently
        # tested in test_course1_provider_guard.py. This unit suite verifies
        # only the pre-AD / installed-mode provisioning decision; the fixture
        # has no real instance path or privileged VMware owner record.
        provider._course1_unwired = Mock(return_value=False)
        provider.is_goad_nomad_segmented = Mock(return_value=True)
        provider.get_runtime_mode = Mock(return_value=mode)
        provider._kingdoms_install_profile = {
            'status': status,
            'provider_success': provider_success,
        }
        provider._require_cached_sudo = Mock(return_value=True)
        provider._apply_router_policy = Mock(return_value=True)
        provider._enable_provisioning_routes = Mock(return_value=True)
        provider._validate_management_plane = Mock(return_value=True)
        return provider

    def make_finalization_provider(self, mode='unknown', status='ansible_running',
                                   provider_success=True):
        provider = self.make_provider(mode, status, provider_success)
        provider.lab_name = 'NORTH'
        current = {'mode': mode}
        provider.get_runtime_mode = Mock(side_effect=lambda: current['mode'])

        def set_mode(value):
            current['mode'] = value
            return True

        provider.set_runtime_mode = Mock(side_effect=set_mode)
        provider._north_tools_transition_gate = Mock(return_value=True)
        return provider, current

    def test_fresh_north_finalization_persists_provisioning_before_isolation(self):
        provider, current = self.make_finalization_provider()
        self.assertEqual(provider.finalize_install(), 'BASE_EXERCISE_PATH')
        self.assertEqual(current['mode'], 'provisioning')
        provider.set_runtime_mode.assert_called_once_with('provisioning')
        self.assertEqual(provider._north_tools_transition_gate.call_count, 4)
        self.assertEqual(provider.base_finalize_calls, 1)

    def test_existing_provisioning_mode_requires_no_mode_replay(self):
        provider, _ = self.make_finalization_provider(mode='provisioning', status='failed')
        self.assertEqual(provider.finalize_install(), 'BASE_EXERCISE_PATH')
        provider.set_runtime_mode.assert_not_called()
        self.assertEqual(provider.base_finalize_calls, 1)

    def test_unknown_mode_without_successful_fresh_install_remains_blocked(self):
        for status, success in [('failed', True), ('ansible_running', False)]:
            with self.subTest(status=status, success=success):
                provider, _ = self.make_finalization_provider(
                    status=status, provider_success=success
                )
                self.assertFalse(provider.finalize_install())
                provider.set_runtime_mode.assert_not_called()
                provider._north_tools_transition_gate.assert_not_called()
                self.assertEqual(getattr(provider, 'base_finalize_calls', 0), 0)

    def test_exercise_mode_cannot_reenter_install_finalization(self):
        provider, _ = self.make_finalization_provider(mode='exercise')
        self.assertFalse(provider.finalize_install())
        provider.set_runtime_mode.assert_not_called()

    def test_failed_mode_transition_blocks_isolation(self):
        provider, _ = self.make_finalization_provider()
        provider.set_runtime_mode = Mock(return_value=False)
        self.assertFalse(provider.finalize_install())
        provider._north_tools_transition_gate.assert_not_called()
        self.assertEqual(getattr(provider, 'base_finalize_calls', 0), 0)

    def test_unpersisted_mode_transition_blocks_isolation(self):
        provider, _ = self.make_finalization_provider()
        provider.set_runtime_mode = Mock(return_value=True)
        self.assertFalse(provider.finalize_install())
        provider._north_tools_transition_gate.assert_not_called()

    def test_failed_tools_gate_prevents_final_isolation(self):
        provider, _ = self.make_finalization_provider()
        provider._north_tools_transition_gate = Mock(return_value=False)
        self.assertFalse(provider.finalize_install())
        provider.set_runtime_mode.assert_called_once_with('provisioning')
        self.assertEqual(getattr(provider, 'base_finalize_calls', 0), 0)

    def test_goad_finalization_keeps_inherited_behavior(self):
        provider, _ = self.make_finalization_provider()
        provider.lab_name = 'GOAD'
        self.assertEqual(provider.finalize_install(), 'BASE_EXERCISE_PATH')
        provider.set_runtime_mode.assert_not_called()
        provider._north_tools_transition_gate.assert_not_called()

    def test_zero_state_ansible_bootstrap_uses_pre_ad_management_only(self):
        provider = self.make_provider()

        self.assertTrue(provider.prepare_provisioning())

        self.assertEqual(provider.base_prepare_calls, 0)
        provider._apply_router_policy.assert_called_once_with('provisioning')
        provider._enable_provisioning_routes.assert_called_once_with()
        provider._validate_management_plane.assert_called_once_with()

    def test_north_fresh_install_uses_existing_pre_ad_management_path(self):
        provider = self.make_provider()
        provider.lab_name = 'NORTH'
        self.assertTrue(provider.prepare_provisioning())
        self.assertEqual(provider.base_prepare_calls, 0)
        provider._apply_router_policy.assert_called_once_with('provisioning')
        provider._enable_provisioning_routes.assert_called_once_with()
        provider._validate_management_plane.assert_called_once_with()

    def test_north_provisioned_instance_cannot_reenter_pre_ad_path(self):
        provider = self.make_provider(mode='exercise')
        provider.lab_name = 'NORTH'
        self.assertEqual(provider.prepare_provisioning(), 'BASE_AD_AWARE_PATH')
        self.assertEqual(provider.base_prepare_calls, 1)
        provider._apply_router_policy.assert_not_called()
        provider._enable_provisioning_routes.assert_not_called()

    def test_installed_instance_keeps_normal_ad_aware_transition(self):
        provider = self.make_provider(mode='exercise')

        self.assertEqual(
            provider.prepare_provisioning(),
            'BASE_AD_AWARE_PATH',
        )
        self.assertEqual(provider.base_prepare_calls, 1)
        provider._apply_router_policy.assert_not_called()
        provider._enable_provisioning_routes.assert_not_called()
        provider._validate_management_plane.assert_not_called()

    def test_unknown_mode_without_active_full_install_fails_into_normal_path(self):
        provider = self.make_provider(status='failed', provider_success=True)

        self.assertEqual(
            provider.prepare_provisioning(),
            'BASE_AD_AWARE_PATH',
        )
        self.assertEqual(provider.base_prepare_calls, 1)


if __name__ == '__main__':
    unittest.main()
