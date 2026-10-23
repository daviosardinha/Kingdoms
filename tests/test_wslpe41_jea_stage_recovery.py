"""Offline WSLPE41 scenario30 JEA staged-source proof recovery contract tests.

No Ansible, VMware, Windows, source-file or network mutation occurs in tests.
"""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kingdoms import wslpe41_jea_stage_recovery as recovery
from kingdoms import wslpe41_provided_install as provided
from kingdoms.wslpe41_fresh_contract import fresh_scenario_manifest
from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked, StageProof
from kingdoms.wslpe41_stage_commands import StageInvocation


class JeaStageProofRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        home = Path(self.temp.name)
        self.root = home / "state"
        self.folder = self.root / recovery.INSTANCE
        self.folder.mkdir(parents=True, mode=0o700)
        self.root.chmod(0o700)
        self.folder.chmod(0o700)
        self.journal = self.folder / "provided-install.json"
        self.identity = FreshGuestIdentity(
            instance_id=recovery.INSTANCE, workspace=str(home),
            vmx=str(home / "ws.vmx"), subnet="172.28.232.0/24",
            source_commit="b" * 40,
        )
        self.context = SimpleNamespace(identity=self.identity)
        self.stages = []
        for row in fresh_scenario_manifest():
            for stage in (("stage", "activate", "validate")
                          if row.number == 30 else ("apply", "validate")):
                self.stages.append(StageInvocation(
                    row.number, row.identifier, stage,
                    "guest_console" if stage == "activate" else "ansible",
                    (), recovery.MARKER if stage == "stage" else "unused",
                    "staged_source_presence",
                ))
        self.assertEqual(len(self.stages), 83)
        self.assertEqual((self.stages[56].number, self.stages[56].stage), (30, "stage"))
        self.record = {
            "schema": provided.SCHEMA, "instance": recovery.INSTANCE,
            "vmx": self.identity.vmx, "source_commit": "a" * 40,
            "jea_nonce": "f" * 32, "status": "BLOCKED",
            "next_stage": 56, "configuration_validated": 28,
            "inflight": {"number": 30, "stage": "stage"},
            "failure_gate": "WSLPE41 scenario #30 stage: runtime proof missing",
            "failure_class": "InstallBlocked",
            "proofs": [
                {"number": step.number, "stage": step.stage,
                 "transport": "ansible", "evidence_id": "wslpe41.proof." + str(index).zfill(3)}
                for index, step in enumerate(self.stages[:56])
            ],
        }
        self._write(self.record)
        self.before = self.journal.read_bytes()
        self.proof = StageProof(
            scenario_number=30, stage="stage", transport="ansible",
            evidence_id="wslpe41.30.stage." + "a" * 32, passed=True,
        )

    def _write(self, content):
        self.journal.write_text(json.dumps(content, sort_keys=True))
        self.journal.chmod(0o600)

    def _mock(self, *, observed_proof=True):
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(provided, "STATE_ROOT", self.root))
        preflight = stack.enter_context(patch.object(
            provided, "_preflight", return_value=(self.context, "operator", "learner")))
        stack.enter_context(patch.object(provided, "_stages", return_value=self.stages))
        stage_proof = stack.enter_context(patch.object(
            recovery, "_verify_live_modules", return_value=self.proof
            if observed_proof else None))
        install = stack.enter_context(patch.object(provided, "_install_steps"))
        return preflight, stage_proof, install

    def test_exact_readonly_stage_proof_archives_old_journal_and_pauses_console(self):
        _, observed, installer = self._mock()
        from contextlib import redirect_stdout
        import io
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(recovery.recover(), "PAUSED")
        self.assertIn("VMWARE CONSOLE ONLY", out.getvalue())
        new = json.loads(self.journal.read_text())
        self.assertEqual(new["status"], "WAITING_CONSOLE_JEA")
        self.assertEqual(new["next_stage"], 57)
        self.assertIsNone(new["inflight"])
        self.assertEqual(new["configuration_validated"], 28)
        self.assertEqual(new["proofs"][:56], self.record["proofs"])
        self.assertEqual(new["proofs"][56]["number"], 30)
        self.assertEqual(new["proofs"][56]["stage"], "stage")
        self.assertEqual(new["source_commit"], "b" * 40)
        self.assertEqual(new["jea_nonce"], self.record["jea_nonce"])
        self.assertEqual(new["jea_staging_proof_recovery"]["blocked_journal_sha256"],
                         hashlib.sha256(self.before).hexdigest())
        self.assertEqual(
            (self.folder / "provided-install.blocked-jea30-stage.json").read_bytes(), self.before)
        self.assertTrue((self.folder / "jea30-staging-proof-recovery-intent.json").is_file())
        observed.assert_called_once()
        installer.assert_not_called()
        with self.assertRaisesRegex(InstallBlocked, "already attempted"):
            recovery.recover()

    def test_failed_live_attestation_preserves_original_state(self):
        _, observer, installer = self._mock()
        observer.side_effect = InstallBlocked("JEA source mismatch")
        with self.assertRaisesRegex(InstallBlocked, "source mismatch"):
            recovery.recover()
        self.assertEqual(self.journal.read_bytes(), self.before)
        self.assertFalse((self.folder/"provided-install.blocked-jea30-stage.json").exists())
        self.assertFalse((self.folder/"jea30-staging-proof-recovery-intent.json").exists())
        installer.assert_not_called()

    def test_incorrect_proof_count_or_stage_blocks_before_guest(self):
        _, observer, installer = self._mock()
        for key, value in (("next_stage", 55),
                           ("configuration_validated", 27),
                           ("inflight", {"number": 30, "stage": "activate"})):
            wrong = dict(self.record)
            wrong[key] = value
            self._write(wrong)
            with self.assertRaisesRegex(InstallBlocked, "Not the exact blocked"):
                recovery.recover()
            observer.assert_not_called()
        self._write(self.record)
        self.assertEqual(self.journal.read_bytes(), self.before)
        installer.assert_not_called()

    def test_rejects_modified_prior_stage_proof(self):
        _, observed, _ = self._mock()
        bad = dict(self.record)
        bad["proofs"] = [dict(p) for p in self.record["proofs"]]
        bad["proofs"][5]["number"] = 99
        self._write(bad)
        with self.assertRaisesRegex(InstallBlocked, "Original 56"):
            recovery.recover()
        observed.assert_not_called()

    def test_remote_script_only_reads_source_and_checks_hash_acl_endpoint(self):
        code = recovery._live_script({name: ("a" * 64) for name in recovery.NAMES})
        for snippet in ("Get-FileHash", "Get-Acl", "Get-PSSessionConfiguration",
                        "Get-LocalGroupMember", "Get-Service", "WSLPE45_JEA_LOCAL_SOURCE=STAGED_NOT_EXECUTED"):
            self.assertIn(snippet, code)
        for forbidden in ("New-PSSessionConfiguration", "Register-PSSessionConfiguration",
                          "Set-ItemProperty", "New-ItemProperty", "Start-Process",
                          "Invoke-Wslpe45JeaLocal -Action Apply", "win_copy"):
            self.assertNotIn(forbidden, code)
        self.assertEqual(code.count("Write-Output 'WSLPE45_JEA_LOCAL_SOURCE=STAGED_NOT_EXECUTED'"), 1)

    def test_marker_is_derived_from_independent_pinned_tls_result(self):
        names = {name: "a" * 64 for name in recovery.NAMES}
        payload = {
            "schema": "kingdoms.wslpe41.jea30.source-audit.v1",
            "machine": "WSLPE-WS01", "module_hashes": names,
            "endpoint_not_registered": True, "winrm_ready": True,
        }
        text = (recovery.AUDIT + json.dumps(payload) + "\r\n" + recovery.MARKER + "\r\n")
        response = SimpleNamespace(status_code=0, std_out=text.encode())
        with (patch.object(recovery, "existing_management",
                           return_value=(SimpleNamespace(vmx=Path(self.identity.vmx)),
                                         {}, b"der", "operator", "learner")),
              patch.object(recovery.management, "auth_helper", return_value=object()),
              patch.object(recovery.management, "operator_session") as session,
              patch.object(recovery.management, "run_powershell", return_value=response) as command):
            session.return_value.__enter__.return_value = object()
            stage = self.stages[56]
            proof = recovery._verify_live_modules(self.context, "operator", names, stage)
            self.assertTrue(proof.passed)
            self.assertEqual(proof.scenario_number, 30)
            self.assertEqual(proof.stage, "stage")
            self.assertIn("Get-FileHash", command.call_args.args[1])
        with (patch.object(recovery, "existing_management",
                           return_value=(SimpleNamespace(vmx=Path(self.identity.vmx)),
                                         {}, b"der", "operator", "learner")),
              patch.object(recovery.management, "auth_helper", return_value=object()),
              patch.object(recovery.management, "operator_session") as session,
              patch.object(recovery.management, "run_powershell",
                           return_value=SimpleNamespace(status_code=0, std_out=(
                               recovery.AUDIT + json.dumps(payload) + "\n" +
                               recovery.MARKER + "\n" + recovery.MARKER).encode()))):
            session.return_value.__enter__.return_value = object()
            with self.assertRaisesRegex(InstallBlocked, "Duplicate"):
                recovery._verify_live_modules(self.context, "operator", names, self.stages[56])


if __name__ == "__main__":
    unittest.main()
