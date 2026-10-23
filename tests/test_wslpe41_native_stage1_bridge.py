"""Source-isolated tests for the native LabManager-to-WSLPE41 bridge."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_native_stage1_bridge import create_native_guest_identity

COMMIT = "a" * 40
PREFIX = "172.28.232"


class Manager:
    def __init__(self, instance=None):
        self.instance = instance

    def get_current_instance(self):
        return self.instance


class NativeBridgeTests(unittest.TestCase):
    def test_unconfirmed_cannot_create(self):
        with patch("kingdoms.wslpe41_native_stage1_bridge.bootstrap_native_wslpe") as boot:
            with self.assertRaises(InstallBlocked):
                create_native_guest_identity(Manager(), PREFIX, COMMIT)
            boot.assert_not_called()

    def test_loaded_instance_cannot_be_reused(self):
        with patch("kingdoms.wslpe41_native_stage1_bridge.bootstrap_native_wslpe") as boot:
            with self.assertRaises(InstallBlocked):
                create_native_guest_identity(Manager(object()), PREFIX, COMMIT, confirmed=True)
            boot.assert_not_called()

    def test_bad_commit_or_network_cannot_create(self):
        with patch("kingdoms.wslpe41_native_stage1_bridge.bootstrap_native_wslpe") as boot:
            for prefix, commit in (("10.4.10", COMMIT), (PREFIX, "not-a-commit")):
                with self.subTest(prefix=prefix, commit=commit):
                    with self.assertRaises(InstallBlocked):
                        create_native_guest_identity(Manager(), prefix, commit, confirmed=True)
            boot.assert_not_called()

    def test_native_stage1_failure_never_retries(self):
        with patch("kingdoms.wslpe41_native_stage1_bridge.bootstrap_native_wslpe", return_value=False) as boot:
            with self.assertRaises(InstallBlocked):
                create_native_guest_identity(Manager(), PREFIX, COMMIT, confirmed=True)
            boot.assert_called_once()

    def test_verified_native_registration_yields_identity_not_attestation(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "abcd1234"
            directory.mkdir()
            instance = SimpleNamespace(instance_id="abcd1234", instance_path=str(directory))
            manager = Manager()
            def boot(*args, **kwargs):
                manager.instance = instance
                return True
            registration = SimpleNamespace(instance_id="abcd1234",
                vmx=str(directory / "provider" / "guest.vmx"),
                subnet=PREFIX + ".0/24")
            with patch("kingdoms.wslpe41_native_stage1_bridge.bootstrap_native_wslpe", side_effect=boot), \
                 patch("kingdoms.wslpe41_native_stage1_bridge.read_only_command", return_value="Total running VMs: 1"), \
                 patch("kingdoms.wslpe41_native_stage1_bridge.inspect_native_registration", return_value=registration):
                identity = create_native_guest_identity(manager, PREFIX, COMMIT, confirmed=True)
            self.assertEqual(identity.instance_id, "abcd1234")
            self.assertEqual(identity.workspace, root)
            self.assertEqual(identity.subnet, PREFIX + ".0/24")
            self.assertFalse(hasattr(identity, "operator_recovery_ready"))

    def test_registration_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "abcd1234"
            directory.mkdir()
            manager = Manager()
            def boot(*args, **kwargs):
                manager.instance = SimpleNamespace(instance_id="abcd1234", instance_path=str(directory))
                return True
            wrong = SimpleNamespace(instance_id="wrong", vmx="/tmp/guest.vmx",
                                    subnet=PREFIX + ".0/24")
            with patch("kingdoms.wslpe41_native_stage1_bridge.bootstrap_native_wslpe", side_effect=boot), \
                 patch("kingdoms.wslpe41_native_stage1_bridge.read_only_command", return_value="Total running VMs: 1"), \
                 patch("kingdoms.wslpe41_native_stage1_bridge.inspect_native_registration", return_value=wrong):
                with self.assertRaises(InstallBlocked):
                    create_native_guest_identity(manager, PREFIX, COMMIT, confirmed=True)


if __name__ == "__main__":
    unittest.main()
