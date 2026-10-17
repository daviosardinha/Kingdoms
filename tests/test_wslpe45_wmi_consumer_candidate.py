"""Native WMI permanent consumer script-trust exercise source checks."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/"ansible/files/wslpe45/WslpeWmiConsumer.psm1"
PLAY=ROOT/"ansible/wslpe45/wmi_permanent_consumer_hijack.yml"
TRIGGER=ROOT/"ansible/files/wslpe45/Kingdom45WmiWake.cs"

class WmiConsumerFixture(unittest.TestCase):
    def test_only_unique_wmi_subscription_objects_are_mutated(self):
        src=MODULE.read_text()
        for token in ("root\\subscription","__EventFilter","__FilterToConsumerBinding",
                      "CommandLineEventConsumer","Win32_ProcessStartTrace",
                      "Kingdom45WmiWake.exe","CreatorSID",
                      "Get-WmiObject","Set-WmiInstance","CommandLineTemplate",
                      "WSLPE45_BATCH_STAGE=",
                      "New-Wslpe45OwnedFixture -Number 37",
                      "Assert-Wslpe45OwnedFixture -Number 37",
                      "Remove-Wslpe45OwnedFixture -Number 37"):
            self.assertIn(token,src)
        for prohibited in ("SetSecurityDescriptor","Set-WmiNamespaceSecurity",
                           "GOAD-WS01","10.4.10.31","Set-MpPreference",
                           "sc.exe sdset scmanager"):
            self.assertNotIn(prohibited,src)
        self.assertIn("NOT_EXPLOIT_PROVEN",src)
        self.assertIn("Thread.Sleep(2000)",TRIGGER.read_text())

    def test_exact_guest_preflight_protects_north(self):
        play=yaml.safe_load(PLAY.read_text())
        self.assertEqual([p["hosts"] for p in play],["localhost","wslpe"])
        conditions=" ".join(play[0]["tasks"][0]["ansible.builtin.assert"]["that"])
        for part in ("wmi_permanent_consumer_hijack","windows_lpe_standalone",
                     "groups.get('dc'","groups.get('domain'",
                     "wslpe_expected_address"):
            self.assertIn(part,conditions)
        script=play[1]["pre_tasks"][0]["ansible.windows.win_powershell"]["script"]
        for part in ("WSLPE-WS01","PartOfDomain","Get-LocalUser","Windows 10"):
            self.assertIn(part,script)
        self.assertIn("WslpeWmiConsumer.psm1",PLAY.read_text())
        self.assertIn("Kingdom45WmiWake.cs",PLAY.read_text())
        self.assertIn("WSLPE45_BATCH_STAGE=wmi_permanent_consumer_hijack",PLAY.read_text())
        self.assertEqual(sum(x.get("ansible.builtin.import_tasks")=="lockdown-library.yml"
                             for x in play[1]["tasks"]),1)

if __name__=="__main__":
    unittest.main()
