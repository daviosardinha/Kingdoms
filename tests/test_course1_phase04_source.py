"""NORTH Course 1 / Module 04 source contract; no guest or directory actions."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "playbooks.yml"
LPE_INSTALL = ROOT / "ansible/ws01-lpe-install.yml"
DEFAULTS = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"
TASKS = ROOT / "ansible/roles/windows_lpe/tasks/techniques"
CATALOG = ROOT / "docs/WINDOWS_LPE_CATALOG.md"


def north_manifest():
    source = MANIFEST.read_text(encoding="utf-8")
    match = re.search(r"(?m)^NORTH:\s*\n(.*?)(?=^[A-Za-z][\w-]*:\s*$|\Z)", source, re.S | re.M)
    if not match:
        raise AssertionError("NORTH must have an explicit Ansible installation manifest")
    return match.group(1)


def yaml_sequence(source, key):
    match = re.search(rf"(?m)^{re.escape(key)}:\s*\n((?:^[ ]{{2}}- .*\n)+)", source)
    if not match:
        raise AssertionError(f"Could not find list {key}")
    return [line.strip()[2:].strip() for line in match.group(1).splitlines()]


class Course1Phase04SourceTests(unittest.TestCase):
    def test_north_seeds_promoted_lpe_after_foundation_and_before_final_health(self):
        manifest = north_manifest()
        for name in ("ws01.yml", "vulnerabilities.yml", "ws01-lpe-install.yml", "kingdoms-health-final.yml"):
            self.assertIn(f"- {name}", manifest)
        self.assertLess(manifest.index("- ws01.yml"), manifest.index("- ws01-lpe-install.yml"))
        self.assertLess(manifest.index("- vulnerabilities.yml"), manifest.index("- ws01-lpe-install.yml"))
        self.assertLess(manifest.index("- ws01-lpe-install.yml"), manifest.index("- kingdoms-health-final.yml"))
        play = LPE_INSTALL.read_text(encoding="utf-8")
        self.assertIn("hosts: ws01", play)
        self.assertIn("role: windows_lpe", play)
        self.assertIn("windows_lpe_action: apply", play)
        self.assertIn("windows_lpe_profile: full-lpe", play)

    def test_all_twenty_lpe_scenarios_implemented_with_individual_role_files(self):
        source = DEFAULTS.read_text(encoding="utf-8")
        catalog = yaml_sequence(source, "windows_lpe_catalog")
        promoted = yaml_sequence(source, "windows_lpe_implemented_techniques")
        self.assertEqual(len(catalog), 20)
        self.assertEqual(len(set(catalog)), 20)
        self.assertEqual(promoted, catalog)
        self.assertRegex(source, r"(?m)^windows_lpe_candidate_techniques:\s*\[\]")
        self.assertEqual({p.stem for p in TASKS.glob("*.yml")}, set(catalog))
        for technique in catalog:
            text = (TASKS / f"{technique}.yml").read_text(encoding="utf-8")
            self.assertIn("windows_lpe_action", text, technique)
            self.assertIn("'apply'", text, technique)
            self.assertIn("'reset'", text, technique)
            self.assertIn("'validate'", text, technique)
        document = CATALOG.read_text(encoding="utf-8")
        self.assertIn("20 techniques Implemented", document)
        self.assertIn("APPLIED / VULNERABLE", document)

    def test_legacy_promoted_and_full_gates_are_not_north_safe(self):
        for path in (
            ROOT / "scripts/validate-windows-lpe-promoted-runtime.sh",
            ROOT / "scripts/validate-windows-lpe-full-runtime.sh",
            ROOT / "scripts/validate-ws01-runtime.sh",
        ):
            with self.subTest(path=path):
                self.assertIn("ad/GOAD/", path.read_text(encoding="utf-8"))
        full = (ROOT / "scripts/validate-windows-lpe-full-runtime.sh").read_text()
        self.assertIn("run_full reset", full)
        self.assertIn("run_full apply", full)

    def test_full_lpe_validation_has_transient_runas_account_right_mutation(self):
        source = (TASKS / "stored_runas_credentials.yml").read_text()
        self.assertIn("Temporarily grant SeBatchLogonRight", source)
        self.assertIn("action: add", source)
        self.assertIn("action: remove", source)
        self.assertIn("when: windows_lpe_action != 'status'", source)
        self.assertIn("windows_lpe_action: status", DEFAULTS.read_text())


if __name__ == "__main__":
    unittest.main()
