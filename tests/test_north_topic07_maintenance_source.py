"""Static source contract for NORTH's scheduled maintenance trigger in Topic 07.

Runtime acceptance still needs a real WS01 and standard-user session.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "ansible" / "build.yml"
ROLE = ROOT / "ansible" / "roles" / "settings" / "north_binary_maintenance" / "tasks" / "main.yml"


class NorthTopic07MaintenanceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = BUILD.read_text(encoding="utf-8")
        cls.role = ROLE.read_text(encoding="utf-8")

    def test_north_ws01_only_in_installation(self):
        self.assertIn("name: NORTH WS01 | register periodic service maintenance for Topic 07", self.build)
        self.assertIn("hosts: workstation", self.build)
        self.assertIn("role: settings/north_binary_maintenance", self.build)
        self.assertIn("north_binary_maintenance", self.build)
        self.assertIn("domain_name == 'NORTH'", self.build)
        self.assertIn("inventory_hostname == 'ws01'", self.build)

    def test_system_maintenance_is_discoverable_but_not_manually_runnable(self):
        for needle in (
            "ansible.windows.win_scheduled_task:",
            "name: Workstation Service Health",
            "description: Check locally installed workstation services",
            r"path: 'C:\Windows\System32\sc.exe'",
            "arguments: start KingdomBinarySvc",
            "username: SYSTEM",
            "logon_type: service_account",
            "allow_demand_start: false",
            "hidden: false",
            "enabled: true",
            "multiple_instances: 2",
            "state: present",
            "interval: PT1M",
            "duration: P1D",
        ):
            self.assertIn(needle, self.role)

    def test_readonly_standard_user_discovery_is_preserved(self):
        self.assertIn("SetSecurityDescriptor($desired, 0)", self.role)
        self.assertIn("D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GR;;;BU)", self.role)
        self.assertIn("NORTH_TOPIC07_MAINTENANCE_ACL_READY", self.role)
        self.assertIn("NORTH_TOPIC07_MAINTENANCE_READY", self.role)
        self.assertIn("Export-ScheduledTask", self.role)
        self.assertIn("$Ansible.Changed = $false", self.role)

    def test_does_not_downgrade_windows_or_start_as_provisioner(self):
        for forbidden in (
            "sc.exe start KingdomBinarySvc\n",
            "Start-Service -Name KingdomBinarySvc",
            "Start-ScheduledTask",
            "Set-MpPreference",
            "DisableRealtimeMonitoring",
            "EnableLUA",
            "ConsentPromptBehaviorAdmin",
            "sc.exe sdset",
            "sc.exe config",
            "New-NetFirewallRule",
            "net localgroup",
            "NT AUTHORITY\\SYSTEM:(F)",
        ):
            self.assertNotIn(forbidden, self.role)


if __name__ == "__main__":
    unittest.main()
