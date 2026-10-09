"""Per-instance Kingdoms profile binding tests; no VM operations."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from goad.course1_instance_binding import (
    PROFILE_FILENAME, inspect_instance_binding, parse_instance_vagrant_roster,
)
from goad.course1_runtime_contract import FULL, ProfileNotReady

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "ad/GOAD/providers/vmware/Vagrantfile").read_text(encoding="utf-8")


class InstanceBindingTests(unittest.TestCase):
    def fake(self, text=SOURCE, manifest=None):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path=Path(d.name)
        (path/"Vagrantfile").write_text(text,encoding="utf-8")
        if manifest is not None:
            (path/PROFILE_FILENAME).write_text(json.dumps(manifest),encoding="utf-8")
        return path

    def test_reference_machine_layout_is_full(self):
        self.assertEqual(set(parse_instance_vagrant_roster(SOURCE)),
                         set(FULL.windows)|{"GOAD-ROUTER"})
        self.assertIs(inspect_instance_binding(self.fake()), FULL)

    def test_m1_missing_ws01_backfill_compatible(self):
        text=SOURCE.replace(':name => "GOAD-WS01"',':name => "OLD-WS01"')
        self.assertIs(inspect_instance_binding(self.fake(text)),FULL)

    def test_reduced_four_guest_candidate_rejected(self):
        text=SOURCE.replace(':name => "GOAD-DC03"',':name => "OLD-DC03"').replace(
            ':name => "GOAD-SRV03"',':name => "OLD-SRV03"')
        with self.assertRaisesRegex(ProfileNotReady,"reduced profile activation is blocked"):
            inspect_instance_binding(self.fake(text))

    def test_reduced_manifest_refused(self):
        with self.assertRaises(ProfileNotReady):
            inspect_instance_binding(self.fake(manifest={
                "profile":"course1-fall-of-the-north",
                "state":"PREVIEW_ONLY_NOT_INSTALLABLE",
                "windows_machines":["GOAD-DC01","GOAD-DC02","GOAD-SRV02","GOAD-WS01"]
            }))

    def test_explicit_legacy_manifest_permitted(self):
        self.assertIs(inspect_instance_binding(self.fake(manifest={
            "profile":FULL.name,
            "state":"ACTIVE_LEGACY",
            "windows_machines":list(FULL.windows),
        })),FULL)

    def test_unknown_manifest_rejected(self):
        with self.assertRaises(ProfileNotReady):
            inspect_instance_binding(self.fake(manifest={"profile":"unknown"}))

    def test_invalid_manifest_rejected(self):
        path=self.fake()
        (path/PROFILE_FILENAME).write_text("{invalid",encoding="utf-8")
        with self.assertRaisesRegex(ProfileNotReady,"invalid instance profile"):
            inspect_instance_binding(path)

    def test_duplicate_guests_rejected(self):
        with self.assertRaisesRegex(ProfileNotReady,"duplicate"):
            inspect_instance_binding(self.fake(SOURCE+'\n  :name => "GOAD-DC01"\n'))

    def test_vagrant_symlink_rejected(self):
        path=self.fake()
        (path/"Vagrantfile").rename(path/"source")
        (path/"Vagrantfile").symlink_to(path/"source")
        with self.assertRaisesRegex(ProfileNotReady,"symlink"):
            inspect_instance_binding(path)

    def test_read_only_cli(self):
        path=self.fake()
        cmd=[sys.executable,"-m","goad.course1_instance_binding","--check-provider",str(path)]
        before=(path/"Vagrantfile").read_bytes()
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("[PASS]",result.stdout)
        self.assertEqual(before,(path/"Vagrantfile").read_bytes())

    def test_provider_guards_sync_and_lifecycle(self):
        vm=(ROOT/"goad/provider/vagrant/vmware.py").read_text(encoding="utf-8")
        ki=(ROOT/"goad/provider/vagrant/vmware_kingdoms.py").read_text(encoding="utf-8")
        self.assertIn("def _require_full_goad_instance_binding(self):",vm)
        self.assertGreaterEqual(vm.count("if not self._require_full_goad_instance_binding():"),2)
        self.assertGreaterEqual(ki.count("if not self._require_full_goad_instance_binding():"),4)

    def test_lab_mode_guards_before_case_dispatch(self):
        sh=(ROOT/"scripts/lab-mode.sh").read_text(encoding="utf-8")
        main=sh[sh.index("main() {"):]
        self.assertIn("python3 -m goad.course1_instance_binding",main)
        self.assertIn("Refusing GOAD mode operation",main)
        self.assertLess(main.index("python3 -m goad.course1_instance_binding"),
                        main.index("        exercise)"))


if __name__=="__main__":
    unittest.main()
