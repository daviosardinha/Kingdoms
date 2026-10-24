"""Source contract for independent read-only NORTH RBCD neutral-state checking."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/course1-phase03-rbcd-neutral.sh"
ENTRY = ROOT / "scripts/course1-phase03-acceptance.sh"
PLAYBOOK = ROOT / "ansible/phase03-rbcd-verify-neutral.yml"


class Course1RBCDNeutralTests(unittest.TestCase):
    def test_shell_source_parses(self):
        for script in (RUNNER, ENTRY):
            with self.subTest(script=script):
                result = subprocess.run(
                    ["bash", "-n", str(script)], capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_verify_action_requires_explicit_baseline(self):
        call = subprocess.run(
            ["bash", str(ENTRY), "ac9fda-north-vmware", "--verify-rbcd"],
            capture_output=True, text=True
        )
        self.assertEqual(call.returncode, 2)
        source = ENTRY.read_text()
        self.assertIn("--verify-rbcd <captured-baseline.json>", source)
        self.assertIn(
            'exec bash scripts/course1-phase03-rbcd-neutral.sh "$INSTANCE" "$3"',
            source
        )

    def test_no_implicit_latest_or_legacy_baseline(self):
        runner = RUNNER.read_text()
        for required in (
            'INSTANCE="$1"', 'BASELINE="$2"',
            'phase03-rbcd-baseline-*/rbcd-baseline.json',
            '[[ -f "$BASELINE" && ! -L "$BASELINE"',
            'sha256sum --check --status',
            'os.getuid()', 'stat.S_IMODE(metadata.st_mode) != mode',
            'flock -n 9', '.course1-phase03-acceptance.lock',
            'scripts/course1-rollout.sh --installed',
            'KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"',
            'ansible/phase03-rbcd-verify-neutral.yml',
            'PHASE03_RBCD_NEUTRAL_VERIFIED=True',
            'PHASE03_RBCD_NEUTRAL_ACCEPTANCE=PASS',
            'PHASE03_RBCD_ACTIVE_ACCEPTANCE=NOT_TESTED',
        ):
            with self.subTest(required=required):
                self.assertIn(required, runner)
        for forbidden in (
            'rollback-rbcd.sh', 'start-rbcd-stage1-add-computer.sh',
            'prove-rbcd-s4u.sh', 'rm -rf', 'New-ADComputer',
        ):
            self.assertNotIn(forbidden, runner)

    def test_playbook_compares_live_state_independently(self):
        source = PLAYBOOK.read_text()
        for required in (
            "hosts: dc02", "gather_facts: false",
            "KINGDOMS_PHASE03_RBCD_BASELINE",
            "lookup(\"ansible.builtin.file\", phase03_rbcd_baseline_path)",
            "$Ansible.Changed = $false",
            "Get-ADComputer -Identity 'WS01'",
            "Get-ADComputer -LDAPFilter '(sAMAccountName=PHASE03RBCD$)'",
            "RBCDPresent", "CandidateExisted", "RBCDBase64", "TargetDN",
            "PHASE03_RBCD_NEUTRAL_DN_MATCH=",
            "PHASE03_RBCD_NEUTRAL_DESCRIPTOR_MATCH=",
            "PHASE03_RBCD_NEUTRAL_CANDIDATE_MATCH=",
            "PHASE03_RBCD_NEUTRAL_VERIFIED=True",
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
        for mutation in (
            "Set-ADComputer", "Remove-ADComputer", "New-ADComputer",
            "Set-ADObject", "Remove-ADObject", "Register-ScheduledTask",
        ):
            self.assertNotIn(mutation, source)
