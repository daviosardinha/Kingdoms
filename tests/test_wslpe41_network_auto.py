"""Source-only network selection; never touches host VMware configuration."""
import unittest
from kingdoms import wslpe41_network_auto as network

VMWARE = """answer VNET_2_HOSTONLY_SUBNET 172.28.231.0
answer VNET_2_HOSTONLY_NETMASK 255.255.255.0
answer VNET_10_HOSTONLY_SUBNET 10.4.10.0
answer VNET_10_HOSTONLY_NETMASK 255.255.255.0
answer VNET_99_HOSTONLY_SUBNET 10.4.99.0
answer VNET_99_HOSTONLY_NETMASK 255.255.255.0
"""


class NetworkAutoTests(unittest.TestCase):
    def test_first_available_prefix_is_deterministic(self):
        self.assertEqual(network.select_available_prefix([], [], VMWARE, []), "172.28.220")

    def test_live_vpn_and_stopped_native_instance_are_reserved(self):
        interfaces = [{"ifname": "tun0", "addr_info": [
            {"family": "inet", "local": "172.28.220.254", "prefixlen": 24}]}]
        routes = [{"dst": "172.28.221.0/24", "dev": "tun0"}]
        selected = network.select_available_prefix(
            interfaces, routes, VMWARE, ["172.28.222"])
        self.assertEqual(selected, "172.28.223")

    def test_existing_vmware_subnet_is_not_reused(self):
        chosen = network.select_available_prefix(
            [], [], VMWARE, [], candidates=("172.28.231", "172.28.232"))
        self.assertEqual(chosen, "172.28.232")

    def test_refuse_missing_or_partial_vmware_metadata(self):
        with self.assertRaises(network.NetworkSelectionBlocked):
            network.select_available_prefix([], [], "", [])
        with self.assertRaises(network.NetworkSelectionBlocked):
            network.select_available_prefix([], [],
                "answer VNET_2_HOSTONLY_SUBNET 172.28.231.0", [])

    def test_refuse_no_available_subnet(self):
        with self.assertRaisesRegex(network.NetworkSelectionBlocked, "No free"):
            network.select_available_prefix([], [], VMWARE,
                ["172.28.220", "172.28.221"],
                candidates=("172.28.220", "172.28.221"))

    def test_refuse_north_and_non_private_candidates(self):
        with self.assertRaises(network.NetworkSelectionBlocked):
            network.select_available_prefix([], [], VMWARE, [],
                candidates=("10.4.10", "8.8.8"))
        with self.assertRaises(network.NetworkSelectionBlocked):
            network.select_available_prefix([], [], VMWARE, [],
                candidates=("8.8.8",))

    def test_malformed_route_fails_closed(self):
        with self.assertRaises(network.NetworkSelectionBlocked):
            network.select_available_prefix([], [{"dst": "not-a-route"}], VMWARE, [])

    def test_malformed_registered_native_prefix_fails_closed(self):
        with self.assertRaises(network.NetworkSelectionBlocked):
            network.select_available_prefix([], [], VMWARE, ["not-a-prefix"])


if __name__ == "__main__":
    unittest.main()
