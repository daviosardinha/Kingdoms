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

    def inspection_fixture(self, root):
        identity = {"target": "WSLPE-WS01", "address": "172.28.231.31",
                    "workspace": "/native/workspace", "inventory": "/native/inventory",
                    "vmx": "/native/guest.vmx", "snapshot": "existing-snapshot"}
        parent = {"schema": "kingdoms.wslpe45.deploy21.v1", "commit": "a"*40,
                  "completed": False, "inflight": None,
                  "exclusions": {str(k): v for k, v in deploy.EXCLUDED.items()},
                  "failure": {"number": 27, "stage": "apply", "exit_code": 2},
                  "runtime_configuration_pass_count": 5, "preserved_state_sha256": "A"*64,
                  "scenarios": [], **identity}
        for index, row in enumerate(deploy.selection()):
            install, validate = ("PASS", "PASS") if index < 5 else (
                ("FAIL", "NOT_ATTEMPTED") if index == 5 else ("NOT_ATTEMPTED", "NOT_ATTEMPTED"))
            parent["scenarios"].append({"number": row["number"], "name": row["id"],
                "installation": install, "configuration_validation": validate})
        path = deploy.durable(root, "wslpe45-deploy21-"+"b"*16+".json", parent)
        sentinel = root / ".wslpe45-recovery-required"
        sentinel.write_text(path.name+"\n")
        sentinel.chmod(0o600)
        return identity, parent, path, sentinel

    def test_inspection_requires_matching_private_journal_and_sentinel(self):
        with TemporaryDirectory() as directory:
            root = batch.make_private_dir(directory)
            identity, parent, path, sentinel = self.inspection_fixture(root)
            observed, digest = deploy.inspection_parent(root, str(path), identity)
            self.assertEqual(observed, parent)
            self.assertEqual(len(digest), 64)
            sentinel.write_text("different.json\n")
            with self.assertRaises(batch.BatchBlocked):
                deploy.inspection_parent(root, str(path), identity)
            sentinel.write_text(path.name+"\n")
            with self.assertRaises(batch.BatchBlocked):
                deploy.inspection_parent(root, str(path), dict(identity, address="10.4.10.31"))
            path.chmod(0o644)
            with self.assertRaises(batch.BatchBlocked):
                deploy.inspection_parent(root, str(path), identity)

    def test_inspection_rejects_changed_failure_order_and_partial_intent(self):
        with TemporaryDirectory() as directory:
            root = batch.make_private_dir(directory)
            identity, parent, path, sentinel = self.inspection_fixture(root)
            changes = [
                dict(parent, inflight={"number": 27, "stage": "apply"}),
                dict(parent, failure={"number": 28, "stage": "apply", "exit_code": 2}),
                dict(parent, scenarios=list(reversed(parent["scenarios"]))),
                dict(parent, preserved_state_sha256=""),
                dict(parent, exclusions={}),
            ]
            for changed in changes:
                deploy.durable(root, path.name, changed)
                with self.assertRaises(batch.BatchBlocked):
                    deploy.inspection_parent(root, str(path), identity)

    def test_read_only_inspection_retains_original_recovery_state_on_pass_and_failure(self):
        for failed_step in (None, 0, 1, 2):
            with TemporaryDirectory() as directory:
                root = batch.make_private_dir(directory)
                identity, parent, path, sentinel = self.inspection_fixture(root)
                original = path.read_bytes(), sentinel.read_bytes()
                calls = []
                def command(cmd, env, timeout):
                    index = len(calls)
                    calls.append(cmd)
                    if index == failed_step:
                        return 2, "native inspection failure"
                    if index == 1:
                        return 0, "WSLPE21_INSPECT27=PASS"
                    return 0, "WSLPE21_PREFLIGHT=PASS WSLPE21_PRESERVED="+"A"*64
                with patch.object(deploy, "run_command", side_effect=command), patch.object(
                        deploy, "save_log", return_value=root/"evidence.log"), patch.object(
                        deploy, "stage_command") as stage:
                    result = deploy.inspect_failure(root, str(path), identity, "c"*40,
                        object(), Path("/ansible"), Path("/inventory"), Path("/vars"), {}, 900)
                self.assertEqual(result, 0 if failed_step is None else 2)
                self.assertEqual(len(calls), 3 if failed_step is None else failed_step+1)
                stage.assert_not_called()
                self.assertEqual((path.read_bytes(), sentinel.read_bytes()), original)

    def test_inspection_script_never_stages_or_activates_fixture(self):
        plays = yaml.safe_load(deploy.INSPECT27.read_text())
        self.assertEqual([p["hosts"] for p in plays], ["localhost", "wslpe"])
        script = plays[1]["tasks"][0]["ansible.windows.win_powershell"]["script"]
        for forbidden in ("Set-Acl", "Set-Content", "Remove-Item", "Start-Process",
                          "Import-Module", "Register-ScheduledTask", "New-Service",
                          "Invoke-Wslpe45ComRegistration", "-ComObject", "LoadFrom"):
            self.assertNotIn(forbidden, script)
        for required in ("GetAssemblyName", "OpenSubKey($SubKey,$false)",
                         "Export-ScheduledTask", "RECOVERY_REVIEW_REQUIRED",
                         "WSLPE21_INSPECT27=PASS"):
            self.assertIn(required, script)

    def test_inspection_cannot_be_combined_with_execute(self):
        with patch.object(deploy, "provenance") as provenance:
            with self.assertRaises(batch.BatchBlocked):
                deploy.run(SimpleNamespace(execute=True, inspect_failure="journal.json"))
            provenance.assert_not_called()


    def recovery_state(self):
        prefix = r"C:\ProgramData\KingdomsWSLPE45\fixtures\com_clsid_registration_hijack"
        paths = (prefix, prefix + r"\.kingdoms-owned.json",
                 prefix + r"\inbox", prefix + r"\Kingdom45ComServer.dll",
                 prefix + r"\inbox\Kingdom45ComServer.dll")
        sid = "S-1-5-21-123-456-789-1002"
        marker = {"schema": "kingdoms.wslpe.fixture-owner.v1",
                  "machine": "WSLPE-WS01", "number": 27,
                  "id": "com_clsid_registration_hijack",
                  "learner_sid": sid, "created_utc": "2026-10-19T08:39:23Z"}
        files = []
        for name in paths:
            directory = name in (prefix, prefix + r"\inbox")
            record = {"path": name, "directory": directory, "sddl": "O:BAG:PAI"}
            if not directory:
                record.update(sha256="A"*64, length=4096)
            if name.endswith(".dll"):
                record["assembly_name"] = "Kingdom45ComServer, Version=0.0.0.0"
            files.append(record)
        return {"schema": "kingdoms.wslpe45.inspect27.v1",
                "target": "WSLPE-WS01", "learner_sid": sid,
                "marker": marker, "files": files, "registry": [],
                "tasks": [], "regasm_processes": [],
                "assessment": "RECOVERY_REVIEW_REQUIRED", "guest_mutations": False,
                "observed_utc": "2026-10-19T10:40:09Z"}

    def test_reviewed_partial_requires_exact_five_owned_entries_and_no_activation(self):
        identity = {"target": "WSLPE-WS01"}
        snapshot = self.recovery_state()
        deploy.validate_partial27(snapshot, identity)
        for wrong in (
            dict(snapshot, registry=[{"path": "unexpected"}]),
            dict(snapshot, tasks=[{"name": "consumer"}]),
            dict(snapshot, regasm_processes=[{"pid": 1}]),
            dict(snapshot, files=snapshot["files"][:-1]),
            dict(snapshot, guest_mutations=True),
            dict(snapshot, learner_sid="S-1-5-21-0-0-0-1002"),
        ):
            with self.subTest(wrong=wrong.keys()):
                with self.assertRaises(batch.BatchBlocked):
                    deploy.validate_partial27(wrong, identity)

    def test_recovery_inspection_requires_protected_journal_bound_logs(self):
        import hashlib
        with TemporaryDirectory() as directory:
            root = batch.make_private_dir(directory)
            identity, parent, original, sentinel = self.inspection_fixture(root)
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            snapshot = self.recovery_state()
            log = root/"wslpe-inspect27-state-"+"a"*12+".log"
            message = "WSLPE21_INSPECT27_JSON="+json.dumps(snapshot, separators=(",", ":"))
            log.write_text('"'+json.dumps(message)[1:-1]+'",\n')
            log.chmod(0o600)
            events = [{"stage": stage, "result": "PASS", "exit_code": 0,
                       "private_log": str(log)} for stage in ("before","state","after")]
            doc = {"schema": "kingdoms.wslpe45.inspect27-controller.v1",
                   "parent_journal": str(original), "parent_sha256": digest,
                   "read_only": True, "completed": True, "inflight": None,
                   "assessment": "RECOVERY_REVIEW_REQUIRED",
                   "events": events, **identity}
            report = deploy.durable(root,"wslpe45-inspect27-"+"c"*16+".json",doc)
            observed, path = deploy.original_inspection(
                root, str(original), digest, identity, str(report))
            self.assertEqual(deploy.stable_inspection(observed),
                             deploy.stable_inspection(snapshot))
            self.assertEqual(path, report)
            doc["parent_sha256"] = "0"*64
            deploy.durable(root, report.name, doc)
            with self.assertRaises(batch.BatchBlocked):
                deploy.original_inspection(root,str(original),digest,identity,str(report))
            doc["parent_sha256"] = digest
            deploy.durable(root, report.name, doc)
            log.chmod(0o644)
            with self.assertRaises(batch.BatchBlocked):
                deploy.original_inspection(root,str(original),digest,identity,str(report))

    def test_recovery_resume_starts_at_27_without_replaying_prior_success(self):
        rows = deploy.selection()
        report = self.report(rows)
        for record in report["scenarios"][:5]:
            record["installation"] = "PASS"
            record["configuration_validation"] = "PASS"
        before = copy.deepcopy(report["scenarios"][:5])
        called = []
        result = deploy.deployment_loop(
            rows, report, lambda: None,
            lambda row, action, state, label:
                (called.append((row["number"], action)) or True, {"exit_code": 0}),
            start_at=5)
        self.assertEqual(result, 0)
        self.assertEqual(called[0], (27, "apply"))
        self.assertEqual(called[-1], (45, "validate"))
        self.assertEqual(len(called), 32)
        self.assertEqual(report["scenarios"][:5], before)

    def test_recovery_playbook_is_exact_and_never_recursive(self):
        path = batch.ROOT/"ansible/wslpe45/deploy21-recover27.yml"
        plays = yaml.safe_load(path.read_text())
        self.assertEqual([play["hosts"] for play in plays], ["localhost", "wslpe"])
        script = plays[1]["tasks"][0]["ansible.windows.win_powershell"]["script"]
        for required in ("WSLPE21_RECOVER27=cleanup:PASS",
                         "WSLPE21_RECOVER27=verify:PASS",
                         "C:\\ProgramData\\KingdomsWSLPE45\\fixtures\\com_clsid_registration_hijack",
                         "ReparsePoint", "Get-FileHash", "learner_sid",
                         "Registry64", "Get-ScheduledTask", "RegAsm.exe",
                         "Remove-Item -LiteralPath"):
            self.assertIn(required, script)
        for forbidden in ("-Recurse", "Stop-Process", "Unregister-ScheduledTask",
                          "Remove-Wslpe45OwnedFixture", "Invoke-Wslpe45ComRegistration",
                          "Register-ScheduledTask", "New-Object -ComObject"):
            self.assertNotIn(forbidden, script)

    def test_recovery_cli_requires_explicit_authority_and_inspection(self):
        scenarios = [
            SimpleNamespace(execute=False, inspect_failure=None, recover_failure="prior.json",
                            inspection_report="inspection.json"),
            SimpleNamespace(execute=True, inspect_failure=None, recover_failure="prior.json",
                            inspection_report=None),
            SimpleNamespace(execute=True, inspect_failure="prior.json", recover_failure="prior.json",
                            inspection_report="inspection.json"),
        ]
        with patch.object(deploy, "provenance") as provenance:
            for args in scenarios:
                with self.assertRaises(batch.BatchBlocked):
                    deploy.run(args)
            provenance.assert_not_called()

if __name__=="__main__":
    unittest.main()
