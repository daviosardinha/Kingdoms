"""Existing Kingdoms VMware provider dispatches only NORTH into safe route mode."""
import ast
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def route_method():
    path = ROOT / "goad/provider/vagrant/vmware_nomad.py"
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "GoadNomadVmwareProvider")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_enable_provisioning_routes")
    namespace = {"subprocess": subprocess, "os": os, "Log": Mock()}
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(path), "exec"), namespace)
    return namespace["_enable_provisioning_routes"]


class RouteProviderTests(unittest.TestCase):
    def fake_provider(self, profile="NORTH", path="/tmp/kingdoms-test/provider"):
        obj = Mock()
        obj.lab_name = profile
        obj.path = path
        obj._script.return_value = "/project/scripts/provisioning-routes.sh"
        return obj

    def test_north_uses_exact_scoped_owned_route_command(self):
        obj = self.fake_provider()
        method = route_method()
        with unittest.mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(method(obj))
        self.assertEqual(run.call_args.args[0], [
            "sudo", "-n", "bash", "/project/scripts/provisioning-routes.sh",
            "--north", "enable", "--provider-dir", "/tmp/kingdoms-test/provider",
        ])

    def test_full_kingdoms_command_is_unchanged(self):
        obj = self.fake_provider("GOAD")
        method = route_method()
        with unittest.mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(method(obj))
        self.assertEqual(run.call_args.args[0], [
            "sudo", "bash", "/project/scripts/provisioning-routes.sh", "enable",
        ])

    def test_north_does_not_enable_without_provider_identity(self):
        obj = self.fake_provider(path=None)
        with unittest.mock.patch("subprocess.run") as run:
            self.assertFalse(route_method()(obj))
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
