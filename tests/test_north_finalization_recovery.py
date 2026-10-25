"""Source-only receipt qualification for the exact NORTH finalization failure."""
import json
from pathlib import Path
import tempfile
import unittest

from goad.course1_finalization_recovery import (
    ATTEMPT, INSTANCE, PLAYBOOKS, NorthFinalizationRecoveryBlocked,
    prove_north_finalization_recovery,
)

ROOT = Path(__file__).resolve().parents[1]


class NorthFinalizationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.instance = Path(self.temp.name) / INSTANCE
        self.provider = self.instance / "provider"
        self.provider.mkdir(parents=True)
        (self.provider / ".goad-nomad-mode").write_text("exercise\n")
        self.timing_dir = self.instance / "install-timings"
        self.timing_dir.mkdir()
        self.receipt = self.timing_dir / (ATTEMPT + ".json")
        self.meta = {
            "id": INSTANCE, "lab": "NORTH", "provider": "vmware",
            "status": "ready for provisioning",
        }
        self.profile = {
            "instance_id": INSTANCE, "attempt_id": ATTEMPT,
            "status": "failed", "provider_success": True, "partial": False,
            "ansible_phases": [
                self.phase("Provisioning management-plane preparation"),
                *[self.phase("Playbook " + name) for name in PLAYBOOKS],
                self.phase("Final exercise-mode transition", "failed"),
            ],
        }
        self.write()

    @staticmethod
    def phase(label, outcome="succeeded", kind="phase"):
        return {"label": label, "outcome": outcome, "kind": kind}

    def write(self):
        self.receipt.write_text(json.dumps(self.profile))

    def prove(self):
        return prove_north_finalization_recovery(
            self.instance, self.provider, self.meta
        )

    def test_canonical_receipt_allows_only_live_validation(self):
        before = self.receipt.read_bytes()
        self.assertTrue(self.prove())
        self.assertEqual(before, self.receipt.read_bytes())
        self.assertEqual(self.meta["status"], "ready for provisioning")

    def test_expected_playbooks_match_north_manifest(self):
        text = (ROOT / "playbooks.yml").read_text(encoding="utf-8")
        block = text.split("\nNORTH:\n", 1)[1].split("\ndefault:\n", 1)[0]
        actual = tuple(
            line.strip()[2:].strip() for line in block.splitlines()
            if line.strip().startswith("- ")
        )
        self.assertEqual(actual, PLAYBOOKS)
        self.assertEqual(len(PLAYBOOKS), 21)

    def test_failed_or_missing_playbook_blocks_recovery(self):
        for replace in ("failed", "missing"):
            with self.subTest(replace=replace):
                saved = list(self.profile["ansible_phases"])
                if replace == "failed":
                    self.profile["ansible_phases"][5] = self.phase(
                        saved[5]["label"], "failed"
                    )
                else:
                    self.profile["ansible_phases"].pop(5)
                self.write()
                with self.assertRaisesRegex(
                    NorthFinalizationRecoveryBlocked, "21 NORTH playbooks"
                ):
                    self.prove()
                self.profile["ansible_phases"] = saved

    def test_reject_other_failed_stage(self):
        self.profile["ansible_phases"][-1]["outcome"] = "succeeded"
        self.write()
        with self.assertRaises(NorthFinalizationRecoveryBlocked):
            self.prove()

    def test_reject_failed_playbook_attempt_even_if_parent_passed(self):
        self.profile["ansible_phases"].insert(
            2, self.phase("Playbook attempt build.yml #1",
                          "failed", kind="playbook_attempt")
        )
        self.write()
        with self.assertRaisesRegex(
            NorthFinalizationRecoveryBlocked, "unsuccessful playbook attempt"
        ):
            self.prove()

    def test_reject_unknown_or_other_instance(self):
        self.meta["id"] = "somewhere-else"
        with self.assertRaises(NorthFinalizationRecoveryBlocked):
            self.prove()
        self.meta["id"] = INSTANCE
        self.meta["status"] = "not provided"
        with self.assertRaises(NorthFinalizationRecoveryBlocked):
            self.prove()

    def test_reject_missing_exercise_mode(self):
        (self.provider / ".goad-nomad-mode").unlink()
        with self.assertRaisesRegex(NorthFinalizationRecoveryBlocked, "exercise"):
            self.prove()

    def test_reject_failed_provider_or_wrong_attempt(self):
        for key, bad in (("provider_success", False),
                         ("attempt_id", "other"),
                         ("partial", True),
                         ("status", "completed")):
            with self.subTest(key=key):
                original = self.profile[key]
                self.profile[key] = bad
                self.write()
                with self.assertRaises(NorthFinalizationRecoveryBlocked):
                    self.prove()
                self.profile[key] = original

    def test_wrong_receipt_location_blocked(self):
        self.receipt.unlink()
        with self.assertRaises(NorthFinalizationRecoveryBlocked):
            self.prove()

    def test_validator_has_strict_gate_not_status_assignment(self):
        src = (ROOT / "scripts/validate-north-runtime.sh").read_text()
        self.assertIn('elif data.get("status") == "ready for provisioning":', src)
        self.assertIn("prove_north_finalization_recovery(instance, provider, data)", src)
        self.assertIn("NORTH_EXACT_FINALIZATION_RECOVERY_ATTESTED", src)
        self.assertIn("NORTH_RUNTIME_ACCEPTANCE=PASS", src)
        self.assertNotIn("data[\"status\"] = \"installed\"", src)


if __name__ == "__main__":
    unittest.main()
