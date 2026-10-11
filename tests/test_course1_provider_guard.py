"""Prove full Kingdoms stays unchanged and unwired NORTH cannot boot."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock

from goad.kingdoms_topology import load_course1_topology

ROOT = Path(__file__).resolve().parents[1]


def load_class(path, name, namespace):
    source = ROOT.joinpath(path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == name)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), path, "exec"), namespace)
    return namespace[name]


class StableKingdomsProvider:
    goad_nomad_windows = ["GOAD-DC01", "GOAD-DC02", "GOAD-DC03",
                          "GOAD-SRV02", "GOAD-SRV03", "GOAD-WS01"]

    def __init__(self, lab_name):
        self.lab_name = lab_name


class ProviderInputTests(unittest.TestCase):
    def make(self, lab):
        cls = load_class("goad/provider/vagrant/vmware_nomad.py",
                         "GoadNomadVmwareProvider", {
                             "VmwareProvider": StableKingdomsProvider,
                             "load_course1_topology": load_course1_topology,
                         })
        return cls(lab)

    def test_full_kingdoms_preserves_six_guest_roster(self):
        provider = self.make("GOAD")
        self.assertEqual(provider.goad_nomad_windows, StableKingdomsProvider.goad_nomad_windows)
        self.assertEqual(len(provider.management_hosts), 6)
        self.assertEqual(len(provider.network_zones), 4)
        self.assertIn(("ESSOS", "vmnet30", "10.4.30.0/24"), provider.network_zones)

    def test_course1_reuses_same_provider_with_four_guest_roster(self):
        provider = self.make("NORTH")
        self.assertEqual(provider.goad_nomad_windows,
                         ["GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"])
        self.assertEqual(provider.management_hosts["GOAD-DC02"], "10.4.10.11")
        self.assertEqual(provider.management_hosts["GOAD-DC01"], "10.4.20.10")
        self.assertEqual(len(provider.management_hosts), 4)
        self.assertEqual(set(zone[1] for zone in provider.network_zones),
                         {"vmnet10", "vmnet20", "vmnet99"})
        self.assertNotIn("ESSOS", str(provider.network_zones))

    def test_another_kingdoms_lab_does_not_mutate_shared_defaults(self):
        north = self.make("NORTH")
        full = self.make("GOAD")
        self.assertEqual(len(north.goad_nomad_windows), 4)
        self.assertEqual(len(full.goad_nomad_windows), 6)
        self.assertEqual(len(StableKingdomsProvider.goad_nomad_windows), 6)


class GuardBase:
    def __init__(self):
        self.calls = []
        self.lab_name = "NORTH"

    def install(self):
        self.calls.append("install")
        return True

    def start(self, vm_name=None):
        self.calls.append("start")
        return True

    def start_vm(self, vm_name):
        self.calls.append("start_vm")
        return True

    def reset(self):
        self.calls.append("reset")
        return True

    def prepare_install(self):
        self.calls.append("prepare_install")
        return True

    def prepare_provisioning(self):
        self.calls.append("prepare_provisioning")
        return True


class UnsafeInstallGuardTests(unittest.TestCase):
    def test_north_cannot_touch_vagrant_or_ansible_yet(self):
        cls = load_class("goad/provider/vagrant/vmware_kingdoms.py",
                         "GoadKingdomsVmwareProvider", {
                             "GoadNomadVmwareProvider": GuardBase,
                             "Log": Mock(),
                         })
        provider = cls()
        self.assertIs(provider.install(), False)
        self.assertIs(provider.start(), False)
        self.assertIs(provider.start_vm("GOAD-DC01"), False)
        self.assertIs(provider.reset(), False)
        self.assertIs(provider.prepare_install(), False)
        self.assertIs(provider.prepare_provisioning(), False)
        self.assertEqual(provider.calls, [])

    def test_other_provider_start_still_delegates_normally(self):
        cls = load_class("goad/provider/vagrant/vmware_kingdoms.py",
                         "GoadKingdomsVmwareProvider", {
                             "GoadNomadVmwareProvider": GuardBase,
                             "Log": Mock(),
                         })
        provider = cls()
        provider.lab_name = "GOAD"
        self.assertTrue(provider.start())
        self.assertEqual(provider.calls, ["start"])


if __name__ == "__main__":
    unittest.main()
