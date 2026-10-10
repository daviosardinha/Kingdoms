"""NORTH AD promotion must not discover the identically named reference forest."""
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "ansible/roles/child_domain/tasks/main.yml"
GUARD = ROOT / "ansible/roles/child_domain/tasks/north_dns_containment.yml"
PROMOTION = ROOT / "ansible/roles/child_domain/tasks/north_promotion.yml"
REFERENCE_DC = "10.4.10.11"
NORTH_PARENT = "10.41.20.10"
NORTH_CHILD = "10.41.10.11"


class NorthChildDnsContainmentTests(unittest.TestCase):
    @staticmethod
    def load(path):
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_north_guard_runs_before_any_child_promotion(self):
        tasks = self.load(ROLE)
        names = [task["name"] for task in tasks]
        guard = next(i for i, x in enumerate(tasks)
                     if x.get("ansible.builtin.include_tasks") == "north_dns_containment.yml")
        legacy = names.index("add child domain to parent domain")
        north = next(i for i, x in enumerate(tasks)
                     if x.get("ansible.builtin.include_tasks") == "north_promotion.yml")
        self.assertLess(guard, legacy)
        self.assertLess(guard, north)
        self.assertEqual(tasks[guard]["when"], "domain_name | default('') == 'NORTH'")
        self.assertEqual(tasks[north]["when"], "domain_name | default('') == 'NORTH'")
        self.assertEqual(tasks[legacy]["when"], "domain_name | default('') != 'NORTH'")

    def test_goa_d_legacy_promotion_is_unchanged_and_gated_out_of_north(self):
        tasks = self.load(ROLE)
        legacy = next(t for t in tasks if t["name"] == "add child domain to parent domain")
        self.assertIn("-SkipPreChecks", legacy["ansible.windows.win_powershell"]["script"])
        self.assertEqual(legacy["when"], "domain_name | default('') != 'NORTH'")
        self.assertEqual(next(t for t in tasks
                              if t["name"].startswith("Reboot legacy GOAD"))["when"][0],
                         "domain_name | default('') != 'NORTH'")

    def test_north_nat_dns_pinned_to_selected_parent_ip(self):
        tasks = self.load(GUARD)
        dns = tasks[0]["ansible.windows.win_dns_client"]
        self.assertEqual(dns["adapter_names"], "{{ nat_adapter }}")
        self.assertEqual(dns["ipv4_addresses"], ["{{ hostvars[dns_domain].ansible_host }}"])
        self.assertEqual(tasks[0]["when"], "two_adapters | bool")
        self.assertNotIn(REFERENCE_DC, GUARD.read_text())

    def test_locator_proof_is_fail_closed_before_promotion(self):
        tasks = self.load(GUARD)
        script = tasks[1]["ansible.windows.win_powershell"]["script"]
        self.assertIn("nltest.exe", script)
        self.assertIn("/force", script)
        self.assertIn("parentAddresses[0] -ne $ParentDns", script)
        self.assertIn("childAddresses[0] -ne $ChildDcIp", script)
        self.assertIn("NORTH_DNS_CONTAINMENT_OK", script)
        self.assertIn("Clear-DnsClientCache", script)
        self.assertIn("natServers[0] -ne $ParentDns", script)
        self.assertIn("ChildDcIp, '127.0.0.1'", script)
        self.assertIn("NORTH DNS containment: unexpected NAT", script)
        self.assertEqual(tasks[1]["changed_when"], False)
        self.assertEqual(tasks[1]["ansible.windows.win_powershell"]["parameters"]["ParentDns"],
                         "{{ hostvars[dns_domain].ansible_host }}")

    def test_north_promotion_uses_local_machine_state_not_foreign_directory(self):
        tasks = self.load(PROMOTION)
        promotion = tasks[0]["ansible.windows.win_powershell"]["script"]
        self.assertIn("Get-CimInstance Win32_ComputerSystem", promotion)
        self.assertIn("DomainRole", promotion)
        self.assertIn("Install-ADDSDomain @promotion", promotion)
        self.assertIn("ErrorAction = 'Stop'", promotion)
        self.assertNotIn("SkipPreChecks", promotion.split("$promotion = @{")[1])
        self.assertNotIn("Get-ADDomain -Identity", promotion)
        self.assertLess(promotion.index("Install-ADDSDomain @promotion"),
                        promotion.index("$Ansible.Changed = $true"))

    def test_north_checks_local_dc_after_reboot_before_dns_zone(self):
        tasks = self.load(PROMOTION)
        self.assertEqual(tasks[1]["when"], "north_child_result.changed")
        self.assertEqual(tasks[2]["ansible.windows.win_service"]["name"], "ADWS")
        self.assertEqual(tasks[2]["ansible.windows.win_service"]["state"], "started")
        proof = tasks[3]["ansible.windows.win_powershell"]["script"]
        self.assertIn("DomainRole -ne 5", proof)
        self.assertIn("Get-ADDomain -Current LocalComputer", proof)
        self.assertIn("NORTH_CHILD_DC_PROMOTION_VERIFIED", proof)
        self.assertGreaterEqual(tasks[3]["retries"], 2)

    def test_cross_instance_reference_and_north_addresses_remain_distinct(self):
        import json
        lab = json.loads((ROOT / "ad/NORTH/data/config.json").read_text())["lab"]
        inventory = (ROOT / "ad/NORTH/providers/vmware/inventory").read_text()
        self.assertEqual(lab["hosts"]["dc02"]["domain"], "north.sevenkingdoms.local")
        self.assertIn(NORTH_PARENT, inventory)
        self.assertIn(NORTH_CHILD, inventory)
        self.assertNotIn(REFERENCE_DC, inventory)


if __name__ == "__main__":
    unittest.main()
