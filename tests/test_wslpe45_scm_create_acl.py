"""Read-only SCM create-service permissions fixture tests (not runtime proof)."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
PLAY=ROOT/"ansible/wslpe45/scm_create_service_acl.yml"

class ScmCandidateTests(unittest.TestCase):
    def test_exact_guest_and_reversible_sddl(self):
        text=PLAY.read_text()
        plays=yaml.safe_load(text)
        self.assertEqual([p["hosts"] for p in plays],["localhost","wslpe"])
        assertions=" ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
        for required in ("wslpe_expected_address","scm_create_service_acl",
                         "wslpe_45_stage_label","windows_lpe_standalone",
                         "groups.get('dc'","groups.get('domain'"):
            self.assertIn(required,assertions)
        body=plays[1]["tasks"][-1]["ansible.windows.win_powershell"]["script"]
        for required in ("sc.exe sdshow scmanager","sc.exe sdset scmanager",
                         "0x0002","New-Wslpe45OwnedFixture -Number 22",
                         "Assert-Wslpe45OwnedFixture -Number 22",
                         "Remove-Wslpe45OwnedFixture -Number 22",
                         "original-scm-sddl.json",
                         "SCM ACL changed outside the intended lab ACE",
                         "manual recovery required",
                         "WSLPE45_BATCH_STAGE="):
            self.assertIn(required,body)
        for unsafe in ("GOAD-WS01","10.4.10.31","New-LocalUser",
                       "Set-MpPreference","SeDebugPrivilege"):
            self.assertNotIn(unsafe,text)
        self.assertIn("VULNERABLE_CONFIGURATION",text)
        self.assertNotIn("LEARNER_EXPLOITED=PASS",text)

if __name__=="__main__":
    unittest.main()
