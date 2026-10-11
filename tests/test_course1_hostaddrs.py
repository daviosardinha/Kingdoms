"""NORTH-only VMware host address assets, never touching host/systemd."""
import subprocess
import unittest
from pathlib import Path

from goad.course1_hostaddrs import (
    HELPER, SERVICE, TIMER, hostaddr_plan, repair_decisions,
    render_hostaddr_assets,
)
from goad.kingdoms_topology import load_course1_topology


class Course1HostAddressTests(unittest.TestCase):
    def setUp(self):
        self.layout = load_course1_topology()
        self.plan = hostaddr_plan(self.layout)
        self.assets = render_hostaddr_assets(self.layout)

    def test_default_owned_two_adapters_parent_is_protected(self):
        self.assertEqual(self.plan["protected"], "vmnet20")
        self.assertEqual(self.plan["interfaces"]["vmnet10"]["desired"], "10.4.10.254/24")
        self.assertEqual(self.plan["interfaces"]["vmnet99"]["desired"], "10.4.99.254/24")
        self.assertEqual(self.plan["interfaces"]["vmnet10"]["vmware_default"], "10.4.10.1/24")
        self.assertEqual(set(self.plan["interfaces"]), {"vmnet10", "vmnet99"})

    def test_safely_replaces_only_vmware_known_one_addresses(self):
        actions = repair_decisions(self.layout, {
            "vmnet10": ["10.4.10.1/24"],
            "vmnet99": ["10.4.99.1/24"],
        })
        self.assertEqual(len(actions), 4)
        self.assertIn(("ip", "-4", "addr", "del", "10.4.10.1/24", "dev", "vmnet10"), actions)
        self.assertIn(("ip", "-4", "addr", "add", "10.4.10.254/24", "dev", "vmnet10"), actions)
        self.assertTrue(all("vmnet20" not in action for action in actions))

    def test_all_valid_addresses_are_noop(self):
        self.assertEqual(repair_decisions(self.layout, {
            "vmnet10": ["10.4.10.254/24"],
            "vmnet99": ["10.4.99.254/24"],
        }), ())

    def test_unsafe_foreign_address_refuses_all_mutations(self):
        with self.assertRaisesRegex(ValueError, "Unowned IPv4"):
            repair_decisions(self.layout, {
                "vmnet10": ["10.4.10.1/24"],
                "vmnet99": ["192.168.99.22/24"],
            })

    def test_exposed_parent_interface_refuses_repair(self):
        with self.assertRaisesRegex(ValueError, "Missing or unexpected"):
            repair_decisions(self.layout, {
                "vmnet10": [],
                "vmnet20": [],
                "vmnet99": [],
            })

    def test_missing_and_duplicate_ipv4_data_are_rejected(self):
        with self.assertRaises(ValueError):
            repair_decisions(self.layout, {"vmnet10": []})
        with self.assertRaisesRegex(ValueError, "duplicated"):
            repair_decisions(self.layout, {
                "vmnet10": ["10.4.10.254/24", "10.4.10.254/24"],
                "vmnet99": [],
            })

    def test_alternate_ten_five_names_and_addresses_are_derived(self):
        other = load_course1_topology(
            "10.5.0.0/16", {"north": 11, "sevenkingdoms": 21, "management": 98}
        )
        plan = hostaddr_plan(other)
        self.assertEqual(plan["protected"], "vmnet21")
        self.assertEqual(plan["interfaces"]["vmnet11"]["desired"], "10.5.10.254/24")
        self.assertEqual(plan["interfaces"]["vmnet98"]["vmware_default"], "10.5.99.1/24")
        script = render_hostaddr_assets(other)["helper"]
        self.assertIn("validate_iface vmnet11 10.5.10.254/24 10.5.10.1/24", script)
        self.assertIn("ip link show dev vmnet21", script)

    def test_shell_helper_validates_everything_before_mutating(self):
        script = self.assets["helper"]
        self.assertIn("validate_iface vmnet10", script)
        self.assertIn("validate_iface vmnet99", script)
        self.assertIn("repair_iface vmnet10", script)
        self.assertIn("repair_iface vmnet99", script)
        self.assertLess(script.index("validate_iface vmnet99"), script.index("repair_iface vmnet10"))
        self.assertLess(script.index("Protected parent adapter exposed"), script.index("repair_iface vmnet10"))
        self.assertNotIn("ip addr flush", script.replace("# Kingdoms NORTH: no ip addr flush;", ""))
        self.assertNotIn("vmnet30", script)

    def test_bash_script_lints_without_execution(self):
        response = subprocess.run(["bash", "-n"], input=self.assets["helper"],
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(response.returncode, 0, response.stderr)

    def test_distinct_service_timer_names_and_same_kingdoms_cadence(self):
        self.assertEqual(set(self.assets), {"helper", "service", "timer"})
        self.assertIn(f"ExecStart={HELPER}", self.assets["service"])
        self.assertIn(f"Unit={SERVICE}", self.assets["timer"])
        self.assertIn("OnUnitInactiveSec=15s", self.assets["timer"])
        self.assertTrue(TIMER.startswith("kingdoms-north"))
        for source in self.assets.values():
            self.assertNotIn("goad-nomad-vmnet-hostaddrs", source)

    def test_no_install_or_systemd_actions_in_asset_renderer(self):
        code = (Path(__file__).resolve().parents[1] /
                "goad/course1_hostaddrs.py").read_text()
        for phrase in ("subprocess.run(", "systemctl start", ".write_text(", "sudo ",
                       "os.replace(", "ip -4 addr flush dev"):
            self.assertNotIn(phrase, code)


if __name__ == "__main__":
    unittest.main()
