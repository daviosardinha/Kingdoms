"""Offline bounded provided-VM journal tests. Never connects to Windows/VMware."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kingdoms import wslpe41_provided_install as provided
from kingdoms import wslpe41_provided_runtime as runtime
from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked, StageProof
from kingdoms.wslpe41_runtime_proof import ObservedStageResult


class Provided41JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.instance = Path(self.tmp.name) / "workspace" / runtime.INSTANCE
        self.instance.mkdir(parents=True)
        self.identity = FreshGuestIdentity(
            instance_id=runtime.INSTANCE, workspace=str(self.instance.parent),
            vmx=str(self.instance / "provider" / "windows_10.vmx"),
            subnet="172.28.232.0/24", source_commit="a" * 40,
        )
        self.context = SimpleNamespace(
            identity=self.identity, instance_dir=self.instance,
            ansible=Path(self.tmp.name) / "bin/ansible-playbook",
            inventory=self.instance / "ansible/inventory.yml",
            private_vars=self.instance / "ansible/private-vars.yml",
            expected_address="172.28.232.31", management_address="172.28.233.31",
        )

    def _source(self, *args):
        return StageProof(
            scenario_number=args[1].number, stage=args[2],
            transport="ansible",
            evidence_id=f"wslpe41.{args[1].number:02d}.{args[2]}.real.marker",
            passed=True,
        )

    def _patches(self):
        return (
            patch.object(provided, "STATE_ROOT", self.root),
            patch.object(provided, "_preflight",
                         return_value=(self.context, "OPSECRET", "LEARNSECRET")),
            patch.object(provided, "run_ansible_stage", side_effect=self._source),
        )

    def _journal(self):
        return self.root / runtime.INSTANCE / "provided-install.json"

    def test_one_journal_pauses_for_jea_and_resumes_without_stage_replay(self):
        with self._patches()[0], self._patches()[1], self._patches()[2] as ansible:
            with redirect_stdout(io.StringIO()):
                result = provided.install("start")
            self.assertEqual(result, "PAUSED")
            record = json.loads(self._journal().read_text())
            self.assertEqual(record["status"], "WAITING_CONSOLE_JEA")
            self.assertEqual(record["next_stage"], 57)  # 28 preceding scenarios + JEA stage
            self.assertEqual(record["configuration_validated"], 28)
            self.assertEqual(len(record["proofs"]), 57)
            self.assertEqual(ansible.call_count, 57)
            with self.assertRaisesRegex(InstallBlocked, "never replay"):
                provided.install("start")
            observation = ObservedStageResult(
                instance_id=self.identity.instance_id, vmx=self.identity.vmx,
                transport="guest_console", returncode=0,
                stdout=("WSLPE45_JEA_LOCAL_APPLY=PASS\n"
                        "WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS\n"),
                stderr="",
            )
            with (patch.object(runtime, "existing_management",
                               return_value=(None, {}, b"fake-cert", "OPSECRET", "LEARNSECRET")),
                  patch.object(provided, "_read_console_observation",
                               return_value=observation),
                  redirect_stdout(io.StringIO())):
                self.assertEqual(provided.install("resume"), "DONE")
            record = json.loads(self._journal().read_text())
            self.assertEqual(record["status"], "CONFIGURATION_VALIDATED")
            self.assertEqual(record["next_stage"], 83)
            self.assertEqual(record["configuration_validated"], 41)
            self.assertEqual(len(record["proofs"]), 83)
            self.assertEqual(ansible.call_count, 82)
            self.assertEqual([p for p in record["proofs"] if p["transport"] == "guest_console"][0]["stage"],
                             "activate")
            self.assertEqual(record["course_release"], "NOT_AUTHORIZED")

    def test_failed_stage_leaves_nonresumable_journal_and_prevents_replay(self):
        def fail(context, scenario, stage):
            if scenario.number == 2 and stage == "apply":
                raise InstallBlocked("injected runtime failure")
            return self._source(context, scenario, stage)
        with (patch.object(provided, "STATE_ROOT", self.root),
              patch.object(provided, "_preflight",
                           return_value=(self.context, "OPSECRET", "LEARNSECRET")),
              patch.object(provided, "run_ansible_stage", side_effect=fail)):
            with self.assertRaisesRegex(InstallBlocked, "injected"):
                with redirect_stdout(io.StringIO()):
                    provided.install("start")
            data = json.loads(self._journal().read_text())
            self.assertEqual(data["status"], "BLOCKED")
            self.assertEqual(data["inflight"], {"number": 2, "stage": "apply"})
            with self.assertRaisesRegex(InstallBlocked, "reviewed JEA"):
                provided.install("resume")
            with self.assertRaisesRegex(InstallBlocked, "never replay"):
                provided.install("start")

    def test_resume_before_console_or_with_source_drift_is_refused(self):
        with (patch.object(provided, "STATE_ROOT", self.root),
              patch.object(provided, "_preflight",
                           return_value=(self.context, "O", "L"))):
            with self.assertRaisesRegex(InstallBlocked, "missing"):
                provided.install("resume")
            p = provided.private_instance_directory(self.root, runtime.INSTANCE)
            record = provided._base_state(self.context)
            record["status"] = "WAITING_CONSOLE_JEA"
            record["source_commit"] = "0" * 40
            provided.checkpoint(p / "provided-install.json", record)
            with self.assertRaisesRegex(InstallBlocked, "mismatch"):
                provided.install("resume")

    def test_console_script_requires_local_session_and_nonce(self):
        cmd = provided.console_command("e" * 32)
        self.assertIn("Assert-Wslpe45JeaConsole", cmd)
        self.assertIn("Invoke-Wslpe45JeaLocal -Action Apply", cmd)
        self.assertIn("WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS", cmd)
        self.assertIn("e" * 32, cmd)
        with self.assertRaisesRegex(InstallBlocked, "nonce"):
            provided.console_command("invalid")

    def test_cli_reports_precise_sudo_guard_without_starting_any_scenario(self):
        source = Path(__file__).resolve().parents[1] / "scripts/wslpe41-provided-install.py"
        spec = importlib.util.spec_from_file_location("provided_cli_gate_test", source)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from kingdoms.wslpe41_management_nic import NicBlocked
        with (patch.object(mod, "install",
                           side_effect=NicBlocked("Host maintenance guard failed: sudo")) as actual,
              redirect_stdout(io.StringIO()) as output):
            self.assertEqual(
                mod.main(["--start", "--authorize", "START-EXISTING-WSLPE41"]), 2)
        self.assertEqual(actual.call_args.args, ("start",))
        self.assertIn("Host maintenance guard failed: sudo", output.getvalue())
        self.assertIn("sudo -v", output.getvalue())
        self.assertIn("[NO SCENARIOS]", output.getvalue())

    def test_cli_requires_explicit_existing_guest_approval(self):
        source = Path(__file__).resolve().parents[1] / "scripts/wslpe41-provided-install.py"
        spec = importlib.util.spec_from_file_location("provided_cli_test", source)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with patch.object(mod, "install") as actual:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--start"]), 2)
                self.assertEqual(mod.main(["--status", "--authorize", "START-EXISTING-WSLPE41"]), 2)
            actual.assert_not_called()


if __name__ == "__main__":
    unittest.main()
