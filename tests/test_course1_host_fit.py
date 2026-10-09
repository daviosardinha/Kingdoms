"""Synthetic host-fit regression tests; never query actual host or hypervisor."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goad import course1_host_fit as fit
from goad.course1_runtime_contract import ProfileNotReady
from tests.test_course1_network_plan import proposal


def host_snapshot():
    return {
        "kind": "KINGDOMS_COURSE1_VMWARE_HOST_READONLY",
        "status": "OBSERVED_SNAPSHOT",
        "coverage": {"ip_addresses": True, "ip_routes": True,
                     "vmware_networking": True, "vmrun_running": True},
        "no_changes_performed": True,
        "candidate_allocation_authorized": False,
        "deployment_authorized": False,
        "observed_vmnets": ["vmnet0", "vmnet1", "vmnet8",
                            "vmnet10", "vmnet20", "vmnet30", "vmnet99"],
        "vmware_configured_subnet_hints": [
            {"vmnet": "vmnet10", "subnet_address": "10.4.10.0"},
            {"vmnet": "vmnet99", "subnet_address": "10.4.99.0"},
        ],
        "host_interfaces": [
            {"interface": "vmnet10", "ipv4": ["10.4.10.254/24"],
             "state": "UNKNOWN"},
            {"interface": "vmnet99", "ipv4": ["10.4.99.254/24"],
             "state": "UNKNOWN"},
            {"interface": "wlan0", "ipv4": ["192.168.1.159/24"], "state": "UP"},
        ],
        "ipv4_routes": [
            {"destination": "10.4.10.0/24", "interface": "vmnet10"},
            {"destination": "10.4.99.0/24", "interface": "vmnet99"},
            {"destination": "192.168.1.0/24", "interface": "wlan0"},
            {"destination": "fe80::/64", "interface": "wlan0"},
            {"destination": "default", "interface": "wlan0"},
        ],
        "running_vm_count": 1,
        "running_vms": [{"readable": True, "adapters": [
            {"adapter": 0, "generatedAddress": "00:0c:29:ad:be:ef"},
            {"adapter": 1, "address": "00:50:56:20:10:11", "vnet": "vmnet10"}
        ]}],
    }


class Course1HostFitTests(unittest.TestCase):
    def reject(self, tweak):
        p = proposal()
        snapshot = host_snapshot()
        tweak(p, snapshot)
        with self.assertRaises(ProfileNotReady):
            fit.inspect_host_fit(p, snapshot)

    def test_matching_survey_does_not_authorize_installation(self):
        result = fit.inspect_host_fit(proposal(), host_snapshot())
        self.assertEqual(result["status"], "NO_OBSERVED_CONFLICTS_NOT_PROVEN_AVAILABLE")
        self.assertTrue(result["host_snapshot_complete"])
        self.assertTrue(result["host_networks_surveyed"])
        self.assertEqual(result["unique_vmnets"], 3)
        self.assertEqual(result["running_vms_examined"], 1)
        self.assertFalse(result["dormant_or_unregistered_vms_examined"])
        self.assertFalse(result["candidate_allocation_authorized"])
        self.assertFalse(result["deployment_authorized"])

    def test_observed_vmnet_is_rejected(self):
        self.reject(lambda p, s: s["observed_vmnets"].append("vmnet11"))

    def test_host_interface_subnet_overlap_is_rejected(self):
        self.reject(lambda p, s: s["host_interfaces"].append({
            "interface": "wlan0.41", "ipv4": ["10.41.10.2/24"], "state": "UP"
        }))

    def test_vmware_networking_hint_overlap_is_rejected(self):
        self.reject(lambda p, s: s["vmware_configured_subnet_hints"].append({
            "vmnet": "vmnet60", "subnet_address": "10.41.20.0"
        }))

    def test_route_overlap_is_rejected(self):
        self.reject(lambda p, s: s["ipv4_routes"].append({
            "destination": "10.41.99.0/24", "interface": "tun0"
        }))

    def test_running_mac_collision_is_rejected(self):
        self.reject(lambda p, s: s["running_vms"][0]["adapters"].append({
            "adapter": 2, "address": "00:50:56:3a:10:11"
        }))

    def test_partial_survey_is_rejected(self):
        self.reject(lambda p, s: s.__setitem__("status", "INCOMPLETE"))

    def test_missing_vmrun_coverage_is_rejected(self):
        self.reject(lambda p, s: s["coverage"].__setitem__("vmrun_running", False))

    def test_incomplete_running_vmx_rejected(self):
        self.reject(lambda p, s: s["running_vms"][0].__setitem__("readable", False))

    def test_running_vm_count_inconsistent_is_rejected(self):
        self.reject(lambda p, s: s.__setitem__("running_vm_count", 2))

    def test_survey_cannot_claim_deployment_authorized(self):
        self.reject(lambda p, s: s.__setitem__("deployment_authorized", True))

    def test_survey_cannot_claim_mutations(self):
        self.reject(lambda p, s: s.__setitem__("no_changes_performed", False))

    def test_bad_observed_route_rejected(self):
        self.reject(lambda p, s: s["ipv4_routes"].append({
            "destination": "not-cidr", "interface": "vpn0"
        }))

    def test_checked_in_candidate_is_three_zones_and_not_deployable(self):
        path = Path(__file__).resolve().parents[1] / "docs/course1-network-candidate.example.json"
        candidate = json.loads(path.read_text(encoding="utf-8"))
        result = fit.validate_proposal(candidate)
        self.assertEqual(result["unique_vmnets"], 3)
        self.assertEqual(result["host_side_interfaces"], 2)
        self.assertFalse(result["deployment_authorized"])
        self.assertNotIn("ESSOS_TRANSITION", candidate["zones"])

    def test_no_hypervisor_mutations(self):
        source = Path(fit.__file__).read_text(encoding="utf-8")
        for item in ("vmrun stop", "vagrant up", "subprocess.run", "os.system",
                     "Path.write_text", "systemctl"):
            self.assertNotIn(item, source)

    def test_inspection_uses_only_mocked_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(proposal()), encoding="utf-8")
            with patch.object(fit, "host_survey", return_value=host_snapshot()) as mocked:
                self.assertTrue(fit.inspect_host_fit(
                    json.loads(path.read_text()), fit.host_survey()
                )["host_snapshot_complete"])
            mocked.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
