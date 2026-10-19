"""Source-only WSLPE41 freeze contract tests. Never contact VMware or Windows."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("wslpe41_freeze",ROOT/"scripts/wslpe41-freeze.py")
freeze=importlib.util.module_from_spec(spec)
spec.loader.exec_module(freeze)


def completed_journal():
    return {
        "schema":"kingdoms.wslpe45.resume_registered27.v1",
        "commit":freeze.SOURCE,
        "target":"WSLPE-WS01",
        "snapshot":freeze.OLD,
        "completed":True,
        "failure":None,
        "inflight":None,
        "runtime_configuration_pass_count":21,
        "baseline_count":20,
        "baseline_count_basis":"operator reported; not recounted",
        "preserved_state_sha256":freeze.FINGERPRINT,
        "learner_exploitation":"NOT_PROVEN_BY_THIS_RUN",
        "exclusions":{"25":"msi","36":"wmi","38":"dcom","40":"rpc"},
        "scenarios":[{
            "number":n,
            "installation":"PASS_EXISTING" if n in (27,30) else "PASS",
            "configuration_validation":"PASS",
            "exploitation":"NOT_TESTED",
        } for n in freeze.SELECTED],
        "resume_events":[
            {"stage":"in-place-completion","result":"PASS","exit_code":0},
            {"stage":"after-completion-preservation","result":"PASS","exit_code":0},
        ],
    }


class FreezeContractTests(unittest.TestCase):
    def test_exact_contract_accepts_final_21_only(self):
        freeze.validate_report(completed_journal())
        self.assertEqual(len(freeze.SELECTED),21)
        self.assertEqual(set(range(21,46))-set(freeze.SELECTED),{25,36,38,40})

    def test_rejects_partial_or_unproven_21(self):
        base=completed_journal()
        import copy
        variants=[]
        for key,value in [
            ("completed",False),("failure",{"number":27}),("inflight",{"number":27}),
            ("runtime_configuration_pass_count",20),("commit","0"*40),
            ("snapshot","other"),("preserved_state_sha256","1"*64)
        ]:
            doc=copy.deepcopy(base);doc[key]=value;variants.append(doc)
        for number in (0,5,20):
            doc=copy.deepcopy(base);doc["scenarios"][number]["configuration_validation"]="NOT_ATTEMPTED";variants.append(doc)
        doc=copy.deepcopy(base);doc["scenarios"][0]["exploitation"]="PASS";variants.append(doc)
        doc=copy.deepcopy(base);doc["exclusions"]["25"]="msi";doc["exclusions"].pop("36");variants.append(doc)
        doc=copy.deepcopy(base);doc["resume_events"][0]["result"]="FAIL";variants.append(doc)
        for doc in variants:
            with self.subTest(doc=doc):
                with self.assertRaises(ValueError):
                    freeze.validate_report(doc)

    def test_snapshot_commands_are_exact_and_read_only_until_execute(self):
        vmx=Path("/tmp/workspace/WSLPE-WS01.vmx")
        output="Total snapshots: 2\nKINGDOMS-WSLPE-PRE-LPE40-20261018\nOther\n"
        with patch.object(subprocess,"run",return_value=SimpleNamespace(returncode=0,stdout=output)) as run:
            names=freeze.snapshot_names(vmx)
        self.assertEqual(names,[freeze.OLD,"Other"])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0],[
            "vmrun","-T","ws","listSnapshots",str(vmx)])
        self.assertFalse(any("snapshot"==p for p in run.call_args.args[0]))

    def test_snapshot_listing_fails_closed(self):
        vmx=Path("/tmp/workspace/WSLPE-WS01.vmx")
        with patch.object(subprocess,"run",return_value=SimpleNamespace(returncode=0,stdout="broken")):
            with self.assertRaises(ValueError):
                freeze.snapshot_names(vmx)

    def test_never_redeploys_or_resets(self):
        src=(ROOT/"scripts/wslpe41-freeze.py").read_text()
        self.assertNotIn('"revertToSnapshot"',src)
        self.assertNotIn('"deleteSnapshot"',src)
        self.assertNotIn("wslpe_action",src)
        self.assertNotIn("--recover-failure",src)
        self.assertNotIn("--complete-registered27",src)
        self.assertIn('"vmrun", "-T", "ws", "snapshot", str(vmx), NAME',src)


if __name__=="__main__":
    unittest.main()
