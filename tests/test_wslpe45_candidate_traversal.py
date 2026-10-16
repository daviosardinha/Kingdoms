"""Candidate #35 standalone fixture source guard; NOT runtime/learner acceptance."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAY = ROOT / "ansible/wslpe45/traversal.yml"
C_SHARP = ROOT / "ansible/files/wslpe45/KingdomTraversalService.cs"
MODULE = ROOT / "ansible/files/wslpe45/WslpeFixture.psm1"


class Wslpe45CandidateTraversalTests(unittest.TestCase):
    def test_exact_standalone_scope_only(self):
        plays = yaml.safe_load(PLAY.read_text(encoding="utf-8"))
        self.assertEqual(len(plays), 2)
        self.assertEqual(plays[0]["hosts"], "localhost")
        self.assertEqual(plays[1]["hosts"], "wslpe")
        self.assertFalse(plays[0]["gather_facts"])
        self.assertFalse(plays[1]["gather_facts"])
        checks = " ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
        for required in ("windows_lpe_standalone", "['ws01']", "wslpe_expected_address",
                         "domain", "dc", "winrm"):
            self.assertIn(required, checks)
        pre = plays[1]["pre_tasks"][0]["ansible.windows.win_powershell"]["script"]
        for required in ("WSLPE-WS01", "PartOfDomain", "lpe.trainee", "Windows 10",
                         "Get-LocalGroupMember"):
            self.assertIn(required, pre)
        self.assertNotIn("roles:", PLAY.read_text())
        self.assertNotIn("10.4.10.31", PLAY.read_text())

    def test_six_stage_actions_are_separate_not_marked_qualified(self):
        tasks = yaml.safe_load(PLAY.read_text())[1]["tasks"]
        scenarios = [(task["name"],task.get("when","")) for task in tasks]
        self.assertTrue(any("apply" in str(condition) for _, condition in scenarios))
        self.assertTrue(any("reset" in str(condition) for _, condition in scenarios))
        self.assertTrue(any("vulnerable" in str(condition) for _, condition in scenarios))
        self.assertTrue(any("clean" in str(condition) for _, condition in scenarios))
        text = PLAY.read_text()
        self.assertNotIn("WSLPE_STANDALONE_45_TECHNIQUES_ACCEPTED", text)
        self.assertNotIn("LEARNER_EXPLOITED=PASS", text)

    def test_service_has_only_owned_proof_path_no_arbitrary_exec(self):
        code = C_SHARP.read_text()
        for required in ("System.ServiceProcess", "ServiceBase",
                         "privileged_path_traversal_write", "WindowsIdentity.GetCurrent",
                         "StringComparison.OrdinalIgnoreCase", "Path.GetFullPath",
                         "WSLPE45_TRAVERSAL_PROOF"):
            self.assertIn(required, code)
        for forbidden in ("Process.Start", "cmd.exe", "powershell.exe",
                          "System32", "CreateProcess", "RegistryKey", "HttpListener"):
            self.assertNotIn(forbidden, code)
        self.assertIn("String.Equals(destination, allowedProof", code)

    def test_shared_ownership_module_refuses_reparse_and_wrong_identity(self):
        ps = MODULE.read_text(encoding="utf-8")
        for required in ("WSLPE-WS01", "PartOfDomain", "Get-LocalUser",
                         "KingdomsWSLPE45", ".kingdoms-owned.json",
                         "Assert-Wslpe45NoReparsePoints",
                         "Remove-Wslpe45OwnedFixture", "ValidateRange(21,45)"):
            self.assertIn(required, ps)
        for forbidden in ("GOAD-WS01", "NORTH\\", "10.4.10.31",
                          "sc.exe sdset scmanager", "Set-MpPreference",
                          "DisableRealtimeMonitoring", "Stop-Process -Name lsass"):
            self.assertNotIn(forbidden, ps)

    def test_candidate_apply_is_explicit_and_reset_checks_service_ownership(self):
        source = PLAY.read_text()
        for required in ("New-Wslpe45OwnedFixture -Number 35", 
                         "Assert-Wslpe45OwnedFixture -Number 35",
                         "Remove-Wslpe45OwnedFixture -Number 35",
                         "if (Get-Service -Name $name",
                         "Refusing to remove service with non-owned ImagePath",
                         "New-Service -Name $name",
                         "LCRP;;;$sid"):
            self.assertIn(required, source)
        self.assertNotIn("sc.exe sdset scmanager", source)
        self.assertNotIn("Remove-Item -LiteralPath 'C:\\Windows", source)


if __name__ == "__main__":
    unittest.main()
