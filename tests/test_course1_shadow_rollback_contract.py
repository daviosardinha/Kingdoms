"""NORTH Shadow Credentials rollback is baseline-bound and fails closed."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/course1-phase03-shadow-rollback.sh"
PLAYBOOK = ROOT / "ansible/phase03-shadow-rollback-north.yml"
NEUTRAL = ROOT / "ansible/phase03-shadow-verify-neutral-north.yml"


class ShadowRollbackContractTests(unittest.TestCase):
    def test_bash_parses_and_requires_exact_explicit_confirmation(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for argv in (
            [], ["ac9fda-north-vmware"], ["goad-vmware", "/tmp/x", "--plan"],
            ["ac9fda-north-vmware", "/tmp/x"],
            ["ac9fda-north-vmware", "/tmp/x", "--apply"],
            ["ac9fda-north-vmware", "/tmp/x", "--apply", "--confirm"],
            ["ac9fda-north-vmware", "/tmp/x", "--apply", "--confirm", "bad"],
            ["ac9fda-north-vmware", "/tmp/x", "--plan", "--confirm"],
        ):
            with self.subTest(argv=argv):
                blocked = subprocess.run(["bash", str(SCRIPT), *argv],
                                         capture_output=True, text=True)
                self.assertEqual(blocked.returncode, 2)

    def test_explicit_current_north_instance_locked_baseline_and_sha(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for token in (
            'ad/NORTH/data/inventory',
            'workspace/$INSTANCE/inventory',
            '.goad-nomad-mode',
            '.course1-phase03-acceptance.lock',
            'flock -n 9',
            'scripts/course1-rollout.sh --installed',
            'phase03-shadow-baseline-*/shadow-baseline.json',
            'shadow-baseline.sha256',
            'sha256sum --check --status',
            'stat.S_IMODE(info.st_mode) != mode',
            'KCLPresent',
            'KCLCount',
            'KCLValues',
            'PHASE03_SHADOW_ROLLBACK_ACCEPTANCE=NOT_TESTED',
            'KINGDOMS_PHASE03_SHADOW_KCL_FINGERPRINT',
            'KINGDOMS_PHASE03_SHADOW_ROLLBACK_ACTION',
            'PHASE03_SHADOW_ROLLBACK_ACCEPTANCE=PASS',
            'PHASE03_SHADOW_NEUTRAL_ACCEPTANCE=PASS',
        ):
            with self.subTest(token=token):
                self.assertIn(token, src)
        for unsafe in (
            'ad/GOAD/data/inventory', 'ROOT:-$HOME/Documents/GOAD_NOMAD',
            'rm -rf', 'snapshot', '--shadow-credentials', 'start-shadow-relay',
            'rollback-shadow.sh',
        ):
            with self.subTest(unsafe=unsafe):
                self.assertNotIn(unsafe, src)

    def test_live_mutation_fails_closed_on_unexpected_kcl_and_identity(self):
        script = PLAYBOOK.read_text(encoding="utf-8")
        for marker in (
            'hosts: dc02',
            'lookup(\'env\',\'KINGDOMS_PHASE03_SHADOW_BASELINE\')',
            'lookup(\'env\',\'KINGDOMS_PHASE03_SHADOW_ROLLBACK_ACTION\')',
            'lookup(\'env\',\'KINGDOMS_PHASE03_SHADOW_KCL_FINGERPRINT\')',
            "'plan', 'apply'",
            'shadow_expected_fingerprint is match',
            '$Ansible.Changed = $false',
            "$values.Count -gt 1",
            "$target.ObjectSid.Value -ne $baseline.TargetSID",
            '[StringComparison]::OrdinalIgnoreCase',
            'SHA256',
            "$fingerprint -cne $expected",
            "Set-ADComputer -Identity $target.DistinguishedName -Clear 'msDS-KeyCredentialLink'",
            'PHASE03_SHADOW_ROLLBACK_APPLIED=True',
            'PHASE03_SHADOW_ROLLBACK_KCL_SHA256=',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)
        for dangerous in ('-Replace', 'Remove-ADComputer', 'Set-ADObject', 'Remove-ADObject'):
            self.assertNotIn(dangerous, script)

    def test_independent_verifier_no_mutation_and_exact_identity_baseline(self):
        source = NEUTRAL.read_text(encoding="utf-8")
        for marker in (
            'hosts: dc02',
            'KINGDOMS_PHASE03_SHADOW_BASELINE',
            '$Ansible.Changed = $false',
            'msDS-KeyCredentialLink',
            'shadow_baseline.TargetSID',
            '$target.ObjectSid.Value -eq $baseline.TargetSID',
            'PHASE03_SHADOW_NEUTRAL_VERIFIED=True',
            "if (-not $identityMatch -or -not $neutral)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)
        for unsafe in ('Set-ADComputer', 'Set-ADObject', 'Remove-ADObject', 'Remove-ADComputer'):
            self.assertNotIn(unsafe, source)


if __name__ == "__main__":
    unittest.main()
