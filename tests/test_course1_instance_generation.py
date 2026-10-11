"""Source-only acceptance for NORTH on the *existing* Kingdoms instance builder.

No VMware/Vagrant operations, systemd writes, host routes, guest creation or AD.
"""
import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from jinja2 import Environment, FileSystemLoader
from goad.course1_artifact_render import render_course1_artifacts
from goad.course1_source_preflight import validate_course1_source

ROOT = Path(__file__).resolve().parents[1]


class StubPaths:
    @staticmethod
    def get_lab_provider_path(lab, provider):
        return str(ROOT / "ad" / lab / "providers" / provider)

    @staticmethod
    def get_lab_data_path(lab):
        return str(ROOT / "ad" / lab / "data")

    @staticmethod
    def get_template_path(provider):
        return str(ROOT / "template" / "provider" / provider)

    @staticmethod
    def get_instance_path(instance_id):
        return str(ROOT / "workspace" / instance_id)

    @staticmethod
    def get_instance_provider_path(instance_id):
        return str(ROOT / "workspace" / instance_id / "provider")


def load_instance_class():
    source = (ROOT / "goad/instance.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef)
               and x.name == "LabInstance")
    namespace = {
        "os": os,
        "sep": os.sep,
        "VMWARE": "vmware",
        "PROVISIONING_VM": "vm",
        "GoadPath": StubPaths,
        "Environment": Environment,
        "FileSystemLoader": FileSystemLoader,
        "render_course1_artifacts": render_course1_artifacts,
        "validate_course1_source": validate_course1_source,
        "Log": Mock(),
        "Utils": SimpleNamespace(get_relative_path=lambda x: str(x)),
    }
    exec(compile(ast.Module(body=[cls], type_ignores=[]),
                 "goad/instance.py", "exec"), namespace)
    return namespace["LabInstance"]


class Course1InstanceGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        cls = load_instance_class()
        self.instance = cls.__new__(cls)
        self.instance.lab_name = "NORTH"
        self.instance.provider_name = "vmware"
        self.instance.provisioner_name = "local"
        self.instance.ip_range = "192.168.56"
        self.instance.extensions = []
        self.instance._course1_artifacts = None
        self.instance.instance_path = str(self.base / "course1-id")
        self.instance.instance_provider_path = str(self.base / "course1-id" / "provider")

    def test_new_course1_instance_normalizes_global_flat_default(self):
        cls = load_instance_class()
        north = cls("north-id", "NORTH", None, "vmware", "local", "192.168.56")
        full = cls("goad-id", "GOAD", None, "vmware", "local", "192.168.56")
        self.assertEqual(north.ip_range, "10.4.0")
        self.assertEqual(full.ip_range, "192.168.56")

    def test_default_settings_resolve_to_kingdoms_10_4(self):
        layout = self.instance._course1_source_artifacts()
        self.assertIn("10.4.10.11", layout["providers/vmware/Vagrantfile"])
        self.assertNotIn("GOAD-DC03", layout["providers/vmware/Vagrantfile"])

    def test_invalid_nondefault_network_fails_before_workspace_exists(self):
        self.instance.ip_range = "10.5.0"
        self.assertFalse(self.instance.create_instance_folder())
        self.assertFalse(Path(self.instance.instance_path).exists())

    def test_different_provider_fails_before_workspace_exists(self):
        self.instance.provider_name = "virtualbox"
        self.assertFalse(self.instance.create_instance_folder())
        self.assertFalse(Path(self.instance.instance_path).exists())

    def test_explicit_default_flat_prefix_keeps_original_lab(self):
        self.instance.ip_range = "10.4.0"
        self.assertIsNotNone(self.instance._course1_source_artifacts())

    def test_one_existing_instance_builder_materializes_coherent_kingdoms_files(self):
        root = Path(self.instance.instance_path)
        provider = Path(self.instance.instance_provider_path)
        provider.mkdir(parents=True)
        self.instance._write_course1_router_artifacts()
        self.instance._create_vagrantfile()
        self.instance._create_provisioning_lab_inventory("inventory_disable_vagrant")
        self.instance._create_provisioning_provider_inventory()

        generated = (provider / "Vagrantfile").read_text()
        self.assertIn(':name => "GOAD-DC01"', generated)
        self.assertIn(':name => "GOAD-WS01"', generated)
        self.assertNotIn(':name => "GOAD-SRV03"', generated)
        self.assertIn("router/provision.sh", generated)
        self.assertNotIn("../../../ad/NORTH/providers/vmware/router/provision.sh", generated)
        self.assertIn("v.enable_vmrun_ip_lookup = false", generated)
        self.assertIn("config.vm.graceful_halt_timeout = 120", generated)
        self.assertEqual((provider / "router" / "provision.sh").read_text(),
                         render_course1_artifacts()["providers/vmware/router/provision.sh"])
        self.assertIn("policy drop;", (provider / "router/nftables/exercise.nft").read_text())
        inventory = (root / "inventory").read_text()
        post = (root / "inventory_disable_vagrant").read_text()
        for name, ip in (("dc01", "10.4.20.10"), ("dc02", "10.4.10.11"),
                         ("srv02", "10.4.10.22"), ("ws01", "10.4.10.31")):
            self.assertIn(f"{name} ansible_host={ip}", inventory)
            self.assertIn(f"{name} ansible_host={ip}", post)

    def test_original_kingdoms_legacy_template_branch_is_preserved(self):
        source = (ROOT / "template/provider/vmware/Vagrantfile").read_text()
        self.assertEqual(source.count("{% if lab_name in ['GOAD', 'NORTH'] %}"), 2)


if __name__ == "__main__":
    unittest.main()
