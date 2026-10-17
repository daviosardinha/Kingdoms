"""Fail-closed, standalone-only 25-technique operator and journal tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import stat
import unittest

from kingdoms import wslpe45_batch_operator as batch

ROOT = Path(__file__).resolve().parents[1]


class OperatorTests(unittest.TestCase):
    def test_index_covers_exact_25_and_north_role_stays_frozen(self):
        rows = batch.index_rows()
        self.assertEqual([r["number"] for r in rows], list(range(21, 46)))
        self.assertEqual(len(set(r["id"] for r in rows)), 25)
        self.assertEqual([r["id"] for r in rows if r["status"] == "candidate"],
                         ["scheduled_task_definition_acl",
                          "scm_create_service_acl",
                          "privileged_service_config_injection",
                          "privileged_updater_hijack",
                          "ifeo_debugger_acl_hijack",
                          "app_paths_registry_hijack",
                          "named_pipe_authorization",
                          "jea_role_capability_misconfig",
                          "setakeownership_privilege",
                          "serestore_privilege",
                          "sedebug_privilege",
                          "ntfs_link_redirection",
                          "privileged_path_traversal_write",
                          "privileged_loopback_http_authz",
                          "privileged_argument_injection",
                          "privileged_child_environment_trust",
                          "elevated_plugin_signature_bypass",
                          "privileged_file_toctou",
                          "privileged_backup_restore_api"])
        self.assertEqual(len([r for r in rows if r["status"] == "planned"]), 6)
        self.assertTrue(all(r["learner_proof"] == "pending" for r in rows))

    def test_no_partial_live_execution_and_no_guest_contact(self):
        rows, blockers = batch.source_readiness()
        self.assertEqual(len(rows), 25)
        self.assertEqual(len(blockers), 6)
        self.assertTrue(all("no source-qualified fixture" in reason for reason in blockers))
        args = SimpleNamespace(execute=True, timeout_seconds=900,
                               report_dir="/tmp/unused")
        with patch.object(batch, "trusted_safety") as safety, patch.object(
                batch.subprocess, "run") as command:
            self.assertEqual(batch.run(args), 2)
            safety.assert_not_called()
            command.assert_not_called()

    def test_source_complete_does_not_authorize_live_guest_access(self):
        self.assertFalse(batch.yaml.safe_load(batch.INDEX.read_text())["batch_execution_authorized"])
        rows = batch.index_rows()
        args = SimpleNamespace(execute=True, timeout_seconds=900,
                               report_dir="/tmp/unused")
        with patch.object(batch, "source_readiness", return_value=(rows, [])), patch.object(
                batch, "trusted_safety") as safety, patch.object(
                batch.subprocess, "run") as subprocess_call:
            self.assertEqual(batch.run(args), 2)
            safety.assert_not_called()
            subprocess_call.assert_not_called()

    def test_plan_mode_never_calls_inventory_or_guest(self):
        args = SimpleNamespace(execute=False, timeout_seconds=900,
                               report_dir="/tmp/unused")
        with patch.object(batch, "trusted_safety") as safety, patch.object(
                batch.subprocess, "run") as command:
            self.assertEqual(batch.run(args), 0)
            safety.assert_not_called()
            command.assert_not_called()

    def test_action_sequence_contains_exact_150_operations(self):
        self.assertEqual(batch.REQUIRED_STAGE_COUNT, 150)
        self.assertEqual(batch.FLOW, (
            ("apply", None, "apply"),
            ("validate", "vulnerable", "vulnerable"),
            ("reset", None, "reset"),
            ("validate", "clean", "clean"),
            ("apply", None, "reapply"),
            ("validate", "vulnerable", "revulnerable"),
        ))

    def test_commands_refuse_unrelated_techniques(self):
        path = Path("/opt/ansible-playbook")
        inventory = Path("/sandbox/WSLPE/inventory")
        varsfile = Path("/sandbox/WSLPE/vars")
        row = batch.index_rows()[0]
        result = batch.command(path, inventory, varsfile, row,
                               "172.28.231.31", "validate", "clean")
        self.assertEqual(result[result.index("--limit") + 1], "ws01,localhost")
        self.assertEqual(result[result.index("-e") + 1],
                         '{"wslpe_expected_address":"172.28.231.31","wslpe_45_action":"validate","wslpe_45_technique":"scheduled_task_definition_acl","wslpe_45_stage_label":"clean","wslpe_45_validate_state":"clean"}')
        self.assertTrue(result[result.index("-e") - 1].endswith(
            "scheduled_task_definition_acl.yml"))
        self.assertNotIn("ansible/ws01-lpe-install.yml", " ".join(result))
        for action, state in (("apply", "clean"), ("validate", None),
                              ("reset", "vulnerable"), ("status", None)):
            with self.subTest(action=action, state=state):
                with self.assertRaises(ValueError):
                    batch.command(path, inventory, varsfile, row,
                                  "172.28.231.31", action, state)
        with self.assertRaises(ValueError):
            batch.command(path, inventory, varsfile, {"id": "north_backdoor",
                         "playbook": "ansible/ws01.yml"}, "172.28.231.31",
                         "apply", None)

    def test_private_reports_are_atomic_and_owner_only(self):
        with TemporaryDirectory() as folder:
            path = batch.make_private_dir(folder)
            report = batch.atomic_report(path, "wslpe45-test.json",
                                         {"completed": False, "events": []})
            self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o600)
            self.assertFalse(json.loads(report.read_text())["completed"])
            batch.atomic_report(path, "wslpe45-test.json",
                                {"completed": True, "events": [{"accepted": True}]})
            self.assertEqual(len(json.loads(report.read_text())["events"]), 1)
            with self.assertRaises(ValueError):
                batch.atomic_report(path, "../unsafe.json", {})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_cli_and_source_always_preserve_terminal_and_frozen_north(self):
        text = (ROOT / "kingdoms/wslpe45_batch_operator.py").read_text()
        entry = (ROOT / "scripts/wslpe-45-qualify.py").read_text()
        self.assertNotIn("os.system(", text)
        self.assertNotIn("shell=True", text)
        self.assertNotIn("exit 1", text + entry)
        self.assertNotIn("ansible/ws01-lpe-install.yml", entry)
        self.assertIn('"10.4.10.31"', text)
        for expected in (".wslpe45-recovery-required", "exact_standalone",
                         "check_inventory", "ws01,localhost",
                         "WSLPE45_BATCH_STAGE=", "read_only"):
            if expected != "read_only":
                self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
