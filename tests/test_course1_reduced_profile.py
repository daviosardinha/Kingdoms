"""Source-level gates for non-deployable Course 1 recipe preview."""
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "course1" / "generate-profile.py"
SOURCE = ROOT / "ad" / "GOAD"


def call(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True, cwd=ROOT)


class ReducedProfileTests(unittest.TestCase):
    def test_check_is_read_only(self):
        result = call("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("4 Windows VMs + router", result.stdout)
        self.assertIn("No installed VMware guest", result.stdout)

    def test_output_is_opt_in_and_contains_private_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "preview"
            refused = call("--output", dest)
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse(dest.exists())
            built = call("--output", dest, "--acknowledge-lab-credentials")
            self.assertEqual(built.returncode, 0, built.stderr)
            manifest = json.loads((dest / "manifest.json").read_text())
            self.assertEqual(manifest["state"], "PREVIEW_ONLY_NOT_INSTALLABLE")
            self.assertEqual(manifest["windows_machines"],
                             ["GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"])
            recipe = json.loads((dest / "data/config.json").read_text())["lab"]
            self.assertEqual(set(recipe["hosts"]), {"dc01", "dc02", "srv02", "ws01"})
            self.assertEqual(set(recipe["domains"]),
                             {"sevenkingdoms.local", "north.sevenkingdoms.local"})
            self.assertEqual(recipe["domains"]["sevenkingdoms.local"]["trust"], "")
            self.assertEqual(recipe["hosts"]["srv02"]["mssql"]["linked_servers"], {})
            self.assertFalse((dest / "data/config.json").stat().st_mode & 0o077)
            self.assertFalse(dest.stat().st_mode & 0o077)
            for item in dest.rglob("*"):
                if item.is_file():
                    self.assertFalse(item.stat().st_mode & 0o077)
            vagrant = (dest / "providers/vmware/Vagrantfile").read_text()
            self.assertEqual(vagrant.count(':name => "GOAD-'), 5)
            self.assertNotIn('"GOAD-SRV03"', vagrant)
            self.assertNotIn('"GOAD-DC03"', vagrant)
            self.assertIn('GOAD-ROUTER', vagrant)
            self.assertIn("vmnet30", vagrant)  # legacy router NIC still present
            inventory = (dest / "data/inventory").read_text()
            self.assertNotIn("\nsrv03", inventory)
            self.assertNotIn("\ndc03", inventory)
            disabled = (dest / "data/inventory_disable_vagrant").read_text()
            self.assertEqual(len([ln for ln in disabled.splitlines()
                                  if ln.startswith("ws01 ansible_host=10.4.10.31 ")]), 1)
            srv02 = next(ln for ln in disabled.splitlines()
                         if ln.startswith("srv02 ansible_host="))
            ws01 = next(ln for ln in disabled.splitlines()
                        if ln.startswith("ws01 ansible_host="))
            self.assertIn("dns_domain=dc02 dict_key=ws01", ws01)
            self.assertEqual(srv02.split("ansible_user=", 1)[-1],
                             ws01.split("ansible_user=", 1)[-1])
            instance = (dest / "instance-preview/Vagrantfile").read_text()
            self.assertIn('Vagrant.configure("2") do |config|', instance)
            self.assertIn('config.vm.box_check_update = false', instance)
            self.assertIn('config.vm.define box[:name]', instance)
            self.assertEqual(instance.count(':name => "GOAD-'), 5)
            self.assertNotIn('GOAD-SRV03', instance)
            self.assertNotIn('GOAD-DC03', instance)
            no_overwrite = call("--output", dest, "--acknowledge-lab-credentials")
            self.assertNotEqual(no_overwrite.returncode, 0)

    def test_git_checkout_cannot_be_used_as_output(self):
        refused = call("--output", ROOT / "profiles/course1-test",
                       "--acknowledge-lab-credentials")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("outside the Git repository", refused.stderr)

    def test_post_vagrant_ws01_uses_canonical_provider_ip(self):
        functions = runpy.run_path(str(SCRIPT))
        disabled = (SOURCE / "data/inventory_disable_vagrant").read_text()
        provider = (SOURCE / "providers/vmware/inventory").read_text()
        result = functions["build_post_vagrant_inventory"](disabled, provider)
        self.assertEqual(sum(line.startswith("ws01 ansible_host=10.4.10.31 ")
                             for line in result.splitlines()), 1)

    def test_changed_ws01_provider_endpoint_is_rejected(self):
        functions = runpy.run_path(str(SCRIPT))
        disabled = (SOURCE / "data/inventory_disable_vagrant").read_text()
        provider = (SOURCE / "providers/vmware/inventory").read_text()
        changed = provider.replace("ws01 ansible_host=10.4.10.31",
                                   "ws01 ansible_host=10.4.10.99")
        self.assertNotEqual(provider, changed)
        with self.assertRaisesRegex(ValueError, "Unexpected canonical WS01 address"):
            functions["build_post_vagrant_inventory"](disabled, changed)

    def test_source_unmodified_by_check(self):
        paths = [SOURCE / "data/config.json",
                 SOURCE / "data/inventory",
                 SOURCE / "providers/vmware/Vagrantfile"]
        before = [p.read_bytes() for p in paths]
        self.assertEqual(call("--check").returncode, 0)
        self.assertEqual(before, [p.read_bytes() for p in paths])


if __name__ == "__main__":
    unittest.main()
