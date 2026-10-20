"""Disposable-only third-NIC source tests. No VMware, Vagrant or host writes."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-disposable-management-preview.py"
spec = importlib.util.spec_from_file_location("wslpe_disposable_nic_preview", SCRIPT)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


@unittest.skipUnless(shutil.which("ruby"), "Ruby required for evaluating real WSLPE recipe")
class DisposableManagementNicTests(unittest.TestCase):
    def test_approved_disposable_candidate_adds_only_slot2(self):
        result = candidate.render_candidate("172.28.231", "172.28.232", "vmnet3")
        self.assertEqual(result["management_subnet"], "172.28.232.0/24")
        self.assertEqual(result["exercise_subnet"], "172.28.231.0/24")
        self.assertEqual(result["extra_adapter_slot"], 2)
        self.assertEqual(result["network_status"], "UNALLOCATED")

    def test_bad_candidate_network_and_reserved_vmnet_rejected(self):
        for exercise, management, vmnet in (
            ("172.28.231", "172.28.231", "vmnet3"),
            ("172.28.231", "10.4.60", "vmnet3"),
            ("172.28.231", "1.2.3", "vmnet3"),
            ("172.28.231", "172.28.999", "vmnet3"),
            ("172.28.231", "172.28.232", "vmnet10"),
            ("172.28.231", "172.28.232", "vmnet99"),
            ("172.28.231", "172.28.232", "vmnet8"),
            ("172.28.231", "172.28.232", "vmnet1"),
            ("172.28.231", "172.28.232", "vmnet bad"),
        ):
            with self.subTest(management=management, vmnet=vmnet):
                with self.assertRaises(ValueError):
                    candidate.render_candidate(exercise, management, vmnet)

    def test_registered_vm_refuses_optin_candidate(self):
        with self.assertRaisesRegex(ValueError, "rejected by Ruby"):
            candidate.render_candidate("172.28.231", "172.28.232", "vmnet3",
                                       existing_registration=True)

    def test_default_wslpe_recipe_remains_two_nic_source(self):
        source = candidate.RECIPE.read_text(encoding="utf-8")
        source = source.replace("{{ip_range}}", "172.28.231")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "Vagrantfile"
            path.write_text(source, encoding="utf-8")
            env = os.environ.copy()
            for key in (candidate.OPTIN, candidate.VNET, candidate.PREFIX):
                env.pop(key, None)
            result = subprocess.run(
                ["ruby", "-rjson", "-e",
                 'eval(File.read(ARGV.fetch(0)) + "\\nputs JSON.generate(boxes)", binding, ARGV.fetch(0))', str(path)],
                cwd=root, env=env, text=True, capture_output=True,
                check=False, timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        box = json.loads(result.stdout)[0]
        self.assertNotIn("vmware_network_adapters", box)
        self.assertEqual(box["ip"], "172.28.231.31")
        self.assertEqual(box["name"], "WSLPE-WS01")

    def test_optin_source_does_not_change_shared_vmware_template(self):
        recipe = candidate.RECIPE.read_text(encoding="utf-8")
        template = (ROOT / "template/provider/vmware/Vagrantfile").read_text()
        self.assertIn('ENV["KINGDOMS_WSLPE_DISPOSABLE_MGMT_NIC"] == "preview"', recipe)
        self.assertIn('boxes[0][:vmware_network_adapters]', recipe)
        self.assertIn('File.exist?(File.join(__dir__, ".vagrant"', recipe)
        self.assertIn('if box.has_key?(:vmware_network_adapters)', template)
        self.assertIn('v.network_adapter(', template)
        self.assertNotIn("KINGDOMS_WSLPE_DISPOSABLE_MGMT_NIC", template)
        self.assertNotIn("KINGDOMS_WSLPE_DISPOSABLE_MGMT_NIC", (
            ROOT / "goad_nomad.py").read_text())

    def test_script_has_no_live_mutating_operations(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("vmrun", source)
        self.assertNotIn('["vagrant",', source)
        self.assertNotIn("nft -f", source)
        self.assertNotIn("sudo", source)
        self.assertNotIn("check=True", source)
        self.assertIn("TemporaryDirectory", source)
        self.assertIn("Ruby", source)


if __name__ == "__main__":
    unittest.main()
