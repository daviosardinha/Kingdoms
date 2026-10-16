"""WSLPE-only direct LSA rights lifecycle: source and failure-order acceptance.

Source regression only. Native Windows LSA lookup is separately exercised
by the Windows CI job. No guest, NORTH, VMware or host networking writes.
"""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "ansible/wslpe-user-rights-tasks.yml"
ADAPTER = ROOT / "ansible/wslpe-lpe-test.yml"
RUNNER_PATH = ROOT / "scripts/wslpe-fast-track-20.py"
SHARED = ROOT / "ansible/roles/windows_lpe/tasks/techniques/sebackup_privilege.yml"

SPEC = importlib.util.spec_from_file_location("wslpe_rights_runner_test", RUNNER_PATH)
assert SPEC and SPEC.loader
FAST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FAST)


class WslpeLocalRightsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tasks = yaml.safe_load(TASK.read_text(encoding="utf-8"))
        if len(tasks) != 1:
            raise AssertionError("WSLPE rights adapter must have exactly one scoped task")
        cls.script = tasks[0]["ansible.windows.win_powershell"]["script"]
        cls.play = yaml.safe_load(ADAPTER.read_text(encoding="utf-8"))[1]

    def test_exact_two_techniques_and_no_north_mutation(self):
        self.assertIn("sebackup_privilege = 'SeBackupPrivilege'", self.script)
        self.assertIn("seimpersonate_privilege = 'SeImpersonatePrivilege'", self.script)
        self.assertIn("WSLPE-WS01", self.script)
        self.assertIn("PartOfDomain", self.script)
        self.assertIn("Get-LocalUser -Name 'lpe.trainee'", self.script)
        self.assertIn("S-1-5-32-544", self.script)
        self.assertNotIn("secedit.exe /export", self.script)
        self.assertNotIn("NORTH\\", self.script)
        self.assertNotIn(" -Recurse", self.script)
        self.assertIn("secedit.exe /export", SHARED.read_text(encoding="utf-8"))

    def test_use_native_lsa_for_mutation_and_direct_verification(self):
        for api in ("LsaAddAccountRights", "LsaRemoveAccountRights",
                    "LsaEnumerateAccountRights", "LsaFreeMemory",
                    "LsaNtStatusToWinError", "LsaClose"):
            self.assertIn(api, self.script)
        self.assertIn("right.Length / 2", self.script)
        self.assertIn("return false; // Account has no direct rights", self.script)
        self.assertIn("Marshal.FreeHGlobal", self.script)
        self.assertIn("WslpeDirectAccountRights]::HasRight($sid, $right)", self.script)
        self.assertIn("WSLPE LSA direct privilege assignment failed verification", self.script)
        self.assertIn("WSLPE LSA direct right remained after reset", self.script)

    def test_existing_snapshot_is_checked_and_not_overwritten(self):
        for marker in (
            "$saved.target -cne $target", "$saved.sid -cne $sid",
            "$saved.right -cne $right", "preexisting",
            "fixture cannot reset or seed a pre-existing account right",
            "Untracked existing account right or fixture directory",
            "Unexpected WSLPE user-right fixture contents",
            "ReparsePoint", "Remove-Item -LiteralPath $stateFile",
            "Remove-Item -LiteralPath $root",
        ):
            self.assertIn(marker, self.script)
        self.assertLess(self.script.index("WSLPE LSA direct right remained after reset"),
                        self.script.index("Remove-Item -LiteralPath $stateFile"))
        self.assertLess(self.script.index("WSLPE LSA direct privilege assignment failed verification"),
                        self.script.index("WSLPE_USER_RIGHT_APPLIED="))

    def test_adapter_isolated_to_two_named_rights_techniques(self):
        play = self.play
        self.assertEqual(play["hosts"], "wslpe")
        shared = play["roles"][0]
        self.assertEqual(shared["role"], "windows_lpe")
        self.assertIn("sebackup_privilege", shared["when"])
        self.assertIn("seimpersonate_privilege", shared["when"])
        self.assertIn("always_install_elevated", shared["when"])
        self.assertEqual(play["tasks"][0]["ansible.builtin.include_tasks"],
                         "wslpe-aie-reset-tasks.yml")
        self.assertEqual(play["tasks"][1]["ansible.builtin.include_tasks"],
                         "wslpe-user-rights-tasks.yml")
        self.assertIn("intersect", play["tasks"][1]["when"])

    def test_source_recovery_rejects_conflicting_modes_and_non_rights(self):
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("if args.recover_user_rights:", source)
        self.assertIn('"sebackup_privilege", "seimpersonate_privilege"', source)
        self.assertIn("recovery.returncode", source)
        self.assertIn('"rights-reset-recovery"', source)
        self.assertIn('args.recover_aie_reset', source)
        parser = FAST.build_parser()
        self.assertFalse(parser.parse_args([]).recover_user_rights)
        self.assertTrue(parser.parse_args(["--execute", "--recover-user-rights",
                                           "--resume-report", "test.json"]).recover_user_rights)

    def test_full_resume_only_verifies_sixteen_then_recovers_sebackup(self):
        catalog = FAST.load_catalog()
        self.assertEqual(catalog[16], "sebackup_privilege")
        self.assertEqual(catalog[17], "seimpersonate_privilege")
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            prefix = directory / "wslpe-qualification-20261016T153256Z.json"
            checkpoint = directory / "wslpe-qualification-20261016T213032Z.json"
            prefix_rows = [
                {"technique": tech, "action": action,
                 "state": state, "exit_code": 0}
                for tech in catalog[:6] for action, state in FAST.FLOW
            ]
            prefix_rows.append({"technique": catalog[6], "action": "apply",
                                "state": None, "exit_code": 2})
            records = [
                {"technique": tech, "action": action,
                 "state": state, "exit_code": 0}
                for tech in catalog[6:16] for action, state in FAST.FLOW
            ]
            records.append({"technique": catalog[16], "action": "apply",
                            "state": None, "exit_code": 2})
            prefix.write_text(json.dumps(prefix_rows), encoding="utf-8")
            checkpoint.write_text(json.dumps(records), encoding="utf-8")
            prefix.chmod(0o600)
            checkpoint.chmod(0o600)
            bin_dir = directory / ".goad/.venv/bin"
            bin_dir.mkdir(parents=True)
            for name in ("ansible-playbook", "ansible-inventory"):
                (bin_dir / name).touch()
            args = FAST.build_parser().parse_args([
                "--execute", "--recover-user-rights",
                "--resume-report", str(checkpoint),
                "--resume-prefix-report", str(prefix),
                "--report-dir", str(directory),
            ])
            events = []

            def simulate(cmd, **kwargs):
                if "--list" in cmd:
                    return SimpleNamespace(returncode=0, stdout="{}", stderr="")
                vars = json.loads(cmd[cmd.index("-e")+1])
                techs = vars.get("wslpe_techniques", [])
                tech = techs[0] if techs else "STATUS"
                action, expected = vars["wslpe_action"], vars.get("windows_lpe_validate_state")
                events.append((tech, action, expected))
                return SimpleNamespace(
                    returncode=2 if (tech == "sebackup_privilege" and action == "apply")
                    else 0,
                    stdout="", stderr="controlled failure")

            with patch.object(FAST.Path, "home", return_value=directory), \
                 patch.object(FAST, "exact_standalone", return_value=(
                     Path("/private/ws/inventory"), Path("/private/ws/vars"), "172.28.231.31"
                 )), patch.object(FAST, "check_inventory"), \
                 patch.object(FAST, "learner_password", return_value="DummyNoLiveUse123!"), \
                 patch.object(FAST.subprocess, "run", side_effect=simulate):
                self.assertEqual(FAST.run(args), 1)
            self.assertEqual(events[0][1], "status")
            self.assertEqual(
                events[1:17],
                [(tech, "validate", "vulnerable") for tech in catalog[:16]],
            )
            self.assertEqual(events[17], ("sebackup_privilege", "reset", None))
            self.assertEqual(events[18], ("sebackup_privilege", "validate", "clean"))
            self.assertEqual(events[19], ("sebackup_privilege", "apply", None))
            self.assertFalse(any(x[0] in catalog[17:] for x in events))
            self.assertFalse(any(x[0] in catalog[:16] and x[1] in ("apply", "reset")
                                 for x in events))


if __name__ == "__main__":
    unittest.main()
