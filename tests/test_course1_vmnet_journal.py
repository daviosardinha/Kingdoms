"""Fail-closed VMware transaction journal and one persistent global lock."""
import json
import tempfile
import unittest
from pathlib import Path

from goad.course1_vmnet_journal import (
    VmnetJournalError, exclusive_vmnet_lock, inspect_vmnet_journals,
    record_journal, require_reconciled,
)


class NorthVmnetJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backups = self.root / "backup"
        self.backups.mkdir(mode=0o700)
        self.folder = self.backups / "north-abc123-unique"
        self.folder.mkdir(mode=0o700)
        self.sample = {
            "state": "PREPARED",
            "provider": "/tmp/kingdoms-instance/provider",
            "backup": str(self.folder / "networking.original"),
            "baseline_sha256": "a" * 64,
            "proposed_sha256": "b" * 64,
        }

    def test_journal_survives_and_refuses_incomplete_transaction(self):
        record_journal(self.folder, self.sample)
        items = inspect_vmnet_journals(self.backups)
        self.assertEqual(items[0]["state"], "PREPARED")
        self.assertEqual(items[0]["provider"], self.sample["provider"])
        with self.assertRaisesRegex(VmnetJournalError, "manual ownership reconciliation"):
            require_reconciled(self.backups)

    def test_terminal_states_allow_future_transaction(self):
        for state in ("COMMITTED", "ROLLED_BACK"):
            with self.subTest(state=state):
                record_journal(self.folder, {**self.sample, "state": state})
                require_reconciled(self.backups)
                self.assertEqual(inspect_vmnet_journals(self.backups)[0]["state"],
                                 state)

    def test_interrupted_verification_and_manual_state_always_block(self):
        for state in ("WRITTEN", "VERIFYING", "MANUAL_RECONCILIATION"):
            with self.subTest(state=state):
                record_journal(self.folder, {**self.sample, "state": state})
                with self.assertRaisesRegex(VmnetJournalError, "manual"):
                    require_reconciled(self.backups)

    def test_unparseable_or_missing_journal_refuses(self):
        with self.assertRaisesRegex(VmnetJournalError, "lacks readable journal"):
            inspect_vmnet_journals(self.backups)
        (self.folder / "journal.json").write_text("not-json")
        with self.assertRaisesRegex(VmnetJournalError, "Unparseable"):
            inspect_vmnet_journals(self.backups)

    def test_journal_symlink_is_rejected(self):
        foreign = self.root / "foreign"
        foreign.write_text(json.dumps(self.sample))
        (self.folder / "journal.json").symlink_to(foreign)
        with self.assertRaisesRegex(VmnetJournalError, "lacks readable journal"):
            inspect_vmnet_journals(self.backups)
        with self.assertRaisesRegex(VmnetJournalError, "symlink"):
            record_journal(self.folder, self.sample)
        self.assertEqual(json.loads(foreign.read_text()), self.sample)

    def test_world_writable_backup_root_blocks_lock(self):
        self.backups.chmod(0o777)
        with self.assertRaisesRegex(VmnetJournalError, "Unsafe global"):
            with exclusive_vmnet_lock(self.backups):
                self.fail("Unsafe backup root must not lock")

    def test_second_concurrent_transaction_is_refused_and_lock_is_stable(self):
        # Lockfile must remain on disk: removing it creates an inode race.
        with exclusive_vmnet_lock(self.backups):
            with self.assertRaisesRegex(VmnetJournalError, "owns the lock"):
                with exclusive_vmnet_lock(self.backups):
                    self.fail("Second transaction should never proceed")
        lockfile = self.backups / ".north-network.lock"
        self.assertTrue(lockfile.is_file())
        inode = lockfile.stat().st_ino
        with exclusive_vmnet_lock(self.backups):
            self.assertEqual(lockfile.stat().st_ino, inode)

    def test_symlinked_global_lock_cannot_be_followed(self):
        destination = self.root / "foreign"
        destination.write_text("never change me")
        (self.backups / ".north-network.lock").symlink_to(destination)
        with self.assertRaisesRegex(VmnetJournalError, "Cannot open guarded"):
            with exclusive_vmnet_lock(self.backups):
                self.fail("Symlinked lock must not be followed")
        self.assertEqual(destination.read_text(), "never change me")

    def test_invalid_stage_or_missing_owner_is_refused(self):
        with self.assertRaisesRegex(VmnetJournalError, "Invalid NORTH"):
            record_journal(self.folder, {**self.sample, "state": "UNKNOWN"})
        record_journal(self.folder, {**self.sample, "provider": ""})
        with self.assertRaisesRegex(VmnetJournalError, "Incomplete historical"):
            inspect_vmnet_journals(self.backups)


if __name__ == "__main__":
    unittest.main()
