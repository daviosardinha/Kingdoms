"""PURPLE-only source regressions for the Sliver DNS C2 provisioning path."""
from pathlib import Path
import unittest
import subprocess

ROOT = Path(__file__).resolve().parents[1]


class PurpleDnsC2SourceTests(unittest.TestCase):
    def test_playbook_is_scoped_after_ad(self):
        main = (ROOT / 'ansible/main.yml').read_text()
        self.assertIn('import_playbook: purple-dns-c2.yml', main)
        self.assertIn("when: domain_name == 'PURPLE'", main)
        self.assertLess(main.index('import_playbook: ad-members.yml'),
                        main.index('import_playbook: purple-dns-c2.yml'))

    def test_dns_changes_guard_ad_zone_and_existing_delegations(self):
        body = (ROOT / 'ansible/purple-dns-c2.yml').read_text()
        for marker in (
            'PURPLE-DC01', 'IsDsIntegrated', 'purple.lab',
            'purple-c2', '172.28.233.60', 'purple-lx01',
            '172.28.233.32', "-ChildZoneName 'c2'",
            'Get-DnsServerZoneDelegation', 'Add-DnsServerZoneDelegation',
            'Get-DnsServerResourceRecord', 'Add-DnsServerResourceRecordA',
            'Refusing overwrite', 'PURPLE_DNS_C2_PROVISIONED=1',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, body)
        for dangerous in ('Remove-DnsServer', 'Set-DnsServerForwarder',
                          'Add-DnsServerConditionalForwarderZone'):
            self.assertNotIn(dangerous, body)

    def test_existing_lab_has_guarded_source_owned_apply_command(self):
        deploy = (ROOT / 'scripts/purple-dns-c2-apply.sh').read_text()
        for marker in (
            '--instance-dir', '--apply', 'purple-dns-c2.yml',
            '--limit dc01', 'ansible-playbook',
            'vagrant upload', 'vagrant ssh PURPLE-LX01',
            'resolvectl query purple-c2.purple.lab',
            'dig +time=3 +tries=1',
        ):
            self.assertIn(marker, deploy)
        self.assertNotIn('goad.sh -t install', deploy)
        self.assertNotIn('vagrant up ', deploy)
        self.assertNotIn('vagrant destroy', deploy)
        subprocess.run(['bash', '-n', str(ROOT / 'scripts/purple-dns-c2-apply.sh')], check=True)

    def test_lx01_split_dns_without_joining_ad(self):
        script = (ROOT / 'ad/PURPLE/providers/vmware/configure-linux-interface.sh').read_text()
        for marker in (
            '172.28.233.32',
            'resolvectl dns "$interface" 172.28.233.30',
            'resolvectl domain "$interface" "~purple.lab"',
            'resolvectl default-route "$interface" false',
        ):
            self.assertIn(marker, script)
        inventory = (ROOT / 'ad/PURPLE/data/inventory').read_text()
        domain = inventory.split('[domain]', 1)[1].split('[', 1)[0]
        self.assertNotIn('lx01', domain)


if __name__ == '__main__':
    unittest.main()
