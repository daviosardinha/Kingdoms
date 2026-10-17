"""Standalone source contracts for WSLPE IFEO and App Paths registry hijack.

These tests do not qualify guest exploitation. They verify ownership,
the protected proof sink, exact workgroup inventory, and distinct registries.
"""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "ansible/files/wslpe45/WslpeRegistryTrust.psm1"
IDENTITIES = (
    (26, "ifeo_debugger_acl_hijack",
     "Image File Execution Options", "Kingdom45IfeoConsumer"),
    (28, "app_paths_registry_hijack",
     "App Paths", "Kingdom45AppPathsConsumer"),
)


class RegistryTrustCandidates(unittest.TestCase):
    def test_registry_attack_surfaces_are_distinct_and_exclusive(self):
        source = MODULE.read_text(encoding="utf-8")
        for needle in ("ifeo_debugger_acl_hijack", "app_paths_registry_hijack",
                       "Image File Execution Options", "App Paths",
                       "Kingdom45IfeoProbe.exe", "Kingdom45AppPathsProbe.exe",
                       "Kingdom45AppPathsLauncher.exe", "UseShellExecute = true",
                       "RegistryRights]::SetValue", "New-ScheduledTaskTrigger",
                       "Register-ScheduledTask", "Unregister-ScheduledTask",
                       "New-Wslpe45OwnedFixture", "Assert-Wslpe45OwnedFixture",
                       "Remove-Wslpe45OwnedFixture",
                       "SetAccessRuleProtection($true, $false)",
                       "WSLPE45_BATCH_STAGE="):
            self.assertIn(needle, source)
        for forbidden in ("10.4.10.31", "GOAD-WS01",
                          "Set-MpPreference", "Stop-Process -Name lsass",
                          "sc.exe sdset scmanager", "Register-ScheduledTask -TaskName 'Windows"):
            self.assertNotIn(forbidden, source)

    def test_both_playbooks_have_exact_target_and_lifecycle_proof(self):
        for number, identifier, registry, task in IDENTITIES:
            with self.subTest(number=number):
                path = ROOT / f"ansible/wslpe45/{identifier}.yml"
                plays = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertEqual(len(plays), 2)
                self.assertEqual(plays[0]["hosts"], "localhost")
                self.assertEqual(plays[1]["hosts"], "wslpe")
                checks = " ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
                for expected in ("windows_lpe_standalone", "domain", "dc",
                                 "wslpe_expected_address", "wslpe_45_stage_label", identifier):
                    self.assertIn(expected, checks)
                preflight = plays[1]["pre_tasks"][0]["ansible.windows.win_powershell"]["script"]
                for expected in ("WSLPE-WS01", "PartOfDomain", "Get-LocalUser",
                                 "Get-LocalGroupMember", "Windows 10"):
                    self.assertIn(expected, preflight)
                op = plays[1]["tasks"][-1]["ansible.windows.win_powershell"]["script"]
                self.assertIn("Invoke-Wslpe45RegistryTrust", op)
                self.assertIn(f"WSLPE45_BATCH_STAGE={identifier}:", op)
                self.assertIn("Where-Object { $_ -ceq $marker }", op)
                self.assertIn("changed_when", plays[1]["tasks"][-1])
                self.assertNotIn("roles:", path.read_text())
                self.assertNotIn("10.4.10.31", path.read_text())

    def test_proof_executable_is_not_used_as_benign_consumer(self):
        text = MODULE.read_text()
        self.assertIn("string path = @\"$proof\"", text)
        self.assertIn("WindowsIdentity.GetCurrent().Name", text)
        self.assertIn("Process.Start(start)", text)
        self.assertIn("start.UseShellExecute = true", text)
        self.assertIn("SetAccessRuleProtection($true, $false)", text)
        self.assertIn("throw 'Learner can write protected evidence without escalation'", text)


if __name__ == "__main__":
    unittest.main()
