"""Three LSA privilege scenarios are distinct and stay on standalone WSLPE."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/"ansible/files/wslpe45/WslpeLsaRights.psm1"
CONTRACT=(
    (31,"setakeownership_privilege","SeTakeOwnershipPrivilege"),
    (32,"serestore_privilege","SeRestorePrivilege"),
    (33,"sedebug_privilege","SeDebugPrivilege"),
)

class LsaRightCandidates(unittest.TestCase):
    def test_direct_local_account_only_and_exact_snapshots(self):
        source=MODULE.read_text(encoding="utf-8")
        for _,name,right in CONTRACT:
            self.assertIn(name,source)
            self.assertIn(right,source)
        for required in (
            "WslpeDirectAccountRights", "HasRight", "Change($sid,$right,$false)",
            "Change($sid,$right,$true)", "New-Wslpe45OwnedFixture",
            "Assert-Wslpe45OwnedFixture", "Remove-Wslpe45OwnedFixture",
            "Assert-Wslpe45Identity", "WSLPE45_BATCH_STAGE=",
            "existing token", "KINGDOMS_WSLPE45_PROTECTED",
            "Kingdom45DebugTarget", "System.ServiceProcess"):
            if required == "existing token":
                self.assertIn("new learner logon",source)
            else:
                self.assertIn(required,source)
        for unsafe in ("GOAD-WS01","10.4.10.31","Set-MpPreference",
                       "lsass.exe","\\Windows\\System32\\config","secedit /configure"):
            self.assertNotIn(unsafe,source)

    def test_every_lsa_playbook_scopes_exact_inventory_and_identity(self):
        for _,name,right in CONTRACT:
            with self.subTest(name=name):
                path=ROOT/f"ansible/wslpe45/{name}.yml"
                text=path.read_text(encoding="utf-8")
                plays=yaml.safe_load(text)
                self.assertEqual([p["hosts"] for p in plays],["localhost","wslpe"])
                checks=" ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
                for required in (name,"wslpe_expected_address","wslpe_45_stage_label",
                                 "windows_lpe_standalone","groups.get('dc'",
                                 "groups.get('domain'"):
                    self.assertIn(required,checks)
                guest=plays[1]["pre_tasks"][0]["ansible.windows.win_powershell"]["script"]
                for required in ("WSLPE-WS01","PartOfDomain","Windows 10",
                                 "Get-LocalUser","Get-LocalGroupMember"):
                    self.assertIn(required,guest)
                execution=plays[1]["tasks"][-1]["ansible.windows.win_powershell"]["script"]
                self.assertIn(f"-Id '{name}'",execution)
                self.assertIn(f"WSLPE45_BATCH_STAGE={name}",execution)
                self.assertNotIn("hosts: dc",text)
                self.assertNotIn("hosts: domain",text)
                self.assertNotIn("roles:",text)

    def test_debug_target_is_not_lsass_or_system_owned_host_executable(self):
        text=MODULE.read_text()
        self.assertIn("Kingdom45DebugTarget.exe",text)
        self.assertIn("StartName -ne 'LocalSystem'",text)
        self.assertNotIn("Get-Process -Name lsass",text)


if __name__=="__main__":
    unittest.main()
