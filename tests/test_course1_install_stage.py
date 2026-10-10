"""Offline validation of sealed Course 1 instance-import staging contracts."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from goad.course1_install_stage import (
    GUARD, PLANNED_WORKSPACE_MAPPING, inspect_bundle,
)
from goad.course1_runtime_contract import ProfileNotReady
from goad.course1_vmware_candidate import render_candidate

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/course1-network-candidate.example.json"
ID = "kingdoms-c1-regress01"


def proposal():
    return json.loads(PLAN.read_text(encoding="utf-8"))


class Course1InstallStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kingdoms-c1-package-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / "noninstallable"
        self.package.mkdir(mode=0o700)
        self.package.chmod(0o700)
        self.artifacts = render_candidate(proposal())
        for rel, content in self.artifacts.items():
            dest = self.package / rel
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            dest.parent.chmod(0o700)
            dest.write_text(content, encoding="utf-8")
            dest.chmod(0o600)

    def check(self):
        return inspect_bundle(self.package, proposal(), ID)

    def test_verified_layout_is_not_installed_or_authorized(self):
        out = self.check()
        self.assertEqual(out["verified_files"], 11)
        self.assertEqual(out["instance_id"], ID)
        self.assertEqual(out["windows_guests"], 4)
        self.assertEqual(out["state"], "STAGED_SOURCE_ONLY_NOT_INSTALLABLE")
        self.assertFalse(out["guest_lifecycle_authorized"])
        self.assertFalse(out["deployment_authorized"])
        self.assertFalse(out["instance_json_created"])
        self.assertFalse(out["vmware_networks_allocated"])
        self.assertEqual(len(out["planned_workspace_files"]), 9)

    def test_vagrantfile_cannot_run_directly(self):
        content = self.artifacts["instance-preview/Vagrantfile"]
        self.assertTrue(content.startswith(GUARD))
        self.assertTrue(content.splitlines()[0].startswith("raise "))

    def test_plan_includes_router_winrm_and_provisioning_layout(self):
        self.assertEqual(PLANNED_WORKSPACE_MAPPING["instance-preview/Vagrantfile"],
                         "provider/Vagrantfile")
        self.assertEqual(PLANNED_WORKSPACE_MAPPING["router/provision.sh"],
                         "router/provision.sh")
        self.assertEqual(PLANNED_WORKSPACE_MAPPING["vagrant/fix_ip.ps1"],
                         "vagrant/fix_ip.ps1")
        self.assertEqual(PLANNED_WORKSPACE_MAPPING["providers/vmware/inventory"],
                         "inventory")
        self.assertNotIn("manifest.json", PLANNED_WORKSPACE_MAPPING)

    def test_tampered_router_provisioner_refused(self):
        file = self.package / "router/provision.sh"
        file.write_text(file.read_text() + "\n# injected\n", encoding="utf-8")
        with self.assertRaisesRegex(ProfileNotReady, "differs"):
            self.check()

    def test_tampered_manifest_refused(self):
        file = self.package / "manifest.json"
        contents = json.loads(file.read_text())
        contents["deployment_authorized"] = True
        file.write_text(json.dumps(contents), encoding="utf-8")
        with self.assertRaisesRegex(ProfileNotReady, "differs"):
            self.check()

    def test_missing_winrm_asset_refused(self):
        (self.package / "vagrant/fix_ip.ps1").unlink()
        with self.assertRaises(ProfileNotReady):
            self.check()

    def test_extra_file_refused(self):
        (self.package / "unexpected.txt").write_text("not allowed")
        with self.assertRaisesRegex(ProfileNotReady, "unexpected"):
            self.check()

    def test_symlink_refused(self):
        original = self.package / "vagrant/fix_ip.ps1"
        copy = self.root / "external-target"
        copy.write_text(original.read_text())
        original.unlink()
        original.symlink_to(copy)
        with self.assertRaisesRegex(ProfileNotReady, "symlink"):
            self.check()

    def test_group_readable_secret_inventory_refused(self):
        (self.package / "data/inventory_disable_vagrant").chmod(0o640)
        with self.assertRaisesRegex(ProfileNotReady, "0600"):
            self.check()

    def test_group_readable_candidate_directory_refused(self):
        (self.package / "data").chmod(0o750)
        with self.assertRaisesRegex(ProfileNotReady, "0700"):
            self.check()

    def test_invalid_instance_identity_refused(self):
        for invalid in ("full-goad", "kingdoms-c1-ABC12345", "kingdoms-c1-x",
                        "../instance", "kingdoms-c1-thisiswaytoolongfortheid000"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ProfileNotReady):
                    inspect_bundle(self.package, proposal(), invalid)

    def test_installed_workspace_marker_refused(self):
        (self.root / "instance.json").write_text("{}")
        with self.assertRaisesRegex(ProfileNotReady, "workspace"):
            self.check()

    def test_proposal_change_cannot_reuse_old_bundle(self):
        altered = proposal()
        altered["machines"]["GOAD-WS01"]["ip"] = "10.41.10.38"
        with self.assertRaises(ProfileNotReady):
            inspect_bundle(self.package, altered, ID)

    def test_cli_produces_read_only_blocked_source_plan(self):
        cmd = [sys.executable, "-m", "goad.course1_install_stage",
               "--check-candidate", str(self.package),
               "--proposal", str(PLAN),
               "--instance-id", ID]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[BLOCKED]", result.stdout)
        self.assertIn('"deployment_authorized": false', result.stdout)
        self.assertFalse((self.package / "instance.json").exists())
        self.assertFalse((self.package / ".vagrant").exists())

    def test_stage_has_no_vm_or_disk_mutating_helpers(self):
        source = (ROOT / "goad/course1_install_stage.py").read_text()
        for forbidden in ("subprocess", "vmrun", "vagrant up", "Path.write_text",
                          "os.system", "shutil.copy"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
