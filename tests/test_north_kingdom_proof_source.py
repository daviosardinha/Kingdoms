"""Source-only contract for the NORTH WS01 harmless execution proof.

The real executable must still be compiled and verified in a Windows guest.
These tests prevent regressions that could accidentally change other labs,
weaken the security baseline, or execute the helper as provisioning admin.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "ansible" / "build.yml"
ROLE = ROOT / "ansible" / "roles" / "settings" / "north_kingdom_proof"
TASKS = ROLE / "tasks" / "main.yml"
SOURCE = ROLE / "files" / "KingdomProof.cs"


class NorthKingdomProofSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = BUILD.read_text(encoding="utf-8")
        cls.tasks = TASKS.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_only_north_ws01_imports_helper(self):
        self.assertIn("name: NORTH WS01 | install harmless execution proof prerequisite", self.build)
        self.assertIn("hosts: workstation", self.build)
        self.assertIn("role: settings/north_kingdom_proof", self.build)
        self.assertIn("domain_name == 'NORTH'", self.build)
        self.assertIn("inventory_hostname == 'ws01'", self.build)
        self.assertIn("north_kingdom_proof", self.build)

    def test_proof_only_records_identity_and_utc_time(self):
        self.assertIn("WindowsIdentity.GetCurrent().Name", self.source)
        self.assertIn('DateTime.UtcNow.ToString("o")', self.source)
        self.assertIn("Directory.CreateDirectory(Path.GetDirectoryName(output))", self.source)
        self.assertIn(r"C:\Users\Public\Documents\KingdomProofs\execution-proof.txt", self.source)
        for forbidden in ("Process.Start", "System.Net", "CreateProcess", "OpenProcess",
                          "TcpClient", "Socket", "cmd.exe", "powershell.exe"):
            self.assertNotIn(forbidden, self.source)

    def test_idempotent_reapply_and_readiness(self):
        self.assertIn("ansible.windows.win_copy:", self.tasks)
        self.assertIn("ansible.windows.win_stat:", self.tasks)
        self.assertIn("north_kingdom_proof_source.changed or not north_kingdom_proof_existing.stat.exists", self.tasks)
        self.assertIn("Add-Type -TypeDefinition", self.tasks)
        self.assertIn("-OutputType ConsoleApplication", self.tasks)
        self.assertIn("NORTH_KINGDOM_PROOF_READY", self.tasks)
        self.assertIn("Get-FileHash", self.tasks)

    def test_no_provisioning_admin_execution_or_security_downgrade(self):
        self.assertNotIn("& $destination", self.tasks)
        self.assertNotIn("Start-Process $destination", self.tasks)
        self.assertNotIn("execution-proof.txt", self.tasks)
        for forbidden in ("Set-MpPreference", "DisableRealtimeMonitoring",
                          "EnableLUA", "ConsentPromptBehaviorAdmin",
                          "net user", "net localgroup", "New-NetFirewallRule"):
            self.assertNotIn(forbidden, self.tasks)


if __name__ == "__main__":
    unittest.main()
