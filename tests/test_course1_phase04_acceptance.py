"""NORTH LPE acceptance contract: plan is inert, live requires explicit consent."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/course1-phase04-acceptance.sh"
FOOTHOLD = ROOT / "ansible/course1-phase04-foothold.yml"


class Course1Phase04AcceptanceTests(unittest.TestCase):
    def test_shell_parses(self):
        result = subprocess.run(["bash", "-n", str(RUNNER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_does_not_require_runtime_and_cannot_change_lab(self):
        result = subprocess.run(
            ["bash", str(RUNNER), "ac9fda-north-vmware", "--plan"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLAN_ONLY=True", result.stdout)
        self.assertIn("PHASE04_LPE_ACTIVE_ACCEPTANCE=NOT_TESTED", result.stdout)
        self.assertNotIn("PHASE04_LPE_ACTIVE_ACCEPTANCE=PASS", result.stdout)

    def test_live_mode_requires_explicit_transient_right_consent(self):
        for args in (
            [], ["ac9fda-north-vmware", "--validate"],
            ["ac9fda-north-vmware", "--validate", "--confirm"],
            ["ac9fda-north-vmware", "--reset", "--confirm-transient-right"],
        ):
            with self.subTest(args=args):
                result = subprocess.run(["bash", str(RUNNER), *args],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)

    def test_north_inventory_and_shared_phase03_lock_are_explicit(self):
        s = RUNNER.read_text()
        for part in (
            'ad/NORTH/data/inventory',
            'workspace/$INSTANCE/inventory',
            'globalsettings.ini',
            '.course1-phase03-acceptance.lock',
            'flock -n 9',
            'scripts/course1-rollout.sh --installed',
            'ansible/course1-phase04-foothold.yml',
            'ansible/windows-lpe.yml',
            'windows_lpe_action=validate',
            'windows_lpe_profile=full-lpe',
            'windows_lpe_validate_state=vulnerable',
            '--confirm-transient-right',
            'PHASE04_LPE_SCENARIOS_VERIFIED=',
            'PHASE04_LPE_ESCALATION_PROOF=NOT_TESTED',
        ):
            with self.subTest(part=part):
                self.assertIn(part, s)
        for forbidden in (
            'ad/GOAD/data/inventory', 'reset all', 'windows_lpe_action=reset',
            'windows_lpe_action=apply', '-t reset', 'snapshot pop',
        ):
            self.assertNotIn(forbidden, s)

    def test_foothold_is_pure_inspection_and_enforces_low_privilege(self):
        src = FOOTHOLD.read_text()
        for marker in (
            'hosts: ws01', '$Ansible.Changed = $false',
            'north.sevenkingdoms.local', 'Test-ComputerSecureChannel',
            'Remote Desktop Users', 'Administrators',
            'north\\rickon.stark', 'EnableLUA',
            'Get-NetFirewallProfile', 'Get-MpComputerStatus',
            'PHASE04_WS01_NORTH_DOMAIN=PASS',
            'PHASE04_WS01_RICKON_NONADMIN_RDP=PASS',
            'PHASE04_WS01_SECURITY_CONTROLS=PASS',
        ):
            self.assertIn(marker, src)
        for mutation in (
            'New-LocalUser', 'Set-LocalUser', 'Set-ItemProperty',
            'New-ADComputer', 'Set-ADComputer', 'Remove-ADComputer',
            'Register-ScheduledTask', 'Set-NetFirewallProfile',
        ):
            self.assertNotIn(mutation, src)


if __name__ == "__main__":
    unittest.main()
