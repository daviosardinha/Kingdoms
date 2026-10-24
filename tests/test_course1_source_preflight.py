"""Catch missing Course 1 assets before any VM, network, or AD operation."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from goad.course1_source_preflight import Course1SourceError, validate_course1_source

ROOT = Path(__file__).resolve().parents[1]


class Course1SourcePreflightTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        shutil.copytree(ROOT / "ad/NORTH", self.root / "ad/NORTH")
        shutil.copytree(ROOT / "ad/GOAD/scripts", self.root / "ad/GOAD/scripts")
        # Mirror only the declared DC02/SRV02 fixtures; the actual compiled
        # IIS tree remains in the repository and must not be copied into
        # every isolated test fixture.
        lab = json.loads((ROOT / "ad/NORTH/data/config.json").read_text())["lab"]
        for host in lab["hosts"].values():
            for fixture in host.get("vulns_vars", {}).get("files", {}).values():
                rel = Path(fixture["src"])
                original = ROOT / "ad/GOAD/files" / rel
                target = self.root / "ad/GOAD/files" / rel
                if original.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    (target / "Default.aspx").write_text("website fixture", encoding="utf-8")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, target)
        role = "ansible/roles/vulns/files/tasks/main.yml"
        (self.root / role).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / role, self.root / role)
        shutil.copy2(ROOT / "playbooks.yml", self.root / "playbooks.yml")
        manifest = yaml.safe_load((ROOT / "playbooks.yml").read_text())
        for play in manifest["NORTH"]:
            shutil.copy2(ROOT / "ansible" / play, self.root / "ansible" / play)

    def edit(self, relative, before, after):
        target = self.root / relative
        raw = target.read_text(encoding="utf-8")
        self.assertIn(before, raw, msg=f"Fixture missing expected text: {relative}")
        target.write_text(raw.replace(before, after, 1), encoding="utf-8")

    def test_default_profile_has_every_prerequisite(self):
        evidence = validate_course1_source(self.root)
        self.assertEqual(len(evidence), 6)
        self.assertIn("SOURCE PRECHECK PASS", evidence[-1])

    def test_playbook_manifest_missing_blocks_before_vagrant(self):
        self.edit("playbooks.yml", "NORTH:\n", "NOT_NORTH:\n")
        with self.assertRaisesRegex(Course1SourceError, "Missing explicit"):
            validate_course1_source(self.root)

    def test_missing_ansible_playbook_blocks_before_vagrant(self):
        (self.root / "ansible/ad-child_domain.yml").unlink()
        with self.assertRaisesRegex(Course1SourceError, "missing or invalid Ansible"):
            validate_course1_source(self.root)

    def test_external_trust_play_is_rejected_for_course1(self):
        raw = (self.root / "playbooks.yml").read_text()
        prefix, sep, tail = raw.partition("NORTH:\n")
        self.assertTrue(sep)
        (self.root / "playbooks.yml").write_text(
            prefix + sep + "  - ad-trusts.yml\n" + tail
        )
        with self.assertRaisesRegex(Course1SourceError, "sequence minus Essos trust"):
            validate_course1_source(self.root)

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

    def test_missing_retained_dc02_script_blocks_before_install(self):
        (self.root / "ad/GOAD/files/dc02/bot_rdp.ps1").unlink()
        with self.assertRaisesRegex(Course1SourceError, "Missing retained Kingdoms file fixture"):
            validate_course1_source(self.root)

    def test_missing_castelblack_website_blocks_before_install(self):
        (self.root / "ad/GOAD/files/srv02/wwwroot/Default.aspx").unlink()
        with self.assertRaisesRegex(Course1SourceError, "Missing retained Kingdoms file fixture"):
            validate_course1_source(self.root)

    def test_file_copy_role_cannot_point_north_back_to_nonexistent_path(self):
        path = "ansible/roles/vulns/files/tasks/main.yml"
        self.edit(path, "../ad/GOAD/files", "../ad/NORTH/files")
        with self.assertRaisesRegex(Course1SourceError, "file-copy role"):
            validate_course1_source(self.root)

    def test_unsafe_retained_file_reference_fails_source_gate(self):
        self.edit("ad/NORTH/data/config.json",
                  "dc02/bot_rdp.ps1", "../../missing/secret.ps1")
        with self.assertRaisesRegex(Course1SourceError, "Unsafe retained file reference"):
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
