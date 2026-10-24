"""Retiring destroyed NORTH must preserve foreign vmnets and never restore WSLPE NAT."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from goad.course1_hostaddrs import render_hostaddr_assets
from goad.course1_network_retire import _read_plan, RetirementBlocked
from goad.course1_vmnet_config import render_vmnet_config
from goad.kingdoms_topology import load_course1_topology


BASELINE = (
    "VERSION=1,0\n"
    "answer VNET_1_HOSTONLY_SUBNET 192.168.56.0\n"
    "answer VNET_8_NAT yes\n"
    "answer VNET_2_HOSTONLY_SUBNET 172.28.231.0\n"
    "add_nat_portfwd 8 tcp 2200 192.168.213.249 5985\n"
    "add_nat_portfwd 8 tcp 2201 192.168.213.249 5986\n"
    "add_nat_portfwd 8 tcp 2202 192.168.213.249 22\n"
)


class RetiredNorthFixtures(unittest.TestCase):
    def setUp(self):
        ctx = tempfile.TemporaryDirectory()
        self.addCleanup(ctx.cleanup)
        self.root = Path(ctx.name)
        self.provider = self.root / "abcdef-north-vmware" / "provider"
        self.provider.mkdir(parents=True)
        self.owner = self.root / "owner.json"
        self.backups = self.root / "backups"
        self.backups.mkdir(mode=0o700)
        self.savedir = self.backups / "north-previous"
        self.savedir.mkdir(mode=0o700)
        self.backup = self.savedir / "networking.original"
        self.backup.write_text(BASELINE)
        self.backup.chmod(0o600)
        self.networking = self.root / "networking"
        layout = load_course1_topology()
        committed = render_vmnet_config(BASELINE, layout)
        self.committed = committed
        # VMware destroyed all Vagrant NAT forwards, not the 3 vmnets.
        active = committed.replace(
            "add_nat_portfwd 8 tcp 2200 192.168.213.249 5985\n", ""
        ).replace(
            "add_nat_portfwd 8 tcp 2201 192.168.213.249 5986\n", ""
        ).replace(
            "add_nat_portfwd 8 tcp 2202 192.168.213.249 22\n", ""
        )
        active = active.replace("answer VNET_10_HOSTONLY_HOSTADDR 10.4.10.254\n", "")
        active = active.replace("answer VNET_99_HOSTONLY_HOSTADDR 10.4.99.254\n", "")
        self.networking.write_text(active)
        self.networking.chmod(0o640)
        self.owner.write_text(json.dumps({
            "profile": "NORTH",
            "provider": str(self.provider),
            "network_base": layout["network_base"],
            "vmnets": {k: v["vmnet"] for k, v in layout["segments"].items()},
            "baseline_sha256": hashlib.sha256(BASELINE.encode()).hexdigest(),
            "installed_sha256": hashlib.sha256(committed.encode()).hexdigest(),
            "backup": str(self.backup),
        }))
        self.owner.chmod(0o600)
        (self.savedir / "journal.json").write_text(json.dumps({
            "state": "COMMITTED", "provider": str(self.provider),
            "baseline_sha256": hashlib.sha256(BASELINE.encode()).hexdigest(),
            "proposed_sha256": hashlib.sha256(committed.encode()).hexdigest(),
            "backup": str(self.backup),
        }))
        self.files = {name: self.root / name for name in ("helper", "service", "timer")}
        for name, content in render_hostaddr_assets(layout).items():
            self.files[name].write_text(content)
            self.files[name].chmod(0o755 if name == "helper" else 0o644)

    def preview(self):
        return _read_plan(self.provider, networking=self.networking,
                          owner=self.owner, backups=self.backups,
                          files=self.files, owner_uid=os.geteuid())

    def test_destroyed_vm_nats_allow_exact_host_retirement_and_keep_foreign(self):
        plan = self.preview()
        after = plan["new_config"].decode()
        self.assertNotIn("VNET_10_", after)
        self.assertNotIn("VNET_20_", after)
        self.assertNotIn("VNET_99_", after)
        self.assertIn("VNET_2_HOSTONLY_SUBNET 172.28.231.0", after)
        self.assertIn("VNET_8_NAT yes", after)
        self.assertIn("VNET_1_HOSTONLY_SUBNET 192.168.56.0", after)
        self.assertEqual(len([line for line in plan["removed"]
                              if line.startswith("answer VNET_")]), 15)
        self.assertEqual(self.networking.read_text().count("VNET_10_"), 5)
        self.assertTrue(self.owner.exists())
        self.assertEqual((self.savedir / "journal.json").stat().st_size > 0, True)

    def test_existing_foreign_nat_forward_blocks_retirement(self):
        with self.networking.open("a") as f:
            f.write("add_nat_portfwd 8 tcp 3456 192.168.213.61 22\n")
        with self.assertRaisesRegex(RetirementBlocked, "NAT forwards still exist"):
            self.preview()

    def test_new_or_duplicated_owned_vmnet_line_is_refused(self):
        with self.networking.open("a") as f:
            f.write("answer VNET_20_DHCP no\n")
        with self.assertRaisesRegex(RetirementBlocked, "inconsistent"):
            self.preview()

    def test_foreign_owner_provider_refused(self):
        data = json.loads(self.owner.read_text())
        data["provider"] = "/tmp/foreign-north-vmware/provider"
        self.owner.write_text(json.dumps(data))
        with self.assertRaisesRegex(RetirementBlocked, "does not match"):
            self.preview()

    def test_committed_hash_mismatch_refused(self):
        data = json.loads(self.owner.read_text())
        data["installed_sha256"] = "0" * 64
        self.owner.write_text(json.dumps(data))
        with self.assertRaisesRegex((RetirementBlocked, RuntimeError), "hash|match"):
            self.preview()

    def test_missing_journal_refused(self):
        (self.savedir / "journal.json").unlink()
        with self.assertRaises((RetirementBlocked, RuntimeError)):
            self.preview()

    def test_remaining_vm_registration_refused(self):
        marker = self.provider / ".vagrant/machines/GOAD-WS01/vmware_desktop/id"
        marker.parent.mkdir(parents=True)
        marker.write_text("/some/other/vmx")
        with self.assertRaisesRegex(RetirementBlocked, "still registered"):
            self.preview()

    def test_host_address_asset_byte_drift_refused(self):
        self.files["helper"].write_text("not the original asset")
        with self.assertRaisesRegex(RetirementBlocked, "content drift"):
            self.preview()

    def test_retirement_never_mutates_during_plan(self):
        before = {name: path.read_bytes()
                  for name, path in self.files.items()}
        owner = self.owner.read_bytes()
        config = self.networking.read_bytes()
        self.preview()
        self.assertEqual(config, self.networking.read_bytes())
        self.assertEqual(owner, self.owner.read_bytes())
        self.assertEqual(before, {name: path.read_bytes()
                                   for name, path in self.files.items()})


if __name__ == "__main__":
    unittest.main()
