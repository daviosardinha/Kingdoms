"""NORTH native source is checked inside the existing Kingdoms workspace."""
import shutil
import tempfile
import unittest
from pathlib import Path

from goad.course1_runtime_contract import ProfileNotReady
from goad.north_native_instance import ROOT, inspect_north_instance_assets
from goad.instance import LabInstance
from goad.utils import VMWARE, PROVISIONING_LOCAL


class NorthNativeInstanceTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory(prefix="kingdoms-north-native-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        provider = root / "provider"
        provider.mkdir()
        instance = object.__new__(LabInstance)
        instance.lab_name = "NORTH"
        instance.provider_name = VMWARE
        instance.provisioner_name = PROVISIONING_LOCAL
        instance.ip_range = "10.41.10"
        instance.instance_path = str(root)
        instance.instance_provider_path = str(provider)
        instance.extensions = []
        instance._create_vagrantfile()
        instance._stage_north_vmware_assets()
        shutil.copyfile(ROOT / "ad/NORTH/providers/vmware/inventory",
                        root / "inventory")
        shutil.copyfile(ROOT / "ad/NORTH/data/inventory_disable_vagrant",
                        root / "inventory_disable_vagrant")
        return root, provider

    def test_native_kingdoms_generated_instance_is_recognized(self):
        _, provider = self.fixture()
        result = inspect_north_instance_assets(provider)
        self.assertEqual(result["status"], "NATIVE_INSTANCE_SOURCE_VERIFIED")
        self.assertEqual(len(result["windows_machines"]), 4)
        self.assertFalse(result["runtime_authorized"])

    def test_reject_foreign_mac_before_any_vm_operation(self):
        _, provider = self.fixture()
        path = provider / "Vagrantfile"
        txt = path.read_text()
        self.assertIn("00:50:56:3a:20:10", txt)
        path.write_text(txt.replace("00:50:56:3a:20:10",
                                    "00:50:56:3a:20:ff", 1))
        with self.assertRaisesRegex(ProfileNotReady, "identity differs"):
            inspect_north_instance_assets(provider)

    def test_reject_external_or_modified_provisioning(self):
        root, provider = self.fixture()
        (root / "vagrant/fix_ip.ps1").write_text("Write-Output 'unsafe'")
        with self.assertRaisesRegex(ProfileNotReady, "script drift"):
            inspect_north_instance_assets(provider)

    def test_reject_missing_or_modified_north_inventory(self):
        root, provider = self.fixture()
        (root / "inventory").write_text("[default]\\ndc03\n")
        with self.assertRaisesRegex(ProfileNotReady, "instance asset differs"):
            inspect_north_instance_assets(provider)

    def test_preview_sidecar_cannot_authorize_operations(self):
        _, provider = self.fixture()
        (provider / ".kingdoms-profile.json").write_text(
            '{"profile":"course1-fall-of-the-north","state":"ACTIVE"}')
        with self.assertRaisesRegex(ProfileNotReady, "not approved"):
            inspect_north_instance_assets(provider)

    def test_real_kingdoms_provider_has_fail_closed_north_install_entrypoints(self):
        src = (ROOT / "goad/provider/vagrant/vmware_kingdoms.py").read_text()
        self.assertIn("def _north_runtime_allowed(self):", src)
        self.assertIn("binding.segmented_install_enabled", src)
        for op in ("start", "stop", "start_vm", "stop_vm", "install", "reset",
                   "snapshot", "destroy", "destroy_non_interactive", "destroy_vm"):
            self.assertIn("def " + op + "(", src)
        self.assertIn("if not self._north_runtime_allowed():", src)
        self.assertIn("route_script = self._script('provisioning-routes.sh')", src)
        self.assertIn("kingdoms-north-vmnet-hostaddrs.service", src)
        self.assertIn("is_north = self.lab_name == 'NORTH'", src)

    def test_do_not_write_to_existing_instance(self):
        root, provider = self.fixture()
        before = {str(p.relative_to(root)): p.read_bytes()
                  for p in root.rglob("*") if p.is_file()}
        inspect_north_instance_assets(provider)
        after = {str(p.relative_to(root)): p.read_bytes()
                 for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
