"""Release bookkeeping must never confuse catalog, source, runtime and exploit proof."""
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from kingdoms import wslpe45_closeout as closeout
from kingdoms import wslpe45_batch_operator as batch

ROOT = Path(__file__).resolve().parents[1]


class CloseoutTests(unittest.TestCase):
    def test_indexed_45_rows_and_explicit_distinct_evidence_gates(self):
        data = closeout.report()
        self.assertEqual(data["scope"], "standalone-wslpe-only")
        self.assertTrue(data["north_frozen"])
        self.assertEqual([x["number"] for x in data["techniques"]], list(range(1, 46)))
        self.assertEqual(len({x["id"] for x in data["techniques"]}), 45)
        self.assertEqual(data["counts"]["foundation_lifecycle_evidence"], 20)
        candidates = sum(
            row["source"] == "candidate_source_ready" for row in data["techniques"][20:])
        self.assertEqual(data["counts"]["additional_source_candidates"], candidates)
        self.assertEqual(data["counts"]["additional_source_incomplete"], 25-candidates)
        self.assertEqual(data["counts"]["additional_six_stage_qualified"], 0)
        self.assertEqual(data["counts"]["independent_learner_exploit_accepted"], 0)
        self.assertFalse(data["ready_for_batch_execution"])
        self.assertFalse(data["ready_for_learner_release"])

    def test_source_blockers_and_runtime_evidence_are_not_conflated(self):
        d = closeout.report()
        _, source_blockers = batch.source_readiness()
        actual_blocked = {
            int(message[1:3]) for message in source_blockers
        }
        incomplete = {
            x["number"] for x in d["techniques"]
            if x["source"] == "source_incomplete"
        }
        self.assertEqual(incomplete, actual_blocked)
        self.assertTrue(all(d["techniques"][n-1]["six_stage_lifecycle"] ==
                            "not_verified" for n in range(21,46)))
        self.assertTrue(all(d["techniques"][n-1]["learner_exploit"] ==
                            "not_verified" for n in range(1,46)))

    def test_bad_source_index_order_blocks_without_guest_call(self):
        rows = batch.index_rows()
        rows[0] = {**rows[0], "id": "unapproved_candidate"}
        with patch.object(closeout.batch, "index_rows", return_value=rows), \
             patch.object(closeout.batch, "trusted_safety") as vm:
            with self.assertRaises(ValueError):
                closeout.report()
            vm.assert_not_called()

    def test_no_guest_access_even_from_cli(self):
        with patch.object(closeout.batch, "trusted_safety") as safe, \
             patch.object(closeout.batch.subprocess, "run") as process:
            self.assertEqual(closeout.main([]), 0)
            safe.assert_not_called()
            process.assert_not_called()

    def test_json_has_release_gates_no_credentials_or_fake_status(self):
        data = closeout.report()
        self.assertGreaterEqual(len(data["release_gates"]), 8)
        self.assertEqual(set(data["release_gates"].values()), {"not_verified"})
        blob = json.dumps(data)
        self.assertNotIn("ansible_password", blob)
        self.assertNotIn("WSLPE45_BATCH_STAGE=", blob)
        self.assertTrue(data["no_guest_contact"])
        source = (ROOT/"scripts/wslpe45-closeout.py").read_text("utf-8")
        self.assertNotIn("exit 1",source)
        self.assertNotIn("set -e",source)
        self.assertNotIn("subprocess",source)


if __name__=="__main__":
    unittest.main()
