"""Offline tests for additive VMware Course 1 network maintenance planning."""
import unittest
from unittest.mock import patch
from pathlib import Path

from goad import course1_vmnet_maintenance as net
from goad.course1_runtime_contract import ProfileNotReady
from tests.test_course1_host_fit import host_snapshot
from tests.test_course1_network_plan import proposal

EXISTING = """VERSION=1,0
answer VNET_1_VIRTUAL_ADAPTER yes
answer VNET_8_DHCP yes
answer VNET_10_DHCP no
answer VNET_20_VIRTUAL_ADAPTER no
answer VNET_30_VIRTUAL_ADAPTER no
answer VNET_99_HOSTONLY_SUBNET 10.4.99.0
add_bridge_mapping eth0 0
"""


class MaintenancePlanTests(unittest.TestCase):
    def plan(self, snapshot=None, text=EXISTING, p=None):
        return net.inspect_maintenance(p or proposal(),
                                       snapshot or host_snapshot(), text)

    def test_three_nets_additive_and_zero_reference_mutation(self):
        config, lines = net.compose_additive(EXISTING, proposal())
        self.assertTrue(config.startswith(EXISTING))
        self.assertEqual(config[:len(EXISTING)], EXISTING)
        self.assertNotIn("VNET_30_", "\n".join(lines))
        for number in (11, 12, 13):
            self.assertIn(f"answer VNET_{number}_DHCP no", lines)
            self.assertIn(f"answer VNET_{number}_HOSTONLY_SUBNET", config)
        self.assertIn("answer VNET_11_VIRTUAL_ADAPTER yes", config)
        self.assertIn("answer VNET_12_VIRTUAL_ADAPTER no", config)
        self.assertIn("answer VNET_13_VIRTUAL_ADAPTER yes", config)
        self.assertNotIn("VNET_12_HOSTONLY_HOSTADDR", "\n".join(lines))

    def test_six_running_guests_require_maintenance_window(self):
        result = self.plan()
        self.assertEqual(result["status"], "MAINTENANCE_WINDOW_REQUIRED")
        self.assertEqual(result["running_vm_count"], 1)
        self.assertTrue(result["running_guest_shutdown_required"])
        self.assertEqual(result["registered_vmx_examined"], 1)
        self.assertTrue(result["original_configuration_preserved"])
        self.assertFalse(result["vmware_networks_modified"])
        self.assertFalse(result["deployment_authorized"])
        self.assertFalse(result["allocation_authorized"])
        self.assertNotEqual(result["vmware_networking_existing_sha256"],
                            result["vmware_networking_proposed_sha256"])

    def test_no_running_guests_still_not_auto_authorized(self):
        snapshot = host_snapshot()
        snapshot["running_vm_count"] = 0
        snapshot["running_vms"] = []
        result = self.plan(snapshot=snapshot)
        self.assertEqual(result["status"], "HOST_CHANGE_REQUIRES_EXPLICIT_APPROVAL")
        self.assertFalse(result["running_guest_shutdown_required"])
        self.assertFalse(result["allocation_authorized"])

    def test_preexisting_proposed_vmnet_denied(self):
        with self.assertRaisesRegex(ProfileNotReady, "refuse overwrite"):
            net.compose_additive(EXISTING + "answer VNET_11_DHCP no\n", proposal())

    def test_corrupted_existing_vmware_config_denied(self):
        with self.assertRaises(ProfileNotReady):
            net.compose_additive(EXISTING.rstrip(), proposal())

    def test_registered_library_missing_denied_for_maintenance(self):
        snap = host_snapshot()
        snap["registered_inventory"].update({
            "library_status": "NOT_FOUND",
            "complete": False,
            "registered_vm_count": 0,
            "registered_vms": [],
        })
        with self.assertRaises(ProfileNotReady):
            self.plan(snapshot=snap)

    def test_candidate_conflicting_registered_vm_denied(self):
        snap = host_snapshot()
        snap["registered_inventory"]["registered_vms"][0]["adapters"][0][
            "vnet"] = "vmnet11"
        with self.assertRaises(ProfileNotReady):
            self.plan(snapshot=snap)

    def test_additive_plan_has_no_host_mutation(self):
        text = Path(net.__file__).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "vmrun stop", "vmware-networks --stop",
                          "Path.write_text", "os.system", "os.replace",
                          "systemctl", "chmod(", "shutil.copy"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
