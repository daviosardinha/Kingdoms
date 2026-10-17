"""Source-only #30 JEA operator gate; no Windows, VMware or NORTH calls."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/wslpe-jea-single.py"
SPEC=importlib.util.spec_from_file_location("wslpe_jea_single_gate",SCRIPT)
assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class JeaSingleGateTests(unittest.TestCase):
    def test_source_only_plan_never_calls_vmware_or_winrm(self):
        with patch.object(sys,"argv",["wslpe-jea-single.py"]), \
             patch.object(MOD,"snapshot_and_running_owner") as v, \
             patch.object(MOD,"run_readonly_probe") as w, \
             patch.object(MOD,"apply_jea") as a:
            self.assertEqual(MOD.main(),0)
            v.assert_not_called()
            w.assert_not_called()
            a.assert_not_called()

    def test_default_apply_refused_without_verified_real_recovery(self):
        with patch.object(sys,"argv",["wslpe-jea-single.py","--apply"]), \
             patch.object(MOD,"snapshot_and_running_owner") as v, \
             patch.object(MOD,"apply_jea") as a:
            self.assertEqual(MOD.main(),2)
            v.assert_not_called()
            a.assert_not_called()

    def test_confirmation_fails_closed_before_ansible(self):
        with patch.object(sys,"argv",["wslpe-jea-single.py","--apply",
                                      "--recovery-rehearsed"]), \
             patch.object(sys.stdin,"isatty",return_value=True), \
             patch.object(MOD,"snapshot_and_running_owner") as vm, \
             patch.object(MOD,"run_readonly_probe") as jea, \
             patch("builtins.input",return_value="NO"), \
             patch.object(MOD,"apply_jea") as a:
            self.assertEqual(MOD.main(),2)
            vm.assert_called_once()
            jea.assert_called_once()
            a.assert_not_called()

    def test_only_explicit_jea_stage_approval_is_allowed(self):
        with patch.object(sys,"argv",["wslpe-jea-single.py","--apply",
                                      "--recovery-rehearsed"]), \
             patch.object(sys.stdin,"isatty",return_value=True), \
             patch.object(MOD,"snapshot_and_running_owner"), \
             patch.object(MOD,"run_readonly_probe"), \
             patch("builtins.input",return_value="APPLY WSLPE JEA 30"), \
             patch.object(MOD,"apply_jea") as a:
            self.assertEqual(MOD.main(),0)
            a.assert_called_once()
            self.assertEqual(a.call_args.args[0]["number"],30)
            self.assertEqual(a.call_args.args[0]["id"],MOD.EXPECTED_ID)

    def test_script_cannot_execute_restart_or_other_lab(self):
        source=SCRIPT.read_text(encoding="utf-8")
        self.assertIn("verify_vmrun_output",source)
        self.assertIn("listSnapshots",source)
        self.assertIn("KINGDOMS-WSLPE-PRE-JEA",source)
        self.assertIn("wslpe-jea-readiness.py",source)
        self.assertIn('command(ansible, inv, varsfile, row, expected, "apply", None, "apply")',source)
        for wrong in ("revertToSnapshot", "vmrun\", \"-T\", \"ws\", \"stop\"",
                      "Restart-Service", "disable_vagrant",
                      "10.4.10.31","GOAD-WS01","--execute",
                      "ansible/roles/windows_lpe"):
            self.assertNotIn(wrong,source)

    def test_source_journal_validates_scoped_candidate(self):
        row=MOD.local_candidate()
        self.assertEqual(row["status"],"candidate")
        self.assertEqual(row["source_ci"],"passed")
        self.assertEqual(row["number"],30)

if __name__=="__main__":
    unittest.main()
