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

    def test_no_stale_minilab_domain_references(self):
        for path in (
            PURPLE / "data" / "inventory_disable_vagrant",
            PURPLE / "files" / "bot.ps1",
        ):
            self.assertNotIn("mini.lab", path.read_text())

    def test_pinned_cached_windows_boxes(self):
        vm = (PURPLE / "providers" / "vmware" / "Vagrantfile").read_text()
        for ref in (
            '"StefanScherer/windows_2019"',
            '"mayfly/windows10"',
            '"bento/debian-12"',
            '"bento/ubuntu-22.04"',
        ):
            self.assertIn(ref, vm)

    def test_explicit_isolated_lab_nics(self):
        vm = (PURPLE / "providers" / "vmware" / "Vagrantfile").read_text()
        self.assertEqual(vm.count(':skip_private_network => true'), 4)
        self.assertEqual(vm.count(':vnet => "vmnet40"'), 4)
        self.assertEqual(vm.count(':slot => 1'), 4)
        self.assertIn('192.168.240', vm)
        for last in ("30", "31", "32", "51"):
            self.assertIn("00:50:56:10:40:" + last, vm)
        self.assertEqual(vm.count(':lab_linux_config_script =>'), 2)
        self.assertNotIn(":lab_gateway =>", vm)

    def test_linux_static_nic_and_preflight_gate(self):
        script = (PURPLE / "providers" / "vmware" / "configure-linux-interface.sh").read_text()
        self.assertIn('ip -4 address replace', script)
        self.assertIn('purple-lab-interface.service', script)
        self.assertIn('/sys/class/net/', script)
        gate = (ROOT / "scripts" / "purple-vmware-preflight.sh").read_text()
        self.assertIn('VNET_40_', gate)
        self.assertIn('192.168.240.0/24', gate)
        self.assertIn('NAT no', gate)
        self.assertIn('DHCP no', gate)

    def test_monitoring_is_next_phase(self):
        vm = (PURPLE / "providers" / "vmware" / "Vagrantfile").read_text()
        self.assertEqual(vm.count('"PURPLE-WAZUH"'), 1)
        self.assertNotIn("wazuh-install.sh", vm)


if __name__ == "__main__":
    unittest.main()
