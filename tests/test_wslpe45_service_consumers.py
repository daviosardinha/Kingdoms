"""Three separate standalone privileged service-consumer LPE mechanisms."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
NAMES=("privileged_service_config_injection","privileged_updater_hijack",
       "privileged_argument_injection")

class ServiceConsumerCandidates(unittest.TestCase):
    def test_real_distinct_unsafe_data_boundaries(self):
        cs=(ROOT/"ansible/files/wslpe45/KingdomServiceConsumer.cs").read_text()
        self.assertIn('Mode == "privileged_service_config_injection"',cs)
        self.assertIn('Mode == "privileged_updater_hijack"',cs)
        self.assertIn('Mode == "privileged_argument_injection"',cs)
        self.assertIn("ProcessStartInfo(\"cmd.exe\", \"/d /c echo BASELINE \" + supplied)",cs)
        self.assertIn("path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)",cs)
        self.assertIn("ProcessStartInfo(path)",cs)
        self.assertIn("whoami.exe",cs)
        self.assertIn("child.UseShellExecute = false",cs)
        self.assertIn("child.WorkingDirectory = inbox",cs)
        for forbidden in ("GOAD-WS01","10.4.10.31","LSASS","Set-MpPreference"):
            self.assertNotIn(forbidden,cs)

    def test_each_exact_guest_has_unique_source_and_constrained_service(self):
        module=(ROOT/"ansible/files/wslpe45/WslpeServiceConsumer.psm1").read_text()
        for number,id,service in (
            (23,"privileged_service_config_injection","Kingdom45ConfigSvc"),
            (24,"privileged_updater_hijack","Kingdom45UpdateSvc"),
            (41,"privileged_argument_injection","Kingdom45ArgsSvc")
        ):
            with self.subTest(name=id):
                path=ROOT/f"ansible/wslpe45/{id}.yml"
                source=path.read_text()
                plays=yaml.safe_load(source)
                self.assertEqual([p["hosts"] for p in plays],["localhost","wslpe"])
                conditions=" ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
                for token in (id,"wslpe_45_stage_label","wslpe_expected_address",
                              "groups.get('dc'","groups.get('domain'"):
                    self.assertIn(token,conditions)
                body=plays[1]["tasks"][-1]["ansible.windows.win_powershell"]["script"]
                self.assertIn(f"WSLPE45_BATCH_STAGE={id}",body)
                self.assertIn("Invoke-Wslpe45ServiceConsumer",body)
                self.assertIn("KingdomServiceConsumer.cs",source)
                self.assertIn(service,module)
                self.assertNotIn("hosts: dc",source)
                self.assertNotIn("roles:",source)
        for contract in ("New-Wslpe45OwnedFixture", "Assert-Wslpe45OwnedFixture",
                         "Remove-Wslpe45OwnedFixture","RegistryRights",):
            if contract=="RegistryRights": continue
            self.assertIn(contract,module)
        self.assertIn("Get-CimInstance Win32_Service",module)
        self.assertIn("LocalSystem",module)
        self.assertIn("WSLPE45_BATCH_STAGE=",module)
        self.assertNotIn("sc.exe sdset scmanager",module)

if __name__=="__main__":
    unittest.main()
