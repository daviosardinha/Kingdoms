"""Course 1 isolated preview gate: source and workspace safety, offline only."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goad.course1_runtime_contract import COURSE1, ProfileNotReady
from goad.course1_source_gate import (
    PROJECT, GENERATOR, inspect_source_preview, _generator_render,
)

class Course1SourceIsolationTests(unittest.TestCase):
    def make_preview(self, parent=None):
        temp = tempfile.TemporaryDirectory() if parent is None else None
        if temp is not None:
            self.addCleanup(temp.cleanup)
            root = Path(temp.name) / "course1-preview"
        else:
            root = parent / "course1-preview"
        root.mkdir(mode=0o700, parents=True)
        for name, data in _generator_render().items():
            path = root / name
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_text(data, encoding="utf-8")
            path.chmod(0o600)
        # pathlib creates *intermediate* parents with the process umask,
        # not the leaf mkdir(mode=...) value. The real generator uses
        # umask(0o077); make this test fixture just as private, even on
        # developer machines configured with a permissive umask.
        for directory in (root, *(p for p in root.rglob("*") if p.is_dir())):
            directory.chmod(0o700)
        return root

    def test_private_preview_has_four_windows_and_no_activation(self):
        stage = self.make_preview()
        parsed = inspect_source_preview(stage)
        self.assertEqual(parsed.windows, COURSE1.windows)
        self.assertEqual(parsed.file_count, 7)
        self.assertEqual(parsed.summary()["deployment_authorized"], False)

    def test_fixture_directory_modes_are_private_with_umask_022(self):
        previous = os.umask(0o022)
        try:
            stage = self.make_preview()
        finally:
            os.umask(previous)
        for directory in (stage, *(p for p in stage.rglob("*") if p.is_dir())):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(inspect_source_preview(stage).profile, COURSE1.name)

    def test_read_only_check_preserves_every_byte(self):
        stage = self.make_preview()
        before = {str(p.relative_to(stage)): p.read_bytes()
                  for p in stage.rglob("*") if p.is_file()}
        inspect_source_preview(stage)
        after = {str(p.relative_to(stage)): p.read_bytes()
                 for p in stage.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_modified_config_is_rejected_without_content_leak(self):
        stage = self.make_preview()
        file = stage / "data/config.json"
        file.write_text(file.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ProfileNotReady, "differs from canonical"):
            inspect_source_preview(stage)

    def test_stale_preview_is_rejected_if_generator_changes(self):
        stage = self.make_preview()
        expected = _generator_render()
        expected["manifest.json"] += " "
        with patch("goad.course1_source_gate._generator_render", return_value=expected):
            with self.assertRaises(ProfileNotReady):
                inspect_source_preview(stage)

    def test_forged_active_manifest_is_rejected(self):
        stage = self.make_preview()
        manifest = stage / "manifest.json"
        parsed = json.loads(manifest.read_text(encoding="utf-8"))
        parsed["state"] = "ACTIVE"
        manifest.write_text(json.dumps(parsed), encoding="utf-8")
        with self.assertRaises(ProfileNotReady):
            inspect_source_preview(stage)

    def test_missing_file_is_rejected(self):
        stage = self.make_preview()
        (stage / "data/inventory").unlink()
        with self.assertRaisesRegex(ProfileNotReady, "missing or symlinked"):
            inspect_source_preview(stage)

    def test_extra_unexpected_file_is_rejected(self):
        stage = self.make_preview()
        (stage / "instance.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ProfileNotReady):
            inspect_source_preview(stage)

    def test_symlinked_artifact_is_rejected(self):
        stage = self.make_preview()
        a = stage / "data/inventory"
        b = stage / "data/inventory_disable_vagrant"
        a.unlink()
        a.symlink_to(b)
        with self.assertRaises(ProfileNotReady):
            inspect_source_preview(stage)

    def test_symlinked_workspace_ancestor_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "real"
            destination.mkdir()
            (Path(temp) / "workspace").symlink_to(destination, target_is_directory=True)
            stage = self.make_preview(Path(temp) / "workspace")
            with self.assertRaisesRegex(ProfileNotReady, "symlink"):
                inspect_source_preview(stage)

    def test_symlinked_root_is_rejected(self):
        stage = self.make_preview()
        linked = stage.parent / "linked-preview"
        linked.symlink_to(stage, target_is_directory=True)
        with self.assertRaisesRegex(ProfileNotReady, "symlink"):
            inspect_source_preview(linked)

    def test_world_readable_private_preview_is_rejected(self):
        stage = self.make_preview()
        stage.chmod(0o755)
        with self.assertRaisesRegex(ProfileNotReady, "exposes confidential"):
            inspect_source_preview(stage)

    def test_world_readable_file_is_rejected(self):
        stage = self.make_preview()
        (stage / "data/config.json").chmod(0o644)
        with self.assertRaisesRegex(ProfileNotReady, "permissions are unsafe"):
            inspect_source_preview(stage)

    def test_installed_workspace_tree_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = self.make_preview(Path(temp) / "workspace")
            with self.assertRaisesRegex(ProfileNotReady, "workspace"):
                inspect_source_preview(stage)

    def test_installed_instance_marker_is_rejected(self):
        stage = self.make_preview()
        (stage.parent / "instance.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ProfileNotReady, "installed instance"):
            inspect_source_preview(stage)

    def test_git_checkout_is_rejected(self):
        with self.assertRaises(ProfileNotReady):
            inspect_source_preview(PROJECT)

    def test_cli_outputs_only_nonsecret_metadata(self):
        stage = self.make_preview()
        proc = subprocess.run(
            [sys.executable, "-m", "goad.course1_source_gate",
             "--check-preview", str(stage)],
            cwd=PROJECT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PREVIEW_ONLY_NOT_INSTALLABLE", proc.stdout)
        self.assertIn('"deployment_authorized": false', proc.stdout)
        self.assertIn("[BLOCKED]", proc.stdout)
        self.assertNotIn("ansible_password", proc.stdout)

    def test_module_does_not_use_vmware_or_modify_installed_source(self):
        source = (PROJECT / "goad/course1_source_gate.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "vmrun", "vagrant up",
                          "Path.write_text", "os.system", "from goad.goadpath import"):
            self.assertNotIn(forbidden, source)
        self.assertTrue(GENERATOR.is_file())

if __name__ == "__main__":
    unittest.main()
