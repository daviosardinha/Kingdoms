"""NORTH is a native lab recipe, derived from the patched Kingdoms base.

These tests validate the files actually discoverable by the existing
./goad.sh path. They do NOT authorize install; the six-guest lifecycle still
needs profile-aware route/AD/WinRM and isolation bindings.
"""
import json
import re
import unittest
from pathlib import Path

from goad.course_catalog import course_manifest
from goad.kingdoms_foundation import FOUNDATION_ID

ROOT = Path(__file__).resolve().parents[1]
NORTH = ROOT / "ad" / "NORTH"
VM = NORTH / "providers" / "vmware"


class NorthNativeRecipeTests(unittest.TestCase):
    def test_consolidated_validation_runner_includes_this_module(self):
        validator = (ROOT / "scripts/course1/validate-course1.sh").read_text()
        self.assertIn("tests.test_course1_native_recipe", validator)

    def test_native_lab_is_selected_through_standard_kingdoms_paths(self):
        from goad.goadpath import GoadPath
        self.assertEqual(
            Path(GoadPath.get_lab_provider_path("NORTH", "vmware")),
            VM,
        )
        self.assertTrue((VM / "Vagrantfile").is_file())
        self.assertTrue((NORTH / "data" / "inventory").is_file())
        self.assertEqual(course_manifest("NORTH")["kingdoms_foundation"],
                         FOUNDATION_ID)

    def test_native_recipe_has_four_windows_and_one_router(self):
        text = (VM / "Vagrantfile").read_text()
        roster = re.findall(r':name\s*=>\s*"([^"]+)"', text)
        self.assertEqual(roster, [
            "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02",
            "GOAD-WS01", "GOAD-ROUTER",
        ])
        self.assertEqual(text.count(":vmware_network_adapters"), 5)
        self.assertNotIn("vmnet30", text)
        self.assertNotIn("GOAD-DC03", text)
        self.assertNotIn("GOAD-SRV03", text)
        for vmnet in ("vmnet11", "vmnet12", "vmnet13"):
            self.assertIn(vmnet, text)
        self.assertIn("../router/provision.sh", text)

    def test_native_network_identities_are_isolated_from_reference(self):
        text = (VM / "Vagrantfile").read_text()
        self.assertNotRegex(text, r"\b10\.4\.")
        for address in ("10.41.20.10", "10.41.10.11",
                        "10.41.10.22", "10.41.10.31"):
            self.assertIn(address, text)
        for reserved in ("00:50:56:3a:20:10", "00:50:56:3a:10:11",
                         "00:50:56:3a:10:22", "00:50:56:3a:10:31"):
            self.assertIn(reserved, text)

    def test_native_ad_data_is_reduced_to_parent_and_north(self):
        lab = json.loads((NORTH / "data" / "config.json").read_text())["lab"]
        self.assertEqual(set(lab["hosts"]), {"dc01", "dc02", "srv02", "ws01"})
        self.assertEqual(set(lab["domains"]),
                         {"sevenkingdoms.local", "north.sevenkingdoms.local"})
        self.assertEqual(lab["domains"]["sevenkingdoms.local"]["trust"], "")
        self.assertEqual(lab["hosts"]["srv02"]["mssql"]["linked_servers"], {})

    def test_native_inventory_preserves_domain_scope_and_ip_translation(self):
        source = (NORTH / "data" / "inventory").read_text()
        post = (NORTH / "data" / "inventory_disable_vagrant").read_text()
        provider = (VM / "inventory").read_text()
        for text in (source, post):
            self.assertIn("domain_name=NORTH", text)
        for text in (post, provider):
            for addr in ("10.41.20.10", "10.41.10.11",
                         "10.41.10.22", "10.41.10.31"):
                self.assertIn("ansible_host=" + addr, text)
            self.assertNotRegex(text, r"10\.4\.")
            self.assertNotRegex(text, r"\b(dc03|srv03)\b")
        self.assertIn("lab_gateway=10.41.10.1", provider)

    def test_native_router_is_three_zone_default_deny(self):
        text = (VM / "router" / "provision.sh").read_text()
        self.assertEqual(text.count('configure_lab_interface "'), 3)
        self.assertIn("policy drop;", text)
        self.assertNotIn('configure_lab_interface "ESSOS"', text)
        self.assertNotRegex(text, r"10\.4\.")
        for gateway in ("10.41.10.1", "10.41.20.1", "10.41.99.1"):
            self.assertIn(gateway, text)
        self.assertNotIn("goad-nomad-vmnet-hostaddrs", text)

    def test_native_instance_assets_are_staged_inside_its_own_workspace(self):
        import tempfile
        from goad.instance import LabInstance
        with tempfile.TemporaryDirectory(prefix="kingdoms-north-assets-") as tmp:
            instance = object.__new__(LabInstance)
            instance.lab_name = "NORTH"
            instance.instance_path = tmp
            instance._stage_north_vmware_assets()
            expected = (
                "router/provision.sh",
                "vagrant/fix_ip.ps1",
                "vagrant/ConfigureRemotingForAnsible.ps1",
                "vagrant/Install-WMF3Hotfix.ps1",
            )
            for item in expected:
                self.assertTrue((Path(tmp) / item).is_file())
            windows = (Path(tmp) / "vagrant" / "fix_ip.ps1").read_text()
            self.assertIn("10.41.0.0", windows)
            self.assertNotIn("10.4.0.0", windows)
            # Idempotent staging never changes already staged files.
            instance._stage_north_vmware_assets()

    def test_actual_kingdoms_vagrant_builder_uses_north_local_winrm_assets(self):
        import tempfile
        from goad.instance import LabInstance
        from goad.utils import VMWARE, PROVISIONING_LOCAL
        with tempfile.TemporaryDirectory(prefix="kingdoms-north-vagrant-") as temp:
            instance = object.__new__(LabInstance)
            instance.lab_name = "NORTH"
            instance.provider_name = VMWARE
            instance.provisioner_name = PROVISIONING_LOCAL
            instance.ip_range = "10.41.10"
            instance.instance_path = temp
            instance.instance_provider_path = str(Path(temp) / "provider")
            instance.extensions = []
            Path(instance.instance_provider_path).mkdir()
            instance._create_vagrantfile()
            instance._stage_north_vmware_assets()
            content = (Path(instance.instance_provider_path) / "Vagrantfile").read_text()
            self.assertEqual(content.count("../vagrant/"), 4)
            self.assertNotIn("../../../vagrant/", content)
            self.assertIn("config.vm.box_check_update = false", content)
            self.assertIn("config.vm.graceful_halt_timeout = 120", content)
            self.assertIn("v.enable_vmrun_ip_lookup = false", content)
            for name in ("fix_ip.ps1", "ConfigureRemotingForAnsible.ps1",
                         "Install-WMF3Hotfix.ps1"):
                self.assertIn("../vagrant/" + name, content)
                self.assertTrue((Path(temp) / "vagrant" / name).is_file())
            for forbidden in ("GOAD-DC03", "GOAD-SRV03", "vmnet30"):
                self.assertNotIn(forbidden, content)

    def test_existing_reference_template_keeps_original_provisioning_paths(self):
        from jinja2 import Environment, StrictUndefined
        template = (ROOT / "template/provider/vmware/Vagrantfile").read_text()
        rendered = Environment(undefined=StrictUndefined, autoescape=False).from_string(
            template
        ).render(lab="boxes = []", lab_name="GOAD", provider_name="vmware",
                 ip_range="10.4.10", extensions="", use_provisioning_vm=False)
        self.assertEqual(rendered.count("../../../vagrant/"), 4)
        self.assertNotIn("../vagrant/Install-WMF3Hotfix.ps1", rendered.replace("../../../vagrant/", ""))
        self.assertIn("config.vm.box_check_update = false", rendered)
        self.assertIn("config.vm.graceful_halt_timeout = 120", rendered)

    def test_install_guard_remains_until_lifecycle_verified(self):
        from goad.course_catalog import refuse_course_mutation
        self.assertTrue(refuse_course_mutation("NORTH", "install"))
        from goad.provider.course_preview import PreviewCourseProvider
        from goad.provider.provider_factory import ProviderFactory
        provider = ProviderFactory.get_provider("vmware", "NORTH", None)
        self.assertIsInstance(provider, PreviewCourseProvider)
        self.assertFalse(provider.install())


if __name__ == "__main__":
    unittest.main()
