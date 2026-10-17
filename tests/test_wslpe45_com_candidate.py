"""Source-only managed COM CLSID registration hijack candidate."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
PLAY=ROOT/"ansible/wslpe45/com_clsid_registration_hijack.yml"
SERVER=ROOT/"ansible/files/wslpe45/Kingdom45ComServer.cs"
MODULE=ROOT/"ansible/files/wslpe45/WslpeComRegistration.psm1"

class ComRegistrationCandidate(unittest.TestCase):
    def test_exact_guest_guard_and_winrm_isolation(self):
        plays=yaml.safe_load(PLAY.read_text(encoding="utf-8"))
        self.assertEqual([p["hosts"] for p in plays],["localhost","wslpe"])
        scope=" ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
        for token in ("com_clsid_registration_hijack","windows_lpe_standalone",
                      "wslpe_expected_address","groups.get('dc'","groups.get('domain'"):
            self.assertIn(token,scope)
        self.assertEqual(sum(t.get("ansible.builtin.import_tasks")=="lockdown-library.yml"
                            for t in plays[1]["tasks"]),1)
        script=plays[1]["tasks"][-1]["ansible.windows.win_powershell"]["script"]
        self.assertIn("Invoke-Wslpe45ComRegistration",script)
        self.assertIn("WSLPE45_BATCH_STAGE=com_clsid_registration_hijack",script)

    def test_managed_com_native_registration_and_scoped_rollback(self):
        code=SERVER.read_text()
        src=MODULE.read_text()
        for token in ("[Guid(", "[ProgId(", "[ComVisible(true)]",
                      "ClassInterfaceType.AutoDual","WindowsIdentity.GetCurrent().Name",
                      "Kingdoms45.ComServer"):
            self.assertIn(token,code)
        for token in ("RegAsm.exe", "'/codebase'", "'/unregister'",
                      "Microsoft.Win32.RegistryView]::Registry64",
                      "SOFTWARE\\Classes\\CLSID",
                      "RegistryRights]::SetValue","New-ScheduledTaskAction",
                      "Register-ScheduledTask","Unregister-ScheduledTask",
                      "New-Wslpe45OwnedFixture -Number 27",
                      "Assert-Wslpe45OwnedFixture -Number 27",
                      "Remove-Wslpe45OwnedFixture -Number 27",
                      "WSLPE45_BATCH_STAGE="):
            self.assertIn(token,src)
        for forbidden in ("10.4.10.31","GOAD-WS01","Stop-Service WinRM",
                          "sc.exe sdset scmanager","lsass.exe"):
            self.assertNotIn(forbidden,src+code)
        self.assertIn("NOT_EXPLOIT_PROVEN",src)

if __name__=="__main__":
    unittest.main()
