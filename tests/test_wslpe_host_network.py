"""WSLPE Linux/VMware host networking: pure read-only collision unit tests."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/wslpe-check-host-network.py"
SPEC = importlib.util.spec_from_file_location("wslpe_host_network", SOURCE)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


VMNET_CONFIG = """
answer VNET_1_HOSTONLY_NETMASK 255.255.255.0
answer VNET_1_HOSTONLY_SUBNET 172.16.195.0
answer VNET_8_NAT yes
answer VNET_8_HOSTONLY_SUBNET 192.168.213.0
answer VNET_8_HOSTONLY_NETMASK 255.255.255.0
answer VNET_10_HOSTONLY_SUBNET 10.4.10.0
answer VNET_10_HOSTONLY_NETMASK 255.255.255.0
answer VNET_99_HOSTONLY_SUBNET 10.4.99.0
answer VNET_99_HOSTONLY_NETMASK 255.255.255.0
"""
HOST_ADDRESSES = [
    {"ifname": "wlan0", "addr_info": [{"family": "inet", "local": "192.168.76.160", "prefixlen": 24}]},
    {"ifname": "vmnet8", "addr_info": [{"family": "inet", "local": "192.168.213.1", "prefixlen": 24}]},
    {"ifname": "vmnet10", "addr_info": [{"family": "inet", "local": "10.4.10.254", "prefixlen": 24}]},
]
HOST_ROUTES = [
    {"dst": "default", "gateway": "192.168.76.108", "dev": "wlan0"},
    {"dst": "192.168.76.0/24", "dev": "wlan0"},
    {"dst": "10.4.99.0/24", "dev": "vmnet99"},
]


class WslpeHostNetworkTests(unittest.TestCase):
    def test_candidate_is_private_explicit_24_and_not_north(self):
        self.assertEqual(str(CHECKER.parse_prefix("172.28.231")), "172.28.231.0/24")
        for prefix in ("10.4.10", "10.4.99", "8.8.8", "127.0.0", "169.254.2", "172.28", "999.1.2"):
            with self.subTest(prefix=prefix):
                with self.assertRaises(ValueError):
                    CHECKER.parse_prefix(prefix)

    def test_vmware_subnets_from_this_operator_are_discovered(self):
        parsed = dict(CHECKER.configured_vmnets(VMNET_CONFIG))
        self.assertEqual(str(parsed["vmnet8"]), "192.168.213.0/24")
        self.assertEqual(str(parsed["vmnet10"]), "10.4.10.0/24")

    def test_operator_candidate_has_no_visible_collision(self):
        evidence, collisions = CHECKER.assess(
            CHECKER.parse_prefix("172.28.231"),
            HOST_ADDRESSES, HOST_ROUTES, VMNET_CONFIG,
        )
        self.assertEqual(collisions, [])
        self.assertTrue(any("vmnet8" in line for line in evidence))

    def test_existing_vmnet8_range_fails_closed(self):
        _evidence, collisions = CHECKER.assess(
            CHECKER.parse_prefix("192.168.213"),
            HOST_ADDRESSES, HOST_ROUTES, VMNET_CONFIG,
        )
        self.assertTrue(any("vmnet8" in x for x in collisions))

    def test_broader_vpn_route_overlap_fails_even_when_no_interface_address(self):
        broad_route = [{"dst": "172.28.0.0/16", "table": "200", "dev": "tailscale0"}]
        _evidence, collisions = CHECKER.assess(
            CHECKER.parse_prefix("172.28.231"),
            [], broad_route, VMNET_CONFIG,
        )
        self.assertTrue(any("route table 200" in x for x in collisions))

    def test_vmnet_incomplete_metadata_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "netmask"):
            CHECKER.configured_vmnets("answer VNET_8_HOSTONLY_SUBNET 172.28.231.0\n")
        with self.assertRaisesRegex(ValueError, "No VMware"):
            CHECKER.configured_vmnets("answer VNET_8_NAT yes\n")

    def test_no_host_network_mutations_or_vagrant_actions_in_checker(self):
        source = SOURCE.read_text(encoding="utf-8")
        for banned in ("vagrant up", "vmrun -T ws start", "vmware-networks --stop",
                       "subprocess.Popen", "os.system", "sudo "):
            self.assertNotIn(banned, source)
        self.assertIn('run_ip("route", "show", "table", "all")', source)
        self.assertIn('run_ip("address", "show")', source)
        self.assertIn('VMWARE_CONFIG = Path("/etc/vmware/networking")', source)


if __name__ == "__main__":
    unittest.main()
