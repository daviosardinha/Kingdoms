"""Read-only strict recovered NORTH metadata eligibility (no VMware required)."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from goad.course1_recovered_runtime import (
    ATTEMPT, INSTANCE, PRE_AD_MARKER, SRV02_MARKER,
    RecoveredRuntimeBlocked, prove_recovered_north_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/validate-north-runtime.sh"


class RecoveredNorthRuntimeTests(unittest.TestCase):
    def fixture(self, root):
        instance = Path(root) / INSTANCE
        provider = instance / "provider"
        provider.mkdir(parents=True)
        (provider / ".goad-nomad-mode").write_text("exercise\n")
        data = {
            "id": INSTANCE, "lab": "NORTH", "provider": "vmware",
            "status": "not provided",
        }
        (instance / "instance.json").write_text(json.dumps(data))
        resume = instance / PRE_AD_MARKER
        resume.write_text(
            "NORTH repaired provider resume for " + INSTANCE +
            "\nAttempt " + ATTEMPT + "\nAuthorized first playbook: build.yml\n"
        )
        resume.chmod(0o600)
        repair = instance / SRV02_MARKER
        repair.write_text("One repair attempt for " + INSTANCE + "/GOAD-SRV02\n")
        repair.chmod(0o600)
        folder = instance / "install-timings"
        folder.mkdir()
        receipt = folder / (ATTEMPT + ".json")
        receipt.write_text(json.dumps({
            "instance_id": INSTANCE, "attempt_id": ATTEMPT,
            "status": "failed", "provider_success": False,
            "ansible_phases": [],
        }))
        return instance, provider, data, receipt

    def test_exact_original_state_allows_only_further_runtime_checks(self):
        with TemporaryDirectory() as root:
            instance, provider, data, _ = self.fixture(root)
            self.assertTrue(prove_recovered_north_metadata(instance, provider, data))
            # The attestation itself neither edits metadata nor asserts that
            # the 21 playbooks actually completed.
            self.assertEqual(json.loads((instance / "instance.json").read_text()),
                             data)

    def test_no_new_instance_or_normal_uninstalled_lab_can_bypass(self):
        with TemporaryDirectory() as root:
            instance, provider, data, _ = self.fixture(root)
            for updated in (
                {**data, "status": "installed"}, {**data, "lab": "GOAD"},
                {**data, "provider": "virtualbox"},
                {**data, "id": "000000-north-vmware"},
            ):
                with self.subTest(updated=updated), \
                     self.assertRaises(RecoveredRuntimeBlocked):
                    prove_recovered_north_metadata(instance, provider, updated)
            with self.assertRaises(RecoveredRuntimeBlocked):
                prove_recovered_north_metadata(
                    Path(root)/"another-north-vmware", provider, data
                )

    def test_markers_or_receipt_mismatch_fail_closed(self):
        with TemporaryDirectory() as root:
            instance, provider, data, receipt_path = self.fixture(root)
            for marker_name in (PRE_AD_MARKER, SRV02_MARKER):
                marker = instance / marker_name
                original = marker.read_text()
                marker.write_text("wrong")
                with self.assertRaises(RecoveredRuntimeBlocked):
                    prove_recovered_north_metadata(instance, provider, data)
                marker.write_text(original)
                marker.chmod(0o600)
            record = json.loads(receipt_path.read_text())
            for different in (
                {"instance_id": "foreign"},
                {"attempt_id": "foreign"},
                {"status": "completed"},
                {"provider_success": True},
                {"ansible_phases": [{"label": "build.yml"}]},
            ):
                receipt_path.write_text(json.dumps({**record, **different}))
                with self.subTest(different=different), \
                     self.assertRaises(RecoveredRuntimeBlocked):
                    prove_recovered_north_metadata(instance, provider, data)
            receipt_path.write_text(json.dumps(record))
            (provider / ".goad-nomad-mode").write_text("unknown")
            with self.assertRaises(RecoveredRuntimeBlocked):
                prove_recovered_north_metadata(instance, provider, data)

    def test_exercise_validator_gates_only_before_existing_strict_runtime(self):
        content = VALIDATOR.read_text()
        self.assertIn("prove_recovered_north_metadata(instance, provider, data)", content)
        self.assertIn("NORTH_EXACT_RECOVERED_INSTANCE_ATTESTED", content)
        self.assertIn("NORTH_RECOVERED_INSTANCE_PENDING_RUNTIME_PROOF", content)
        self.assertIn("NORTH_INSTANCE_INSTALLED_EXERCISE", content)
        self.assertLess(content.index("prove_recovered_north_metadata("),
                        content.index("NORTH_FIVE_OWNED_VMS_RUNNING"))
        self.assertLess(content.index("NORTH_EXACT_RECOVERED_INSTANCE_ATTESTED"),
                        content.index("NORTH_HOST_NETWORK_OWNER_VERIFIED"))
        self.assertIn("NORTH_AD_IDENTITY_TIME_TRUST_READY", content)
        self.assertIn("NORTH_EXERCISE_MODE_PRESERVED", content)
        self.assertIn("NORTH_RUNTIME_ACCEPTANCE=PASS", content)
        self.assertNotIn("set_status(", content)
        self.assertNotIn("vagrant up", content)
        self.assertNotIn("vmrun -T ws stop", content)


if __name__ == "__main__":
    unittest.main()
