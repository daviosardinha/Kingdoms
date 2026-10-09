"""Offline Kingdoms four-VM network collision tests."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from goad.course1_network_plan import (
    ROOT, ZONES, preview_shared_identifiers, reference_contract, validate_proposal,
)
from goad.course1_runtime_contract import COURSE1, ProfileNotReady
from goad.course1_source_gate import _generator_render


def proposal():
    # SYNTHETIC values. These VMware networks have NOT been checked on a host.
    return {
        "profile": COURSE1.name,
        "state": "PROPOSED_NOT_DEPLOYABLE",
        "zones": {
            "NORTH": {"vmnet": "vmnet41", "subnet": "10.41.10.0/24",
                      "gateway": "10.41.10.1"},
            "SEVENKINGDOMS": {"vmnet": "vmnet42", "subnet": "10.41.20.0/24",
                             "gateway": "10.41.20.1"},
            "MANAGEMENT": {"vmnet": "vmnet49", "subnet": "10.41.99.0/24",
                           "gateway": "10.41.99.1"},
        },
        "machines": {
            "GOAD-DC01": {"zone": "SEVENKINGDOMS", "ip": "10.41.20.10",
                          "mac": "02:44:20:00:00:10"},
            "GOAD-DC02": {"zone": "NORTH", "ip": "10.41.10.11",
                          "mac": "02:44:10:00:00:11"},
            "GOAD-SRV02": {"zone": "NORTH", "ip": "10.41.10.22",
                           "mac": "02:44:10:00:00:22"},
            "GOAD-WS01": {"zone": "NORTH", "ip": "10.41.10.31",
                          "mac": "02:44:10:00:00:31"},
        },
        "host_addresses": {"NORTH": "10.41.10.254", "MANAGEMENT": "10.41.99.254"},
        "router_macs": {
            "NORTH": "02:44:10:00:01:01",
            "SEVENKINGDOMS": "02:44:20:00:01:01",
            "MANAGEMENT": "02:44:99:00:01:01",
        },
    }


class Course1NetworkPlanTests(unittest.TestCase):
    def reject(self, mutate):
        p = proposal()
        mutate(p)
        with self.assertRaises(ProfileNotReady):
            validate_proposal(p)

    def test_reference_segments_include_router_management(self):
        surface, networks = reference_contract()
        self.assertEqual(surface.vmnets, frozenset(
            {"vmnet10", "vmnet20", "vmnet30", "vmnet99"}))
        self.assertEqual(len(surface.ips), 6)
        self.assertEqual(len(surface.macs), 10)
        self.assertEqual({str(n) for n in networks},
                         {"10.4.10.0/24", "10.4.20.0/24",
                          "10.4.30.0/24", "10.4.99.0/24"})

    def test_current_preview_has_reference_collisions(self):
        text = _generator_render()["instance-preview/Vagrantfile"]
        found = preview_shared_identifiers(text)
        self.assertEqual(found["shared_vmnets"], 4)
        self.assertGreater(found["shared_macs"], 0)
        self.assertEqual(found["shared_ips"], 4)

    def test_valid_synthetic_plan_is_still_not_deployable(self):
        s = validate_proposal(proposal())
        self.assertEqual(s["unique_vmnets"], 3)
        self.assertEqual(s["windows_guests"], 4)
        self.assertEqual(s["unique_macs"], 7)
        self.assertEqual(s["host_side_interfaces"], 2)
        self.assertEqual(s["zones"], list(ZONES))
        self.assertFalse(s["host_networks_surveyed"])
        self.assertFalse(s["deployment_authorized"])

    def test_existing_vmnet_rejected(self):
        self.reject(lambda p: p["zones"]["NORTH"].__setitem__("vmnet", "vmnet10"))

    def test_duplicate_vmnet_rejected(self):
        self.reject(lambda p: p["zones"]["NORTH"].__setitem__("vmnet", "vmnet42"))

    def test_default_nat_vmnet_rejected(self):
        self.reject(lambda p: p["zones"]["NORTH"].__setitem__("vmnet", "vmnet8"))

    def test_reference_subnet_rejected(self):
        self.reject(lambda p: p["zones"]["NORTH"].__setitem__("subnet", "10.4.10.0/24"))

    def test_duplicate_subnet_rejected(self):
        self.reject(lambda p: p["zones"]["MANAGEMENT"].__setitem__(
            "subnet", "10.41.10.0/24"))

    def test_non_24_subnet_rejected(self):
        self.reject(lambda p: p["zones"]["NORTH"].__setitem__("subnet", "10.41.10.0/25"))

    def test_duplicate_guest_mac_rejected(self):
        self.reject(lambda p: p["machines"]["GOAD-WS01"].__setitem__(
            "mac", "02:44:10:00:00:22"))

    def test_reference_guest_mac_rejected(self):
        self.reject(lambda p: p["machines"]["GOAD-WS01"].__setitem__(
            "mac", "00:50:56:20:10:31"))

    def test_router_mac_reuses_guest_rejected(self):
        self.reject(lambda p: p["router_macs"].__setitem__(
            "NORTH", "02:44:10:00:00:11"))

    def test_missing_attacker_host_address_rejected(self):
        self.reject(lambda p: p["host_addresses"].pop("NORTH"))

    def test_host_attacker_ip_collision_rejected(self):
        self.reject(lambda p: p["host_addresses"].__setitem__("NORTH", "10.41.10.31"))

    def test_host_management_address_wrong_subnet_rejected(self):
        self.reject(lambda p: p["host_addresses"].__setitem__("MANAGEMENT", "10.41.20.254"))

    def test_fifth_windows_guest_rejected(self):
        self.reject(lambda p: p["machines"].__setitem__(
            "GOAD-DC03", {"zone": "ESSOS_TRANSITION", "ip": "10.41.30.12",
                          "mac": "02:44:30:00:00:12"}))

    def test_reintroduced_essos_router_zone_rejected(self):
        self.reject(lambda p: p["zones"].__setitem__("ESSOS_TRANSITION", {
            "vmnet": "vmnet43", "subnet": "10.41.30.0/24", "gateway": "10.41.30.1"
        }))

    def test_guest_wrong_security_zone_rejected(self):
        self.reject(lambda p: p["machines"]["GOAD-DC01"].__setitem__("zone", "NORTH"))

    def test_guest_as_gateway_rejected(self):
        self.reject(lambda p: p["machines"]["GOAD-WS01"].__setitem__("ip", "10.41.10.1"))

    def test_guest_address_outside_subnet_rejected(self):
        self.reject(lambda p: p["machines"]["GOAD-WS01"].__setitem__(
            "ip", "10.41.20.31"))

    def test_duplicate_guest_address_rejected(self):
        self.reject(lambda p: p["machines"]["GOAD-WS01"].__setitem__(
            "ip", "10.41.10.22"))

    def test_invalid_active_status_rejected(self):
        self.reject(lambda p: p.__setitem__("state", "ACTIVE"))

    def test_ipv6_guest_address_rejected(self):
        self.reject(lambda p: p["machines"]["GOAD-WS01"].__setitem__("ip", "fd00::31"))

    def test_cli_proposal_only_returns_static_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposal.json"
            path.write_text(json.dumps(proposal()), encoding="utf-8")
            command = [sys.executable, "-m", "goad.course1_network_plan",
                       "--check-proposal", str(path)]
            proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('"deployment_authorized": false', proc.stdout)
            self.assertIn("[BLOCKED]", proc.stdout)

    def test_no_hypervisor_or_os_mutation(self):
        source = (ROOT / "goad/course1_network_plan.py").read_text(encoding="utf-8")
        for token in ("subprocess", "vmrun", "vagrant up",
                      "ansible-playbook", "os.system", "Path.write_text"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
