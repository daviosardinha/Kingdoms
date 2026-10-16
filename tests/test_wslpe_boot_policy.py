"""WSLPE-only live-port boot candidate checks; no host writes."""
import unittest
from kingdoms.wslpe_boot_policy import (
    make_boot_candidate, boot_protection_readiness,
)

class WslpeBootPolicyTests(unittest.TestCase):
    def test_live_discovered_port_is_used_not_hardcoded(self):
        for port in (2210, 2299, 59859):
            with self.subTest(port=port):
                p = make_boot_candidate(
                    port, "vmnet2", "172.28.231.0/24",
                    "172.28.231.1", "172.28.231.31")
                self.assertIn(f"tcp dport {port} drop", p.nft_source)
                self.assertIn('iifname "vmnet2"', p.nft_source)
                self.assertIn("add table inet kingdoms_wslpe_winrm", p.nft_source)
                self.assertIn("add table inet kingdoms_wslpe_exercise", p.nft_source)
                self.assertFalse(p.boot_install_authorized)

    def test_invalid_ports_and_other_vmnets_fail_closed(self):
        for port in (0, 80, 65536, "2210", None):
            with self.subTest(port=port), self.assertRaises(ValueError):
                make_boot_candidate(port, "vmnet2", "172.28.231.0/24",
                                    "172.28.231.1", "172.28.231.31")
        with self.assertRaises(ValueError):
            make_boot_candidate(2210, "vmnet10", "172.28.231.0/24",
                                "172.28.231.1", "172.28.231.31")

    def test_boot_release_blocks_live_port_drift_and_unproven_order(self):
        result = boot_protection_readiness(
            discovered_port=2299, guarded_port=2210, guard_persists=False,
            filter_persists=False, vmware_start_is_ordered=False)
        self.assertEqual(len(result), 4)
        self.assertFalse(boot_protection_readiness(
            discovered_port=2299, guarded_port=2299, guard_persists=True,
            filter_persists=True, vmware_start_is_ordered=True))

    def test_policy_does_not_change_global_firewall_or_nat(self):
        p = make_boot_candidate(
            2210, "vmnet2", "172.28.231.0/24",
            "172.28.231.1", "172.28.231.31")
        for token in ("flush ruleset", "masquerade", "delete table",
                      "vmnet10", "vmnet8", "10.4.10.11", "iptables"):
            self.assertNotIn(token, p.nft_source)

if __name__ == "__main__":
    unittest.main()
