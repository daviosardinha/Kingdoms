"""Only simulated filesystem/VMware callbacks; never touch real networking."""
import base64
from contextlib import nullcontext
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from kingdoms import wslpe_management_vmnet_transaction as txn

BASE = (
    "VERSION=1,0\n"
    "answer VNET_3_DHCP no\n"
    "answer VNET_3_NAT no\n"
    "answer VNET_3_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_3_HOSTONLY_SUBNET 172.28.232.0\n"
    "answer VNET_10_HOSTONLY_SUBNET 10.4.10.0\n"
    "answer VNET_10_HOSTONLY_NETMASK 255.255.255.0\n"
)


class ManagementVmnetTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.networking = self.base / "networking"
        self.networking.write_text(BASE)
        self.journal = self.base / "transaction.json"
        self.lock = self.base / "transaction.lock"
        self.events = []
        self.guests = 0
        self.preflight_fail = False
        self.verify_fail = False
        self.fail_first_start = False
        self.start_count = 0

        def preflight(vmnet, subnet):
            self.events.append("preflight")
            if self.preflight_fail:
                raise txn.NetworkTransactionBlocked("VMX registration coverage missing")
            self.assertEqual((vmnet, subnet), ("vmnet4", "172.28.233.0/24"))

        def action(operation):
            self.events.append(operation)
            if operation == "start":
                self.start_count += 1
                if self.fail_first_start and self.start_count == 1:
                    raise RuntimeError("Simulated VMware service start failure")

        def verify(vmnet, subnet):
            self.events.append("verify")
            if self.verify_fail:
                raise RuntimeError("Host adapter or isolation validation failed")

        self.manager = txn.WslpeVmnetTransaction(
            networking=self.networking, journal=self.journal, lock=self.lock,
            running_guests=lambda: self.guests, live_preflight=preflight,
            vmware_action=action, verify_created_network=verify,
        )
        original_read = txn._read_regular
        original_atomic = txn._atomic_replace

        def simulated_root_file(path, bound):
            content, info = original_read(path, bound)
            return content, SimpleNamespace(
                st_uid=0, st_gid=info.st_gid, st_mode=info.st_mode,
                st_ino=info.st_ino, st_dev=info.st_dev, st_size=info.st_size,
                st_nlink=info.st_nlink,
            )

        def simulated_root_replace(path, payload, *, mode, uid, gid):
            self.assertEqual(uid, 0)
            return original_atomic(path, payload, mode=mode, uid=os.getuid(), gid=os.getgid())

        # Unprivileged CI: spoof root only inside this test-scoped filesystem.
        for target, value in (
            ("_read_regular", simulated_root_file),
            ("_atomic_replace", simulated_root_replace),
        ):
            patcher = mock.patch.object(txn, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(self.manager, "_exclusive", return_value=nullcontext())
        patcher.start()
        self.addCleanup(patcher.stop)

    def apply(self, *, authorized=True, sha=None):
        return self.manager.apply(
            vmnet="vmnet4", subnet="172.28.233.0/24",
            exercise_vmnet="vmnet3", exercise_subnet="172.28.232.0/24",
            expected_source_sha256=sha or txn._digest(BASE.encode()),
            maintenance_approved=authorized,
        )

    def test_commit_records_exact_snapshot_and_preserves_all_existing_directives(self):
        new_sha = self.apply()
        contents = self.networking.read_text()
        self.assertTrue(contents.startswith(BASE))
        self.assertIn("answer VNET_4_HOSTONLY_SUBNET 172.28.233.0", contents)
        self.assertEqual(txn._digest(contents.encode()), new_sha)
        saved = json.loads(self.journal.read_text())
        self.assertEqual(saved["status"], "committed")
        self.assertEqual(base64.b64decode(saved["original_b64"]), BASE.encode())
        self.assertEqual(stat.S_IMODE(self.journal.stat().st_mode), 0o600)
        self.assertEqual(self.events, ["preflight", "stop", "start", "verify"])

    def test_failed_host_only_adapter_verification_rolls_back(self):
        self.verify_fail = True
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "restored"):
            self.apply()
        self.assertEqual(self.networking.read_text(), BASE)
        saved = json.loads(self.journal.read_text())
        self.assertEqual(saved["status"], "rolled_back")
        self.assertEqual(saved["failure_stage"], "host-adapter-and-isolation-acceptance")
        self.assertEqual(saved["failure_class"], "RuntimeError")
        self.assertEqual(saved["failure_reason"], "RuntimeError")

    def test_failed_restart_recovers_exact_bytes_and_journals_rollback(self):
        self.fail_first_start = True
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "restored"):
            self.apply()
        self.assertEqual(self.networking.read_text(), BASE)
        saved = json.loads(self.journal.read_text())
        self.assertEqual(saved["status"], "rolled_back")
        self.assertEqual(saved["failure_stage"], "vmware-network-start")
        self.assertEqual(saved["failure_class"], "RuntimeError")
        self.assertEqual(self.events, ["preflight", "stop", "start", "stop", "start"])

    def test_live_workspace_ownership_preflight_fails_before_journal(self):
        self.preflight_fail = True
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "coverage"):
            self.apply()
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertFalse(self.journal.exists())

    def test_no_maintenance_authorization_or_stale_hash(self):
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "maintenance"):
            self.apply(authorized=False)
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "Stale"):
            self.apply(sha="0" * 64)
        self.assertEqual(self.events, [])
        self.assertFalse(self.journal.exists())

    def test_prior_successful_journal_blocks_reapply_or_rollback(self):
        self.apply()
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "Prior transaction"):
            self.apply()
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "not an unfinished"):
            self.manager.recover()

    def test_recovery_refuses_unrelated_config_drift(self):
        def crash_on_start(operation):
            if operation == "start":
                raise SystemExit("crash")
        self.manager.vmware_action = crash_on_start
        with self.assertRaises(SystemExit):
            self.apply()
        self.networking.write_text(self.networking.read_text() + "# external edit\n")
        self.manager.vmware_action = lambda action: self.events.append(action)
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "drift"):
            self.manager.recover()
        self.assertTrue(self.networking.read_text().endswith("# external edit\n"))

    def test_refuses_running_guests_before_any_write_or_restart(self):
        self.guests = 2
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "guest activity"):
            self.apply()
        self.assertEqual(self.events, [])
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertFalse(self.journal.exists())

    def test_root_gate_stays_mandatory(self):
        real = txn.WslpeVmnetTransaction(
            networking=self.networking, journal=self.journal, lock=self.lock,
            running_guests=lambda: 0, live_preflight=lambda *_: None,
            vmware_action=lambda *_: None, verify_created_network=lambda *_: None,
        )
        with mock.patch.object(txn.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "Root"):
                with real._exclusive():
                    pass

    def test_simulated_crash_after_install_requires_explicit_recovery(self):
        def crash_on_start(operation):
            self.events.append(operation)
            if operation == "start":
                raise SystemExit("simulated abrupt termination")
        self.manager.vmware_action = crash_on_start
        with self.assertRaises(SystemExit):
            self.apply()
        self.assertEqual(json.loads(self.journal.read_text())["status"], "installed")
        self.assertNotEqual(self.networking.read_text(), BASE)
        self.manager.vmware_action = lambda action: self.events.append(action)
        self.assertEqual(self.manager.recover(), txn._digest(BASE.encode()))
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertEqual(json.loads(self.journal.read_text())["status"], "rolled_back")

    def test_rejects_candidate_that_would_trim_original_bytes(self):
        # The original planner normalizes trailing blank lines. An actual
        # transaction must fail instead of rewriting any existing byte.
        changed = BASE + "\n\n"
        self.networking.write_text(changed)
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "rewrite"):
            self.apply(sha=txn._digest(changed.encode()))
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.events, [])

    def test_completed_rollback_archival_preserves_evidence_without_network_restart(self):
        self.verify_fail = True
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "restored"):
            self.apply()
        old_bytes = self.journal.read_bytes()
        vmware_actions = tuple(self.events)
        saved = self.manager.archive_rolled_back(
            expected_source_sha256=txn._digest(BASE.encode()),
            vmnet4_absent=lambda: True,
        )
        archived = Path(saved)
        self.assertTrue(archived.is_file())
        self.assertEqual(archived.read_bytes(), old_bytes)
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertEqual(tuple(self.events), vmware_actions)

    def test_archival_requires_unchanged_original_checksum_and_no_vmnet4(self):
        self.verify_fail = True
        with self.assertRaises(txn.NetworkTransactionBlocked):
            self.apply()
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "source hash"):
            self.manager.archive_rolled_back(
                expected_source_sha256="0" * 64, vmnet4_absent=lambda: True)
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "absence"):
            self.manager.archive_rolled_back(
                expected_source_sha256=txn._digest(BASE.encode()),
                vmnet4_absent=lambda: False)
        self.assertTrue(self.journal.exists())

    def test_archival_refuses_any_running_guest(self):
        self.verify_fail = True
        with self.assertRaises(txn.NetworkTransactionBlocked):
            self.apply()
        self.guests = 1
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "guest activity"):
            self.manager.archive_rolled_back(
                expected_source_sha256=txn._digest(BASE.encode()),
                vmnet4_absent=lambda: True)
        self.assertTrue(self.journal.exists())

    def test_archival_refuses_committed_transactions(self):
        self.apply()
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "rolled_back"):
            self.manager.archive_rolled_back(
                expected_source_sha256=txn._digest(BASE.encode()),
                vmnet4_absent=lambda: True)
        self.assertTrue(self.journal.exists())

    def test_symlinked_networking_is_blocked(self):
        actual = self.base / "real-networking"
        self.networking.rename(actual)
        self.networking.symlink_to(actual)
        with self.assertRaisesRegex(txn.NetworkTransactionBlocked, "Unsafe"):
            self.apply()
        self.assertFalse(self.journal.exists())


if __name__ == "__main__":
    unittest.main()
