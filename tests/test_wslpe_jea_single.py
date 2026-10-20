"""#30 independent local JEA lifecycle: source-only checks; no guest calls."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock
import yaml

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/wslpe-jea-single.py"
STAGE=ROOT/"ansible/wslpe45/jea_local_stage.yml"
FIXTURE=ROOT/"ansible/wslpe45/jea_role_capability_misconfig.yml"
LOCAL=ROOT/"ansible/files/wslpe45/WslpeJeaLocal.psm1"
MODULE=ROOT/"ansible/files/wslpe45/WslpeJea.psm1"
LOCKDOWN=ROOT/"ansible/wslpe45/lockdown-library.yml"

SPEC=importlib.util.spec_from_file_location("wslpe_jea_single_test_target",SCRIPT)
assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class JeaLocalLifecycleTests(unittest.TestCase):
    def test_plan_source_only_no_vmware_or_ansible(self):
        with patch.object(sys,"argv",[str(SCRIPT)]), \
             patch.object(MOD,"exact_running_vm_and_snapshot") as vm, \
             patch.object(MOD,"stage_sources") as stage, \
             patch.object(MOD,"pinned_https_preflight") as tls:
            self.assertEqual(MOD.main(),0)
            vm.assert_not_called()
            stage.assert_not_called()
            tls.assert_not_called()

    def test_all_remote_endpoint_mutation_flags_stay_blocked(self):
        for args in (["--apply"],["--recovery-rehearsed"],
                     ["--apply","--recovery-rehearsed"]):
            with self.subTest(args=args),patch.object(sys,"argv",[str(SCRIPT),*args]), \
                 patch.object(MOD,"stage_sources") as stage:
                self.assertEqual(MOD.main(),2)
                stage.assert_not_called()

    def test_staging_requires_interactive_confirmation(self):
        with patch.object(sys,"argv",[str(SCRIPT),"--stage"]), \
             patch.object(sys.stdin,"isatty",return_value=False), \
             patch.object(MOD,"stage_sources") as stage:
            self.assertEqual(MOD.main(),2)
            stage.assert_not_called()
        with patch.object(sys,"argv",[str(SCRIPT),"--stage"]), \
             patch.object(sys.stdin,"isatty",return_value=True), \
             patch.object(MOD,"stage_sources") as stage:
            self.assertEqual(MOD.main(),0)
            stage.assert_called_once_with()

    def test_staging_provenance_exact_owned_sources(self):
        row=MOD.local_candidate()
        self.assertEqual(row["number"],30)
        plays=yaml.safe_load(STAGE.read_text(encoding="utf-8"))
        self.assertEqual([p["hosts"] for p in plays],["localhost","wslpe"])
        tasks=plays[1]["tasks"]
        copies=[t["ansible.windows.win_copy"]["src"] for t in tasks
                if "ansible.windows.win_copy" in t]
        self.assertEqual(copies,[
            "../files/wslpe45/WslpeFixture.psm1",
            "../files/wslpe45/WslpeJea.psm1",
            "../files/wslpe45/WslpeJeaLocal.psm1"])
        self.assertTrue(all((STAGE.parent/s).is_file() for s in copies))
        self.assertIn("wslpe_jea_stage_approved",
                      " ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"]))
        self.assertEqual(sum(
            t.get("ansible.builtin.import_tasks")=="lockdown-library.yml"
            for t in tasks),1)
        self.assertEqual(
            yaml.safe_load(LOCKDOWN.read_text())[0]["when"],
            "wslpe_45_action == 'apply' and not (wslpe_pilot_preserve_shared | default(false) | bool)")
        imports=[t for t in tasks if t.get("ansible.builtin.import_tasks")=="lockdown-library.yml"]
        self.assertEqual(imports[0]["vars"]["wslpe_45_action"],"apply")
        text=STAGE.read_text()
        for token in ("Register-PSSessionConfiguration",
                      "Unregister-PSSessionConfiguration",
                      "Restart-Service", "Start-Service WinRM",
                      "Invoke-Wslpe45Jea -Action"):
            self.assertNotIn(token,text)

    def test_console_check_fails_closed_without_active_session(self):
        local=LOCAL.read_text(encoding="utf-8")
        self.assertIn("if ($consoleId -eq [uint32]::MaxValue",local)
        self.assertIn("WTSGetActiveConsoleSessionId",local)
        self.assertIn('Get-Variable PSSenderInfo',local)
        self.assertIn('IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)',local)
        self.assertNotIn("$env:SESSIONNAME -cne 'Console'",local)
        module=MODULE.read_text(encoding="utf-8")
        self.assertIn("Assert-Wslpe45JeaConsole",module)
        self.assertNotIn("$env:SESSIONNAME -cne 'Console'",module)

    def test_remote_journal_hard_blocks_apply_reset(self):
        plays=yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(plays[1]["pre_tasks"][0]["when"],
           "(wslpe_45_action | default('')) in ['apply', 'reset']")
        self.assertIn("ansible.builtin.fail",plays[1]["pre_tasks"][0])

    def test_local_mutation_requires_console_and_owning_admin(self):
        local=LOCAL.read_text(encoding="utf-8")
        module=MODULE.read_text(encoding="utf-8")
        for token in ("WTSGetActiveConsoleSessionId","Console","PSSenderInfo",
                      "IsInRole","Assert-Wslpe45Identity","Get-Service WinRM"):
            self.assertIn(token,local)
        self.assertIn("Assert-Wslpe45OwnedFixture",local)
        self.assertIn("WSLPE45_JEA_LOCAL_INSPECTION=PASS",local)
        self.assertIn("Restore-Wslpe45WinrmAfterLocalJea",local)
        self.assertIn("Start-Service WinRM",local)
        self.assertIn("Get-NetTCPConnection -LocalPort 5986",local)
        self.assertIn("finally {",local)
        self.assertIn("WSLPE45_JEA_HTTPS_REMOTE_PROOF=PENDING",local)
        self.assertIn("PSSenderInfo",local)
        self.assertIn("Wslpe45ConsoleSessionNative",local)
        self.assertIn("[uint32]::MaxValue",local)
        self.assertIn("$processSessionId -eq 0",local)
        self.assertIn("$processSessionId -ne $consoleId",local)
        self.assertIn("Assert-Wslpe45JeaConsole",module)
        self.assertIn("WslpeJeaLocal.psm1",module)
        self.assertIn("Assert-Wslpe45JeaConsole",local)
        self.assertNotIn("$env:SESSIONNAME",local)
        self.assertNotIn("$env:SESSIONNAME",module)
        self.assertNotIn(" -NoServiceRestart -Force",module)
        self.assertNotIn("Restart-Service",local)
        for forbidden in ("revertToSnapshot","GOAD-WS01","10.4.10.31",
                          "Disable-LocalUser","Remove-LocalUser","vmrun"):
            self.assertNotIn(forbidden,local)

if __name__=="__main__":
    unittest.main()
