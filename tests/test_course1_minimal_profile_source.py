"""Course 1's reduced source must match original GOAD minus Essos only.

These checks are deliberately offline. Passing never authorizes a live
Vagrant/Ansible install while the shared provider is still six-host-only.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOAD = ROOT / "ad/GOAD"
NORTH = ROOT / "ad/NORTH"
HOSTS = {"dc01", "dc02", "srv02", "ws01"}
DOMAINS = {"sevenkingdoms.local", "north.sevenkingdoms.local"}
MACHINES = {"GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01", "GOAD-ROUTER"}


class Course1MinimalProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.goad = json.loads((GOAD / "data/config.json").read_text(encoding="utf-8"))["lab"]
        cls.north = json.loads((NORTH / "data/config.json").read_text(encoding="utf-8"))["lab"]

    def test_exact_reduced_machine_and_domain_set(self):
        self.assertEqual(set(self.north["hosts"]), HOSTS)
        self.assertEqual(set(self.north["domains"]), DOMAINS)
        self.assertEqual(len(self.goad["hosts"]), 6)
        self.assertIn("essos.local", self.goad["domains"])

    def test_retained_host_data_matches_original_except_essos_links(self):
        for key in HOSTS:
            with self.subTest(host=key):
                original = json.loads(json.dumps(self.goad["hosts"][key]))
                new = self.north["hosts"][key]
                if key == "dc01":
                    original["scripts"].remove("sidhistory.ps1")
                if key == "srv02":
                    del original["mssql"]["linked_servers"]["BRAAVOS"]
                self.assertEqual(new, original)

    def test_domain_content_retains_all_non_essos_features(self):
        for domain in DOMAINS:
            with self.subTest(domain=domain):
                expected = json.loads(json.dumps(self.goad["domains"][domain]))
                if domain == "sevenkingdoms.local":
                    del expected["trust"]
                    del expected["multi_domain_groups_member"]["AcrossTheNarrowSea"]
                    if not expected["multi_domain_groups_member"]:
                        del expected["multi_domain_groups_member"]
                self.assertEqual(self.north["domains"][domain], expected)

    def test_no_essos_remnants_in_minimal_profile_data(self):
        text = (NORTH / "data/config.json").read_text(encoding="utf-8")
        for token in ("essos.local", "BRAAVOS", "meereen", "daenerys.targaryen"):
            self.assertNotIn(token.lower(), text.lower())

    def test_ansible_inventory_contains_only_retained_nodes(self):
        inventory = (NORTH / "data/inventory").read_text(encoding="utf-8")
        self.assertIn("domain_name=NORTH", inventory)
        self.assertNotRegex(inventory, r"(?m)^\s*(dc03|srv03)\b")
        self.assertIn("[child_dc]", inventory)
        self.assertIn("[parent_dc]", inventory)
        self.assertIn("[workstation]", inventory)
        provider = (NORTH / "providers/vmware/inventory").read_text()
        for machine, address in (
            ("dc01", "10.4.20.10"),
            ("dc02", "10.4.10.11"),
            ("srv02", "10.4.10.22"),
            ("ws01", "10.4.10.31"),
        ):
            self.assertRegex(provider, rf"(?m)^{machine}\s+ansible_host={re.escape(address)}\b")
        self.assertNotRegex(provider, r"(?m)^(dc03|srv03)\s")
        post_vagrant = (NORTH / "data/inventory_disable_vagrant").read_text()
        self.assertNotRegex(post_vagrant, r"(?m)^(dc03|srv03)\s")
        self.assertIn("domain_name=NORTH", post_vagrant)

    def test_vagrant_definition_keeps_four_windows_and_router(self):
        source = (NORTH / "providers/vmware/Vagrantfile").read_text()
        roster = re.findall(r':name\s*=>\s*"([^"]+)"', source)
        self.assertEqual(set(roster), MACHINES)
        self.assertEqual(len(roster), len(MACHINES))
        self.assertNotIn("vmnet30", source)
        self.assertIn("vmnet10", source)
        self.assertIn("vmnet20", source)
        self.assertIn("vmnet99", source)
        self.assertIn("../../../ad/NORTH/providers/vmware/router/provision.sh", source)
        for item in ("GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"):
            self.assertIn(item, source)

    def test_router_removes_only_essos_segment_and_its_rules(self):
        router = NORTH / "providers/vmware/router"
        bootstrap = (router / "provision.sh").read_text()
        exercise = (router / "nftables/exercise.nft").read_text()
        provisioning = (router / "nftables/provisioning.nft").read_text()
        for text in (bootstrap, exercise, provisioning):
            self.assertNotIn("ESSOS", text.upper())
            self.assertNotIn("10.4.30.", text)
        self.assertIn('configure_lab_interface "NORTH"', bootstrap)
        self.assertIn('configure_lab_interface "SEVENKINGDOMS"', bootstrap)
        self.assertIn('configure_lab_interface "MANAGEMENT"', bootstrap)
        self.assertIn("policy drop;", exercise)
        self.assertIn("ip saddr 10.4.10.11 ip daddr 10.4.20.10", exercise)
        self.assertIn("ip saddr 10.4.20.10 ip daddr 10.4.10.11", exercise)
        self.assertIn("policy accept;", provisioning)

    def test_retained_power_shell_fixtures_are_sourced_from_goad(self):
        script_names = {
            name for host in self.north["hosts"].values()
            for name in host.get("scripts", [])
        }
        self.assertNotIn("sidhistory.ps1", script_names)
        for name in script_names:
            with self.subTest(name=name):
                self.assertTrue((GOAD / "scripts" / name).is_file())
        ansible = (ROOT / "ansible/vulnerabilities.yml").read_text()
        self.assertEqual(ansible.count("domain_name == 'NORTH'"), 2)
        self.assertIn("../ad/GOAD/scripts", ansible)

    def test_working_goad_baseline_is_not_replaced(self):
        vagrant = (GOAD / "providers/vmware/Vagrantfile").read_text()
        self.assertIn('GOAD-DC03', vagrant)
        self.assertIn('GOAD-SRV03', vagrant)
        self.assertIn('vmnet30', vagrant)


if __name__ == "__main__":
    unittest.main()
