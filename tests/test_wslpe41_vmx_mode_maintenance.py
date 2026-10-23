"""Exact VMX 0771->0600 maintenance, journal and no-network-write regression."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

from kingdoms import wslpe41_management_nic as nic

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/wslpe41-normalize-vmx-mode.py"
SPEC = importlib.util.spec_from_file_location("wslpe41_normalize_vmx_mode", PATH)
assert SPEC and SPEC.loader
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)

ORIGINAL = (
    b'ethernet0.present = "TRUE"\n'
    b'ethernet0.connectionType = "nat"\n'
    b'ethernet1.present = "TRUE"\n'
    b'ethernet1.connectionType = "custom"\n'
    b'ethernet1.vnet = "vmnet3"\n'
)


class ExactVMXModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.vmx = self.base / "windows_10.vmx"
        self.vmx.write_bytes(ORIGINAL)
        self.vmx.chmod(0o771)
        self.target = nic.Target(
            self.base, self.vmx, ORIGINAL, hashlib.sha256(ORIGINAL).hexdigest())
        self.state = self.base / "state" / nic.INSTANCE
        self.nic_journal = self.base / "nic-journal.json"

    def test_legacy_mode_is_observable_but_never_accepted_by_attachment(self):
        with self.assertRaisesRegex(nic.NicBlocked, "group/other-writable"):
            nic._read_vmx(self.vmx)
        self.assertEqual(nic._read_vmx(self.vmx, exact_legacy_0771_probe=True), ORIGINAL)
        self.vmx.chmod(0o775)
        with self.assertRaisesRegex(nic.NicBlocked, "group/other-writable"):
            nic._read_vmx(self.vmx, exact_legacy_0771_probe=True)

    def test_one_time_change_preserves_exact_contents_and_records_mode(self):
        with (mock.patch.object(APP, "STATE", self.state),
              mock.patch.object(APP, "NIC_JOURNAL", self.nic_journal),
              mock.patch.object(APP, "preflight",
                                side_effect=lambda: (self.target, self.vmx.lstat())),
              mock.patch.object(APP, "zero_vmware_guests") as zero):
            APP.normalize(self.target.digest, APP.APPROVAL)
            self.assertEqual(self.vmx.read_bytes(), ORIGINAL)
            self.assertEqual(stat.S_IMODE(self.vmx.stat().st_mode), 0o600)
            record_path = self.state / "receipt.json"
            record = json.loads(record_path.read_text())
            self.assertEqual(record["status"], "committed")
            self.assertEqual(record["old_mode"], "0771")
            self.assertEqual(record["new_mode"], "0600")
            self.assertEqual(stat.S_IMODE(record_path.stat().st_mode), 0o600)
            zero.assert_called_once()
            with self.assertRaises(APP.NicBlocked):
                APP.normalize(self.target.digest, APP.APPROVAL)

    def test_invalid_authorization_and_original_hash_refuse_writes(self):
        with (mock.patch.object(APP, "STATE", self.state),
              mock.patch.object(APP, "preflight",
                                side_effect=lambda: (self.target, self.vmx.lstat()))):
            for digest, approval in (
                ("0" * 64, APP.APPROVAL),
                (self.target.digest, "wrong"),
            ):
                with self.assertRaises(APP.NicBlocked):
                    APP.normalize(digest, approval)
                self.assertEqual(stat.S_IMODE(self.vmx.stat().st_mode), 0o771)
                self.assertFalse(self.state.exists())

    def test_preflight_blocks_existing_management_nic_journal(self):
        self.nic_journal.write_text('{"status": "prepared"}')
        with (mock.patch.object(APP, "NIC_JOURNAL", self.nic_journal),
              mock.patch.object(APP, "zero_vmware_guests"),
              mock.patch.object(APP, "host_operator_network_ready")):
            with self.assertRaisesRegex(APP.NicBlocked, "prior NIC transaction"):
                APP.preflight()

    def test_read_only_plan_and_no_shared_mutation(self):
        with (mock.patch.object(APP, "preflight",
                                side_effect=lambda: (self.target, self.vmx.lstat())),
              mock.patch.object(APP, "normalize") as normalize):
            self.assertEqual(APP.main(["--plan"]), 0)
            normalize.assert_not_called()
        text = PATH.read_text()
        for forbidden in ("vmware-networks", "vmrun -T ws start",
                          "vmrun -T ws stop", "sysctl -w", "chown -R",
                          "chmod -R", "ip address add", "New-LocalUser"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
