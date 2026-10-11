"""No-host-write acceptance for native NORTH VMware + .254 setup adapter."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goad.course1_host_network_apply import (apply, diagnose_installed_north, inspect_installed_north, NorthSetupError)
from goad.course1_vmnet_journal import inspect_vmnet_journals

BASE = (
    "VERSION=1,0\n"
    "answer VNET_1_HOSTONLY_SUBNET 192.168.56.0\n"
    "answer VNET_1_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_8_NAT yes\n"
)


class Course1NativeNetworkApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.networking = self.root / "networking"
        self.networking.write_text(BASE)
        self.networking.chmod(0o640)
        self.netmap = self.root / "netmap.conf"
        self.netmap.write_text("ORIGINAL_NETMAP\n")
        self.netmap.chmod(0o640)
        self.backups = self.root / "backups"
        self.owner = self.root / "owner.json"
        self.provider = self.root / "instance-provider"
        self.provider.mkdir(mode=0o700)
        self.vmware = self.root / "vmware-networks"
        self.vmware.write_text("#!/bin/sh\n")
        self.vmware.chmod(0o755)
        self.paths = {name: self.root / name for name in
                      ("helper", "service", "timer")}
        self.events = []
        self.sha = hashlib.sha256(BASE.encode()).hexdigest()

    def launch(self, vmware_behavior=None, extra=None, hostaddr_check=None):
        import goad.course1_host_network_apply as runtime
        def fake_command(*args, **kw):
            self.events.append(tuple(map(str, args)))
            if vmware_behavior:
                vmware_behavior(args)
        def noop(*args, **kw):
            return ()
        with patch.object(runtime, "require_explicit_root", noop), \
             patch.object(runtime, "inspect_live", noop), \
             patch.object(runtime, "inspect_live_hostaddrs", hostaddr_check or noop), \
             patch.object(runtime, "inspect_live_hostaddr_assets", noop), \
             patch.object(runtime, "asset_paths", return_value=self.paths), \
             patch.object(runtime, "run_command", fake_command):
            if extra:
                with extra:
                    return apply(
                        str(self.provider), self.sha, networking=self.networking,
                        netmap=self.netmap, backups=self.backups, owner=self.owner,
                        library=self.root / "inventory.vmls", vmware_networks=self.vmware,
                    )
            return apply(
                str(self.provider), self.sha, networking=self.networking,
                netmap=self.netmap, backups=self.backups, owner=self.owner,
                library=self.root / "inventory.vmls", vmware_networks=self.vmware,
            )

    def test_vmware_restart_counts_second_callback_as_rollback(self):
        import goad.course1_host_network_apply as runtime
        restart = runtime.VMwareNetworkRestart(
            self.netmap, self.netmap.read_bytes(), self.netmap.stat(),
            executable=self.vmware,
        )
        with patch.object(runtime, "run_command", return_value=None):
            restart()
            self.assertEqual(restart.calls, 1)
            restart()
            self.assertEqual(restart.calls, 2)
        self.assertEqual(self.netmap.read_text(), "ORIGINAL_NETMAP\n")

    def test_full_owned_setup_uses_existing_transaction_with_three_vmnets(self):
        installed = self.launch()
        text = self.networking.read_text()
        self.assertEqual(installed["profile"], "NORTH")
        self.assertIn("VNET_10_HOSTONLY_SUBNET 10.4.10.0", text)
        self.assertIn("VNET_20_HOSTONLY_SUBNET 10.4.20.0", text)
        self.assertIn("VNET_99_HOSTONLY_SUBNET 10.4.99.0", text)
        self.assertNotIn("VNET_30_", text)
        self.assertEqual(json.loads(self.owner.read_text())["profile"], "NORTH")
        self.assertTrue(all(p.is_file() for p in self.paths.values()))
        self.assertEqual(inspect_vmnet_journals(self.backups)[0]["state"], "COMMITTED")
        self.assertEqual([item[1] for item in self.events if len(item) > 1
                          and item[0] == str(self.vmware)], ["--stop", "--start"])
        self.assertTrue(any(item[:2] == ("systemctl", "enable") for item in self.events))

    def test_vmware_restart_failure_rolls_back_vmnet_without_assets(self):
        attempts = []
        def fail_first_start(args):
            if len(args) > 1 and args[0] == str(self.vmware) and args[1] == "--start":
                attempts.append("start")
                if len(attempts) == 1:
                    raise NorthSetupError("simulated VMware failure")
        with self.assertRaisesRegex(RuntimeError, "failed safely"):
            self.launch(vmware_behavior=fail_first_start)
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertEqual(self.netmap.read_text(), "ORIGINAL_NETMAP\n")
        self.assertFalse(self.owner.exists())
        self.assertTrue(all(not p.exists() for p in self.paths.values()))
        self.assertEqual(inspect_vmnet_journals(self.backups)[0]["state"], "ROLLED_BACK")

    def test_late_commit_failure_rolls_back_networks_and_address_assets(self):
        from goad import course1_vmnet_transaction as transaction
        actual_record = transaction.record_journal
        def fail_commit(folder, data):
            if data["state"] == "COMMITTED":
                raise RuntimeError("simulated failed commit")
            actual_record(folder, data)
        with self.assertRaisesRegex(RuntimeError, "failed safely"):
            self.launch(extra=patch.object(transaction, "record_journal", fail_commit))
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertFalse(self.owner.exists())
        self.assertEqual(self.netmap.read_text(), "ORIGINAL_NETMAP\n")
        self.assertTrue(all(not p.exists() for p in self.paths.values()))
        self.assertTrue(any(item[:2] == ("systemctl", "disable") for item in self.events))

    def test_absent_netmap_is_normal_and_no_dummy_file_is_created(self):
        self.netmap.unlink()
        installed = self.launch()
        self.assertEqual(installed["profile"], "NORTH")
        self.assertFalse(self.netmap.exists())
        self.assertTrue(self.owner.is_file())
        self.assertEqual(inspect_vmnet_journals(self.backups)[0]["state"], "COMMITTED")

    def test_absent_netmap_restart_failure_restores_original_networking(self):
        self.netmap.unlink()
        starts = []
        def fail_first_start(args):
            if args[:2] == (str(self.vmware), "--start"):
                starts.append(1)
                if len(starts) == 1:
                    raise NorthSetupError("simulated startup failure")
        with self.assertRaisesRegex(RuntimeError, "failed safely"):
            self.launch(vmware_behavior=fail_first_start)
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertFalse(self.netmap.exists())
        self.assertFalse(self.owner.exists())
        self.assertEqual(inspect_vmnet_journals(self.backups)[0]["state"], "ROLLED_BACK")

    def test_vmware_generated_netmap_is_removed_only_when_owned_during_rollback(self):
        self.netmap.unlink()
        starts = []
        def create_on_first_start(args):
            if args[:2] == (str(self.vmware), "--start"):
                starts.append(1)
                if len(starts) == 1:
                    self.netmap.write_text("VMWARE_CREATED_MAP\n")
        def fail_addr(*args, **kwargs):
            raise RuntimeError("deliberately fail address verification")
        with self.assertRaisesRegex(RuntimeError, "failed safely"):
            self.launch(vmware_behavior=create_on_first_start, hostaddr_check=fail_addr)
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertFalse(self.netmap.exists())
        self.assertFalse(self.owner.exists())
        self.assertEqual(inspect_vmnet_journals(self.backups)[0]["state"], "ROLLED_BACK")

    def test_foreign_netmap_change_after_restart_blocks_unsafe_rollback(self):
        self.netmap.unlink()
        starts = []
        def create_or_change_on_restart(args):
            if args[:2] == (str(self.vmware), "--start"):
                starts.append(1)
                if len(starts) == 1:
                    self.netmap.write_text("VMWARE_CREATED_MAP\n")
            elif args[:2] == (str(self.vmware), "--stop") and starts:
                self.netmap.write_text("FOREIGN_MAP_CHANGE\n")
        def fail_addr(*args, **kwargs):
            raise RuntimeError("verify failed")
        with self.assertRaisesRegex(RuntimeError, "network restart failed"):
            self.launch(vmware_behavior=create_or_change_on_restart,
                        hostaddr_check=fail_addr)
        self.assertEqual(self.netmap.read_text(), "FOREIGN_MAP_CHANGE\n")
        self.assertEqual(inspect_vmnet_journals(self.backups)[0]["state"], "MANUAL_RECONCILIATION")

    def test_symlinked_netmap_is_refused_without_host_writes(self):
        self.netmap.unlink()
        target = self.root / "foreign-netmap"
        target.write_text("UNRELATED\n")
        self.netmap.symlink_to(target)
        with self.assertRaisesRegex(NorthSetupError, "symlink"):
            self.launch()
        self.assertEqual(target.read_text(), "UNRELATED\n")
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertFalse(self.backups.exists())
        self.assertFalse(self.owner.exists())

    def test_bad_digest_refuses_before_any_vmware_restart(self):
        self.sha = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "changed since reviewed baseline"):
            self.launch()
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertFalse(self.owner.exists())
        self.assertFalse(any(str(self.vmware) == item[0] for item in self.events))

    def test_existing_systemd_asset_refuses_before_any_network_write(self):
        self.paths["timer"].write_text("foreign")
        with self.assertRaisesRegex(NorthSetupError, "Existing NORTH"):
            self.launch()
        self.assertEqual(self.paths["timer"].read_text(), "foreign")
        self.assertEqual(self.networking.read_text(), BASE)
        self.assertFalse(self.owner.exists())

    def attest(self):
        return inspect_installed_north(
            self.provider, networking=self.networking, owner=self.owner,
            backups=self.backups, owner_uid=os.getuid(), inspect_host=False,
        )

    def test_installed_owner_matches_exact_north_instance_and_journal(self):
        self.launch()
        proofs = self.attest()
        self.assertEqual(len(proofs), 2)

    def test_owner_attestation_rejects_wrong_instance_and_modified_vmnet(self):
        self.launch()
        foreign = self.root / "other-instance"
        foreign.mkdir()
        with self.assertRaisesRegex(NorthSetupError, "another instance"):
            inspect_installed_north(
                foreign, networking=self.networking, owner=self.owner,
                backups=self.backups, owner_uid=os.getuid(), inspect_host=False,
            )
        self.networking.write_text(self.networking.read_text() + "# changed\n")
        with self.assertRaisesRegex(NorthSetupError, "differs from owned"):
            self.attest()

    def test_owner_attestation_rejects_untrusted_record(self):
        self.launch()
        self.owner.chmod(0o644)
        with self.assertRaisesRegex(NorthSetupError, "permissions are unsafe"):
            self.attest()
        self.owner.chmod(0o600)
        other = self.root / "owner-real"
        self.owner.rename(other)
        self.owner.symlink_to(other)
        with self.assertRaisesRegex(NorthSetupError, "missing or unsafe"):
            self.attest()

    def test_owner_attestation_rejects_missing_backup_and_stale_journal(self):
        self.launch()
        record = json.loads(self.owner.read_text())
        Path(record["backup"]).unlink()
        with self.assertRaisesRegex(NorthSetupError, "backup is missing"):
            self.attest()
        Path(record["backup"]).write_bytes(BASE.encode())
        journal_path = next(self.backups.glob("north-*")) / "journal.json"
        data = json.loads(journal_path.read_text())
        data["state"] = "MANUAL_RECONCILIATION"
        journal_path.write_text(json.dumps(data))
        with self.assertRaisesRegex(NorthSetupError, "requires reconciliation"):
            self.attest()

    def test_owner_attestation_checks_live_addresses_by_default(self):
        self.launch()
        import goad.course1_host_network_apply as runtime
        with patch.object(runtime, "inspect_live_hostaddrs",
                          side_effect=ValueError("address drift")):
            with self.assertRaisesRegex(ValueError, "address drift"):
                inspect_installed_north(
                    self.provider, networking=self.networking, owner=self.owner,
                    backups=self.backups, owner_uid=os.getuid(),
                )

    def test_ownership_verify_cli_does_not_call_network_apply(self):
        import sys
        import goad.course1_host_network_apply as runtime
        with patch.object(sys, "argv", ["north-host", "verify", "--provider-dir",
                                        str(self.provider)]), \
             patch.object(runtime, "require_explicit_root") as root, \
             patch.object(runtime, "inspect_installed_north",
                          return_value=("owner matched",)) as check, \
             patch.object(runtime, "apply") as apply_vmware:
            runtime.main()
        root.assert_called_once_with()
        check.assert_called_once_with(str(self.provider))
        apply_vmware.assert_not_called()

    def diagnose(self):
        return diagnose_installed_north(
            self.provider, networking=self.networking, owner=self.owner,
            backups=self.backups, owner_uid=os.getuid(),
        )

    def test_readonly_diagnose_matches_committed_networking(self):
        self.launch()
        before = self.networking.read_bytes()
        report = self.diagnose()
        self.assertTrue(report["exact_match"])
        self.assertEqual(report["vmnet_topology"], "PASS")
        self.assertEqual(report["diff"], [])
        self.assertEqual(self.networking.read_bytes(), before)

    def test_readonly_diagnose_reports_post_vmware_foreign_key_without_rebasing_owner(self):
        self.launch()
        initial = self.owner.read_bytes()
        self.networking.write_text(
            self.networking.read_text()
            + "answer VNET_1_HOSTONLY_HOSTADDR 192.168.56.1\\n"
        )
        report = self.diagnose()
        self.assertFalse(report["exact_match"])
        self.assertEqual(report["vmnet_topology"], "PASS")
        self.assertIn("answer VNET_1_HOSTONLY_HOSTADDR", "\\n".join(report["diff"]))
        self.assertEqual(self.owner.read_bytes(), initial)

    def test_readonly_diagnose_flags_protected_vmnet_change(self):
        self.launch()
        text = self.networking.read_text()
        self.assertIn("answer VNET_20_VIRTUAL_ADAPTER no", text)
        self.networking.write_text(text.replace(
            "answer VNET_20_VIRTUAL_ADAPTER no",
            "answer VNET_20_VIRTUAL_ADAPTER yes",
        ))
        report = self.diagnose()
        self.assertFalse(report["exact_match"])
        self.assertTrue(report["vmnet_topology"].startswith("FAIL:"))
        self.assertIn("VNET_20_VIRTUAL_ADAPTER", "\\n".join(report["diff"]))

    def test_readonly_diagnose_blocks_other_instance(self):
        self.launch()
        foreign = self.root / "different-provider"
        foreign.mkdir()
        with self.assertRaisesRegex(NorthSetupError, "different instance"):
            diagnose_installed_north(
                foreign, networking=self.networking, owner=self.owner,
                backups=self.backups, owner_uid=os.getuid(),
            )

    def test_diagnose_cli_never_calls_network_apply(self):
        import sys
        import goad.course1_host_network_apply as runtime
        healthy = {
            "owned_sha256": self.sha,
            "observed_sha256": "0" * 64,
            "exact_match": False,
            "vmnet_topology": "PASS",
            "diff": ["+answer VNET_1_X changed"],
            "diff_truncated": False,
        }
        with patch.object(sys, "argv", ["north-host", "diagnose", "--provider-dir",
                                        str(self.provider)]), \
             patch.object(runtime, "require_explicit_root"), \
             patch.object(runtime, "diagnose_installed_north", return_value=healthy), \
             patch.object(runtime, "apply") as apply_vmware:
            with self.assertRaises(SystemExit) as error:
                runtime.main()
        self.assertEqual(error.exception.code, 2)
        apply_vmware.assert_not_called()

    def test_no_implicit_host_apply_in_one_command_validator(self):
        script = (Path(__file__).resolve().parents[1] /
                  "scripts/validate-course1.sh").read_text()
        self.assertNotIn("--north apply", script)
        rollout = (Path(__file__).resolve().parents[1] /
                   "scripts/course1-rollout.sh").read_text()
        self.assertNotIn("--north apply", rollout)


if __name__ == "__main__":
    unittest.main()
