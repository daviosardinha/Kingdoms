"""Source safeguards: NORTH RBCD rollback must never delete by name alone."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "scripts/course1-phase03-rbcd-register.sh"
ROLLBACK = ROOT / "scripts/course1-phase03-rbcd-rollback.sh"
OWNER = ROOT / "ansible/phase03-rbcd-record-ownership-north.yml"
RESTORE = ROOT / "ansible/phase03-rbcd-rollback-north.yml"
BASELINE = ROOT / "ansible/phase03-rbcd-baseline.yml"
NEUTRAL = ROOT / "ansible/phase03-rbcd-verify-neutral.yml"


class NorthRBCDRollbackContractTests(unittest.TestCase):
    def test_new_shell_entrypoints_parse(self):
        for script in (REGISTER, ROLLBACK):
            with self.subTest(script=script):
                result = subprocess.run(["bash", "-n", str(script)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_mutating_entrypoint_requires_explicit_confirmation(self):
        for argv in ([], ["ac9fda-north-vmware", "/tmp/foo", "--apply"],
                     ["ac9fda-north-vmware", "/tmp/foo", "--apply", "wrong"]):
            with self.subTest(argv=argv):
                r = subprocess.run(["bash", str(ROLLBACK), *argv],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 2)

    def test_stage1_receipt_is_attested_to_a_fresh_pre_attack_baseline(self):
        b = BASELINE.read_text()
        register = REGISTER.read_text()
        owner = OWNER.read_text()
        self.assertIn("CapturedAtUtc", b)
        for token in (
            ".course1-phase03-acceptance.lock",
            "rbcd-baseline.sha256",
            "sha256sum -c",
            "scripts/course1-rollout.sh --installed",
            "phase03-rbcd-record-ownership-north.yml",
            'rbcd-ownership.json',
            'rbcd-ownership.sha256',
            "PHASE03_RBCD_STAGE1_OWNERSHIP_CAPTURE=PASS",
        ):
            self.assertIn(token, register)
        for token in (
            "CandidateSID", "CandidateGUID", "CandidateDN",
            "CandidateCreatedAtUtc", "BaselineSHA256",
            "CapturedAtUtc", "ObjectSid,ObjectGUID,whenCreated",
            "CandidateExisted", "RBCDPresent", "TargetDN",
            "force: false", "mode: '0600'",
            "PHASE03_RBCD_STAGE1_OWNERSHIP_REGISTERED=True",
        ):
            self.assertIn(token, owner)

    def test_clean_baseline_and_neutral_checks_never_miss_security_descriptor_object(self):
        baseline = BASELINE.read_text()
        self.assertEqual(baseline.count("- name: Capture NORTH RBCD baseline"), 1)
        self.assertEqual(baseline.count("      changed_when: false"), 1)
        self.assertIn("Target = 'WS01$'", baseline)
        self.assertIn("CapturedAtUtc = (Get-Date).ToUniversalTime()", baseline)
        self.assertIn("if ($rbcd -is [byte[]]) { $rbcdPresent = $rbcd.Length -gt 0 }", baseline)
        preflight = (ROOT / "ansible/phase03-rbcd-preflight.yml").read_text()
        neutral = NEUTRAL.read_text()
        restore = RESTORE.read_text()
        self.assertIn("if ($rbcd -is [byte[]]) { $rbcdPresent = $rbcd.Length -gt 0 }", preflight)
        self.assertIn("if ($current -is [byte[]]) { $isPresent = $current.Length -gt 0 }", neutral)
        self.assertIn("if ($raw -is [byte[]]) { $rbcdPresent = $raw.Length -gt 0 }", restore)

    def test_receipt_hashes_include_trailing_json_newline(self):
        for playbook in (OWNER, RESTORE):
            with self.subTest(playbook=playbook):
                source = playbook.read_text()
                self.assertIn(
                    "lookup('ansible.builtin.file', rbcd_baseline_path, rstrip=False) | hash('sha256')",
                    source,
                )
        register = REGISTER.read_text()
        self.assertIn("hashlib.sha256(baseline_path.read_bytes()).hexdigest()", register)
        self.assertIn("PHASE03_RBCD_STAGE1_OWNERSHIP_REGISTERED=True", register)

    def test_rollback_checks_all_provenance_before_writes(self):
        src = RESTORE.read_text()
        read_section, writes = src.split("          if ($rbcdPresent) {\n              Set-ADComputer", 1)
        for token in (
            "CandidateSID", "CandidateGUID",
            "CandidateCreatedAtUtc", "CandidateDN",
            "BaselineSHA256", "CapturedAtUtc",
            "Get-ADComputer -LDAPFilter '(sAMAccountName=PHASE03RBCD$)'",
            "$candidate.ObjectSid.Value -ne $receipt.CandidateSID",
            "candidate.ObjectGUID", "candidate.DistinguishedName",
            "RawSecurityDescriptor", "$aces.Count -ne 1",
            "$aces[0].SecurityIdentifier.Value -ne $receipt.CandidateSID",
            "throw 'RBCD contains unexpected delegation entries",
        ):
            with self.subTest(token=token):
                self.assertIn(token, read_section)
        self.assertNotIn("Remove-ADComputer", read_section)
        self.assertIn("Remove-ADComputer -Identity $candidate.DistinguishedName", writes)
        self.assertIn("PHASE03_RBCD_ROLLBACK_COMPLETE=True", writes)
        self.assertNotIn("New-ADComputer", src)
        self.assertNotIn("Set-ADComputer -Replace", src)

    def test_orchestrator_refuses_untrusted_state_and_verifies_separately(self):
        src = ROLLBACK.read_text()
        for token in (
            'phase03-rbcd-baseline-*/rbcd-baseline.json',
            "rbcd-baseline.sha256", "rbcd-ownership.sha256",
            "sha256sum --check --status",
            ".course1-phase03-acceptance.lock", "flock -n 9",
            'scripts/course1-rollout.sh --installed',
            "ansible/phase03-rbcd-rollback-north.yml",
            "ansible/phase03-rbcd-verify-neutral.yml",
            "PHASE03_RBCD_ROLLBACK_ACCEPTANCE=PASS",
            "PHASE03_RBCD_NEUTRAL_ACCEPTANCE=PASS",
            "PHASE03_RBCD_ACTIVE_ACCEPTANCE=NOT_TESTED",
        ):
            with self.subTest(token=token):
                self.assertIn(token, src)
        i_restore = src.index("ansible/phase03-rbcd-rollback-north.yml")
        i_neutral = src.index("ansible/phase03-rbcd-verify-neutral.yml")
        i_success = src.index("echo 'PHASE03_RBCD_ROLLBACK_ACCEPTANCE=PASS'")
        self.assertLess(i_restore, i_neutral)
        self.assertLess(i_neutral, i_success)
        self.assertNotIn("snapshot pop", src)
        self.assertNotIn("rm -rf", src)
        self.assertNotIn("start-rbcd-stage1-add-computer.sh", src)
        self.assertIn("PHASE03_RBCD_NEUTRAL_VERIFIED=True", NEUTRAL.read_text())
