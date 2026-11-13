"""PURPLE-only source regressions for the Sliver DNS C2 provisioning path."""
from pathlib import Path
import unittest
import subprocess

ROOT = Path(__file__).resolve().parents[1]


class PurpleDnsC2SourceTests(unittest.TestCase):
    def test_fresh_purple_install_runs_dns_after_domain_creation(self):
        manifest = (ROOT / 'playbooks.yml').read_text()
        self.assertEqual(manifest.count('\nPURPLE:\n'), 1)
        profile = manifest.split('\nPURPLE:\n', 1)[1].split('\ndefault:\n', 1)[0]
        default = manifest.split('\ndefault:\n', 1)[1]
        read_playbooks = lambda s: [
            line.strip().removeprefix('- ')
            for line in s.splitlines() if line.startswith('  - ')
        ]
        purple = read_playbooks(profile)
        original = read_playbooks(default)
        self.assertEqual(purple.count('purple-dns-c2.yml'), 1)
        self.assertEqual([p for p in purple if p != 'purple-dns-c2.yml'], original)
        self.assertLess(purple.index('ad-members.yml'),
                        purple.index('purple-dns-c2.yml'))
        self.assertLess(purple.index('purple-dns-c2.yml'),
                        purple.index('ad-trusts.yml'))

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

    def test_first_run_does_not_look_up_a_missing_child_delegation(self):
        body = (ROOT / 'ansible/purple-dns-c2.yml').read_text()
        # WinDNS raises WIN32 9714 if queried directly for a missing child.
        self.assertNotIn("Get-DnsServerZoneDelegation -Name 'purple.lab' -ChildZoneName 'c2'", body)
        self.assertEqual(body.count("Get-DnsServerZoneDelegation -Name 'purple.lab' -ErrorAction Stop"), 2)
        self.assertEqual(body.count("([string]$_.ChildZoneName).TrimEnd('.').ToLowerInvariant() -eq 'c2.purple.lab'"), 2)
        self.assertIn('Add-DnsServerZoneDelegation', body)
        self.assertIn('PURPLE_DNS_DELEGATION_UNCHANGED=1', body)

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
