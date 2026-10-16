"""WSLPE-only host nft policy renderer. No network or VM access."""
from pathlib import Path
import unittest
from kingdoms.wslpe_isolation_policy import (
    TABLE, INPUT_CHAIN, FORWARD_CHAIN, exact_rollback,
    render_host_filter, validate_boundary,
)

ROOT = Path(__file__).resolve().parents[1]


class WslpeHostPolicyTests(unittest.TestCase):
    def test_dedicated_vmnet_only(self):
        validate_boundary("vmnet2", "172.28.231.0/24",
                          "172.28.231.1", "172.28.231.31")
        for vmnet in ("vmnet1", "vmnet8", "vmnet10", "vmnet20", "vmnet30",
                      "vmnet99", "", "vmnet2; flush ruleset", "lo", "vmnetX"):
            with self.subTest(vmnet=vmnet), self.assertRaises(ValueError):
                validate_boundary(vmnet, "172.28.231.0/24",
                                  "172.28.231.1", "172.28.231.31")

    def test_foreign_ambiguous_ip_ranges_are_blocked(self):
        cases = (
            ("10.4.10.0/24", "10.4.10.1", "10.4.10.31"),
            ("172.28.231.0/16", "172.28.231.1", "172.28.231.31"),
            ("172.28.231.0/24", "10.4.10.1", "172.28.231.31"),
            ("172.28.231.0/24", "172.28.231.31", "172.28.231.31"),
            ("172.28.231.0/24", "172.28.231.1", "172.28.231.33"),
            ("172.28.231.0/24", "172.28.231.1", "172.28.231.255"),
            ("172.28.231.0/24", "172.28.231.0", "172.28.231.31"),
        )
        for subnet, host, guest in cases:
            with self.subTest(subnet=subnet, host=host, guest=guest):
                with self.assertRaises(ValueError):
                    validate_boundary("vmnet2", subnet, host, guest)

    def test_nft_candidate_scoped_to_one_table_and_vmnet(self):
        data = render_host_filter("vmnet2", "172.28.231.0/24",
                                  "172.28.231.1", "172.28.231.31")
        self.assertEqual(data.count("add table inet"), 1)
        self.assertEqual(data.count("add chain inet"), 2)
        self.assertEqual(data.count("add rule inet"), 4)
        self.assertIn(f"add table inet {TABLE}", data)
        self.assertIn("hook input priority -75", data)
        self.assertIn("hook forward priority -75", data)
        self.assertIn('iifname "vmnet2" ct state established,related accept', data)
        self.assertIn('iifname "vmnet2" drop', data)
        self.assertIn('oifname "vmnet2" drop', data)
        for forbidden in ("vmnet10", "vmnet20", "vmnet99", "flush ruleset",
                          "delete table", "masquerade", "set policy drop"):
            self.assertNotIn(forbidden, data)
        self.assertIn(INPUT_CHAIN, data)
        self.assertIn(FORWARD_CHAIN, data)

    def test_exact_table_only_rollback(self):
        self.assertEqual(exact_rollback(),
                         f"delete table inet {TABLE}\n")

    def test_plan_tool_never_mutates(self):
        source = (ROOT / "scripts/wslpe-p1c-isolation-plan.py").read_text()
        for required in ("stage2.find_instance(", "stage2.locate_registered_vm(",
                         "running_registered(vmx, state)",
                         "topology.validated_exercise_vnet(",
                         "CANDIDATE ONLY", "RELEASE BLOCKED"):
            self.assertIn(required, source)
        for forbidden in ("subprocess.Popen(", "nft -f", "iptables -A",
                          "vmrun start", "vmrun stop", "vagrant up",
                          "Restart-Computer"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
