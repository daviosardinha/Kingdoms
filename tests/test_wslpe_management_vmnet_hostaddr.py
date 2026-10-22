"""Guarded VMware vmnet4 .254 host-address correction tests with simulated iproute2."""
import json
from pathlib import Path
import unittest
from unittest import mock

from kingdoms import wslpe_management_vmnet_hostaddr as h
from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked

CONFIG = (
    "VERSION=1,0\n"
    "answer VNET_3_HOSTONLY_SUBNET 172.28.232.0\n"
    "answer VNET_4_DHCP no\n"
    "answer VNET_4_NAT no\n"
    "answer VNET_4_HOSTONLY_HOSTADDR 172.28.233.254\n"
    "answer VNET_4_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_4_HOSTONLY_SUBNET 172.28.233.0\n"
    "answer VNET_4_VIRTUAL_ADAPTER yes\n"
)
LINK = [{"ifname": "vmnet4", "flags": ["BROADCAST", "UP", "LOWER_UP"],
         "operstate": "UNKNOWN"}]
ROUTE = [{"dst": "172.28.233.0/24", "dev": "vmnet4", "scope": "link"}]


def addr(ip="172.28.233.1", prefix=24):
    return [{"ifname": "vmnet4", "addr_info": (
        [] if ip is None else [
            {"family": "inet", "local": ip, "prefixlen": prefix}]
    )}]


def transition(*, addresses=None, links=None, routes=None, config=CONFIG):
    return h.address_transition(
        vmnet="vmnet4", subnet=h.SUBNET, networking_text=config,
        address_rows=addr() if addresses is None else addresses,
        link_rows=LINK if links is None else links,
        route_rows=ROUTE if routes is None else routes,
    )


class HostAddressReconcileTests(unittest.TestCase):
    def test_default_vmware_point_one_gets_replaced_only_on_vmnet4(self):
        self.assertEqual(transition(), (
            ["-4", "address", "del", "172.28.233.1/24", "dev", "vmnet4"],
            ["-4", "address", "add", "172.28.233.254/24", "dev", "vmnet4"],
        ))

    def test_missing_ipv4_gets_only_desired_address(self):
        self.assertEqual(transition(addresses=addr(None), routes=[]), (
            ["-4", "address", "add", "172.28.233.254/24", "dev", "vmnet4"],
        ))

    def test_correct_host_address_is_idempotent(self):
        self.assertEqual(transition(addresses=addr("172.28.233.254")), ())

    def test_missing_address_with_route_does_not_mutate(self):
        with self.assertRaisesRegex(NetworkTransactionBlocked, "route with no address"):
            transition(addresses=addr(None))

    def test_wrong_or_multiple_addresses_are_refused(self):
        for addresses in (
            addr("10.4.10.254"), addr("172.28.232.254"),
            addr("172.28.233.1", 16),
            addr("172.28.233.0"),
            addr("172.28.233.255"),
            [{"ifname": "vmnet4", "addr_info": addr()[0]["addr_info"] * 2}],
        ):
            with self.subTest(addresses=addresses):
                with self.assertRaises(NetworkTransactionBlocked):
                    transition(addresses=addresses)

    def test_unexpected_routes_never_trigger_ip_write(self):
        for routes in (
            [{"dst": "default", "dev": "vmnet4"}],
            [{"dst": "10.4.10.0/24", "dev": "vmnet4"}],
            [{"dst": "172.28.233.0/24", "dev": "vmnet4", "gateway": "172.28.233.1"}],
        ):
            with self.subTest(routes=routes):
                with self.assertRaisesRegex(NetworkTransactionBlocked, "route"):
                    transition(routes=routes)

    def test_untrusted_link_and_networking_refused(self):
        for link in (
            {"ifname": "vmnet4", "flags": ["UP"], "master": "br0"},
            {"ifname": "vmnet4", "flags": ["UP"], "link": "eth0"},
            {"ifname": "vmnet4", "flags": ["DOWN"]},
            {"ifname": "vmnet3", "flags": ["UP"]},
        ):
            with self.subTest(link=link):
                with self.assertRaises(NetworkTransactionBlocked):
                    transition(links=[link])
        with self.assertRaisesRegex(NetworkTransactionBlocked, "metadata"):
            transition(config=CONFIG.replace(
                "answer VNET_4_NAT no", "answer VNET_4_NAT yes"))

    def test_real_reconciler_uses_exact_argv_without_shell(self):
        calls = []
        observations = iter((addr(), LINK, ROUTE))
        def runner(argv, *, timeout):
            calls.append((argv, timeout))
            if len(calls) <= 3:
                return json.dumps(next(observations))
            return ""
        device = h.Vmnet4HostAddressReconciler(run=runner)
        with mock.patch.object(h, "_trusted_binary"):
            result = device.reconcile("vmnet4", h.SUBNET, CONFIG)
        self.assertEqual(result, "VMNET4_IPV4_RECONCILED")
        self.assertEqual([q[0][1:] for q in calls[-2:]], [
            ["-4", "address", "del", "172.28.233.1/24", "dev", "vmnet4"],
            ["-4", "address", "add", "172.28.233.254/24", "dev", "vmnet4"],
        ])
        self.assertTrue(all(q[0][0] == "/usr/bin/ip" and q[1] == 15 for q in calls))

    def test_wrong_vmnet_is_rejected_before_ip_execution(self):
        with self.assertRaisesRegex(NetworkTransactionBlocked, "Wrong"):
            h.address_transition(
                vmnet="vmnet10", subnet=h.SUBNET, networking_text=CONFIG,
                address_rows=addr(), link_rows=LINK, route_rows=ROUTE)

    def test_no_global_or_other_vmnet_mutation(self):
        source = (Path(__file__).resolve().parents[1] /
                  "kingdoms/wslpe_management_vmnet_hostaddr.py").read_text()
        for forbidden in ("flush", "vmnet10", "sysctl -w", "iptables", "vmware-networks"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
