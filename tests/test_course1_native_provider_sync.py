"""NORTH must retain its four-host inventories in the original VMware provider.

Tests execute only selected provider methods with temporary filesystem fixtures.
No VMware/Vagrant/Ansible operation is performed.
"""
import ast
import os
from pathlib import Path
import re
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
VMWARE = ROOT / "goad/provider/vagrant/vmware.py"


def provider_method(name):
    tree = ast.parse(VMWARE.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "VmwareProvider")
    method = next(node for node in cls.body
                  if isinstance(node, ast.FunctionDef) and node.name == name)
    paths = SimpleNamespace(
        get_lab_provider_path=lambda lab, backend: str(ROOT / "ad" / lab / "providers" / backend),
        get_lab_data_path=lambda lab: str(ROOT / "ad" / lab / "data"),
    )
    scope = {"os": os, "re": re, "shutil": shutil, "Log": Mock(), "GoadPath": paths}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(VMWARE), "exec"), scope)
    return scope[name]


class NorthProviderSyncTests(unittest.TestCase):
    def test_north_inventory_sync_never_imports_essos_hosts(self):
        with tempfile.TemporaryDirectory() as folder:
            provider_dir = Path(folder) / "provider"
            provider_dir.mkdir()
            for name in ("inventory", "inventory_disable_vagrant"):
                (Path(folder) / name).write_text("obsolete", encoding="utf-8")
            provider = SimpleNamespace(lab_name="NORTH", path=str(provider_dir))
            self.assertTrue(provider_method("_sync_goad_nomad_inventories")(provider))
            for name in ("inventory", "inventory_disable_vagrant"):
                content = (Path(folder) / name).read_text(encoding="utf-8")
                self.assertIn("ws01", content)
                self.assertIn("dc01", content)
                self.assertIn("dc02", content)
                self.assertIn("srv02", content)
                self.assertNotIn("essos.local", content.lower())
                self.assertNotIn("srv03 ", content.lower())
                self.assertNotIn("dc03 ", content.lower())

    def test_north_vagrantfile_compatibility_never_injects_six_host_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Vagrantfile"
            content = ' '.join((
                "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02",
                "GOAD-WS01", "GOAD-ROUTER",
            ))
            path.write_text(content, encoding="utf-8")
            provider = SimpleNamespace(lab_name="NORTH", path=folder)
            sync = provider_method("_sync_goad_nomad_vagrantfile_compatibility")
            self.assertTrue(sync(provider))
            self.assertEqual(path.read_text(encoding="utf-8"), content)
            path.write_text(content + " GOAD-SRV03", encoding="utf-8")
            self.assertFalse(sync(provider))

    def test_original_goad_compatibility_branches_preserved(self):
        source = VMWARE.read_text(encoding="utf-8")
        self.assertIn("get_lab_provider_path('GOAD', 'vmware')", source)
        self.assertIn("GoadPath.get_lab_data_path('GOAD')", source)
        self.assertIn("GOAD-WS01", source)


if __name__ == "__main__":
    unittest.main()
