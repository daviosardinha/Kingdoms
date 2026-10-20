"""Offline guards for read-only RBCD post-attack recovery inspection.

This is forensic corroboration only. It must never be accepted as the
Stage 1 ownership receipt or silently enable the protected rollback.
"""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/course1-phase03-rbcd-postattack-inspect.sh"
PLAYBOOK = ROOT / "ansible/phase03-rbcd-postattack-inspect-north.yml"


class TestRBCDPostattackInspector(unittest.TestCase):
    def test_shell_syntax_and_invalid_args(self):
        parsed = subprocess.run(["bash", "-n", str(RUNNER)], capture_output=True, text=True)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        for args in ([], ["ac9fda-north-vmware"], ["ac9fda-north-vmware", "/tmp/x", "--apply"],
                     ["ac9fda-north-vmware", "/tmp/x", "--inspect", "--confirm"]):
            with self.subTest(args=args):
                result = subprocess.run(["bash", str(RUNNER), *args],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)

    def test_exact_north_host_inventories_and_shared_lock(self):
        s = RUNNER.read_text(encoding="utf-8")
        for expected in (
            "ad/NORTH/data/inventory", "workspace/$INSTANCE/inventory",
            "ac9fda", ".course1-phase03-acceptance.lock",
            "rbcd-baseline.sha256", "sha256sum --check --status",
            "scripts/course1-rollout.sh --installed",
            "phase03-rbcd-postattack-inspect-north.yml",
            "PHASE03_RBCD_RECOVERY_APPROVAL=REQUIRED",
            "PHASE03_RBCD_ROLLBACK_ACCEPTANCE=NOT_TESTED",
        ):
            if expected == "ac9fda":
                continue  # Instance ID is supplied by the operator, never hardcoded.
            self.assertIn(expected, s)
        self.assertNotIn("ad/GOAD/data/inventory", s)

    def test_playbook_reads_current_ad_without_mutation(self):
        s = PLAYBOOK.read_text(encoding="utf-8")
        for marker in (
            "hosts: dc02", "$Ansible.Changed = $false",
            "Get-ADComputer -Identity 'WS01'",
            "Get-ADComputer -LDAPFilter '(sAMAccountName=PHASE03RBCD$)'",
            "ObjectSid", "ObjectGUID", "whenCreated", "mS-DS-CreatorSID",
            "RawSecurityDescriptor", "DiscretionaryAcl", "AccessAllowed",
            "PHASE03_RBCD_POST_ATTACK_ONLY_CONTROLLED_ACE=",
            "PHASE03_RBCD_POST_ATTACK_CREATED_AFTER_BASELINE=",
            "PHASE03_RBCD_POST_ATTACK_CONSISTENT=",
            "PHASE03_RBCD_POST_ATTACK_READ_ONLY=True",
        ):
            self.assertIn(marker, s)
        for forbidden in (
            "Set-ADComputer", "Remove-ADComputer", "New-ADComputer",
            "Add-ADComputer", "Set-ADObject", "Remove-ADObject",
            "Set-ItemProperty", "New-ItemProperty",
        ):
            self.assertNotIn(forbidden, s)

    def test_wrapper_does_not_create_an_ownership_receipt_or_snapshot(self):
        s = RUNNER.read_text(encoding="utf-8")
        for forbidden in (
            "rbcd-ownership.json", "rbcd-ownership.sha256",
            "phase03-rbcd-rollback-north.yml",
            "course1-phase03-rbcd-rollback.sh",
            "--apply", "--confirm", "Goad.do_reset",
            "vmrun revertToSnapshot",
        ):
            # --apply/--confirm may occur in comments or assertions, but never in live call.
            if forbidden in ("--apply", "--confirm"):
                self.assertNotIn(f"\"{forbidden}\"", s)
                continue
            self.assertNotIn(forbidden, s)


if __name__ == "__main__":
    unittest.main()
