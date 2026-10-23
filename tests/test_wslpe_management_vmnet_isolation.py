"""vmnet4 isolation snapshot tests; all kernel/network calls are mocks."""
import json
from pathlib import Path
import unittest
from unittest import mock

from kingdoms import wslpe_management_vmnet_isolation as iso
from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked

STATES = {str(path): "0" for path in iso.ZERO_PATHS}
LINK = [{"ifname": "vmnet4", "flags": ["UP"], "operstate": "UNKNOWN"}]
ROUTES = [
    {"dst": "172.28.233.0/24", "dev": "vmnet4", "protocol": "kernel"},
    {"dst": "10.4.10.0/24", "dev": "vmnet10", "protocol": "kernel"},
    {"dst": "local 172.28.233.254", "dev": "vmnet4", "type": "local", "table": "local"},
    {"dst": "broadcast 172.28.233.255", "dev": "vmnet4", "type": "broadcast", "table": "local"},
]


class Vmnet4IsolationTests(unittest.TestCase):
    def snapshot(self, states=None, links=None, routes=None):
        return iso.validate_isolation_snapshot(
            vmnet="vmnet4", subnet="172.28.233.0/24",
            sysctls=STATES if states is None else states,
            links=LINK if links is None else links,
            ipv4_routes=ROUTES if routes is None else routes,
        )

    def test_valid_vmnet4_with_normal_local_and_broadcast_routes(self):
        self.assertEqual(self.snapshot(), "VMNET4_KERNEL_NONROUTING=PASS")

    def test_vmnet4_per_interface_forwarding_must_be_zero(self):
        for path in iso.ZERO_PATHS:
            with self.subTest(path=str(path)):
                for value in ("1", "unknown", None):
                    states = dict(STATES)
                    states[str(path)] = value
                    with self.assertRaisesRegex(NetworkTransactionBlocked, "forwarding"):
                        self.snapshot(states=states)

    def test_any_bridge_or_enslaved_interface_is_denied(self):
        for link in (
            {"ifname": "vmnet4", "master": "br0"},
            {"ifname": "vmnet4", "link": "eth0"},
            {"ifname": "vmnet4", "linkinfo": {"info_kind": "veth"}},
            {"ifname": "vmnet4", "linkinfo": {"info_kind": "bridge"}},
        ):
            with self.subTest(link=link):
                with self.assertRaisesRegex(NetworkTransactionBlocked, "bridged"):
                    self.snapshot(links=[link])

    def test_extra_unicast_route_on_management_is_denied(self):
        extra = {"dst": "10.4.10.0/24", "dev": "vmnet4"}
        with self.assertRaisesRegex(NetworkTransactionBlocked, "Unexpected vmnet4"):
            self.snapshot(routes=ROUTES + [extra])

    def test_gateway_behind_management_interface_is_denied(self):
        routes = [dict(ROUTES[0], gateway="172.28.233.1"), *ROUTES[1:]]
        with self.assertRaisesRegex(NetworkTransactionBlocked, "gateway"):
            self.snapshot(routes=routes)

    def test_lost_connected_route_is_denied(self):
        with self.assertRaisesRegex(NetworkTransactionBlocked, "Unexpected vmnet4"):
            self.snapshot(routes=ROUTES[1:])

    def test_scope_mismatch_is_denied(self):
        with self.assertRaisesRegex(NetworkTransactionBlocked, "Unexpected"):
            iso.validate_isolation_snapshot(
                vmnet="vmnet3", subnet="172.28.233.0/24",
                sysctls=STATES, links=LINK, ipv4_routes=ROUTES)

    def test_live_verifier_only_reads_sysctls_and_iproute2(self):
        calls = []
        data = iter((LINK, ROUTES))
        def read(path):
            calls.append(("read", path))
            return "0"
        def run(command, *, timeout):
            calls.append(("ip", tuple(command), timeout))
            return json.dumps(next(data))
        verifier = iso.Vmnet4KernelIsolationVerifier(run=run, read=read)
        with mock.patch.object(iso, "_trusted_binary"):
            self.assertEqual(verifier.verify("vmnet4", "172.28.233.0/24"),
                             "VMNET4_KERNEL_NONROUTING=PASS")
        self.assertEqual([c for c in calls if c[0] == "read"],
                         [("read", p) for p in iso.ZERO_PATHS])
        self.assertEqual([c[-1] for c in calls if c[0] == "ip"], [15, 15])

    def test_missing_kernel_forwarding_file_fails_closed(self):
        with self.assertRaisesRegex(NetworkTransactionBlocked, "Cannot read kernel"):
            iso.Vmnet4KernelIsolationVerifier._bounded_read(
                Path("/a/nonexistent/vmnet4/forwarding"))

    def test_no_sysctl_firewall_or_route_mutation_exposed(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] /
                  "kingdoms/wslpe_management_vmnet_isolation.py").read_text()
        for forbidden in ("sysctl -w", "iptables -A", "nft add", "ip route add"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
