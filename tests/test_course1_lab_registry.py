"""Native Kingdoms console discovery: NORTH is selectable but NOT deployable."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from goad.course_catalog import course_manifest, is_course_lab, refuse_course_mutation
from goad.labs import Lab
from goad.lab_manager import LabManager
from goad.instance import LabInstance
from goad.provider.course_preview import PreviewCourseProvider
from goad.provider.provider_factory import ProviderFactory
from goad.settings import Settings


class NorthNativeLabTests(unittest.TestCase):
    def test_north_discovery_does_not_import_runtime_credential_stacks(self):
        # A fresh Python interpreter must be able to discover an unreleased
        # course without importing its live WinRM or ansible-runner clients.
        # This is the bug reported on Kali Python 3.14 (no winrm package).
        import subprocess
        import sys
        script = """
import builtins
original = builtins.__import__
def deny_credential_clients(name, *args, **kwargs):
    if name.split('.')[0] in ('winrm', 'ansible_runner'):
        raise RuntimeError('preview discovery imported live client: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = deny_credential_clients
from goad.labs import Lab
from goad.provider.course_preview import PreviewCourseProvider
lab = Lab('NORTH', None)
assert isinstance(lab.get_provider('vmware'), PreviewCourseProvider)
assert lab.get_first_provider_name() == 'vmware'
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, check=False, timeout=20
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_north_metadata_matches_course_one(self):
        m = course_manifest("NORTH")
        self.assertEqual(m["lab"], "NORTH")
        self.assertEqual(m["kingdoms_foundation"], "kingdoms-foundation-v1")
        self.assertEqual(m["title"], "Fall of the North")
        self.assertEqual(m["runtime_profile"], "course1-fall-of-the-north")
        self.assertEqual(m["state"], "PREVIEW_ONLY_NOT_INSTALLABLE")
        self.assertEqual(m["providers"], {"vmware": "preview"})
        self.assertTrue(is_course_lab("NORTH"))
        self.assertFalse(is_course_lab("GOAD"))

    def test_north_uses_standard_native_lab_provider_discovery(self):
        lab = Lab("NORTH", None)
        self.assertIn("vmware", lab.providers)
        self.assertIsInstance(lab.get_provider("vmware"), PreviewCourseProvider)
        self.assertIsNone(lab.get_provider("ludus"))
        self.assertEqual(lab.lab_name, "NORTH")
        self.assertEqual(lab.get_first_provider_name(), "vmware")

    def test_set_lab_native_selection(self):
        lab = Lab("NORTH", None)
        manager = SimpleNamespace(
            is_lab_exist=lambda name: name == "NORTH",
            get_lab=lambda name: lab if name == "NORTH" else None,
        )
        settings = Settings(manager)
        settings.set_lab_name("NORTH")
        self.assertEqual(settings.lab_name, "NORTH")
        self.assertEqual(settings.provider_name, "vmware")
        self.assertEqual(settings.provisioner_name, "local")

    def test_provider_refuses_all_vm_lifecycle_actions(self):
        provider = ProviderFactory.get_provider("vmware", "NORTH", None)
        self.assertIsInstance(provider, PreviewCourseProvider)
        self.assertFalse(provider.check())
        self.assertFalse(provider.install())
        self.assertFalse(provider.start())
        self.assertFalse(provider.stop())
        self.assertFalse(provider.destroy())
        self.assertFalse(provider.destroy_non_interactive())
        self.assertFalse(provider.reset())
        self.assertFalse(provider.snapshot())
        self.assertFalse(provider.start_vm("GOAD-WS01"))
        self.assertFalse(provider.stop_vm("GOAD-WS01"))
        self.assertFalse(provider.destroy_vm("GOAD-WS01"))
        self.assertFalse(provider.status())

    def test_registry_lists_north_as_preview_not_available(self):
        from goad.infos import show_labs_providers_table
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_labs_providers_table([Lab("NORTH", None)])
        text = buf.getvalue()
        self.assertIn("NORTH", text)
        self.assertIn("preview", text.lower())

    def test_manager_blocks_instance_creation_before_instantiation(self):
        manager = LabManager()
        previous = manager.current_settings
        manager.current_settings = SimpleNamespace(lab_name="NORTH")
        self.addCleanup(setattr, manager, "current_settings", previous)
        with patch("goad.lab_manager.LabInstance") as ctor:
            self.assertFalse(manager.create_instance())
            ctor.assert_not_called()

    def test_direct_instance_folder_create_is_blocked_without_writes(self):
        with tempfile.TemporaryDirectory(prefix="kingdoms-native-north-") as dirname:
            instance = object.__new__(LabInstance)
            instance.lab_name = "NORTH"
            instance.instance_path = str(Path(dirname) / "forbidden-instance")
            self.assertFalse(instance.create_instance_folder())
            self.assertFalse(Path(instance.instance_path).exists())

    def test_console_mutating_entrypoints_refuse_north_without_sudo(self):
        from goad_nomad import GoadNomad
        console = object.__new__(GoadNomad)
        console.lab_manager = SimpleNamespace(
            get_current_lab_name=lambda: "NORTH",
        )
        for method, arg in [
            ("do_create", ""), ("do_create", "--non-interactive"),
            ("do_install", ""), ("do_create_empty", ""),
            ("do_install_instance", ""), ("do_provide", ""),
            ("do_provision_lab", ""), ("do_provision", "main.yml"),
            ("do_provision_lab_from", "main.yml"), ("do_ws01", ""),
        ]:
            with self.subTest(action=method):
                self.assertIs(getattr(console, method)(arg), False)

    def test_goa_d_legacy_cannot_be_reinterpreted_as_course_one(self):
        self.assertIsNone(course_manifest("GOAD"))
        self.assertFalse(refuse_course_mutation("GOAD", "start"))
        # Prove legacy dispatch still chooses the actual Kingdoms VMware
        # implementation WITHOUT importing live WinRM/VMware dependencies.
        import sys
        from types import ModuleType
        name = "goad.provider.vagrant.vmware_kingdoms_profile"
        mock_module = ModuleType(name)
        class LegacyKingdomsProvider:
            def __init__(self, lab_name):
                self.lab_name = lab_name
        mock_module.ProfiledGoadKingdomsVmwareProvider = LegacyKingdomsProvider
        with patch.dict(sys.modules, {name: mock_module}):
            existing = ProviderFactory.get_provider("vmware", "GOAD", None)
        self.assertIsInstance(existing, LegacyKingdomsProvider)
        self.assertEqual(existing.lab_name, "GOAD")
        self.assertNotIsInstance(existing, PreviewCourseProvider)

    def test_future_course_only_requires_native_manifest_and_provider_folder(self):
        # This verifies the generic format without registering a fake course
        # in the repository or claiming a future course as installable.
        from goad import course_catalog
        with tempfile.TemporaryDirectory(prefix="kingdoms-catalog-") as root:
            folder = Path(root) / "FUTURE"
            (folder / "providers/vmware").mkdir(parents=True)
            (folder / "course.json").write_text(json.dumps({
                "lab": "FUTURE", "title": "Future Campaign",
                "kingdoms_foundation": "kingdoms-foundation-v1",
                "runtime_profile": "course2", "state": "PREVIEW_ONLY_NOT_INSTALLABLE",
                "providers": {"vmware": "preview"},
            }), encoding="utf-8")
            with patch.object(course_catalog.GoadPath, "get_lab_path",
                              side_effect=lambda name: str(Path(root) / name)):
                self.assertEqual(course_catalog.course_manifest("FUTURE")["lab"],
                                 "FUTURE")
                self.assertTrue(course_catalog.refuse_course_mutation("FUTURE", "install"))
                unsupported = json.loads((folder / "course.json").read_text())
                unsupported["kingdoms_foundation"] = "upstream-goad"
                (folder / "course.json").write_text(json.dumps(unsupported))
                with self.assertRaisesRegex(
                    course_catalog.CourseCatalogError, "patched Kingdoms foundation"
                ):
                    course_catalog.course_manifest("FUTURE")


if __name__ == "__main__":
    unittest.main()
