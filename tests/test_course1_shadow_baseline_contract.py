"""Offline NORTH Shadow Credentials baseline source and containment contract."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/course1-phase03-shadow-baseline.sh"
PLAYBOOK = ROOT / "ansible/phase03-shadow-baseline.yml"


class Course1ShadowBaselineContractTests(unittest.TestCase):
    def test_runner_parses_and_requires_exact_capture_confirmation(self):
        result = subprocess.run(["bash", "-n", str(RUNNER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for argv in ([], ["ac9fda-north-vmware"], ["ac9fda-north-vmware", "--capture"],
                     ["ac9fda-north-vmware", "--reset", "--confirm"],
                     ["goad-vmware", "--capture", "--confirm"]):
            with self.subTest(argv=argv):
                blocked = subprocess.run(["bash", str(RUNNER), *argv],
                                         capture_output=True, text=True)
                self.assertEqual(blocked.returncode, 2)

    def test_uses_exact_north_instance_and_shared_lock(self):
        src = RUNNER.read_text(encoding="utf-8")
        for token in (
            'ad/NORTH/data/inventory',
            'workspace/$INSTANCE/inventory',
            '.goad-nomad-mode',
            '.course1-phase03-acceptance.lock',
            'flock -n 9',
            'scripts/course1-rollout.sh --installed',
            'ansible/phase03-shadow-preflight.yml',
            'PHASE03_SHADOW_KCL_EMPTY=True',
            'PHASE03_SHADOW_SELF_VALIDATED_WRITE=True',
            'PHASE03_SHADOW_KDC_CERT_COUNT=[1-9][0-9]*',
            'PHASE03_SHADOW_CERTUTIL_RC=0',
        ):
            with self.subTest(token=token):
                self.assertIn(token, src)
        self.assertNotIn('ad/GOAD/', src)
        self.assertNotIn('GOAD_NOMAD', src)

    def test_preserves_old_baseline_and_writes_private_unique_evidence(self):
        src = RUNNER.read_text(encoding="utf-8")
        for token in (
            'mktemp -d "$EVIDENCE_ROOT/phase03-shadow-baseline-XXXXXXXX"',
            'chmod 700 "$EVIDENCE"',
            'BASELINE="$EVIDENCE/shadow-baseline.json"',
            'KINGDOMS_PHASE03_SHADOW_BASELINE="$BASELINE"',
            'ansible/phase03-shadow-baseline.yml',
            'stat.S_IMODE(meta.st_mode) != 0o600',
            'shadow-baseline.sha256',
            'PHASE03_SHADOW_BASELINE_NEUTRAL=True',
            'PHASE03_SHADOW_BASELINE_CAPTURE=PASS',
            'PHASE03_SHADOW_ACTIVE_ACCEPTANCE=NOT_TESTED',
            'KCLCount',
            'KCLValues',
            'CapturedUTC',
        ):
            with self.subTest(token=token):
                self.assertIn(token, src)
        self.assertNotIn('rm -rf', src)
        self.assertNotIn('phase03-shadow-baseline.json', src)
        self.assertNotIn('--shadow-credentials', src)
        self.assertNotIn('windows_lpe_action', src)

    def test_playbook_explicit_env_is_backward_compatible(self):
        src = PLAYBOOK.read_text(encoding="utf-8")
        self.assertIn("lookup('env','KINGDOMS_PHASE03_SHADOW_BASELINE')", src)
        self.assertIn("'/.config/kingdoms/phase03-shadow-baseline.json'", src)
        self.assertIn('dest: "{{ phase03_shadow_baseline_path }}"', src)
        self.assertIn('path: "{{ phase03_shadow_baseline_path | dirname }}"', src)
        self.assertIn("PHASE03_SHADOW_BASELINE_FILE={{ phase03_shadow_baseline_path }}", src)
        self.assertIn("$Ansible.Changed = $false", src)
        for prohibited in ("Set-ADComputer", "Remove-ADComputer", "Set-ADObject"):
            self.assertNotIn(prohibited, src)


if __name__ == "__main__":
    unittest.main()
