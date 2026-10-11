"""Catch missing Course 1 assets before any VM, network, or AD operation."""
import shutil
import tempfile
import unittest
from pathlib import Path

from goad.course1_source_preflight import Course1SourceError, validate_course1_source

ROOT = Path(__file__).resolve().parents[1]


class Course1SourcePreflightTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        shutil.copytree(ROOT / "ad/NORTH", self.root / "ad/NORTH")
        shutil.copytree(ROOT / "ad/GOAD/scripts", self.root / "ad/GOAD/scripts")

    def edit(self, relative, before, after):
        target = self.root / relative
        raw = target.read_text(encoding="utf-8")
        self.assertIn(before, raw, msg=f"Fixture missing expected text: {relative}")
        target.write_text(raw.replace(before, after, 1), encoding="utf-8")

    def test_default_profile_has_every_prerequisite(self):
        evidence = validate_course1_source(self.root)
        self.assertEqual(len(evidence), 5)
        self.assertIn("SOURCE PRECHECK PASS", evidence[-1])

    def test_postvagrant_missing_ws01_fails_early(self):
        target = "ad/NORTH/data/inventory_disable_vagrant"
        path = self.root / target
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        lines = [line for line in lines if not line.startswith("ws01 ansible_host=")]
        path.write_text("".join(lines), encoding="utf-8")
        with self.assertRaisesRegex(Course1SourceError, "missing=\\['ws01'\\]"):
            validate_course1_source(self.root)

    def test_removed_external_trust_cannot_remain_in_ansible_group(self):
        self.edit("ad/NORTH/data/inventory",
                  "[trust]\n; No external Essos forest trust exists",
                  "[trust]\ndc01\n; No external Essos forest trust exists")
        with self.assertRaisesRegex(Course1SourceError, "External trust group"):
            validate_course1_source(self.root)

    def test_old_essos_member_cannot_hide_in_inventory(self):
        self.edit("ad/NORTH/data/inventory", "[dc]\ndc01\ndc02",
                  "[dc]\ndc01\ndc02\ndc03")
        with self.assertRaisesRegex(Course1SourceError, "Wrong domain-controller group"):
            validate_course1_source(self.root)

    def test_missing_kingdoms_script_is_detected(self):
        script = self.root / "ad/GOAD/scripts/asrep_roasting.ps1"
        script.unlink()
        with self.assertRaisesRegex(Course1SourceError, "Missing retained Kingdoms script"):
            validate_course1_source(self.root)

    def test_router_parent_dc_forwarding_cannot_go_missing(self):
        policy = "ad/NORTH/providers/vmware/router/nftables/exercise.nft"
        self.edit(policy, "ip saddr 10.4.10.11 ip daddr 10.4.20.10",
                  "ip saddr 10.4.10.11 ip daddr 10.4.20.12")
        with self.assertRaisesRegex(Course1SourceError, "AD forwarding"):
            validate_course1_source(self.root)


if __name__ == "__main__":
    unittest.main()
