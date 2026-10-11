"""Reduced NORTH route controller: fail closed, never delete foreign routes."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goad import course1_routes as routes


class KingdomsCourse1RouteTests(unittest.TestCase):
    def setUp(self):
        self.plan = routes.route_plan()
        self.entry = {
            "dst": self.plan["destination"],
            "gateway": self.plan["gateway"],
            "dev": self.plan["interface"],
            "protocol": int(self.plan["protocol"]),
        }

    def test_north_adds_only_parent_route_no_essos(self):
        self.assertEqual(self.plan["destination"], "10.4.20.0/24")
        self.assertEqual(self.plan["gateway"], "10.4.10.1")
        self.assertEqual(self.plan["interface"], "vmnet10")
        self.assertEqual(self.plan["host_address"], "10.4.10.254/24")
        self.assertNotIn("10.4.30.", str(self.plan))

    def test_alternate_network_produces_same_kingdoms_route_contract(self):
        plan = routes.route_plan(
            "10.5.0.0/16",
            {"north": 11, "sevenkingdoms": 21, "management": 98},
        )
        self.assertEqual(plan["destination"], "10.5.20.0/24")
        self.assertEqual(plan["gateway"], "10.5.10.1")
        self.assertEqual(plan["interface"], "vmnet11")
        self.assertEqual(plan["host_address"], "10.5.10.254/24")

    def test_unowned_route_is_never_overwritten_or_removed(self):
        with self.assertRaisesRegex(routes.RouteConflict, "Foreign/overlapping"):
            routes.check_routes(
                [{"dst": "10.4.20.0/24", "gateway": "10.4.10.99", "dev": "vmnet10"}],
                self.plan, False,
            )
        with self.assertRaisesRegex(routes.RouteConflict, "no Course 1 ownership"):
            routes.check_routes([self.entry], self.plan, False)

    def test_broad_vpn_route_blocks_mutation(self):
        with self.assertRaisesRegex(routes.RouteConflict, "overlapping"):
            routes.check_routes([{"dst": "10.4.0.0/16", "dev": "wg0"}], self.plan, False)

    def test_correct_owned_route_is_idempotent(self):
        self.assertTrue(routes.check_routes([self.entry], self.plan, True))
        self.assertFalse(routes.check_routes([], self.plan, False))

    def test_stale_record_cannot_hide_missing_route(self):
        with self.assertRaisesRegex(routes.RouteConflict, "kernel route is missing"):
            routes.check_routes([], self.plan, True)

    def test_state_must_match_provider_and_topology(self):
        with tempfile.TemporaryDirectory() as temp:
            provider = Path(temp)
            with patch.object(routes, "STATE_DIR", provider):
                record, identity = routes.provider_state(str(provider))
                self.assertFalse(routes.read_owned(record, identity, self.plan))
                record.write_text(json.dumps({"provider": "/wrong", "route": self.plan}))
                with self.assertRaisesRegex(routes.RouteConflict, "does not match"):
                    routes.read_owned(record, identity, self.plan)
                record.write_text(json.dumps({"provider": identity, "route": self.plan}))
                self.assertTrue(routes.read_owned(record, identity, self.plan))

    def test_status_is_read_only_and_requires_provider_context(self):
        with self.assertRaisesRegex(routes.RouteConflict, "requires --provider-dir"):
            routes.execute("status")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(routes, "route_table", return_value=[]):
                self.assertEqual(routes.execute("status", tmp), "ABSENT")
            with patch.object(routes, "route_table", return_value=[self.entry]):
                with self.assertRaisesRegex(routes.RouteConflict, "no Course 1 ownership"):
                    routes.execute("status", tmp)

    def test_enable_checks_host_first_and_does_not_use_route_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(routes.os, "geteuid", return_value=0), patch.object(
                routes, "route_table", return_value=[]
            ), patch.object(routes, "check_host_adapter") as adapter, patch.object(
                routes, "run"
            ) as shell, patch.object(routes, "save_state") as save:
                result = routes.execute("enable", tmp)
                self.assertEqual(result, "ADDED OWNED ROUTE")
                adapter.assert_called_once_with(self.plan)
                command = shell.call_args.args
                self.assertEqual(command[:4], ("ip", "-4", "route", "add"))
                self.assertNotIn("replace", command)
                self.assertEqual(command[-2:], ("proto", routes.PROTO))
                save.assert_called_once()

    def test_owned_disable_removes_exact_route_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = Path(tmp)
            with patch.object(routes, "STATE_DIR", provider):
                state_path, identity = routes.provider_state(str(provider))
                state_path.write_text(json.dumps({"provider": identity, "route": self.plan}))
                with patch.object(routes.os, "geteuid", return_value=0), patch.object(
                    routes, "route_table", return_value=[self.entry]
                ), patch.object(routes, "run") as shell:
                    self.assertEqual(routes.execute("disable", str(provider)),
                                     "REMOVED OWNED ROUTE")
                    self.assertFalse(state_path.exists())
                    self.assertEqual(shell.call_args.args[:4],
                                     ("ip", "-4", "route", "del"))

    def test_missing_state_and_route_disable_does_not_modify_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(routes.os, "geteuid", return_value=0), patch.object(
                routes, "route_table", return_value=[]
            ), patch.object(routes, "run") as shell:
                self.assertEqual(routes.execute("disable", tmp), "ALREADY ABSENT")
                shell.assert_not_called()

    def test_bash_script_dispatches_only_for_explicit_north(self):
        file = Path(__file__).resolve().parents[1] / "scripts/provisioning-routes.sh"
        source = file.read_text()
        self.assertIn('if [[ "\${1:-}" == "--north" ]]', source)
        self.assertIn("python3 -m goad.course1_routes", source)
        legacy = source.split('fi\n', 1)[1]
        self.assertIn('readonly ESSOS_NET="10.4.30.0/24"', legacy)
        self.assertIn('ip route replace "\${ESSOS_NET}"', legacy)


if __name__ == "__main__":
    unittest.main()
