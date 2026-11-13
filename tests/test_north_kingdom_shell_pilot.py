"""Source-only pilot regressions. Real SYSTEM/RDP verification requires WS01."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ansible/roles/settings/north_kingdom_shell/files/KingdomShell.cs"
PLAY = ROOT / "ansible/north-kingdom-shell-pilot.yml"

class ShellPilotTests(unittest.TestCase):
    def test_scope(self):
        s = SRC.read_text(encoding="utf-8")
        for marker in ["WS01", "rickon.stark", "NORTH", "KingdomBinarySvc",
                       "KingdomUpdaterSvc", "KingdomProgramSvc",
                       "CreateProcessAsUser", "OnSessionChange", "ExistingShell"]:
            self.assertIn(marker, s)
        for forbidden in ["System.Net", "TcpClient", "HttpClient", "schtasks",
                          "execution-proof.txt", "Register-ScheduledTask"]:
            self.assertNotIn(forbidden, s)
    def test_pilot_is_opt_in(self):
        s = PLAY.read_text(encoding="utf-8")
        self.assertIn("north_kingdom_shell_pilot", s)
        self.assertIn("domain_name == 'NORTH'", s)
        self.assertIn("inventory_hostname == 'ws01'", s)
        self.assertIn("NORTH_SHELL_PILOT_READY", s)
        self.assertNotIn("sc.exe start", s)
        self.assertNotIn("Start-Process", s)

if __name__ == "__main__":
    unittest.main()
