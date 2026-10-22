"""WSLPE maintenance command tests: mock ALL privileged calls and guest state."""
import importlib.util
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-vmnet4-maintenance.py"
SPEC = importlib.util.spec_from_file_location("wslpe_vmnet4_cli_test", SCRIPT)
assert SPEC and SPEC.loader
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class MaintenanceCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.roots = tuple(self.base / f"workspace{i}" for i in range(4))
        for directory in self.roots:
            directory.mkdir()
        self.source = b"VERSION=1,0\n"
        self.expected = hashlib.sha256(self.source).hexdigest()
        self.calls = []
        self.txn = SimpleNamespace(
            apply=lambda **k: self.calls.append(("apply", k)) or "finalhash",
            recover=lambda: self.calls.append(("recover",)) or "originalhash",
        )
        self.assembled = SimpleNamespace(assemble=lambda: self.txn)

    def call(self, args):
        with redirect_stdout(StringIO()) as output:
            result = APP.main(args)
        return result, output.getvalue()

    def patches(self):
        stack = mock.patch.multiple(
            APP,
            workspaces=mock.DEFAULT,
            running_zero=mock.DEFAULT,
            create_private_state_dir=mock.DEFAULT,
            _read_regular=mock.DEFAULT,
            Vmnet4KernelIsolationVerifier=mock.DEFAULT,
            Vmnet4MaintenanceRuntime=mock.DEFAULT,
        )
        values = stack.start()
        self.addCleanup(stack.stop)
        values["workspaces"].return_value = self.roots
        values["running_zero"].return_value = 0
        values["_read_regular"].return_value = (self.source, None)
        values["Vmnet4MaintenanceRuntime"].return_value = self.assembled
        return values

    def valid_args(self):
        return ["--apply", "--owner", "stark", "--approve", APP.APPROVAL,
                "--expected-sha256", self.expected]

    def test_missing_approval_denies_without_any_guest_mutation(self):
        patches = self.patches()
        with mock.patch.object(APP.os, "geteuid", return_value=0):
            status, output = self.call([
                "--apply", "--owner", "stark", "--expected-sha256", self.expected])
        self.assertEqual(status, 2)
        self.assertIn("approval", output)
        patches["running_zero"].assert_not_called()
        self.assertEqual(self.calls, [])

    def test_nonroot_denies_before_zero_guest_probe(self):
        patches = self.patches()
        with mock.patch.object(APP.os, "geteuid", return_value=1000):
            status, out = self.call(self.valid_args())
        self.assertEqual(status, 2)
        self.assertIn("Root required", out)
        patches["running_zero"].assert_not_called()

    def test_two_running_vms_never_create_state_or_stop_service(self):
        patches = self.patches()
        patches["running_zero"].side_effect = NetworkTransactionBlocked(
            "Shared networking deferred; vmware-vmx=2, owner-vmrun=2")
        with mock.patch.object(APP.os, "geteuid", return_value=0):
            status, out = self.call(self.valid_args())
        self.assertEqual(status, 2)
        self.assertIn("vmware-vmx=2", out)
        patches["create_private_state_dir"].assert_not_called()
        self.assertEqual(self.calls, [])

    def test_stale_sha_fails_before_transaction_apply(self):
        patches = self.patches()
        with mock.patch.object(APP.os, "geteuid", return_value=0):
            args = self.valid_args()
            args[-1] = "0" * 64
            status, out = self.call(args)
        self.assertEqual(status, 2)
        self.assertIn("since source approval", out)
        self.assertEqual(self.calls, [])

    def test_successful_authorized_apply_uses_exact_network_contract(self):
        patches = self.patches()
        with mock.patch.object(APP.os, "geteuid", return_value=0):
            status, out = self.call(self.valid_args())
        self.assertEqual(status, 0)
        self.assertIn("[COMMITTED]", out)
        self.assertEqual(len(self.calls), 1)
        expected = self.calls[0][1]
        self.assertEqual(expected["vmnet"], "vmnet4")
        self.assertEqual(expected["subnet"], "172.28.233.0/24")
        self.assertEqual(expected["exercise_vmnet"], "vmnet3")
        self.assertEqual(expected["expected_source_sha256"], self.expected)
        self.assertTrue(expected["maintenance_approved"])
        patches["create_private_state_dir"].assert_called_once()

    def test_recovery_requires_real_journal(self):
        patches = self.patches()
        with (mock.patch.object(APP.os, "geteuid", return_value=0),
              mock.patch.object(APP.Path, "is_file", return_value=False)):
            status, out = self.call([
                "--recover", "--owner", "stark", "--approve", APP.APPROVAL])
        self.assertEqual(status, 2)
        self.assertIn("No incomplete", out)
        self.assertEqual(self.calls, [])

    def test_recovery_invokes_only_recover(self):
        patches = self.patches()
        with (mock.patch.object(APP.os, "geteuid", return_value=0),
              mock.patch.object(APP.Path, "is_file", return_value=True)):
            status, out = self.call([
                "--recover", "--owner", "stark", "--approve", APP.APPROVAL])
        self.assertEqual(status, 0)
        self.assertEqual(self.calls, [("recover",)])
        self.assertIn("[RECOVERED]", out)

    def test_status_is_read_only_without_root_or_maintenance(self):
        patches = self.patches()
        with mock.patch.object(APP.os, "geteuid", return_value=1000):
            status, out = self.call(["--status", "--owner", "stark"])
        self.assertEqual(status, 0)
        self.assertIn(self.expected, out)
        patches["running_zero"].assert_not_called()
        patches["Vmnet4MaintenanceRuntime"].assert_not_called()
        patches["create_private_state_dir"].assert_not_called()

    def test_unexpected_recovery_hash_refused(self):
        patches = self.patches()
        with mock.patch.object(APP.os, "geteuid", return_value=0):
            status, out = self.call([
                "--recover", "--owner", "stark", "--approve", APP.APPROVAL,
                "--expected-sha256", self.expected])
        self.assertEqual(status, 2)
        self.assertIn("never takes", out)
        self.assertEqual(self.calls, [])

    def test_read_only_status_rejects_approval_token(self):
        self.patches()
        status, out = self.call([
            "--status", "--owner", "stark", "--approve", APP.APPROVAL])
        self.assertEqual(status, 2)
        self.assertIn("read only", out)

    def test_no_auto_guest_power_or_global_firewall_changes(self):
        source = SCRIPT.read_text()
        for forbidden in ("vmrun stop", "vmrun suspend", "sysctl -w",
                          "iptables -F", "nft flush", "systemctl stop"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
