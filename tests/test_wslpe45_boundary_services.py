"""Distinct #29/#34/#39/#43/#44/#45 standalone Windows native consumer contracts."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
MOD=ROOT/"ansible/files/wslpe45/WslpeBoundary.psm1"
SERVICE=ROOT/"ansible/files/wslpe45/KingdomBoundaryService.cs"
IDS=(
    (29,"named_pipe_authorization","PipeLoop"),
    (34,"ntfs_link_redirection","LinkProof"),
    (43,"elevated_plugin_signature_bypass","PluginProof"),
    (39,"privileged_loopback_http_authz","HttpLoop"),
    (44,"privileged_file_toctou","RaceLoop"),
    (45,"privileged_backup_restore_api","RestoreLoop"),
)

class BoundaryFixtureTests(unittest.TestCase):
    def test_four_real_independent_windows_mechanisms(self):
        c=SERVICE.read_text(encoding="utf-8")
        for _,id,method in IDS:
            self.assertIn(id,c)
            self.assertIn("private void "+method+"()",c)
        for fragment in (
            "NamedPipeServerStream", "PipeSecurity", "BuiltinUsersSid",
            "GetFinalPathNameByHandle", "FileMode.Open", "SafeFileHandle",
            "Assembly.LoadFrom", "manifest.txt", "trusted=true",
            "HttpListener", "127.0.0.1:45939", "AuthenticationSchemes.Anonymous",
            "Thread.Sleep(1600)", "VALIDATED", "File.ReadAllText(input).Trim()",
            '"RESTORE"', '"backup.txt"', "Protected(", "WindowsIdentity.GetCurrent().Name",
            "ServiceBase.Run"):
            self.assertIn(fragment,c)
        for forbidden in ("Process.Start", "cmd.exe", "powershell.exe",
                          "GOAD-WS01", "10.4.10.31","Set-MpPreference"):
            self.assertNotIn(forbidden,c)

    def test_exact_vm_guards_and_scoped_six_stage_evidence(self):
        m=MOD.read_text()
        for required in ("Assert-Wslpe45Identity", "New-Wslpe45OwnedFixture",
                         "Assert-Wslpe45OwnedFixture", "Remove-Wslpe45OwnedFixture",
                         "LocalSystem", "WSLPE45_BATCH_STAGE=",
                         "Kingdom45PipeSvc", "Kingdom45LinkSvc", "Kingdom45HttpSvc",
                         "Kingdom45PluginSvc",
                         "Kingdom45RaceSvc", "Kingdom45RestoreSvc",
                         "Protected", "KingdomBoundaryService.cs"):
            if required=="Protected":
                self.assertIn("Join-Path $root 'protected'",m)
            else:
                self.assertIn(required,m)
        for number,id,method in IDS:
            with self.subTest(number=number):
                p=ROOT/f"ansible/wslpe45/{id}.yml"
                content=p.read_text()
                plays=yaml.safe_load(content)
                self.assertEqual([x["hosts"] for x in plays],["localhost","wslpe"])
                checks=" ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
                for term in (id,"wslpe_expected_address","windows_lpe_standalone",
                             "groups.get('dc'","groups.get('domain'",
                             "wslpe_45_stage_label"):
                    self.assertIn(term,checks)
                pre=plays[1]["pre_tasks"][0]["ansible.windows.win_powershell"]["script"]
                for term in ("WSLPE-WS01","PartOfDomain","Windows 10",
                             "Get-LocalUser","Get-LocalGroupMember"):
                    self.assertIn(term,pre)
                script=plays[1]["tasks"][-1]["ansible.windows.win_powershell"]["script"]
                self.assertIn("Invoke-Wslpe45Boundary",script)
                self.assertIn("WSLPE45_BATCH_STAGE="+id,script)
                self.assertEqual(sum(task.get("ansible.builtin.import_tasks")=="lockdown-library.yml"
                        for task in plays[1]["tasks"]),1)
                self.assertNotIn("roles:",content)
                self.assertNotIn("hosts: dc",content)
                self.assertNotIn("10.4.10.31",content)
        self.assertNotIn("sc.exe sdset scmanager",m)

    def test_junction_cleanup_is_exact_34_only_and_never_recursive(self):
        module=MOD.read_text()
        owned=(ROOT/"ansible/files/wslpe45/WslpeFixture.psm1").read_text()
        start=module.index("function Remove-Wslpe45OwnedLinkJunction")
        end=module.index("function Invoke-Wslpe45Boundary")
        recovery=module[start:end]
        for item in ("kingdoms.wslpe.fixture-owner.v1",
                     "ntfs_link_redirection", "owner.learner_sid",
                     "owner.number -ne 34", "LinkType -cne 'Junction'",
                     "owned protected directory", "GetFullPath",
                     "TrimEnd([char]92)", "System32\\cmd.exe",
                     "rmdir"):
            self.assertIn(item,recovery)
        self.assertIn("if($Id -eq 'ntfs_link_redirection')",module)
        self.assertLess(
            module.index("Remove-Wslpe45OwnedLinkJunction -FixtureRoot"),
            module.index("Assert-Wslpe45OwnedFixture -Number $number -Id $Id")
        )
        self.assertNotIn("rmdir /s",recovery.lower())
        self.assertNotIn("Remove-Item -LiteralPath $link -Recurse",recovery)
        self.assertIn("Assert-Wslpe45NoReparsePoints",owned)
        self.assertIn("refusing recursive cleanup",owned.lower())

    def test_plugin_source_is_scoped_to_owned_proof(self):
        sample=(ROOT/"ansible/files/wslpe45/Kingdom45Plugin.cs").read_text()
        self.assertIn("namespace Kingdom45Plugin",sample)
        self.assertIn("class Entry",sample)
        self.assertIn("protected",sample)
        self.assertIn("WindowsIdentity.GetCurrent().Name",sample)
        self.assertIn("Kingdom45Plugin.cs",(ROOT/"ansible/wslpe45/elevated_plugin_signature_bypass.yml").read_text())

if __name__=="__main__":
    unittest.main()
