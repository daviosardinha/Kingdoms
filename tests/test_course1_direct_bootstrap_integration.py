"""NORTH failed first Vagrant up must recover without looping through Vagrant."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def provider_class():
    source = (ROOT / "goad/provider/vagrant/vmware_kingdoms.py").read_text()
    tree = ast.parse(source)
    cls = next(x for x in tree.body
               if isinstance(x, ast.ClassDef) and x.name == "GoadKingdomsVmwareProvider")
    ns = {"GoadNomadVmwareProvider": object, "Log": Mock()}
    exec(compile(ast.Module(body=[cls], type_ignores=[]),
                 "goad/provider/vagrant/vmware_kingdoms.py", "exec"), ns)
    return ns["GoadKingdomsVmwareProvider"]


class DirectBootstrapIntegrationTests(unittest.TestCase):
    def make(self, *, lab="NORTH", first_up=False, direct=True, strict=False):
        provider = provider_class()()
        provider.lab_name = lab
        provider.goad_nomad_windows = ["GOAD-DC01"]
        provider._last_bounded_vagrant_reaped = True
        provider.path = "/tmp/fake-instance/provider"
        provider._course1_unwired = Mock(return_value=False)
        provider.prepare_install = Mock(return_value=True)
        provider._sync_goad_nomad_inventories = Mock(return_value=True)
        provider._sync_goad_nomad_vagrantfile_compatibility = Mock(return_value=True)
        provider._bring_up_router = Mock(return_value=True)
        provider.command = Mock()
        provider.command.run_vagrant.return_value = first_up
        provider._ensure_vmware_tools = Mock(return_value=strict)
        provider._north_direct_first_boot_recovery = Mock(return_value=direct)
        provider._authenticated_guest_recovery_ready = Mock(return_value=True)
        provider._recover_failed_windows_vagrant_up = Mock(return_value=True)
        provider._enable_provisioning_routes = Mock(return_value=True)
        return provider

    def test_failed_vagrant_up_and_proved_direct_bootstrap_skips_repeat_up(self):
        provider = self.make()
        self.assertTrue(provider.install())
        provider._north_direct_first_boot_recovery.assert_called_once_with("GOAD-DC01")
        provider._recover_failed_windows_vagrant_up.assert_not_called()
        provider._ensure_vmware_tools.assert_not_called()
        provider._enable_provisioning_routes.assert_called_once_with()

    def test_proved_guest_but_failed_direct_script_stops_without_vagrant_loop(self):
        provider = self.make(direct=False)
        self.assertFalse(provider.install())
        provider._recover_failed_windows_vagrant_up.assert_not_called()
        provider._enable_provisioning_routes.assert_not_called()

    def test_direct_proof_unavailable_keeps_legacy_recovery(self):
        provider = self.make(direct=None)
        self.assertTrue(provider.install())
        provider._recover_failed_windows_vagrant_up.assert_called_once_with("GOAD-DC01")

    def test_vagrant_success_but_canonical_not_ready_uses_north_direct(self):
        provider = self.make(first_up=True, strict=False)
        self.assertTrue(provider.install())
        provider._north_direct_first_boot_recovery.assert_called_once_with("GOAD-DC01")
        provider._recover_failed_windows_vagrant_up.assert_not_called()

    def test_full_kingdoms_still_uses_original_recovery(self):
        provider = self.make(lab="GOAD")
        provider._enable_provisioning_routes = Mock()
        # Full KINGDOMS uses the standard provisioning-routes.sh script.
        provider._script = Mock(return_value="/tmp/provisioning-routes.sh")
        import subprocess
        from unittest.mock import patch
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertTrue(provider.install())
        provider._north_direct_first_boot_recovery.assert_not_called()
        provider._recover_failed_windows_vagrant_up.assert_called_once_with("GOAD-DC01")


if __name__ == "__main__":
    unittest.main()
