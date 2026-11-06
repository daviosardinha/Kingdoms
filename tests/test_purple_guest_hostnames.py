"""Fresh PURPLE guest hostnames are exact, scoped and assigned pre-domain.

Source-only checks: don't power guests on or retroactively rename installed
VMs. Windows names flow through Ansible; Linux names through Vagrant.
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "ad/PURPLE"
VM = LAB / "providers/vmware/Vagrantfile"
CONFIG = LAB / "data/config.json"
TEMPLATE = ROOT / "template/provider/vmware/Vagrantfile"
MANIFEST = ROOT / "playbooks.yml"

NAMES = {
    "PURPLE-DC01": "172.28.233.30",
    "PURPLE-WS01": "172.28.233.31",
    "PURPLE-LX01": "172.28.233.32",
    "PURPLE-WAZUH": "172.28.233.51",
    "PURPLE-C2": "172.28.233.60",
}
LINUX = ("PURPLE-LX01", "PURPLE-WAZUH", "PURPLE-C2")


class PurpleGuestHostnamesTests(unittest.TestCase):
    def test_exact_five_registered_vm_names_and_ips_preserved(self):
        data = VM.read_text()
        found = re.findall(r':name => "(PURPLE-[A-Z0-9]+)"', data)
        self.assertEqual(found, list(NAMES))
        for machine, ip in NAMES.items():
            suffix = ip.rsplit(".", 1)[1]
            head = data.split(f':name => "{machine}"', 1)[1].split(":box =>", 1)[0]
            self.assertIn(f':ip => "{{{{ip_range}}}}.{suffix}"', head)
        self.assertIn('"vmnet4"', data)
        self.assertNotIn("PURPLE-C2", (ROOT / "ad/NORTH/data/config.json").read_text())

    def test_linux_hostnames_are_explicit_vagrant_guest_properties(self):
        data = VM.read_text()
        for machine in LINUX:
            header = data.split(f':name => "{machine}"', 1)[1].split(":box =>", 1)[0]
            self.assertEqual(header.count(f':hostname => "{machine}"'), 1)
        template = TEMPLATE.read_text()
        self.assertIn('target.vm.hostname = box[:hostname] if box.has_key?(:hostname)', template)
        # Windows computer rename stays inside Ansible: Vagrant must not
        # introduce an early WinRM-dependent hostname/reboot before recovery.
        for machine in ("PURPLE-DC01", "PURPLE-WS01"):
            header = data.split(f':name => "{machine}"', 1)[1].split(":box =>", 1)[0]
            self.assertNotIn(":hostname =>", header)

    def test_windows_names_are_source_owned_and_set_before_ad(self):
        config = json.loads(CONFIG.read_text())
        hosts = config["lab"]["hosts"]
        self.assertEqual(set(hosts), {"dc01", "ws01"})
        self.assertEqual(hosts["dc01"]["hostname"], "PURPLE-DC01")
        self.assertEqual(hosts["ws01"]["hostname"], "PURPLE-WS01")
        self.assertEqual(hosts["dc01"]["type"], "dc")
        self.assertEqual(hosts["ws01"]["type"], "workstation")
        self.assertEqual(hosts["dc01"]["domain"], "purple.lab")
        self.assertEqual(hosts["ws01"]["domain"], "purple.lab")
        self.assertIn("purple.lab", config["lab"]["domains"])

        ad_servers = (ROOT / "ansible/ad-servers.yml").read_text()
        role = (ROOT / "ansible/roles/settings/hostname/tasks/main.yml").read_text()
        self.assertIn("role: 'settings/hostname'", ad_servers)
        self.assertIn('hostname: "{{lab.hosts[dict_key].hostname}}"', ad_servers)
        self.assertIn("win_hostname:", role)
        self.assertIn('name: "{{hostname}}"', role)
        self.assertIn("when: win_hostname.reboot_required", role)

        playbooks = MANIFEST.read_text()
        # PURPLE uses the existing default Ansible manifest, unchanged.
        default = playbooks.split("\ndefault:", 1)[1]
        self.assertLess(default.index("  - ad-servers.yml"),
                        default.index("  - ad-parent_domain.yml"))
        self.assertLess(default.index("  - ad-servers.yml"),
                        default.index("  - ad-members.yml"))

    def test_no_existing_vm_or_security_installation_side_effects(self):
        vm = VM.read_text()
        self.assertEqual(vm.count(":hostname =>"), 3)
        self.assertEqual(vm.count("provision-sliver-trainee.sh"), 1)
        self.assertEqual(vm.count("provision-wazuh-all-in-one.sh"), 1)
        c2 = vm.split(':name => "PURPLE-C2"', 1)[1]
        self.assertNotIn(":provision_scripts", c2)
        self.assertIn("configure-linux-interface.sh", c2)
        self.assertEqual(vm.count(':skip_private_network => true'), 3)
        self.assertEqual(vm.count(':vnet => "vmnet4"'), 3)


if __name__ == "__main__":
    unittest.main()
