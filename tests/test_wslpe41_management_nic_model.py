"""Exact registered legacy WSLPE vmnet4 model repair regression tests."""
import base64
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from kingdoms import wslpe41_management_nic as nic
from kingdoms import wslpe41_management_nic_model as model

BASE = (
    b'ethernet0.present = "TRUE"\n'
    b'ethernet0.connectionType = "nat"\n'
    b'ethernet0.virtualDev = "e1000e"\n'
    b'ethernet1.present = "TRUE"\n'
    b'ethernet1.connectionType = "custom"\n'
    b'ethernet1.vnet = "vmnet3"\n'
    b'ethernet1.virtualDev = "e1000e"\n'
)
LEGACY = BASE + ("\n".join(model.OLD_NIC_LINES) + "\n").encode() + (
    b'ethernet2.generatedAddress = "00:0c:29:2f:d7:6f"\n'
)


class ManagementModelRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.vmx = self.home / "windows_10.vmx"
        self.vmx.write_bytes(LEGACY)
        self.vmx.chmod(0o771)
        self.target = nic.Target(
            self.home, self.vmx, LEGACY, hashlib.sha256(LEGACY).hexdigest())
        self.history = self.home / model.HISTORY_NAME / nic.INSTANCE
        self.history.mkdir(parents=True, mode=0o700)
        old = {
            "schema": "kingdoms.wslpe41.nic.v1", "status": "committed",
            "instance": nic.INSTANCE, "vmx": str(self.vmx),
            "original_b64": base64.b64encode(BASE).decode(),
            "original_sha256": hashlib.sha256(BASE).hexdigest(),
            "proposed_sha256": hashlib.sha256(
                BASE + ("\n".join(model.OLD_NIC_LINES) + "\n").encode()
            ).hexdigest(),
        }
        self.journal = self.history / "journal.json"
        self.journal.write_text(json.dumps(old))
        self.journal.chmod(0o600)
        self.repair = self.home / model.REPAIR_NAME / nic.INSTANCE

    def test_only_slot2_virtualdev_is_added_and_old_mac_is_preserved(self):
        result = model.candidate(LEGACY)
        self.assertEqual(result, LEGACY + model.EXACT_LINE)
        nic.verify_layout(result, allow_management=True)
        with self.assertRaisesRegex(nic.NicBlocked, "must be pinned"):
            nic.verify_layout(LEGACY, allow_management=True)
        self.assertIn(b'ethernet2.generatedAddress = "00:0c:29:2f:d7:6f"', result)

    def test_foreign_mac_and_wrong_existing_models_denied(self):
        with self.assertRaisesRegex(nic.NicBlocked, "MAC differs"):
            model.candidate(LEGACY.replace(b"2f:d7:6f", b"2f:d7:70"))
        with self.assertRaisesRegex(nic.NicBlocked, "working NIC models"):
            model.candidate(LEGACY.replace(
                b'ethernet1.virtualDev = "e1000e"',
                b'ethernet1.virtualDev = "e1000"'))
        vmware_explicit = LEGACY + b'ethernet2.virtualDev = "e1000"\n'
        repaired = model.candidate(vmware_explicit)
        self.assertEqual(repaired, LEGACY + model.EXACT_LINE)
        with self.assertRaisesRegex(nic.NicBlocked, "not a legacy e1000"):
            model.candidate(LEGACY + model.EXACT_LINE)

    def test_requires_committed_historical_journal_integrity(self):
        model._committed_attachment(self.home, self.vmx)
        original = json.loads(self.journal.read_text())
        for key, value in (
            ("status", "rolled_back"),
            ("vmx", str(self.home / "older.vmx")),
            ("proposed_sha256", "0"*64),
        ):
            with self.subTest(key=key):
                bad = dict(original, **{key: value})
                self.journal.write_text(json.dumps(bad))
                with self.assertRaises(nic.NicBlocked):
                    model._committed_attachment(self.home, self.vmx)
        self.journal.write_text(json.dumps(original))

    def test_successful_exact_offline_repair_creates_private_separate_receipt(self):
        original_history = self.journal.read_bytes()
        with (mock.patch.object(nic, "identify", return_value=self.target),
              mock.patch.object(nic, "zero_vmware_guests") as zero,
              mock.patch.object(nic, "host_operator_network_ready") as network):
            journal = model.apply(self.home, expected_sha256=self.target.digest,
                                  approval=model.APPROVAL)
            state = json.loads(Path(journal).read_text())
            self.assertEqual(state["status"], "committed")
            self.assertEqual(state["original_sha256"], self.target.digest)
            self.assertEqual(self.vmx.read_bytes(), LEGACY + model.EXACT_LINE)
            self.assertEqual(stat.S_IMODE(self.vmx.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(Path(journal).stat().st_mode), 0o600)
            self.assertEqual(self.journal.read_bytes(), original_history)
            zero.assert_called()
            network.assert_called_once()
            with self.assertRaisesRegex(nic.NicBlocked, "not a legacy e1000"):
                model.candidate(self.vmx.read_bytes())

    def test_wrong_hash_missing_approval_and_duplicate_journal_denied(self):
        with (mock.patch.object(nic, "identify", return_value=self.target),
              mock.patch.object(nic, "zero_vmware_guests"),
              mock.patch.object(nic, "host_operator_network_ready")):
            for digest, approval in (("0"*64, model.APPROVAL),
                                     (self.target.digest, "wrong")):
                with self.assertRaises(nic.NicBlocked):
                    model.apply(self.home, expected_sha256=digest,
                                approval=approval)
                self.assertEqual(self.vmx.read_bytes(), LEGACY)
            self.repair.mkdir(parents=True, mode=0o700)
            with self.assertRaisesRegex(nic.NicBlocked, "Existing NIC-model"):
                model.apply(self.home, expected_sha256=self.target.digest,
                            approval=model.APPROVAL)

    def test_no_other_vmware_or_windows_mutation_capability(self):
        text = (Path(__file__).resolve().parents[1] /
                "kingdoms/wslpe41_management_nic_model.py").read_text()
        for forbidden in ("vmware-networks", "vmrun -T ws start", "vmrun -T ws stop",
                          "New-NetIPAddress", "Set-NetAdapter", "systemctl restart",
                          "netsh", "ansible-playbook", "vmnet10"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
