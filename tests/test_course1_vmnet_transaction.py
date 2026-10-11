"""Offline transaction tests; never call VMware, sudo, or systemd."""
import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from goad.course1_vmnet_transaction import (
    VmnetTransactionError, execute_testable_network_transaction,
)
from goad.kingdoms_topology import load_course1_topology

BASELINE = (
    "VERSION=1,0\n"
    "answer VNET_1_HOSTONLY_SUBNET 192.168.56.0\n"
    "answer VNET_1_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_8_NAT yes\n"
)


class Course1VmnetTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.networking = root / "networking"
        self.networking.write_text(BASELINE)
        self.networking.chmod(0o640)
        self.backups = root / "backups"
        self.backups.mkdir(mode=0o700)
        self.state = root / "owner.json"
        self.provider = root / "kingdoms-instance" / "provider"
        self.provider.mkdir(parents=True, mode=0o700)
        self.layout = load_course1_topology()
        self.expected = hashlib.sha256(BASELINE.encode()).hexdigest()
        self.calls = []

    def run_txn(self, restart=None, verify=None, digest=None):
        def default_restart():
            self.calls.append("restart")
        def default_verify():
            self.calls.append("verify")
        return execute_testable_network_transaction(
            self.networking, self.backups, self.state,
            self.provider, self.layout, digest or self.expected,
            restart or default_restart, verify or default_verify,
        )

    def test_success_preserves_foreign_config_and_records_backup(self):
        record = self.run_txn()
        result = self.networking.read_text()
        self.assertTrue(result.startswith(BASELINE))
        self.assertIn("answer VNET_10_HOSTONLY_SUBNET 10.4.10.0", result)
        self.assertNotIn("VNET_30_", result)
        self.assertEqual(self.calls, ["restart", "verify"])
        self.assertEqual(Path(record["backup"]).read_text(), BASELINE)
        self.assertEqual(json.loads(self.state.read_text()), record)
        self.assertEqual(record["provider"], str(self.provider.resolve()))
        self.assertEqual(stat.S_IMODE(self.networking.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o600)

    def test_outdated_reviewed_hash_never_changes_anything(self):
        with self.assertRaisesRegex(VmnetTransactionError, "changed after plan"):
            self.run_txn(digest="bad-hash")
        self.assertEqual(self.networking.read_text(), BASELINE)
        self.assertFalse(self.state.exists())
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_failed_restart_restores_original_and_retains_backup(self):
        def fail_restart():
            self.calls.append("restart")
            if len(self.calls) == 1:
                raise RuntimeError("simulated VMware start error")
        with self.assertRaisesRegex(VmnetTransactionError, "failed safely"):
            self.run_txn(restart=fail_restart)
        self.assertEqual(self.networking.read_text(), BASELINE)
        self.assertEqual(self.calls, ["restart", "restart"])
        self.assertFalse(self.state.exists())
        self.assertEqual(len(list(self.backups.iterdir())), 1)

    def test_failed_verification_restores_original_without_owner_record(self):
        def fail_verify():
            raise RuntimeError("simulated missing vmnet99")
        with self.assertRaisesRegex(VmnetTransactionError, "failed safely"):
            self.run_txn(verify=fail_verify)
        self.assertEqual(self.networking.read_text(), BASELINE)
        self.assertEqual(self.calls, ["restart", "restart"])
        self.assertFalse(self.state.exists())

    def test_concurrent_host_edit_is_never_overwritten_by_rollback(self):
        def foreign_edit_then_fail():
            self.networking.write_text("FOREIGN CHANGE\n")
            raise RuntimeError("simulated concurrent host edit")
        with self.assertRaisesRegex(VmnetTransactionError, "refusing unsafe"):
            self.run_txn(verify=foreign_edit_then_fail)
        self.assertEqual(self.networking.read_text(), "FOREIGN CHANGE\n")
        self.assertFalse(self.state.exists())
        folders = list(self.backups.iterdir())
        self.assertEqual(len(folders), 1)
        self.assertEqual((folders[0] / "networking.original").read_text(), BASELINE)

    def test_existing_owner_record_blocks_another_transaction(self):
        self.state.write_text("foreign owner\n")
        with self.assertRaisesRegex(VmnetTransactionError, "ownership record"):
            self.run_txn()
        self.assertEqual(self.networking.read_text(), BASELINE)
        self.assertEqual(self.state.read_text(), "foreign owner\n")

    def test_missing_instance_provider_refuses_before_any_write(self):
        self.provider.rename(self.provider.parent / "provider-old")
        with self.assertRaisesRegex(VmnetTransactionError, "provider identity"):
            self.run_txn()
        self.assertEqual(self.networking.read_text(), BASELINE)
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_symlinked_networking_refuses_before_any_write(self):
        target = self.networking.with_suffix(".real")
        self.networking.rename(target)
        self.networking.symlink_to(target)
        with self.assertRaisesRegex(VmnetTransactionError, "regular file"):
            self.run_txn()
        self.assertEqual(target.read_text(), BASELINE)
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_transaction_module_has_no_host_apply_entrypoint(self):
        file = Path(__file__).resolve().parents[1] / "goad/course1_vmnet_transaction.py"
        contents = file.read_text()
        self.assertNotIn("vmware-networks", contents)
        self.assertNotIn("subprocess.run(", contents)
        self.assertNotIn("sudo ", contents)
        self.assertNotIn("if __name__", contents)


if __name__ == "__main__":
    unittest.main()
