"""Source-only Purple Team four-VM baseline regression checks."""
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PURPLE = ROOT / "ad" / "PURPLE"


class PurpleLabSourceTests(unittest.TestCase):
    def test_ad_is_independent(self):
        config = json.loads((PURPLE / "data" / "config.json").read_text())
        self.assertEqual(set(config["lab"]["hosts"]).intersection({"dc01", "ws01"}), {"dc01", "ws01"})
        self.assertIn("purple.lab", config["lab"]["domains"])
        self.assertEqual(config["lab"]["hosts"]["ws01"]["domain"], "purple.lab")

    def test_four_vm_definitions(self):
        vm = (PURPLE / "providers" / "vmware" / "Vagrantfile").read_text()
        for name in ("PURPLE-DC01", "PURPLE-WS01", "PURPLE-LX01", "PURPLE-WAZUH"):
            self.assertEqual(vm.count(':name => "' + name + '"'), 1)
        self.assertIn("bento/debian-12", vm)
        self.assertIn("bento/ubuntu-22.04", vm)
        self.assertIn("provision-ubuntu-desktop.sh", vm)

    def test_windows_only_ad_provisioning(self):
        inventory = (PURPLE / "data" / "inventory").read_text()
        domain_part = inventory.split("[domain]", 1)[1].split("[", 1)[0]
        self.assertIn("dc01", domain_part)
        self.assertIn("ws01", domain_part)
        self.assertNotIn("lx01", domain_part)
        self.assertNotIn("wazuh", domain_part)
        self.assertIn("domain_name=PURPLE", inventory)

    def test_monitoring_is_next_phase(self):
        vm = (PURPLE / "providers" / "vmware" / "Vagrantfile").read_text()
        self.assertEqual(vm.count('"PURPLE-WAZUH"'), 1)
        self.assertNotIn("wazuh-install.sh", vm)


if __name__ == "__main__":
    unittest.main()
