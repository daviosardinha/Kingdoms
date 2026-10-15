"""Read-only tests of actual Kingdoms LabInstance WSLPE template rendering."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-preview-native-instance.py"
SPEC = importlib.util.spec_from_file_location("wslpe_preview", SCRIPT)
assert SPEC and SPEC.loader
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)


class NativeWslpeInstancePreviewTests(unittest.TestCase):
    def test_reject_north_network_range(self):
        for prefix in ("10.4.10", "10.4.0", "10.4.99"):
            with self.subTest(prefix=prefix):
                with self.assertRaisesRegex(ValueError, "overlap"):
                    PREVIEW.validate_prefix(prefix)

    def test_reject_nonprivate_and_invalid_prefixes(self):
        for prefix in ("8.8.8", "999.168.50", "192.168", "127.0.0", "169.254.1"):
            with self.subTest(prefix=prefix):
                with self.assertRaises(ValueError):
                    PREVIEW.validate_prefix(prefix)

    def test_native_labinstance_preview_outputs_single_standalone_guest(self):
        with tempfile.TemporaryDirectory() as directory:
            preview_root = Path(directory) / "preview"
            summary = PREVIEW.render_preview("172.28.231", preview_root)
            self.assertEqual(summary["guest"], "WSLPE-WS01")
            self.assertEqual(summary["guest_ip"], "172.28.231.31")
            self.assertEqual(summary["candidate_network"], "172.28.231.0/24")
            vm = (preview_root / "provider" / "Vagrantfile").read_text()
            self.assertEqual(vm.count(':name => "WSLPE-WS01"'), 1)
            self.assertNotIn(':name => "GOAD-', vm)
            self.assertIn('target.vm.network :private_network, ip: box[:ip]', vm)
            self.assertIn('guest', summary)

    def test_real_provider_and_post_vagrant_inventories_render(self):
        with tempfile.TemporaryDirectory() as directory:
            preview_root = Path(directory) / "preview"
            PREVIEW.render_preview("172.28.231", preview_root)
            provider = (preview_root / "inventory").read_text()
            post = (preview_root / "inventory_disable_vagrant").read_text()
            initial = (ROOT / "ad/WSLPE/data/inventory").read_text()
            self.assertIn("ws01 ansible_host=172.28.231.31", provider)
            self.assertIn("[wslpe]", initial)
            self.assertIn("[wslpe]", post)
            self.assertIn("[windows_lpe_standalone]", initial)
            self.assertIn("ansible_connection=winrm", initial)

    def test_preview_writes_nothing_to_real_kingdoms_workspace(self):
        from unittest.mock import patch
        from goad.goadpath import GoadPath

        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "should-never-be-created"
            preview = Path(directory) / "preview"
            original = GoadPath.get_instance_path
            try:
                with patch.object(
                    GoadPath, "get_instance_path",
                    return_value=str(sentinel),
                ):
                    PREVIEW.render_preview("172.28.231", preview)
                self.assertFalse(sentinel.exists())
            finally:
                self.assertTrue(preview.exists())


if __name__ == "__main__":
    unittest.main()
