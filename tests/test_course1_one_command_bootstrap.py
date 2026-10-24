"""NORTH one-command bootstrap: no VMware/systemd/guest writes in these tests."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import subprocess
import unittest
from unittest.mock import Mock, patch

from goad_nomad import GoadNomad
from goad import course1_host_network_apply as network


class NorthNativeInstallBootstrapTests(unittest.TestCase):
    def make(self, root):
        provider_dir = Path(root) / "provider"
        provider_dir.mkdir()
        manager = Mock()
        manager.get_current_lab_name.return_value = "NORTH"
        manager.get_current_provider_name.return_value = "vmware"
        manager.get_current_instance.return_value = SimpleNamespace(
            lab_name="NORTH", provider_name="vmware",
            instance_provider_path=provider_dir,
        )
        goad = GoadNomad.__new__(GoadNomad)
        goad.lab_manager = manager
        provider = Mock()
        provider.lab_name = "NORTH"
        provider.path = str(provider_dir)
        provider._script.return_value = "/repo/scripts/setup-vmware-networks.sh"
        provider._course1_unwired.return_value = False
        return goad, provider

    def fixture_path(self, real, root):
        owner = Path(root) / "north-owner.json"
        return lambda value: owner if str(value) == (
            "/etc/vmware/kingdoms-course1-owner.json") else real(value)

    def test_first_cli_install_scopes_bootstrap_flag_to_new_instance(self):
        console = GoadNomad.__new__(GoadNomad)
        manager = Mock()
        manager.get_current_instance.return_value = None
        manager.create_instance.return_value = True
        manager.get_current_lab_name.return_value = "NORTH"
        manager.get_current_provider_name.return_value = "vmware"
        console.lab_manager = manager
        observed = []

        def install():
            observed.append(console._native_north_bootstrap_requested)
            return True

        console.do_install_instance = install
        self.assertTrue(console.do_create("--non-interactive"))
        self.assertEqual(observed, [True])
        self.assertIs(console._native_north_bootstrap_requested, False)

    def test_full_kingdoms_cli_install_never_requests_north_bootstrap(self):
        console = GoadNomad.__new__(GoadNomad)
        manager = Mock()
        manager.get_current_instance.return_value = None
        manager.create_instance.return_value = True
        manager.get_current_lab_name.return_value = "GOAD"
        manager.get_current_provider_name.return_value = "vmware"
        console.lab_manager = manager
        observed = []
        console.do_install_instance = lambda: observed.append(
            console._native_north_bootstrap_requested) or True
        self.assertTrue(console.do_create("--non-interactive"))
        self.assertEqual(observed, [False])

    def test_only_new_north_cli_calls_bootstrap_before_vm_provider(self):
        console = GoadNomad.__new__(GoadNomad)
        manager = Mock()
        provider = Mock()
        provider.install.return_value = False
        manager.get_current_instance_provider.return_value = provider
        console.lab_manager = manager
        console._native_north_bootstrap_requested = True
        console._bootstrap_north_fresh_network = Mock(return_value=False)
        self.assertFalse(console.do_provide())
        console._bootstrap_north_fresh_network.assert_called_once_with(provider)
        provider.install.assert_not_called()

    def test_bootstrap_requires_clean_absent_owner_and_exact_instance(self):
        with TemporaryDirectory() as root:
            console, provider = self.make(root)
            actual = Path
            with patch("goad_nomad.Path", side_effect=self.fixture_path(actual, root)):
                with patch("goad_nomad.subprocess.run", return_value=subprocess.CompletedProcess(
                        args=[], returncode=0)) as run:
                    self.assertTrue(console._bootstrap_north_fresh_network(provider))
            run.assert_called_once()
            args = run.call_args.args[0]
            self.assertEqual(args[:5], [
                "sudo", "-n", "bash",
                "/repo/scripts/setup-vmware-networks.sh", "--north",
            ])
            self.assertEqual(args[5:7], ["native-bootstrap", "--provider-dir"])
            self.assertEqual(args[7], str(Path(root) / "provider"))
            provider._course1_unwired.assert_called_once()

    def test_existing_owner_refused_without_any_network_write(self):
        with TemporaryDirectory() as root:
            console, provider = self.make(root)
            (Path(root) / "north-owner.json").write_text("original")
            real = Path
            with patch("goad_nomad.Path", side_effect=self.fixture_path(real, root)):
                with patch("goad_nomad.subprocess.run") as run:
                    self.assertFalse(console._bootstrap_north_fresh_network(provider))
            run.assert_not_called()

    def test_bootstrap_failure_never_launches_provider(self):
        with TemporaryDirectory() as root:
            console, provider = self.make(root)
            real = Path
            with patch("goad_nomad.Path", side_effect=self.fixture_path(real, root)):
                with patch("goad_nomad.subprocess.run", return_value=subprocess.CompletedProcess(
                        args=[], returncode=3)):
                    self.assertFalse(console._bootstrap_north_fresh_network(provider))
            provider._course1_unwired.assert_not_called()

    def test_non_north_provider_identity_is_rejected(self):
        with TemporaryDirectory() as root:
            console, provider = self.make(root)
            provider.lab_name = "GOAD"
            with patch("goad_nomad.subprocess.run") as run:
                self.assertFalse(console._bootstrap_north_fresh_network(provider))
            run.assert_not_called()

    def test_native_bootstrap_captures_sha_and_invokes_existing_transaction(self):
        with TemporaryDirectory() as root:
            baseline = Path(root) / "networking"
            baseline.write_bytes(b"answer VNET_8_NAT yes\n")
            with patch.object(network, "NETWORKING", baseline):
                with patch.object(network, "require_explicit_root"), \
                     patch.object(network, "apply") as apply, \
                     patch.object(network, "inspect_installed_north", return_value=["verified"]), \
                     patch("sys.argv", ["host-network", "native-bootstrap",
                                        "--provider-dir", str(Path(root) / "provider")]):
                    network.main()
            import hashlib
            expected = hashlib.sha256(baseline.read_bytes()).hexdigest()
            apply.assert_called_once_with(str(Path(root) / "provider"), expected)

    def test_bash_native_bootstrap_dispatch_parses_without_mutation(self):
        script = Path(__file__).resolve().parents[1] / "scripts/setup-vmware-networks.sh"
        result = subprocess.run(["bash", "-n", str(script)],
                                capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
