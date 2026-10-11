"""Offline checks for the single-source reduced Kingdoms network model."""
import json
import tempfile
import unittest
from pathlib import Path

from goad.kingdoms_topology import (
    load_course1_topology, parse_vmnet_args, MANIFEST_PATH,
)


class Course1TopologyTests(unittest.TestCase):
    def test_default_network_is_original_kingdoms_three_zone_subgraph(self):
        layout = load_course1_topology()
        self.assertEqual(layout["network_base"], "10.4.0.0/16")
        self.assertEqual(set(layout["windows"]), {
            "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"})
        self.assertEqual(layout["segments"]["north"]["cidr"], "10.4.10.0/24")
        self.assertEqual(layout["segments"]["sevenkingdoms"]["cidr"], "10.4.20.0/24")
        self.assertEqual(layout["segments"]["management"]["cidr"], "10.4.99.0/24")
        self.assertEqual(layout["windows"]["GOAD-DC01"]["address"], "10.4.20.10")
        self.assertEqual(layout["windows"]["GOAD-DC02"]["address"], "10.4.10.11")
        self.assertEqual(layout["windows"]["GOAD-SRV02"]["address"], "10.4.10.22")
        self.assertEqual(layout["windows"]["GOAD-WS01"]["address"], "10.4.10.31")
        self.assertEqual(layout["segments"]["north"]["host_address"], "10.4.10.254")
        self.assertIsNone(layout["segments"]["sevenkingdoms"]["host_address"])

    def test_nondefault_ten_five_with_explicit_unique_vmnets(self):
        allocations = {"north": 11, "sevenkingdoms": 21, "management": 98}
        layout = load_course1_topology("10.5.0.0/16", allocations)
        self.assertEqual(layout["network_base"], "10.5.0.0/16")
        self.assertEqual(layout["windows"]["GOAD-DC02"]["address"], "10.5.10.11")
        self.assertEqual(layout["windows"]["GOAD-DC01"]["address"], "10.5.20.10")
        self.assertEqual(layout["segments"]["management"]["gateway"], "10.5.99.1")
        self.assertEqual(layout["segments"]["north"]["vmnet"], "vmnet11")
        self.assertEqual(layout["segments"]["sevenkingdoms"]["vmnet"], "vmnet21")
        self.assertEqual(layout["segments"]["management"]["vmnet"], "vmnet98")

    def test_alternate_network_with_default_vmnets_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "explicit independent"):
            load_course1_topology("10.5.0.0/16")

    def test_invalid_prefix_is_rejected(self):
        for candidate in ("10.5.0.0/24", "10.5.10.0/16",
                          "192.168.0.0/16", "10.5.0.0/8"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    load_course1_topology(candidate)

    def test_colliding_or_reserved_vmnets_are_rejected(self):
        for allocations in (
            {"north": 10, "sevenkingdoms": 10, "management": 99},
            {"north": 8, "sevenkingdoms": 20, "management": 99},
            {"north": 10, "sevenkingdoms": 20, "management": 1},
            {"north": 10, "sevenkingdoms": 20},
            {"north": 10, "sevenkingdoms": True, "management": 99},
        ):
            with self.subTest(allocations=allocations):
                with self.assertRaises(ValueError):
                    load_course1_topology(vmnets=allocations)

    def test_unknown_machine_fails_before_vm_creation(self):
        modified = json.loads(MANIFEST_PATH.read_text())
        modified["windows"]["GOAD-DC03"] = {
            "inventory": "dc03", "segment": "north", "host_octet": 12}
        with tempfile.TemporaryDirectory() as path:
            file = Path(path) / "topology.json"
            file.write_text(json.dumps(modified))
            with self.assertRaisesRegex(ValueError, "Unexpected Course 1"):
                load_course1_topology(manifest_path=file)

    def test_protected_zone_must_have_no_host_adapter(self):
        modified = json.loads(MANIFEST_PATH.read_text())
        modified["segments"]["sevenkingdoms"]["host_interface"] = 254
        with tempfile.TemporaryDirectory() as path:
            file = Path(path) / "topology.json"
            file.write_text(json.dumps(modified))
            with self.assertRaisesRegex(ValueError, "Protected Seven Kingdoms"):
                load_course1_topology(manifest_path=file)

    def test_single_parser_with_distinct_segment_keys(self):
        self.assertEqual(
            parse_vmnet_args(["north=11", "sevenkingdoms=21", "management=98"]),
            {"north": 11, "sevenkingdoms": 21, "management": 98})
        for raw in (["north=11", "north=12"], ["north=invalid"], ["north"]):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_vmnet_args(raw)

    def test_source_only_never_mutates_runtime(self):
        script = (Path(__file__).resolve().parents[1] / "goad/kingdoms_topology.py").read_text()
        for forbidden in ("subprocess.", "sudo ", "vagrant up", "vmrun", "ip route replace"):
            self.assertNotIn(forbidden, script)


if __name__ == "__main__":
    unittest.main()
