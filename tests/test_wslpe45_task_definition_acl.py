"""Source-only WSLPE Task Scheduler task-definition DACL fixture checks.

Task ACL testing is separate from the existing Foundation task executable ACL
and from real local learner exploitation.
"""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "ansible/wslpe45/scheduled_task_definition_acl.yml"
LIBRARY = ROOT / "ansible/files/wslpe45/WslpeFixture.psm1"


class TaskDefinitionCandidateTests(unittest.TestCase):
    def test_exact_standalone_scope(self):
        plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
        self.assertEqual([item["hosts"] for item in plays], ["localhost", "wslpe"])
        checks = " ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
        for token in ("wslpe_expected_address", "wslpe_45_stage_label",
                      "scheduled_task_definition_acl", "groups.get('dc'",
                      "groups.get('domain'", "windows_lpe_standalone"):
            self.assertIn(token, checks)
        target_check = plays[1]["pre_tasks"][0]["ansible.windows.win_powershell"]["script"]
        for token in ("WSLPE-WS01", "PartOfDomain", "Windows 10",
                      "Get-LocalUser", "Get-LocalGroupMember"):
            self.assertIn(token, target_check)

    def test_task_ace_is_scoped_to_own_new_system_task(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        for required in ("Kingdom45DefinitionTask", "GetSecurityDescriptor(4)",
                         "SetSecurityDescriptor(", "CommonAce", "0x001f01ff",
                         "Register-ScheduledTask", "Unregister-ScheduledTask",
                         "New-Wslpe45OwnedFixture -Number 21",
                         "Assert-Wslpe45OwnedFixture -Number 21",
                         "Remove-Wslpe45OwnedFixture -Number 21",
                         "WSLPE45_BATCH_STAGE="):
            self.assertIn(required, text)
        for forbidden in ("GOAD-WS01", "10.4.10.31",
                          "KingdomTaskBinary", "KingdomTaskDirectory",
                          "sc.exe sdset scmanager", "Set-MpPreference",
                          "hosts: dc", "hosts: domain", "roles:"):
            self.assertNotIn(forbidden, text)
        self.assertIn("VULNERABLE_CONFIGURATION", text)
        self.assertNotIn("LEARNER_EXPLOITED=PASS", text)

    def test_owned_directory_blocks_unintended_binary_replacement(self):
        source = LIBRARY.read_text(encoding="utf-8")
        self.assertIn("SetAccessRuleProtection($true, $false)", source)
        self.assertIn("Set-Acl -LiteralPath $root", source)
        self.assertIn("FullControl", source)
        self.assertIn("'S-1-5-18','S-1-5-32-544'", source)


if __name__ == "__main__":
    unittest.main()
