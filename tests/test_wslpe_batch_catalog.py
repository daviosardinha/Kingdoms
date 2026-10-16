"""Standalone 45-technique planning and frozen NORTH source regression."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest
from kingdoms import wslpe_batch_catalog as batch

ROOT = Path(__file__).resolve().parents[1]


class BatchTests(unittest.TestCase):
    def test_all_45_distinct_ordered_no_false_status(self):
        rows = batch.catalog()
        self.assertEqual([r["number"] for r in rows], list(range(1, 46)))
        self.assertEqual(len({r["id"] for r in rows}), 45)
        self.assertEqual([r["stage"] for r in rows].count("foundation"), 20)
        self.assertEqual([r["stage"] for r in rows].count("advanced"), 15)
        self.assertEqual([r["stage"] for r in rows].count("expert"), 10)
        self.assertTrue(all(r["status"] == "planned" for r in rows[20:]))
        self.assertTrue(all(not r["learner_exploited"] for r in rows))

    def test_north_is_frozen_and_advanced_never_promoted(self):
        original = batch.load
        source = original(batch.NORTH_SOURCE)
        self.assertEqual(source["windows_lpe_catalog"], list(batch.FROZEN_FOUNDATION))
        self.assertEqual(source["windows_lpe_candidate_techniques"], [])
        def drift(path):
            data = deepcopy(original(path))
            if path == batch.NORTH_SOURCE:
                data["windows_lpe_catalog"].append("unapproved")
            return data
        with patch.object(batch, "load", side_effect=drift), self.assertRaises(ValueError):
            batch.catalog()
        def forgery(path):
            data = deepcopy(original(path))
            if path == batch.EXPERT:
                data["techniques"][0]["status"] = "implemented"
            return data
        with patch.object(batch, "load", side_effect=forgery), self.assertRaises(ValueError):
            batch.catalog()

    def test_source_is_offline_and_cannot_contact_any_guest(self):
        content = (ROOT / "kingdoms/wslpe_batch_catalog.py").read_text()
        content += (ROOT / "scripts/wslpe-45-batch.py").read_text()
        for forbidden in ("import subprocess", "winrm.Session(", "vmrun", "ansible-playbook", "10.4.10.31"):
            self.assertNotIn(forbidden, content)
        report = batch.summary()
        self.assertFalse(report["ready_for_live_batch"])
        self.assertFalse(report["north_mutation"])
        self.assertEqual(report["planned"], 25)


if __name__ == "__main__":
    unittest.main()
