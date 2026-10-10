"""NORTH route resume/rollback regression: no real routes or VMs are mutated."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from goad.course1_route_state import classify_route

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/course1/provisioning-routes.sh"
IDENTITY = {
    "network": "10.41.20.0/24",
    "gateway": "10.41.10.1",
    "device": "vmnet11",
    "host_source": "10.41.10.254",
}
OWNED = {
    "dst": "10.41.20.0/24",
    "gateway": "10.41.10.1",
    "dev": "vmnet11",
    "protocol": "boot",
    "scope": "global",
    "flags": [],
}


class NorthRouteStateTests(unittest.TestCase):
    def state(self, value):
        return classify_route(json.dumps(value), **IDENTITY)

    def test_route_absent_retries_safely(self):
        self.assertEqual(self.state([]), "absent")

    def test_known_route_survives_iproute2_format_and_metadata(self):
        for route in (
            OWNED,
            {**OWNED, "protocol": "static", "metric": 100},
            {**OWNED, "prefsrc": "10.41.10.254", "table": "main"},
            {**OWNED, "table": 254, "type": "unicast"},
        ):
            with self.subTest(route=route):
                self.assertEqual(self.state([route]), "owned")

    def test_foreign_or_ambiguous_routes_fail_closed(self):
        cases = (
            {**OWNED, "gateway": "10.41.10.99"},
            {**OWNED, "dev": "vmnet10"},
            {**OWNED, "dst": "10.4.20.0/24"},
            {**OWNED, "prefsrc": "10.4.10.254"},
            {**OWNED, "table": 120},
            {**OWNED, "scope": "link"},
            {**OWNED, "type": "blackhole"},
            {**OWNED, "nexthops": [{"via": "10.41.10.1"}]},
            {**OWNED, "flags": ["onlink"]},
        )
        for route in cases:
            with self.subTest(route=route):
                self.assertEqual(self.state([route]), "foreign")
        self.assertEqual(self.state([OWNED, OWNED]), "foreign")
        self.assertEqual(self.state({"dst": OWNED["dst"]}), "foreign")
        self.assertEqual(classify_route("not-json", **IDENTITY), "foreign")
        self.assertEqual(classify_route("null", **IDENTITY), "foreign")

    def mock_shell_route(self, initial):
        """Run the actual NORTH shell helper with only sandboxed fake ip/ping.

        EUID and the installed host-address path are redirected ONLY in a
        private temporary copy, never in source or the real workstation.
        """
        temp = tempfile.TemporaryDirectory(prefix="north-route-shell-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "scripts/course1").mkdir(parents=True)
        (root / "goad").mkdir()
        (root / "bin").mkdir()
        state = root / "route.json"
        state.write_text(json.dumps(initial), encoding="utf-8")
        original = SCRIPT.read_text(encoding="utf-8")
        original_root = 'require_root() { [[ ${EUID} -eq 0 ]] || fail "requires root"; }'
        self.assertIn(original_root, original)
        script = original.replace(original_root, 'require_root() { :; }')
        host_helper = root / "bin/north-host-addresses"
        host_helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        host_helper.chmod(0o700)
        script = script.replace(
            "/usr/local/sbin/kingdoms-north-vmnet-hostaddrs", str(host_helper)
        )
        (root / "scripts/course1/provisioning-routes.sh").write_text(
            script, encoding="utf-8"
        )
        (root / "goad/course1_route_state.py").write_bytes(
            (ROOT / "goad/course1_route_state.py").read_bytes()
        )
        fake_ip = root / "bin/ip"
        fake_ip.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "state = pathlib.Path(os.environ['FAKE_NORTH_ROUTE_STATE'])\n"
            "args = sys.argv[1:]\n"
            "rows = json.loads(state.read_text())\n"
            "if args[:4] == ['-j', '-4', 'route', 'show']:\n"
            "    print(json.dumps(rows)); sys.exit(0)\n"
            "if args[:4] == ['-4', 'route', 'show', 'exact']:\n"
            "    for row in rows:\n"
            "        print(row['dst'] + ' via ' + row.get('gateway','')"
            " + ' dev ' + row.get('dev',''))\n"
            "    sys.exit(0)\n"
            "if args[:4] == ['-4', '-o', 'addr', 'show']:\n"
            "    addr = {'vmnet11':'10.41.10.254/24',"
            "'vmnet13':'10.41.99.254/24'}[args[-1]]\n"
            "    print('2: ' + args[-1] + ' inet ' + addr); sys.exit(0)\n"
            "if args[:3] == ['-4', 'route', 'add']:\n"
            "    if rows: sys.exit(2)\n"
            "    state.write_text(json.dumps(["
            "{'dst':'10.41.20.0/24','gateway':'10.41.10.1',"
            "'dev':'vmnet11','protocol':'boot','scope':'global'}]))\n"
            "    sys.exit(0)\n"
            "if args[:3] == ['-4', 'route', 'del']:\n"
            "    if not rows: sys.exit(2)\n"
            "    state.write_text('[]'); sys.exit(0)\n"
            "sys.exit(98)\n", encoding="utf-8"
        )
        fake_ip.chmod(0o700)
        ping = root / "bin/ping"
        ping.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        ping.chmod(0o700)
        env = dict(os.environ)
        env["PATH"] = str(root / "bin") + os.pathsep + env["PATH"]
        env["FAKE_NORTH_ROUTE_STATE"] = str(state)
        shell = root / "scripts/course1/provisioning-routes.sh"

        def invoke(operation):
            return subprocess.run(
                ["bash", str(shell), operation], env=env,
                capture_output=True, text=True, check=False,
            )
        return invoke, state

    def test_existing_owned_route_is_idempotent_then_cleanly_removed(self):
        invoke, state = self.mock_shell_route([OWNED])
        self.assertEqual(invoke("enable").returncode, 0)
        self.assertEqual(json.loads(state.read_text()), [OWNED])
        self.assertEqual(invoke("disable").returncode, 0)
        self.assertEqual(json.loads(state.read_text()), [])
        self.assertEqual(invoke("disable").returncode, 0)
        self.assertEqual(invoke("enable").returncode, 0)
        self.assertEqual(classify_route(state.read_text(), **IDENTITY), "owned")

    def test_foreign_route_survives_enable_disable_and_status_unchanged(self):
        foreign = [{**OWNED, "gateway": "10.41.10.99"}]
        invoke, state = self.mock_shell_route(foreign)
        for action in ("status", "enable", "disable"):
            with self.subTest(action=action):
                self.assertNotEqual(invoke(action).returncode, 0)
                self.assertEqual(json.loads(state.read_text()), foreign)

    def test_script_never_overwrites_foreign_or_reference_route(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('ip -j -4 route show exact', text)
        self.assertIn('ip -4 route add', text)
        self.assertIn('ip -4 route del', text)
        self.assertIn('[[ "$state" == owned ]]', text)
        self.assertNotIn('ip -4 route replace', text)
        self.assertIn("COURSE1_ROOT", text)
        self.assertIn("10.41.20.0/24", text)
        self.assertIn("vmnet11", text)
        self.assertNotIn('vmnet10', text)
        self.assertNotIn('10.4.20.0/24', text)
        completed = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
