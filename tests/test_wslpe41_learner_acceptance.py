"""Source-only learner acceptance manifest tests. No guest or VMware access."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("wslpe41_acceptance",ROOT/"scripts/wslpe41-learner-acceptance.py")
acceptance=importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


class Wslpe41AcceptancePlanTests(unittest.TestCase):
    def test_41_unique_original_ids_and_four_retired(self):
        rows=acceptance.scenario_manifest()
        self.assertEqual(len(rows),41)
        self.assertEqual(len({r["number"] for r in rows}),41)
        self.assertEqual(len({r["id"] for r in rows}),41)
        self.assertEqual([r["number"] for r in rows[:20]],list(range(1,21)))
        self.assertEqual([r["number"] for r in rows[20:]],
            [21,22,23,24,26,27,28,29,30,31,32,33,34,35,37,39,41,42,43,44,45])
        self.assertEqual({r["learner"] for r in rows},{"NOT_TESTED"})
        self.assertEqual(acceptance.EXCLUDED,{25,36,38,40})

    def test_default_plan_does_not_touch_local_guest(self):
        from io import StringIO
        with patch.object(acceptance,"verify_receipt") as receipt,patch("sys.stdout",new_callable=StringIO) as stdout:
            self.assertEqual(acceptance.main([]),0)
        receipt.assert_not_called()
        self.assertIn("0 demonstrated",stdout.getvalue())
        self.assertIn("no WinRM, VMware",stdout.getvalue())

    def test_frozen_receipt_gate_rejects_missing_and_incomplete(self):
        from kingdoms import wslpe45_batch_operator as batch
        with TemporaryDirectory() as tmp:
            root=batch.make_private_dir(tmp)
            path=root/("wslpe41-freeze-"+"a"*16+".json")
            data={
                "schema":"kingdoms.wslpe41.freeze.v1",
                "status":"PASS",
                "snapshot":acceptance.FREEZE_SNAPSHOT,
                "deployed_source_commit":"6b612e9abf2547dc76e4d4a89f4df1be6137f6e6",
                "fingerprint":"9AB97BF7EB5D424B87F2893D41816BE78683F7BAC407C68B4ADAC2E5BB724D26",
                "learner_exploitation":"NOT_TESTED"
            }
            batch.atomic_report(root,path.name,data)
            self.assertEqual(acceptance.verify_receipt(str(path),root)["status"],"PASS")
            for key,bad in (("status","STARTED"),("snapshot","UNKNOWN"),
                            ("deployed_source_commit","0"*40),("learner_exploitation","PASS")):
                mutated=dict(data,**{key:bad})
                batch.atomic_report(root,path.name,mutated)
                with self.assertRaises(ValueError):
                    acceptance.verify_receipt(str(path),root)
            batch.atomic_report(root,path.name,data)
            with self.assertRaises(ValueError):
                acceptance.verify_receipt(str(root/"unrelated.json"),root)

    def test_scheduled_task_pilot21_is_read_only_and_scoped(self):
        path=ROOT/"scripts/wslpe41-learner-pilot21-readonly.ps1"
        script=path.read_text(encoding="utf-8")
        for expected in ("Get-CimInstance Win32_ComputerSystem",
                         "WSLPE-WS01","lpe.trainee",
                         "Get-NetAdapter","GetSecurityDescriptor(4)",
                         "scheduled_task_definition_acl", "Kingdom45DefinitionTask",
                         "Kingdom45Task21.exe",
                         "WSLPE41_21_LEARNER_EXPLOITATION=NOT_TESTED",
                         "WSLPE41_21_READONLY_PREFLIGHT=PASS"):
            self.assertIn(expected,script)
        self.assertNotIn("exit 2",script)
        self.assertIn("WSLPE41_21_FAILED_STAGE=",script)
        self.assertIn("WSLPE41_21_LEARNER_EXPLOITATION=NOT_TESTED",script)
        self.assertIn("throw ('WSLPE41_21_READONLY_PREFLIGHT=BLOCKED at ' + $stage)",script)
        for stage in ("LEARNER_BOUNDARY","OWNED_FIXTURE","SYSTEM_TASK","LEARNER_TASK_ACL"):
            self.assertIn("$stage = '"+stage+"'",script)
        for forbidden in ("SetSecurityDescriptor(","Register-ScheduledTask",
                          "Set-ScheduledTask","Start-ScheduledTask",
                          "Unregister-ScheduledTask","Invoke-Command",
                          "New-ScheduledTaskAction","Set-ItemProperty",
                          "Remove-Item","-Execute ", "New-Service"):
            self.assertNotIn(forbidden,script)

    def test_no_exploit_execution_in_plan(self):
        source=(ROOT/"scripts/wslpe41-learner-acceptance.py").read_text()
        for banned in ("ansible-playbook", "Invoke-Command", "wmic ", "vmrun",
                       "snapshots -delete", "subprocess.run", "--execute"):
            self.assertNotIn(banned,source)


if __name__=="__main__":
    unittest.main()
