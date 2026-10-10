"""NORTH collision preflight: owner VMX, registered and running guests."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goad.north_instance_collisions import inspect_north_guest_collisions
from goad.course1_vmnet_phase import inspect_network_phase
from goad.course1_runtime_contract import ProfileNotReady
from tests.test_course1_host_fit import host_snapshot
from tests.test_course1_network_plan import proposal

ROOT = Path(__file__).resolve().parents[1]


class NorthCollisionTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory(prefix="kingdoms-north-vm-collision-")
        self.addCleanup(temp.cleanup)
        provider = Path(temp.name) / "provider"
        provider.mkdir()
        snap = host_snapshot()
        for k, guest in enumerate(
            [*snap["running_vms"], *snap["registered_inventory"]["registered_vms"]]
        ):
            guest["vmx_identifier"] = f"{k + 1:012x}"
        return provider, snap

    def test_reference_running_and_registered_guests_are_allowed(self):
        provider, snap = self.fixture()
        result = inspect_north_guest_collisions(provider, proposal(), snap)
        self.assertEqual(result["status"], "NO_IDENTIFIED_NORTH_VM_COLLISIONS")
        self.assertEqual(result["foreign_vmx_examined"], 2)
        self.assertEqual(result["owned_vmx_examined"], 0)
        self.assertFalse(result["runtime_authorized"])

    def test_foreign_guest_on_north_vmnet_is_rejected(self):
        provider, snap = self.fixture()
        snap["registered_inventory"]["registered_vms"][0]["adapters"][0]["vnet"] = "vmnet11"
        with self.assertRaisesRegex(ProfileNotReady, "foreign.*vmnet"):
            inspect_north_guest_collisions(provider, proposal(), snap)

    def test_foreign_guest_using_reserved_mac_is_rejected(self):
        provider, snap = self.fixture()
        snap["running_vms"][0]["adapters"][0]["address"] = proposal()["machines"]["GOAD-WS01"]["mac"]
        with self.assertRaisesRegex(ProfileNotReady, "foreign.*MAC"):
            inspect_north_guest_collisions(provider, proposal(), snap)

    def test_partial_registered_inventory_is_rejected(self):
        provider, snap = self.fixture()
        snap["registered_inventory"]["complete"] = False
        with self.assertRaisesRegex(ProfileNotReady, "complete registered"):
            inspect_north_guest_collisions(provider, proposal(), snap)

    def test_owned_instance_vmx_must_have_correct_course_mac(self):
        provider, snap = self.fixture()
        guest = "GOAD-DC02"
        root = provider / ".vagrant/machines" / guest / "vmware_desktop"
        root.mkdir(parents=True)
        vmx = provider / "owned.vmx"
        vmx.write_text('config.version = "8"\n')
        (root / "id").write_text(str(vmx))
        label = hashlib.sha256(str(vmx).encode()).hexdigest()[:12]
        vmx_guest = {
            "vmx_identifier": label, "readable": True,
            "adapters": [{"adapter": 1, "vnet": "vmnet11",
                          "address": proposal()["machines"][guest]["mac"]}],
        }
        snap["registered_inventory"]["registered_vms"].append(vmx_guest)
        snap["registered_inventory"]["registered_vm_count"] += 1
        result = inspect_north_guest_collisions(provider, proposal(), snap)
        self.assertEqual(result["owned_vmx_examined"], 1)
        snap["registered_inventory"]["registered_vms"][-1]["adapters"][0]["address"] = (
            "00:50:56:3b:fe:ff"
        )
        with self.assertRaisesRegex(ProfileNotReady, "expected guest MAC"):
            inspect_north_guest_collisions(provider, proposal(), snap)

    def deployed_snapshot(self):
        """Exact owned NORTH VMX + existing foreign lab, no hypervisor I/O."""
        provider, snap = self.fixture()
        p = proposal()
        for zone in ("NORTH", "SEVENKINGDOMS", "MANAGEMENT"):
            net = p["zones"][zone]
            snap["observed_vmnets"].append(net["vmnet"])
            snap["vmware_configured_subnet_hints"].append({
                "vmnet": net["vmnet"],
                "subnet_address": net["subnet"].split("/")[0].rsplit(".", 1)[0] + ".0",
            })
        snap["host_interfaces"].extend([
            {"interface": "vmnet11", "ipv4": ["10.41.10.254/24"]},
            {"interface": "vmnet13", "ipv4": ["10.41.99.254/24"]},
        ])
        snap["ipv4_routes"].extend([
            {"destination": "10.41.10.0/24", "interface": "vmnet11"},
            {"destination": "10.41.99.0/24", "interface": "vmnet13"},
            {"destination": "10.41.20.0/24", "interface": "vmnet11",
             "gateway": "10.41.10.1"},
        ])
        for i, guest in enumerate(snap["running_vms"]):
            guest["vmx_identifier"] = f"{i + 1:012x}"
        for i, guest in enumerate(snap["registered_inventory"]["registered_vms"]):
            guest["vmx_identifier"] = f"{i + 101:012x}"
        guest_id = "GOAD-WS01"
        id_dir = provider / ".vagrant" / "machines" / guest_id / "vmware_desktop"
        id_dir.mkdir(parents=True)
        vmx = provider / "NORTH-owned.vmx"
        vmx.write_text('config.version = "8"\\n', encoding="utf-8")
        (id_dir / "id").write_text(str(vmx), encoding="utf-8")
        ours = {
            "readable": True,
            "vmx_identifier": hashlib.sha256(str(vmx).encode()).hexdigest()[:12],
            "adapters": [{"adapter": 1, "vnet": "vmnet11",
                          "address": p["machines"][guest_id]["mac"]}],
        }
        snap["running_vms"].append(ours)
        snap["running_vm_count"] += 1
        return provider, p, snap

    def test_deployed_north_scoped_readiness_preserves_foreign_evidence(self):
        provider, p, snap = self.deployed_snapshot()
        # Source-binding validator is separately regression-tested; the
        # synthetic temp fixture intentionally has no native inventories.
        with patch("goad.course1_vmnet_phase.inspect_north_instance_assets",
                   return_value={"status": "NATIVE_INSTANCE_SOURCE_VERIFIED"}):
            result = inspect_network_phase(p, snap, instance_provider=provider)
        self.assertEqual(result["status"], "NORTH_HOST_ADDRESSES_READY")
        self.assertEqual(result["north_owned_vmx_verified"], 1)
        self.assertEqual(result["running_vm_count"], 2)
        self.assertEqual(result["registered_vm_count"], 1)
        self.assertFalse(result["deployment_authorized"])

    def test_post_install_scope_is_mandatory_for_running_north_vmx(self):
        _, p, snap = self.deployed_snapshot()
        with self.assertRaises(ProfileNotReady):
            inspect_network_phase(p, snap)

    def test_scoped_readiness_rejects_foreign_vmnet_and_foreign_route(self):
        provider, p, snap = self.deployed_snapshot()
        with patch("goad.course1_vmnet_phase.inspect_north_instance_assets",
                   return_value={}):
            snap["registered_inventory"]["registered_vms"][0]["adapters"][0][
                "vnet"] = "vmnet11"
            with self.assertRaisesRegex(ProfileNotReady, "foreign.*vmnet"):
                inspect_network_phase(p, snap, instance_provider=provider)
            snap["registered_inventory"]["registered_vms"][0]["adapters"][0][
                "vnet"] = "vmnet88"
            snap["ipv4_routes"][-1]["gateway"] = "10.41.10.99"
            with self.assertRaisesRegex(ProfileNotReady, "overlaps observed"):
                inspect_network_phase(p, snap, instance_provider=provider)

    def test_scoped_readiness_rejects_unverified_instance_source(self):
        provider, p, snap = self.deployed_snapshot()
        with patch("goad.course1_vmnet_phase.inspect_north_instance_assets",
                   side_effect=ProfileNotReady("source drift")):
            with self.assertRaisesRegex(ProfileNotReady, "source drift"):
                inspect_network_phase(p, snap, instance_provider=provider)

    def test_provider_uses_north_survey_instead_of_reference_only_guard(self):
        src = (ROOT / "goad/provider/vagrant/vmware_kingdoms.py").read_text()
        self.assertIn("if self.lab_name == 'NORTH':", src)
        self.assertIn("inspect_north_guest_collisions(", src)
        self.assertIn("host_survey()", src)
        self.assertIn("guard = self._script('check-vmware-instance-conflicts.sh')", src)

    def test_owned_instance_vmx_cannot_point_outside_provider(self):
        provider, snap = self.fixture()
        vm = provider / ".vagrant/machines/GOAD-DC01/vmware_desktop"
        vm.mkdir(parents=True)
        outside = provider.parent / "reference.vmx"
        outside.write_text("fake\n")
        (vm / "id").write_text(str(outside))
        with self.assertRaisesRegex(ProfileNotReady, "outside this instance"):
            inspect_north_guest_collisions(provider, proposal(), snap)
