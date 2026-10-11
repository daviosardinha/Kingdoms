"""No-host-write acceptance for native NORTH VMware + .254 setup adapter."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goad.course1_host_network_apply import apply, NorthSetupError
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

    def launch(self, vmware_behavior=None, extra=None):
        import goad.course1_host_network_apply as runtime
        def fake_command(*args, **kw):
            self.events.append(tuple(map(str, args)))
            if vmware_behavior:
                vmware_behavior(args)
        def noop(*args, **kw):
            return ()
        with patch.object(runtime, "require_explicit_root", noop), \
             patch.object(runtime, "inspect_live", noop), \
             patch.object(runtime, "inspect_live_hostaddrs", noop), \
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

    def test_no_implicit_host_apply_in_one_command_validator(self):
        script = (Path(__file__).resolve().parents[1] /
                  "scripts/validate-course1.sh").read_text()
        self.assertNotIn("--north apply", script)
        rollout = (Path(__file__).resolve().parents[1] /
                   "scripts/course1-rollout.sh").read_text()
        self.assertNotIn("--north apply", rollout)


if __name__ == "__main__":
    unittest.main()
