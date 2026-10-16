"""WSLPE qualification checkpoint only: no VMs, no NORTH, no Ansible."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from kingdoms.wslpe_fast_track_resume import resume_position, load_private_checkpoint, load_chained_private_checkpoint

CATALOG = (
    "unquoted_service_path", "weak_service_dacl",
    "weak_service_binary_permissions", "weak_service_registry_permissions",
    "service_dll_hijacking", "path_search_order_hijacking",
    "always_install_elevated", "registry_run_keys",
    "writable_startup_folder", "scheduled_task_binary_permissions",
    "scheduled_task_directory_permissions", "unattend_credentials",
    "powershell_history_credentials", "hardcoded_application_credentials",
    "stored_runas_credentials", "stored_winlogon_credentials",
    "sebackup_privilege", "seimpersonate_privilege",
    "writable_program_directory", "insecure_service_registry",
)
FLOW = (
    ("apply", None), ("validate", "vulnerable"), ("reset", None),
    ("validate", "clean"), ("apply", None), ("validate", "vulnerable"),
)


def checkpoint():
    rows = []
    for tech in CATALOG[:6]:
        for action, state in FLOW:
            rows.append({"technique": tech, "action": action,
                         "state": state, "exit_code": 0})
    rows.append({"technique": CATALOG[6], "action": "apply",
                 "state": None, "exit_code": 2})
    return rows


class WslpeFastTrackResumeTests(unittest.TestCase):
    def test_exact_36_passes_then_failed_seventh_apply(self):
        self.assertEqual(resume_position(checkpoint(), CATALOG, FLOW), 6)

    def test_malformed_prefix_failed_validate_and_reordered_catalog_block(self):
        rows = checkpoint()
        for modified in (
            rows[:-1], # no failed step
            rows[:-2] + [rows[-1]], # incomplete previous technique
            rows[:5] + [dict(rows[5], exit_code=1)] + rows[6:],
            rows[:36] + [dict(rows[-1], action="reset")],
            rows[:36] + [dict(rows[-1], technique=CATALOG[7])],
            rows[:36] + [dict(rows[-1], exit_code=False)],
            rows[:36] + [dict(rows[-1], other=True)],
            [],
        ):
            with self.subTest(last=repr(modified[-1:])), self.assertRaises(ValueError):
                resume_position(modified, CATALOG, FLOW)

    def test_private_checkpoint_roundtrip_and_permissions(self):
        with TemporaryDirectory() as base:
            root = Path(base) / "approved"
            root.mkdir(mode=0o700)
            path = root / "wslpe-qualification-20261016T153256Z.json"
            path.write_text(json.dumps(checkpoint()), encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(load_private_checkpoint(path, root, CATALOG, FLOW), 6)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                load_private_checkpoint(path, root, CATALOG, FLOW)
            path.chmod(0o600)
            other = Path(base) / "not-approved"
            other.mkdir(mode=0o700)
            with self.assertRaises(ValueError):
                load_private_checkpoint(path, other, CATALOG, FLOW)
            linked = root / "wslpe-qualification-20261016T154000Z.json"
            linked.symlink_to(path)
            with self.assertRaises(ValueError):
                load_private_checkpoint(linked, root, CATALOG, FLOW)

    def test_exact_original_plus_newer_report_proves_sixteen_passes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "private"
            root.mkdir(mode=0o700)
            prefix = root / "wslpe-qualification-20261016T153256Z.json"
            later = root / "wslpe-qualification-20261016T213032Z.json"
            first = checkpoint()
            later_rows = [
                {"technique": tech, "action": action,
                 "state": state, "exit_code": 0}
                for tech in CATALOG[6:16] for action, state in FLOW
            ]
            later_rows.append({
                "technique": "sebackup_privilege", "action": "apply",
                "state": None, "exit_code": 2,
            })
            self.assertEqual(len(first), 37)
            self.assertEqual(len(later_rows), 61)
            prefix.write_text(json.dumps(first))
            later.write_text(json.dumps(later_rows))
            prefix.chmod(0o600)
            later.chmod(0o600)
            self.assertEqual(
                load_chained_private_checkpoint(prefix, later, root, CATALOG, FLOW),
                16,
            )
            with self.assertRaises(ValueError):
                load_private_checkpoint(later, root, CATALOG, FLOW)
            with self.assertRaises(ValueError):
                load_chained_private_checkpoint(later, later, root, CATALOG, FLOW)
            for changed in (
                later_rows[1:],
                later_rows[:5] + [dict(later_rows[5], exit_code=2)] + later_rows[6:],
                later_rows[:-1] + [dict(later_rows[-1], action="reset")],
                later_rows[:-1] + [dict(later_rows[-1], technique="seimpersonate_privilege")],
            ):
                later.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    load_chained_private_checkpoint(prefix, later, root, CATALOG, FLOW)
            later.write_text(json.dumps(later_rows))
            later.chmod(0o644)
            with self.assertRaises(ValueError):
                load_chained_private_checkpoint(prefix, later, root, CATALOG, FLOW)

    def test_resume_has_no_guest_mutations_in_preflight_source(self):
        source = (Path(__file__).resolve().parents[1]
                  / "scripts/wslpe-fast-track-20.py").read_text()
        self.assertIn('catalog[:resume_index]', source)
        self.assertIn('"validate", "vulnerable"', source)
        self.assertIn('catalog[resume_index:]', source)
        self.assertIn('"validate", "clean"', source)
        self.assertIn("Previous failed apply may have partial state", source)
        self.assertIn('"--resume-report"', source)
        self.assertIn('load_private_checkpoint(', source)

if __name__ == "__main__":
    unittest.main()
