"""NORTH route resume/rollback regression: no real routes or VMs are mutated."""
import json
import subprocess
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
