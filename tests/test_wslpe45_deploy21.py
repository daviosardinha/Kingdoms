"""Offline behavioral tests. No guest or VMware actions."""
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import yaml
from kingdoms import wslpe45_deploy21 as deploy
from kingdoms import wslpe45_batch_operator as batch

class DeploymentTests(unittest.TestCase):
    def report(self, rows):
        return {"completed": False, "inflight": None, "scenarios": [
            {"number": r["number"], "installation": "NOT_ATTEMPTED",
             "configuration_validation": "NOT_ATTEMPTED", "events": []} for r in rows]}

    def test_exact_selection_and_four_exclusions(self):
        rows = deploy.selection()
        self.assertEqual([r["number"] for r in rows],
                         [21,22,23,24,26,27,28,29,30,31,32,33,34,35,37,39,41,42,43,44,45])
        self.assertEqual(set(deploy.EXCLUDED), {25,36,38,40})
        self.assertEqual(len(rows),21)

    def test_every_failure_stops_without_reset_or_later_application(self):
        rows = deploy.selection()
        for failure in range(42):
            with self.subTest(failure=failure):
                report = self.report(rows)
                calls, saves = [], []
                def invoke(row, action, state, label):
                    self.assertEqual(report["inflight"]["number"], row["number"])
                    self.assertEqual(saves[-1]["inflight"]["stage"], label)
                    calls.append((row["number"], action))
                    return len(calls)-1 != failure, {"exit_code": 1 if len(calls)-1 == failure else 0}
                result = deploy.deployment_loop(rows, report,
                    lambda: saves.append(copy.deepcopy(report)), invoke)
                self.assertEqual(result, 2)
                self.assertEqual(len(calls), failure+1)
                self.assertFalse(report["completed"])
                self.assertEqual(calls, [(r["number"],a) for r in rows for a in ("apply","validate")][:failure+1])
                for previous in report["scenarios"][:failure//2]:
                    self.assertEqual(previous["configuration_validation"], "PASS")
                for later in report["scenarios"][failure//2+1:]:
                    self.assertEqual(later["installation"],"NOT_ATTEMPTED")

    def test_complete_run_keeps_installed_and_distinguishes_existing_jea(self):
        rows = deploy.selection()
        report = self.report(rows)
        self.assertEqual(deploy.deployment_loop(rows, report, lambda:None,
                        lambda *args:(True, {"exit_code":0})), 0)
        self.assertTrue(report["completed"])
        self.assertEqual(sum(r["configuration_validation"]=="PASS" for r in report["scenarios"]),21)
        self.assertEqual(report["scenarios"][8]["installation"],"PASS_EXISTING")

    def test_exception_retains_last_intent(self):
        rows = deploy.selection()
        report = self.report(rows)
        saved = []
        def interrupt(*args):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            deploy.deployment_loop(rows, report, lambda:saved.append(copy.deepcopy(report)), interrupt)
        self.assertEqual(saved[-1]["inflight"]["number"],21)
        self.assertFalse(report["completed"])

    def test_command_uses_only_exact_target_and_never_reset(self):
        paths = (Path("/ansible"),Path("/inventory"),Path("/vars"))
        for row in deploy.selection():
            for action,state,label in deploy.FLOW:
                command, marker = deploy.stage_command(*paths,row,"172.28.231.31",action,state,label)
                self.assertEqual(command[command.index("--limit")+1],"ws01,localhost")
                variables = json.loads(command[-1])
                self.assertTrue(variables["wslpe_pilot_preserve_shared"])
                self.assertTrue(variables["wslpe_deploy21"])
                self.assertNotIn(variables["wslpe_45_action"],("reset","reapply"))
                if row["number"]==30:
                    self.assertEqual(variables["wslpe_45_action"],"validate")
        for row in batch.index_rows():
            if row["number"] in deploy.EXCLUDED:
                with self.assertRaises(batch.BatchBlocked):
                    deploy.stage_command(*paths,row,"172.28.231.31","apply",None,"apply")
        with self.assertRaises(batch.BatchBlocked):
            deploy.stage_command(*paths,deploy.selection()[0],"172.28.231.31","reset",None,"reset")

    def test_plan_has_no_runtime_access(self):
        with patch.object(deploy,"provenance") as provenance, patch.object(deploy,"helper") as helper:
            self.assertEqual(deploy.run(SimpleNamespace(execute=False)),0)
            provenance.assert_not_called()
            helper.assert_not_called()

    def test_private_atomic_checkpoint_and_symlink_refusal(self):
        with TemporaryDirectory() as d:
            root = batch.make_private_dir(d)
            path = deploy.durable(root,"test.json",{"inflight":21})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(json.loads(path.read_text()),{"inflight":21})
            linked = root/"linked"
            linked.symlink_to(root,target_is_directory=True)
            with self.assertRaises(batch.BatchBlocked):
                batch.make_private_dir(str(linked))

    def test_recovery_sentinel_blocks_and_is_never_cleared(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            sentinel=deploy.require_recovery_clear(root)
            sentinel.write_text("previous-journal.json")
            with self.assertRaises(batch.BatchBlocked):
                deploy.require_recovery_clear(root)
            self.assertEqual(sentinel.read_text(),"previous-journal.json")
            sentinel.unlink()
            sentinel.symlink_to(root/"missing")
            with self.assertRaises(batch.BatchBlocked):
                deploy.require_recovery_clear(root)

    def test_timeout_preserves_partial_diagnostics(self):
        error = subprocess.TimeoutExpired(["ansible"],2,output=b"partial evidence",stderr=b"failed detail")
        with patch.object(deploy.subprocess,"run",side_effect=error):
            code, output = deploy.run_command(["ansible"],{},60)
        self.assertEqual(code,124)
        self.assertIn("partial evidence",output)
        self.assertIn("failed detail",output)

    def test_all_selected_playbooks_preserve_verified_common_library(self):
        for row in deploy.selection():
            path = batch.ROOT/row["playbook"]
            plays = yaml.safe_load(path.read_text())
            self.assertEqual([p["hosts"] for p in plays],["localhost","wslpe"])
            self.assertFalse(batch.controller_source_blockers(path,plays))
            for task in plays[1]["tasks"]:
                payload = task.get("ansible.windows.win_copy",{})
                directory = task.get("ansible.windows.win_file",{})
                if payload.get("src","").endswith("WslpeFixture.psm1") or directory:
                    self.assertIn("not (wslpe_pilot_preserve_shared",task["when"])
            self.assertIn("WSLPE21_STAGE=",str(plays[1]["post_tasks"]))

    def test_preflight_is_read_only_and_preserves_jea_rpc_25(self):
        plays = yaml.safe_load(deploy.PREFLIGHT.read_text())
        script = plays[1]["tasks"][0]["ansible.windows.win_powershell"]["script"]
        for prohibited in ("Set-Acl","Set-Content","Remove-Item","Stop-Process","Stop-Service","Register-PSSessionConfiguration"):
            self.assertNotIn(prohibited,script)
        for required in ("Kingdom40LocalRpcServer.exe","OWNED_MARKER_ONLY","learner_sid",
                         "AreAccessRulesProtected","Get-FileHash","WSLPE21_PRESERVED="):
            self.assertIn(required,script)
        jea = deploy.JEA.read_text()
        self.assertIn("no_log: true",jea)
        self.assertIn("-Operation Status",jea)
        self.assertNotIn("-Operation Proof",jea)

    def test_updater_executes_protected_copy_of_verified_open_handle(self):
        source=(batch.ROOT/"ansible/files/wslpe45/KingdomServiceConsumer.cs").read_text()
        self.assertIn("GetFinalPathNameByHandle(input.SafeFileHandle",source)
        self.assertIn("FileAccess.Read, FileShare.Read",source)
        self.assertIn("FileMode.CreateNew",source)
        self.assertLess(source.index("path = StageOpenedUpdate(path, prefix)"),
                        source.index("child = new ProcessStartInfo(path)"))

    def test_selected_sources_do_not_address_excluded_rpc_resources(self):
        resources = ("custom_rpc_authorization", "KingdomsWSLPE40",
                     "Kingdom40LocalRpc", "Wslpe40RpcOperator")
        for row in deploy.selection():
            path = batch.ROOT / row["playbook"]
            sources = [path]
            for play in yaml.safe_load(path.read_text()):
                for key in ("pre_tasks", "tasks", "post_tasks"):
                    for task in play.get(key, []):
                        source = task.get("ansible.windows.win_copy", {}).get("src")
                        if source:
                            self.assertNotIn("{{", source)
                            sources.append((path.parent / source).resolve())
            for source in sources:
                content = source.read_text()
                for resource in resources:
                    self.assertNotIn(resource, content, str(source))

    def test_rpc_coexistence_checks_identity_without_invoking_rpc(self):
        script = yaml.safe_load(deploy.PREFLIGHT.read_text())[1]["tasks"][0][
            "ansible.windows.win_powershell"]["script"]
        self.assertNotIn("Existing #40 privileged RPC host is active", script)
        for required in ("Assert-Wslpe21RpcObservation", "ExecutablePath", "CommandLine",
                         "--serve-local-only", "-MethodName GetOwnerSid",
                         "Get-NetTCPConnection", "Get-NetUDPEndpoint", "NetworkEndpointCount",
                         "Wrong #40 ownership marker", "WSLPE21_RPC40="):
            self.assertIn(required, script)
        for forbidden in ("Invoke-Wslpe40RpcOperator", "Start-Process", "Import-Module",
                          "Kingdom40OwnedProof", "Kingdom40Status"):
            self.assertNotIn(forbidden, script)

if __name__=="__main__":
    unittest.main()
