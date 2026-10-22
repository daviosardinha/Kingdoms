"""vmnet4-only persistent address keeper regressions; no root or network mutation."""
from contextlib import redirect_stdout
from io import StringIO
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/wslpe-vmnet4-hostaddr-keeper.py"
SPEC = importlib.util.spec_from_file_location("wslpe_vmnet4_keeper_tests", PATH)
assert SPEC and SPEC.loader
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)

OLD = (
    "VERSION=1,0\n"
    "answer VNET_3_HOSTONLY_SUBNET 172.28.232.0\n"
    "answer VNET_10_HOSTONLY_SUBNET 10.4.10.0\n"
    "answer VNET_10_HOSTONLY_HOSTADDR 10.4.10.254\n"
    "answer VNET_99_HOSTONLY_SUBNET 10.4.99.0\n"
    "answer VNET_99_HOSTONLY_HOSTADDR 10.4.99.254\n"
)
ADD = (
    "answer VNET_4_DHCP no\n"
    "answer VNET_4_NAT no\n"
    "answer VNET_4_HOSTONLY_SUBNET 172.28.233.0\n"
    "answer VNET_4_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_4_HOSTONLY_HOSTADDR 172.28.233.254\n"
    "answer VNET_4_VIRTUAL_ADAPTER yes\n"
)
FULL = (OLD + ADD).encode()
LINK = [{"ifname": "vmnet4", "flags": ["UP"], "operstate": "UNKNOWN"}]
ROUTES = [
    {"dst": "10.4.10.0/24", "dev": "vmnet10"},
    {"dst": "172.28.233.0/24", "dev": "vmnet4", "scope": "link",
     "prefsrc": "172.28.233.1", "protocol": "kernel"},
]


def addresses(ip="172.28.233.1"):
    return [{"ifname": "vmnet4", "addr_info": (
        [] if ip is None else [{"family": "inet", "local": ip, "prefixlen": 24}]
    )}]


