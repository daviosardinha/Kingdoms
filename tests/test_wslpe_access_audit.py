"""Static WSLPE-only access-audit safety/contract checks.

No VM, Ansible, PowerShell, HTTPS, RDP or network operation runs here.
"""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "ansible/wslpe-access-audit.yml"
RUNNER = ROOT / "scripts/wslpe-access-audit.sh"


class WslpeAccessAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PLAYBOOK.read_text(encoding="utf-8")
        cls.runner = RUNNER.read_text(encoding="utf-8")
        cls.document = yaml.safe_load(cls.source)

    def test_only_standalone_wslpe_targeted(self):
        self.assertEqual(len(self.document), 1)
        play = self.document[0]
        self.assertEqual(play["hosts"], "wslpe")
        self.assertIs(play["gather_facts"], False)
        self.assertIn("WSLPE-WS01", self.source)
        self.assertIn("PartOfDomain", self.source)
        for foreign in ("NORTH\\rickon", "GOAD-WS01", "hosts: dc", "hosts: ws01"):
            self.assertNotIn(foreign, self.source)

    def test_reuses_north_supported_native_windows_checks(self):
        for required in (
            r"WSMan:\localhost\Listener",
            "Get-WSManInstance",
            "Get-Service TermService",
            "Get-Service WinRM",
            "fDenyTSConnections",
            "UserAuthentication",
            "SecurityLayer",
            "CertificateThumbprint",
            "Cert:",
            "Get-NetTCPConnection",
        ):
            self.assertIn(required, self.source)
        self.assertNotIn("winrm.exe", self.source.split("script: |", 1)[1].split("$Ansible.Result", 1)[0].replace(
            "# WSMan provider; never assume winrm.exe is a valid executable.", ""))

    def test_source_is_read_only_and_never_promotes_course(self):
        script = self.document[0]["tasks"][0]["ansible.windows.win_powershell"]["script"]
        self.assertIn("$Ansible.Changed = $false", script)
        for action in (
            "New-WSManInstance", "Remove-WSManInstance", "Set-ItemProperty",
            "Set-NetFirewallRule", "New-NetFirewallRule", "Set-NetFirewallProfile",
            "Set-LocalUser", "New-LocalUser", "Restart-Service",
            "Restart-Computer", "Enable-PSRemoting", "Set-WSManInstance",
            "win_reboot", "vagrant up", "lab-mode.sh",
        ):
            self.assertNotIn(action, script)
        self.assertIn("NOT VERIFIED", self.source)
        self.assertIn("HTTPSCertificateTimeValid", self.source)
        self.assertIn("RDPNLARequired", self.source)

    def test_runner_uses_native_instance_and_existing_operator_venv(self):
        self.assertIn("find_instance(", self.runner)
        self.assertIn("instance / 'inventory'", self.runner)
        self.assertIn("ad/WSLPE/data/inventory_disable_vagrant", self.runner)
        self.assertIn("test_wslpe_access_audit.py", self.runner)
        self.assertIn("--limit ws01", self.runner)
        self.assertNotIn("sudo", self.runner)
        for forbidden in ("vagrant up", "vagrant destroy", "vmrun start", "lab-mode.sh"):
            self.assertNotIn(forbidden, self.runner)


if __name__ == "__main__":
    unittest.main()
