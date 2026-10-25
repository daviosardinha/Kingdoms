"""NORTH snapshot-generation and retrospective audit never invoke VMware."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from goad.course1_snapshot_evidence import (
    GUESTS, SnapshotEvidenceError, audit_evidence,
    prove_generation, verify_restored_generation,
)


class SnapshotEvidenceTests(unittest.TestCase):
    def sample(self):
        before = {guest: [] for guest in GUESTS}
        after = {guest: [f"push_{1792932651+i*2}_{4000+i}"]
                 for i, guest in enumerate(sorted(GUESTS))}
        return before, after

    def fixture(self, folder):
        before, after = self.sample()
        path = Path(folder)
        (path / "snapshots-before.json").write_text(json.dumps(before))
        (path / "snapshots-after.json").write_text(json.dumps(after))
        target = "".join(f"NORTH snapshot target: {guest} -> {name[0]}\n"
                         for guest, name in sorted(after.items()))
        done = "".join(
            f"NORTH offline snapshot restore verified: {guest} -> {name[0]}\n"
            for guest, name in sorted(after.items())
        )
        (path / "05-snapshot-restore.log").write_text(
            target + done +
            "snapshot restored and offline exercise NIC contract reasserted\n"
            "segmented lab started and readiness verified (mode: exercise)\n"
        )
        for step in ("04-post-snapshot-health.log", "06-post-restore-health.log"):
            (path / step).write_text(
                "[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS\n"
                "[PASS] NORTH_EXERCISE_MODE_PRESERVED\n"
                "instance status is installed\n"
            )
        (path / "07-owner-final.log").write_text(
            "[PASS] NORTH immutable owner, baseline backup and committed journal match\n"
            "[PASS] NORTH live vmnets and permitted VMware normalization verified\n"
        )
        (path / "summary.txt").write_text(
            "instance=8aafc9-north-vmware\n"
            "PASS | 03-snapshot-create\nPASS | 05-snapshot-restore\n"
            "PASS | 06-post-restore-health\n"
        )
        return path

    def test_one_matching_generation_is_proven(self):
        old, new = self.sample()
        selected = prove_generation(old, new)
        self.assertEqual(selected, {name: snapshots[0] for name, snapshots in new.items()})

    def test_missing_duplicated_or_mixed_generations_refuse(self):
        old, new = self.sample()
        for alteration in (
            lambda x: x.pop("GOAD-WS01"),
            lambda x: x["GOAD-WS01"].append(x["GOAD-WS01"][0]),
            lambda x: x["GOAD-WS01"].append("push_1792932651_12345"),
            lambda x: x.__setitem__("GOAD-WS01", ["push_1792949000_1234"]),
        ):
            altered = {k: v[:] for k, v in new.items()}
            alteration(altered)
            with self.assertRaises(SnapshotEvidenceError):
                prove_generation(old, altered)
        altered = dict(old)
        altered["GOAD-WS01"] = ["push_1792932651_55"]
        with self.assertRaises(SnapshotEvidenceError):
            prove_generation(altered, new)

    def test_original_evidence_audits_without_vm_calls(self):
        with TemporaryDirectory() as tmp:
            folder = self.fixture(tmp)
            selection = audit_evidence(folder)
            self.assertEqual(len(selection), 5)
            result = subprocess.run(
                [sys.executable, "-m", "goad.course1_snapshot_evidence", str(folder)],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[PASS] NORTH_SNAPSHOT_EVIDENCE_AUDIT=PASS", result.stdout)

    def test_fail_closed_if_restore_or_ad_health_evidence_is_absent(self):
        with TemporaryDirectory() as tmp:
            folder = self.fixture(tmp)
            log = folder / "05-snapshot-restore.log"
            text = log.read_text()
            log.write_text(text.replace("NORTH offline snapshot restore verified: GOAD-DC02",
                                        "NORTH offline snapshot restore verified: FOREIGN"))
            with self.assertRaises(SnapshotEvidenceError):
                audit_evidence(folder)
            log.write_text(text)
            post = folder / "06-post-restore-health.log"
            post.write_text("NORTH_RUNTIME_ACCEPTANCE=FAIL\n")
            with self.assertRaises(SnapshotEvidenceError):
                audit_evidence(folder)

    def test_generation_only_cli_blocks_invalid_inventory(self):
        with TemporaryDirectory() as tmp:
            folder = self.fixture(tmp)
            cmd = [sys.executable, "-m", "goad.course1_snapshot_evidence",
                   "--generation-only", str(folder / "snapshots-before.json"),
                   str(folder / "snapshots-after.json")]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("NORTH_FIVE_VM_SNAPSHOT_GENERATION=PASS", result.stdout)
            (folder / "snapshots-after.json").write_text("{}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("NORTH_FIVE_VM_SNAPSHOT_GENERATION=PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