def plan(addr=None, routes=None, flags=(True, True, True)):
    return APP.plan_snapshot(
        links=LINK, addresses=addresses() if addr is None else addr,
        routes=ROUTES if routes is None else routes, forwarding=flags
    )


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.journal = {
            "version": 1, "status": "committed", "vmnet": "vmnet4",
            "subnet": "172.28.233.0/24",
            "networking": str(APP.NETWORKING),
            "original_b64": base64.b64encode(OLD.encode()).decode(),
            "original_sha256": hashlib.sha256(OLD.encode()).hexdigest(),
            "proposed_sha256": APP.EXPECTED_COMMIT,
        }

    def test_accepted_committed_source_and_vmware_stripped_hostaddr(self):
        APP.verify_committed_state(self.journal, FULL)
        normalized = FULL.replace(b"answer VNET_4_HOSTONLY_HOSTADDR 172.28.233.254\n", b"")
        normalized = normalized.replace(
            b"answer VNET_10_HOSTONLY_HOSTADDR 10.4.10.254\n", b"")
        APP.verify_committed_state(self.journal, normalized)

    def test_uncommitted_wrong_scope_or_source_drift_blocks(self):
        for field, value in (
            ("status", "rolled_back"),
            ("vmnet", "vmnet10"),
            ("subnet", "10.4.10.0/24"),
            ("proposed_sha256", "0"*64),
        ):
            with self.subTest(field=field):
                journal = dict(self.journal, **{field: value})
                with self.assertRaises(APP.Denied):
                    APP.verify_committed_state(journal, FULL)
        for changed in (
            FULL.replace(b"VNET_4_NAT no", b"VNET_4_NAT yes"),
            FULL.replace(b"10.4.10.0", b"10.4.11.0"),
            FULL + b"answer VNET_4_BRIDGE yes\n",
            FULL + b"answer VNET_12_DHCP yes\n",
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(APP.Denied):
                    APP.verify_committed_state(self.journal, changed)

    def test_live_default_point_one_has_exact_two_vmnet4_operations(self):
        self.assertEqual(plan(), (
            ["del", "172.28.233.1/24", "dev", "vmnet4"],
            ["add", "172.28.233.254/24", "dev", "vmnet4"],
        ))

    def test_already_correct_requires_good_kernel_route(self):
        good = [dict(ROUTES[0]), dict(ROUTES[1], prefsrc="172.28.233.254")]
        self.assertEqual(plan(addr=addresses("172.28.233.254"), routes=good), ())
        with self.assertRaises(APP.Denied):
            plan(addr=addresses("172.28.233.254"))

    def test_recover_only_absent_address_without_route(self):
        self.assertEqual(
            plan(addr=addresses(None), routes=[]),
            (["add", "172.28.233.254/24", "dev", "vmnet4"],)
        )
        with self.assertRaises(APP.Denied):
            plan(addr=addresses(None))

    def test_foreign_ip_subnet_or_multiple_address_fails_closed(self):
        for row in (
            addresses("10.4.10.254"),
            addresses("172.28.233.99"),
            [{"ifname": "vmnet4", "addr_info": addresses()[0]["addr_info"] * 2}],
        ):
            with self.assertRaises(APP.Denied):
                plan(addr=row)

    def test_foreign_routes_and_global_forwarding_fail_closed(self):
        for bad in (
            ROUTES + [{"dst": "default", "dev": "vmnet4"}],
            [dict(ROUTES[0]), dict(ROUTES[1], gateway="172.28.233.1")],
            [dict(ROUTES[0]), dict(ROUTES[1], dev="vmnet10")],
        ):
            with self.assertRaises(APP.Denied):
                plan(routes=bad)
        for flags in ((False, True, True), (True, False, True), (True, True, False)):
            with self.assertRaises(APP.Denied):
                plan(flags=flags)

    def test_bridge_is_never_repaired(self):
        with self.assertRaises(APP.Denied):
            APP.plan_snapshot(
                links=[dict(LINK[0], master="br0")],
                addresses=addresses(), routes=ROUTES, forwarding=(True, True, True)
            )

    def test_check_reports_drift_without_mutation(self):
        fake_dir = type("Info", (), {"st_mode": stat.S_IFDIR | 0o700,
                                    "st_uid": 0})()
        with (mock.patch.object(APP.os, "geteuid", return_value=0),
              mock.patch.object(Path, "lstat", return_value=fake_dir),
              mock.patch.object(APP, "_read_root", side_effect=[
                  json.dumps(self.journal).encode(), FULL,
              ]),
              mock.patch.object(APP, "snapshot",
                                return_value=(LINK, addresses(), ROUTES, (True, True, True))),
              mock.patch.object(APP, "_write_ip") as write,
              redirect_stdout(StringIO()) as out):
            rc = APP.main(["--check"])
        self.assertEqual(rc, 1)
        self.assertIn("[DRIFT]", out.getvalue())
        write.assert_not_called()

    def test_repair_changes_only_vmnet4_and_rechecks(self):
        fake_dir = type("Info", (), {"st_mode": stat.S_IFDIR | 0o700,
                                    "st_uid": 0})()
        correct = (LINK, addresses("172.28.233.254"),
                   [ROUTES[0], dict(ROUTES[1], prefsrc="172.28.233.254")],
                   (True, True, True))
        with (mock.patch.object(APP.os, "geteuid", return_value=0),
              mock.patch.object(Path, "lstat", return_value=fake_dir),
              mock.patch.object(APP, "_read_root", side_effect=[
                  json.dumps(self.journal).encode(), FULL,
              ]),
              mock.patch.object(APP, "snapshot", side_effect=[
                  (LINK, addresses(), ROUTES, (True, True, True)), correct,
              ]),
              mock.patch.object(APP, "_write_ip") as write,
              redirect_stdout(StringIO()) as out):
            rc = APP.main(["--repair"])
        self.assertEqual(rc, 0)
        self.assertEqual(write.call_args_list, [
            mock.call(["del", "172.28.233.1/24", "dev", "vmnet4"]),
            mock.call(["add", "172.28.233.254/24", "dev", "vmnet4"]),
        ])
        self.assertIn("VMNET4_HOSTADDR_PERSISTENCE=PASS", out.getvalue())

    def test_service_and_installer_have_no_shared_network_restart(self):
        installer = (ROOT / "scripts/wslpe-vmnet4-install-persistence.sh").read_text()
        service = (ROOT / "ops/systemd/kingdoms-wslpe-vmnet4-hostaddr.service").read_text()
        timer = (ROOT / "ops/systemd/kingdoms-wslpe-vmnet4-hostaddr.timer").read_text()
        keeper = PATH.read_text()
        self.assertIn("/usr/local/libexec/kingdoms/wslpe-vmnet4-hostaddr-keeper.py", service)
        self.assertIn("OnUnitInactiveSec=15s", timer)
        self.assertIn("vmrun -T ws list", installer)
        self.assertIn("INSTALL-VMNET4-KEEPER", installer)
        for source in (installer, keeper, service, timer):
            for forbidden in ("vmware-networks --stop", "vmware-networks --start",
                              "ip addr flush", "vmrun -T ws stop", "nft flush"):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
