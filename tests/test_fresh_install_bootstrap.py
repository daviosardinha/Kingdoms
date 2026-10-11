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


class FreshInstallBootstrapTests(unittest.TestCase):
    def make_provider(self, mode='unknown', status='ansible_running',
                      provider_success=True):
        cls = load_provider(BaseProvider)
        provider = cls()
        provider.lab_name = 'GOAD'
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
