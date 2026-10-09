"""Mocked transaction and rollback tests; absolutely no host VMware mutations."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goad import course1_vmnet_transaction as tx
ORIGINAL_VM_GUARD = tx._verify_no_vmware_guests
from goad.course1_runtime_contract import ProfileNotReady
from tests.test_course1_host_fit import host_snapshot
from tests.test_course1_network_plan import proposal
from tests.test_course1_vmnet_maintenance import EXISTING


def stopped_snapshot():
    report = host_snapshot()
    report["running_vm_count"] = 0
    report["running_vms"] = []
    return report


class VmwareNetworkTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="c1-vmware-tx-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "networking"
        self.config.write_text(EXISTING, encoding="utf-8")
        self.backups = self.root / "private-backups"
        self.netmap = self.root / "netmap.conf"
        self.device_root = self.root / "dev"
        self.device_root.mkdir()
        for name in ("vmnet11", "vmnet12", "vmnet13"):
            (self.device_root / name).touch()
        patches = [
            patch.object(tx, "CONFIG", self.config),
            patch.object(tx, "BACKUPS", self.backups),
            patch.object(tx, "NETMAP", self.netmap),
            patch.object(tx, "VMNET_DEVICE_ROOT", self.device_root),
            patch.object(tx.os, "geteuid", return_value=0),
            patch.object(tx, "_verify_no_vmware_guests"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.proposal = proposal()
        self.snap = stopped_snapshot()

    def test_read_only_key_inspection_preserves_old_config(self):
        self.assertEqual(tx._keys(EXISTING.encode())[(10, "DHCP")], "no")
        before = self.config.read_bytes()
        report = tx.inspect_maintenance(self.proposal, self.snap, EXISTING)
        self.assertTrue(report["original_configuration_preserved"])
        self.assertEqual(before, self.config.read_bytes())

    def test_successful_apply_and_rollback_preserve_reference(self):
        with patch.object(tx, "_run_networks") as cmd:
            result = tx.apply(self.proposal, self.snap)
            self.assertEqual(result["status"], "COURSE1_NETWORK_CONFIG_APPLIED")
            self.assertFalse(result["deployment_authorized"])
            self.assertTrue(result["new_host_addresses_and_persistence_pending"])
            config = self.config.read_text()
            self.assertTrue(config.startswith(EXISTING))
            self.assertIn("answer VNET_11_DHCP no", config)
            self.assertIn("answer VNET_13_VIRTUAL_ADAPTER yes", config)
            backup_id = result["backup_id"]
            backup = self.backups / backup_id
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
            self.assertEqual(
                (backup / "networking.original").read_text(), EXISTING
            )
            self.assertEqual(
                json.loads((backup / "manifest.json").read_text())["state"],
                "APPLIED"
            )
            recovered = tx.rollback(backup_id)
            self.assertEqual(recovered["status"],
                             "REFERENCE_VMWARE_NETWORK_CONFIG_RESTORED")
            self.assertEqual(self.config.read_text(), EXISTING)
            self.assertEqual(cmd.call_count, 4)
            self.assertEqual(
                json.loads((backup / "manifest.json").read_text())["state"],
                "ROLLED_BACK"
            )

    def test_original_netmap_restored_on_rollback(self):
        self.netmap.write_text("ORIGINAL-NETMAP\n", encoding="utf-8")
        with patch.object(tx, "_run_networks"):
            result = tx.apply(self.proposal, self.snap)
            self.netmap.write_text("CHANGED-NETMAP\n", encoding="utf-8")
            tx.rollback(result["backup_id"])
        self.assertEqual(self.netmap.read_text(), "ORIGINAL-NETMAP\n")

    def test_vmware_restart_failure_auto_rolls_back(self):
        calls = []
        def fake_net(option):
            calls.append(option)
            if len(calls) == 2:
                raise ProfileNotReady("simulated failure")
        with patch.object(tx, "_run_networks", side_effect=fake_net):
            with self.assertRaisesRegex(ProfileNotReady, "original networking restored"):
                tx.apply(self.proposal, self.snap)
        self.assertEqual(self.config.read_text(), EXISTING)
        self.assertEqual(calls, ["--stop", "--start", "--stop", "--start"])
        manifest = list(self.backups.glob("*/manifest.json"))
        self.assertEqual(len(manifest), 1)
        self.assertEqual(json.loads(manifest[0].read_text())["state"],
                         "ROLLED_BACK")

    def test_failed_auto_rollback_calls_out_manual_recovery(self):
        def fake_net(option):
            raise ProfileNotReady("simulated vmware failure")
        with patch.object(tx, "_run_networks", side_effect=fake_net):
            with self.assertRaisesRegex(ProfileNotReady, "manual recovery"):
                tx.apply(self.proposal, self.snap)
        manifests = list(self.backups.glob("*/manifest.json"))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(json.loads(manifests[0].read_text())["state"],
                         "RECOVERY_NEEDED")

    def test_running_guests_refused_prior_to_backup(self):
        bad = host_snapshot()
        with self.assertRaisesRegex(ProfileNotReady, "snapshot is stale"):
            tx.apply(self.proposal, bad)
        self.assertFalse(self.backups.exists())
        self.assertEqual(self.config.read_text(), EXISTING)

    def test_active_vmware_process_guard_fail_closed(self):
        with patch.object(tx.subprocess, "run") as run:
            for rc in (0, 2):
                run.return_value.returncode = rc
                with self.subTest(returncode=rc):
                    with self.assertRaises(ProfileNotReady):
                        ORIGINAL_VM_GUARD()
            run.return_value.returncode = 1
            ORIGINAL_VM_GUARD()

    def test_changed_host_config_refuses_rollback(self):
        with patch.object(tx, "_run_networks"):
            result = tx.apply(self.proposal, self.snap)
            self.config.write_text(self.config.read_text() + "UNRELATED=1\n")
            with self.assertRaisesRegex(ProfileNotReady, "manual review required"):
                tx.rollback(result["backup_id"])

    def test_backup_id_path_traversal_refused(self):
        for value in ("../../reference", "c1-INVALID", "c1-20261009T210000Z-.."):
            with self.subTest(backup_id=value):
                with self.assertRaises(ProfileNotReady):
                    tx._read_backup(value)

    def test_static_assertion_requires_vmware_specific_confirmation(self):
        self.assertEqual(tx.CONFIRM,
                         "I_APPROVE_KINGDOMS_COURSE1_VMWARE_NETWORK_MAINTENANCE")
        shell = Path(__file__).resolve().parents[1] / (
            "scripts/course1/maintain-vmware-networks.sh"
        )
        content = shell.read_text(encoding="utf-8")
        self.assertIn("--confirm-maintenance", content)
        self.assertIn("pgrep -x vmware-vmx", content)
        self.assertNotIn("vmrun stop", content)
        self.assertNotIn("vagrant up", content)


if __name__ == "__main__":
    unittest.main()
