"""Windows-native JEA fixture source contract; NOT learner runtime proof."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
PLAY=ROOT/"ansible/wslpe45/jea_role_capability_misconfig.yml"
MODULE=ROOT/"ansible/files/wslpe45/WslpeJea.psm1"

class JeaContract(unittest.TestCase):
    def test_exact_workgroup_target_and_source_isolation(self):
        src=PLAY.read_text(encoding="utf-8")
        plays=yaml.safe_load(src)
        self.assertEqual([p["hosts"] for p in plays],["localhost","wslpe"])
        assertions=" ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
        for expected in ("jea_role_capability_misconfig","windows_lpe_standalone",
                         "wslpe_expected_address","groups.get('dc'","groups.get('domain'"):
            self.assertIn(expected,assertions)
        check=plays[1]["pre_tasks"][1]["ansible.windows.win_powershell"]["script"]
        for expected in ("WSLPE-WS01","Get-LocalUser","PartOfDomain","Windows 10"):
            self.assertIn(expected,check)
        self.assertEqual(sum(x.get("ansible.builtin.import_tasks")=="lockdown-library.yml" for x in plays[1]["tasks"]),1)
        for token in ("WslpeJea.psm1","Invoke-Wslpe45Jea","WSLPE45_BATCH_STAGE=jea_role_capability_misconfig"):
            self.assertIn(token,src)
        self.assertNotIn("10.4.10.31",src)
        self.assertNotIn("GOAD-WS01",src)

    def test_authentic_jea_api_and_restriction_on_winrm_mutation(self):
        src=MODULE.read_text(encoding="utf-8")
        for expected in ("New-PSRoleCapabilityFile","New-PSSessionConfigurationFile",
                         "Test-PSSessionConfigurationFile","Register-PSSessionConfiguration",
                         "Unregister-PSSessionConfiguration","-NoServiceRestart",
                         "-RunAsVirtualAccount","Invoke-Kingdoms45Maintenance",
                         "New-Wslpe45OwnedFixture -Number 30",
                         "Assert-Wslpe45OwnedFixture -Number 30",
                         "Remove-Wslpe45OwnedFixture -Number 30",
                         "WSLPE45_BATCH_STAGE=","Kingdoms45Role",
                         "WSLPE-WS01\\lpe.trainee","-SessionType RestrictedRemoteServer"):
            self.assertIn(expected,src)
        for forbidden in ("Restart-Service","Restart-Computer","Stop-Service WinRM",
                          "Set-Service WinRM","Set-Item WSMan:\\localhost\\Service",
                          "10.4.10.31","GOAD-WS01"):
            self.assertNotIn(forbidden,src)
        self.assertIn("CONFIGURATION_PRESENT_NOT_EXECUTION_PROOF",src)

if __name__=="__main__":
    unittest.main()
