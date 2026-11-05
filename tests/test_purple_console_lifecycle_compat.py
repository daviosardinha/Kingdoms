"""PURPLE console lifecycle must bypass stale local Vagrant VMware code.

Tests the Kingdoms provider override independently of the (possibly locally
modified) base provider file. No VMware VM is changed in CI.
"""
import ast
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
import unittest

SRC = Path(__file__).resolve().parents[1] / "goad/provider/vagrant/vmware_kingdoms.py"


def extract_runtime():
    tree = ast.parse(SRC.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "GoadKingdomsVmwareProvider")
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in ("start", "stop", "start_vm", "stop_vm")]
    assert len(methods) == 4
    # Assemble only the relevant override methods. The base intentionally
    # raises: if PURPLE falls back to a legacy start/stop, test must fail.
    base = type("LegacyVmwareBase", (), {
        name: lambda self, *a, **k: (_ for _ in ()).throw(
            AssertionError("PURPLE used legacy Vagrant lifecycle"))
        for name in ("start", "stop", "start_vm", "stop_vm")
    })
    node = ast.ClassDef(
        name="SelectedKingdomsProvider", bases=[ast.Name(id="LegacyVmwareBase", ctx=ast.Load())],
        keywords=[], body=methods, decorator_list=[])
    ast.fix_missing_locations(node)
    scope = {
        "__name__": "purple_console_lifecycle_offline",
        "LegacyVmwareBase": base,
        "Log": SimpleNamespace(error=lambda *_: None)
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SRC), "exec"), scope)
    return scope["SelectedKingdomsProvider"]


class PurpleConsoleLifecycleTests(unittest.TestCase):
    def setUp(self):
        cls = extract_runtime()
        self.p = cls()
        self.p.lab_name = "PURPLE"
        self.p.path = Path("/workspace/ef5c0b-purple-vmware/provider")
        self.p._course1_unwired = Mock(return_value=False)
        self.start = Mock(return_value=True)
        self.stop = Mock(return_value=True)
        stub = ModuleType("goad.purple_existing_start")
        stub.start_existing_purple = self.start
        stub.stop_existing_purple = self.stop
        self.inserted = patch.dict(sys.modules, {"goad.purple_existing_start": stub})
        self.inserted.start()

    def tearDown(self):
        self.inserted.stop()

    def test_console_start_uses_direct_lifecycle(self):
        self.assertTrue(self.p.start())
        self.start.assert_called_once_with(self.p.path, vm_name=None)
        self.stop.assert_not_called()

    def test_console_stop_uses_direct_lifecycle(self):
        self.assertTrue(self.p.stop())
        self.stop.assert_called_once_with(self.p.path)
        self.start.assert_not_called()

    def test_single_vm_start_and_stop_stay_scoped(self):
        self.assertTrue(self.p.start_vm("PURPLE-LX01"))
        self.start.assert_called_once_with(self.p.path, vm_name="PURPLE-LX01")
        self.assertTrue(self.p.stop_vm("PURPLE-LX01"))
        self.stop.assert_called_once_with(self.p.path, vm_name="PURPLE-LX01")

    def test_missing_provider_refuses_without_legacy_fallback(self):
        self.p.path = None
        self.assertFalse(self.p.start())
        self.assertFalse(self.p.stop())
        self.assertFalse(self.p.stop_vm("PURPLE-WS01"))
        self.assertFalse(self.p.start_vm("PURPLE-WS01"))
        self.start.assert_not_called()
        self.stop.assert_not_called()

    def test_north_and_kingdoms_methods_remain_outside_purple_guard(self):
        src = SRC.read_text()
        self.assertIn("if self.lab_name not in ('GOAD', 'NORTH'):", src)
        self.assertEqual(src.count("if self.lab_name == 'PURPLE':"), 4)
        self.assertEqual(src.count("from goad.purple_existing_start import"), 3)


if __name__ == "__main__":
    unittest.main()
