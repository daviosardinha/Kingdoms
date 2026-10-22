"""Simulated VMware service and host-only NIC contracts. No real host changes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from kingdoms import wslpe_management_vmnet_workstation as ws
from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked

CONFIG = (
    "VERSION=1,0\n"
    "answer VNET_3_DHCP no\n"
    "answer VNET_3_NAT no\n"
    "answer VNET_3_HOSTONLY_SUBNET 172.28.232.0\n"
    "answer VNET_3_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_4_DHCP no\n"
    "answer VNET_4_NAT no\n"
    "answer VNET_4_HOSTONLY_SUBNET 172.28.233.0\n"
    "answer VNET_4_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_4_HOSTONLY_HOSTADDR 172.28.233.254\n"
    "answer VNET_4_VIRTUAL_ADAPTER yes\n"
    "answer VNET_10_HOSTONLY_SUBNET 10.4.10.0\n"
)
ADDR = [{"ifname": "vmnet4", "addr_info": [
    {"family": "inet", "local": "172.28.233.254", "prefixlen": 24}]}]
LINK = [{"ifname": "vmnet4", "flags": ["BROADCAST", "UP", "LOWER_UP"],
         "operstate": "UNKNOWN"}]
ROUTE = [{"dst": "172.28.233.0/24", "dev": "vmnet4", "scope": "link"}]


class WorkstationHostCallbacksTests(unittest.TestCase):
    def test_default_binaries_match_verified_kali_host_paths(self):
        self.assertEqual(ws.BIN, Path("/usr/bin/vmware-networks"))
        self.assertEqual(ws.IP, Path("/usr/bin/ip"))
        self.assertEqual(ws.WorkstationNetworkService().binary, ws.BIN)
        self.assertEqual(ws.WorkstationHostAdapterVerifier().ip_binary, ws.IP)

    def test_valid_host_only_nic_metadata_and_route(self):
        self.assertEqual(ws.validate_vmnet4_host_state(
            vmnet="vmnet4", subnet="172.28.233.0/24",
            networking_text=CONFIG, address_rows=ADDR, link_rows=LINK,
            route_rows=ROUTE), "HOST_VMNET4_ADDRESS_AND_METADATA=PASS")

    def test_wrong_network_or_missing_host_address_is_denied(self):
        for vmnet, subnet in (
            ("vmnet3", "172.28.232.0/24"),
            ("vmnet4", "172.28.234.0/24"),
        ):
            with self.subTest(vmnet=vmnet):
                with self.assertRaises(NetworkTransactionBlocked):
                    ws.validate_vmnet4_host_state(
                        vmnet=vmnet, subnet=subnet, networking_text=CONFIG,
                        address_rows=ADDR, link_rows=LINK, route_rows=ROUTE)
        with self.assertRaisesRegex(NetworkTransactionBlocked, "metadata"):
            ws.validate_vmnet4_host_state(
                vmnet="vmnet4", subnet="172.28.233.0/24",
                networking_text=CONFIG.replace(
                    "answer VNET_4_HOSTONLY_HOSTADDR 172.28.233.254",
                    "answer VNET_4_HOSTONLY_HOSTADDR 172.28.233.1"),
                address_rows=ADDR, link_rows=LINK, route_rows=ROUTE)

    def test_duplicate_addresses_and_unexpected_routes_are_denied(self):
        duplicate = [dict(ADDR[0], addr_info=ADDR[0]["addr_info"] * 2)]
        for addresses, routes in (
            (duplicate, ROUTE),
            (ADDR, ROUTE + [{"dst": "default", "dev": "vmnet4"}]),
            (ADDR, [{"dst": "172.28.234.0/24", "dev": "vmnet4"}]),
            (ADDR, []),
        ):
            with self.subTest(addresses=addresses, routes=routes):
                with self.assertRaises(NetworkTransactionBlocked):
                    ws.validate_vmnet4_host_state(
                        vmnet="vmnet4", subnet="172.28.233.0/24",
                        networking_text=CONFIG, address_rows=addresses,
                        link_rows=LINK, route_rows=routes)

    def test_down_or_duplicate_adapter_denied(self):
        for links in (
            [dict(LINK[0], flags=["BROADCAST"], operstate="DOWN")],
            [dict(LINK[0], operstate="DOWN")],
            LINK * 2,
        ):
            with self.assertRaises(NetworkTransactionBlocked):
                ws.validate_vmnet4_host_state(
                    vmnet="vmnet4", subnet="172.28.233.0/24",
                    networking_text=CONFIG, address_rows=ADDR,
                    link_rows=links, route_rows=ROUTE)

    def test_service_uses_only_exact_stop_start_no_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "vmware-networks"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            recorded = []
            def record(args, *, timeout):
                recorded.append((args, timeout))
                return ""
            svc = ws.WorkstationNetworkService(binary=executable, run=record)
            with (mock.patch.object(ws.os, "geteuid", return_value=0),
                  mock.patch.object(ws, "_trusted_binary")):
                svc.action("stop")
                svc.action("start")
            self.assertEqual(recorded, [
                ([str(executable), "--stop"], 90),
                ([str(executable), "--start"], 90),
            ])
            self.assertNotIn("vmrun", str(recorded))

    def test_service_rejects_unknown_verb_and_nonroot(self):
        svc = ws.WorkstationNetworkService(run=lambda *_a, **_k: self.fail("ran command"))
        with self.assertRaisesRegex(NetworkTransactionBlocked, "Unexpected"):
            svc.action("restart")
        with mock.patch.object(ws.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "root"):
                svc.action("start")

    def test_missing_or_symlinked_binary_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            absent = Path(tmp) / "absent"
            with self.assertRaisesRegex(NetworkTransactionBlocked, "missing"):
                ws._trusted_binary(absent)
            executable = Path(tmp) / "real"
            executable.write_text("ok")
            symlink = Path(tmp) / "linked"
            symlink.symlink_to(executable)
            with self.assertRaisesRegex(NetworkTransactionBlocked, "Unsafe"):
                ws._trusted_binary(symlink)

    def test_root_owned_vmrun_symlink_may_resolve_only_to_trusted_usr_tree(self):
        import stat
        from types import SimpleNamespace

        launcher = Path("/usr/bin/vmrun")
        target = Path("/usr/lib/vmware/bin/vmrun")

        def mode(kind, owner=0):
            return SimpleNamespace(st_mode=kind | 0o755, st_uid=owner)

        def lstat(path):
            if path == launcher:
                return mode(stat.S_IFLNK)
            return mode(stat.S_IFDIR)

        with (mock.patch.object(Path, "lstat", lstat),
              mock.patch.object(Path, "resolve", return_value=target),
              mock.patch.object(Path, "stat", return_value=mode(stat.S_IFREG))):
            ws._trusted_binary(launcher, allow_trusted_symlink=True)
            with self.assertRaisesRegex(NetworkTransactionBlocked, "Symlinked binary"):
                ws._trusted_binary(launcher)

    def test_binary_symlink_refuses_untrusted_target_or_directory(self):
        import stat
        from types import SimpleNamespace

        launcher = Path("/usr/bin/vmrun")
        target = Path("/usr/lib/vmware/bin/vmrun")
        def mode(kind, owner=0, bits=0o755):
            return SimpleNamespace(st_mode=kind | bits, st_uid=owner)

        for unsafe_target in (Path("/tmp/vmrun"), Path("/home/stark/vmrun")):
            with (mock.patch.object(Path, "lstat", new=lambda p: (
                    mode(stat.S_IFLNK) if p == launcher else mode(stat.S_IFDIR))),
                  mock.patch.object(Path, "resolve", return_value=unsafe_target)):
                with self.assertRaisesRegex(NetworkTransactionBlocked, "trusted /usr"):
                    ws._trusted_binary(launcher, allow_trusted_symlink=True)

        def lstat(path):
            if path == launcher:
                return mode(stat.S_IFLNK)
            if path == Path("/usr/lib/vmware"):
                return mode(stat.S_IFDIR, bits=0o777)
            return mode(stat.S_IFDIR)

        with (mock.patch.object(Path, "lstat", lstat),
              mock.patch.object(Path, "resolve", return_value=target)):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "Untrusted executable parent"):
                ws._trusted_binary(launcher, allow_trusted_symlink=True)

    def test_binary_symlink_requires_root_owned_launcher_and_target(self):
        import stat
        from types import SimpleNamespace

        launcher = Path("/usr/bin/pgrep")
        target = Path("/usr/bin/pgrep.real")
        def item(kind, owner=0, bits=0o755):
            return SimpleNamespace(st_mode=kind | bits, st_uid=owner)

        with mock.patch.object(Path, "lstat", new=lambda p: (
                item(stat.S_IFLNK, owner=1000) if p == launcher else item(stat.S_IFDIR))):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "Non-root-owned"):
                ws._trusted_binary(launcher, allow_trusted_symlink=True)

        with (mock.patch.object(Path, "lstat", new=lambda p: (
                item(stat.S_IFLNK) if p == launcher else item(stat.S_IFDIR))),
              mock.patch.object(Path, "resolve", return_value=target),
              mock.patch.object(Path, "stat", return_value=item(stat.S_IFREG, owner=1000))):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "ownership/mode unsafe"):
                ws._trusted_binary(launcher, allow_trusted_symlink=True)

    def test_host_adapter_calls_are_bounded_and_read_only(self):
        queries = []
        answers = [ADDR, LINK, ROUTE]
        def capture(args, *, timeout):
            queries.append((args, timeout))
            return json.dumps(answers.pop(0))
        verifier = ws.WorkstationHostAdapterVerifier(ip_binary=Path("/usr/bin/ip"), run=capture)
        with mock.patch.object(ws, "_trusted_binary"):
            result = verifier.verify_host_adapter("vmnet4", "172.28.233.0/24", CONFIG)
        self.assertIn("PASS", result)
        self.assertEqual([q[0][1:] for q in queries], [
            ["-j", "-4", "address", "show", "dev", "vmnet4"],
            ["-j", "link", "show", "dev", "vmnet4"],
            ["-j", "-4", "route", "show", "dev", "vmnet4"],
        ])
        self.assertEqual([t for _, t in queries], [15] * 3)

    def test_host_adapter_rejects_empty_or_malformed_command_results(self):
        with self.assertRaisesRegex(NetworkTransactionBlocked, "Empty"):
            ws._json_list("", "address")
        with self.assertRaisesRegex(NetworkTransactionBlocked, "Malformed"):
            ws._json_list("{oops", "address")
        with self.assertRaisesRegex(NetworkTransactionBlocked, "shape"):
            ws._json_list('{"ifname":"vmnet4"}', "address")

    def test_shared_network_restart_is_not_exposed_to_operator(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        cli = (root / "scripts" / "wslpe-management-vmnet-plan.py").read_text()
        host = (root / "scripts" / "wslpe-management-vmnet-host-audit.py").read_text()
        registry = (root / "scripts" / "wslpe-management-vmnet-registry-audit.py").read_text()
        assert 'add_argument("--apply"' not in cli
        assert "vmware-networks" not in host and "vmware-networks" not in registry
        code = (root / "kingdoms" / "wslpe_management_vmnet_workstation.py").read_text()
        self.assertNotIn('if __name__ == "__main__"', code)


if __name__ == "__main__":
    unittest.main()
