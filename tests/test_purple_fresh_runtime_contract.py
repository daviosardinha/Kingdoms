"""Fresh PURPLE VM names and DNS/trust settings are replayable and scoped.

This uses source/awk fixtures only. It does not connect to or modify VMs.
"""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "ad/PURPLE"
LINUX = LAB / "providers/vmware/configure-linux-interface.sh"
VAGRANT = LAB / "providers/vmware/Vagrantfile"
AD_HOSTS = LAB / "data/config.json"


class PurpleFreshRuntimeContractTests(unittest.TestCase):
    def test_guest_hostname_comes_from_fresh_vagrant_and_linux_bootstrap(self):
        source = LINUX.read_text()
        vm = VAGRANT.read_text()
        self.assertEqual(vm.count(":lab_linux_config_script =>"), 3)
        self.assertIn('target.vm.hostname = box[:hostname]',
                      (ROOT / "template/provider/vmware/Vagrantfile").read_text())
        for ip, name in (
            ("172.28.233.32", "purple-lx01"),
            ("172.28.233.51", "purple-wazuh"),
            ("172.28.233.60", "purple-c2"),
        ):
            self.assertIn(f'{ip}) guest_hostname="{name}" ;;', source)
            machine = name.upper()
            block = vm.split(f':name => "{machine}"', 1)[1].split(":box =>", 1)[0]
            self.assertIn(f':hostname => "{machine}"', block)
        self.assertIn('hostnamectl set-hostname "$guest_hostname"', source)
        self.assertIn('hostnamectl --static', source)
        self.assertIn('$(hostname)', source)
        self.assertIn("127.0.1.1", source)
        self.assertIn("getent hosts", source)
        self.assertIn("preserve_hostname: true", source)
        self.assertIn('99-purple-guest-hostname.cfg', source)
        self.assertIn('PURPLE_BOOT_SERVICE:-0', source)
        self.assertLess(source.index('PURPLE_LINUX_HOSTNAME_READY'),
                        source.index('# Preserve lab NIC configuration'))
        self.assertNotIn("apt-get", source)
        self.assertNotIn("systemctl restart networking", source)

    def test_hosts_file_rewrite_deduplicates_without_erasing_other_names(self):
        # Run the exact /etc/hosts awk program against a disposable fixture,
        # not against an actual Linux host.
        shell = LINUX.read_text()
        pattern = re.compile(
            r'awk -v name="\$guest_hostname" \'(?P<program>.*?)\' /etc/hosts > "\$hosts_candidate"',
            re.S,
        )
        m = pattern.search(shell)
        self.assertIsNotNone(m, "Linux local-hostname rewrite missing")
        with tempfile.TemporaryDirectory() as td:
            sample = Path(td) / "hosts"
            sample.write_text(
                "127.0.0.1 localhost\n"
                "127.0.1.1 old-box old-alias\n"
                "172.28.233.30 purple-dc01.purple.lab\n"
                "127.0.1.1 duplicate-old-box\n"
                "::1 localhost ip6-localhost\n"
            )
            cmd = ["awk", "-v", "name=purple-wazuh", m["program"], str(sample)]
            one = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
            sample.write_text(one)
            two = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
            self.assertEqual(one, two)
            self.assertEqual(one.count("127.0.1.1"), 1)
            self.assertIn("127.0.1.1\tpurple-wazuh", one)
            self.assertIn("172.28.233.30 purple-dc01.purple.lab", one)
            self.assertIn("127.0.0.1 localhost", one)
            self.assertIn("::1 localhost ip6-localhost", one)
            self.assertNotIn("old-box", one)

    def test_existing_windows_hostname_and_dns_roles_apply_before_ad(self):
        config = json.loads(AD_HOSTS.read_text())
        self.assertEqual(config["lab"]["hosts"]["dc01"]["hostname"], "PURPLE-DC01")
        self.assertEqual(config["lab"]["hosts"]["ws01"]["hostname"], "PURPLE-WS01")
        self.assertEqual(config["lab"]["hosts"]["dc01"]["domain"], "purple.lab")
        self.assertEqual(config["lab"]["hosts"]["ws01"]["domain"], "purple.lab")

        playbooks = (ROOT / "playbooks.yml").read_text().split("\ndefault:", 1)[1]
        self.assertLess(playbooks.index("  - ad-servers.yml"),
                        playbooks.index("  - ad-parent_domain.yml"))
        self.assertLess(playbooks.index("  - ad-servers.yml"),
                        playbooks.index("  - ad-members.yml"))

        prepare = (ROOT / "ansible/ad-servers.yml").read_text()
        self.assertIn("role: 'settings/hostname'", prepare)
        self.assertIn('hostname: "{{lab.hosts[dict_key].hostname}}"', prepare)
        self.assertIn("win_hostname", (ROOT / "ansible/roles/settings/hostname/tasks/main.yml").read_text())

        dc = (ROOT / "ansible/roles/domain_controller/tasks/main.yml").read_text()
        self.assertIn('Set-DNSClient -RegisterThisConnectionsAddress $False', dc)
        self.assertIn('dnscmd . /resetlistenaddresses {{ hostvars[dict_key].ansible_host }}', dc)
        self.assertIn("when: two_adapters", dc)
        wk = (ROOT / "ansible/roles/commonwkstn/tasks/main.yml").read_text()
        self.assertIn("win_dns_client:", wk)
        self.assertIn("win_domain_membership:", wk)
        self.assertIn("when: domain_state.reboot_required", wk)
        self.assertIn("172.28.233", VAGRANT.read_text())

    def test_no_new_windows_rename_or_dns_mutation_on_installed_vm(self):
        script = LINUX.read_text()
        self.assertNotIn("netdom ", script)
        self.assertNotIn("PublishAddresses", script)
        self.assertNotIn("RegisterDnsARecords", script)
        self.assertNotIn("Remove-DnsServerResourceRecord", script)
        self.assertNotIn("/etc/vmware/networking", script)
        self.assertNotIn("vmrun", script)
        self.assertEqual(VAGRANT.read_text().count(":skip_private_network => true"), 3)


if __name__ == "__main__":
    unittest.main()
