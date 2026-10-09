"""Regression: one patched Kingdoms VMware provider, two isolated identities."""
import unittest
from dataclasses import replace

from goad.kingdoms_vmware_profile import (
    REFERENCE, KingdomsVMwareBinding, binding_for, north_binding,
)
from goad.course1_runtime_contract import FULL_WINDOWS, COURSE1_WINDOWS


class NativeKingdomsVMwareProfileTests(unittest.TestCase):
    def test_existing_kingdoms_reference_unchanged(self):
        b = binding_for("GOAD")
        self.assertIs(b, REFERENCE)
        self.assertEqual(b.roster.windows, FULL_WINDOWS)
        self.assertEqual(b.roster.management_hosts["GOAD-DC03"], "10.4.30.12")
        self.assertEqual(b.router_management, "10.4.99.1")
        self.assertEqual(tuple(z[1] for z in b.zones),
                         ("vmnet10", "vmnet20", "vmnet30", "vmnet99"))
        self.assertTrue(b.segmented_install_enabled)

    def test_north_is_four_guest_independent_profile(self):
        b = north_binding()
        self.assertEqual(b.lab, "NORTH")
        self.assertEqual(b.roster.windows, COURSE1_WINDOWS)
        self.assertEqual(b.roster.management_hosts, {
            "GOAD-DC01": "10.41.20.10",
            "GOAD-DC02": "10.41.10.11",
            "GOAD-SRV02": "10.41.10.22",
            "GOAD-WS01": "10.41.10.31",
        })
        self.assertEqual(tuple(z[1] for z in b.zones),
                         ("vmnet11", "vmnet12", "vmnet13"))
        self.assertEqual(b.router_management, "10.41.99.1")
        self.assertEqual(b.north_host, "10.41.10.254")
        self.assertEqual(b.management_host, "10.41.99.254")
        self.assertFalse(b.segmented_install_enabled)

    def test_north_topological_dependencies_preserved(self):
        b = binding_for("NORTH")
        self.assertEqual(b.roster.requested_start("GOAD-WS01"),
                         ("GOAD-DC01", "GOAD-DC02", "GOAD-WS01"))
        self.assertEqual(b.roster.ordered_stop(),
                         ("GOAD-WS01", "GOAD-SRV02", "GOAD-DC02", "GOAD-DC01"))

    def test_unknown_legacy_labs_do_not_receive_north_binding(self):
        self.assertIsNone(binding_for("GOAD-Light"))
        self.assertIsNone(binding_for("DRACARYS"))
        self.assertIsNone(binding_for("TEMPLATE"))

    def test_network_collisions_and_early_activation_fail_closed(self):
        b = north_binding()
        with self.assertRaisesRegex(ValueError, "not authorized"):
            replace(b, segmented_install_enabled=True)
        with self.assertRaisesRegex(ValueError, "must be unique"):
            replace(b, zones=(b.zones[0], (b.zones[1][0], b.zones[0][1], b.zones[1][2])))

    def test_patched_provider_has_a_profile_binding_hook(self):
        from pathlib import Path
        from goad.kingdoms_vmware_profile import ROOT
        source = (ROOT / "goad/provider/vagrant/vmware_nomad.py").read_text()
        self.assertIn("binding = binding_for(lab_name)", source)
        self.assertIn("self.goad_nomad_windows = list(binding.roster.windows)", source)
        self.assertIn("self.management_hosts = dict(binding.roster.management_hosts)", source)
        # Until production lifecycle is ready, installing NORTH must remain
        # impossible in the native console.
        self.assertIn("if self.lab_name == 'GOAD':", source)
        self.assertIn("binding.segmented_install_enabled", source)


if __name__ == "__main__":
    unittest.main()
