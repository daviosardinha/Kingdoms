"""Offline readiness checks for four *unqualified* native prototypes.

No guest calls, no installer invocation, and no source-to-candidate promotion.
"""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ansible/files/wslpe45"


class FinalFourSourceBatchTests(unittest.TestCase):
    def test_candidate_index_still_fail_closed(self):
        doc = yaml.safe_load(
            (ROOT / "kingdoms/wslpe45_implementation_index.yml").read_text()
        )
        self.assertFalse(doc["batch_execution_authorized"])
        for number in (25, 36, 38, 40):
            with self.subTest(number=number):
                row = next(t for t in doc["techniques"] if t["number"] == number)
                self.assertEqual(row["status"], "planned")
                self.assertEqual(row["source_ci"], "pending")
                self.assertEqual(row["learner_proof"], "pending")
                self.assertEqual(row["six_stage_qualification"], "pending")
                self.assertFalse((ROOT / row["playbook"]).exists())

    def test_accepted_prototypes_are_native_and_bounded(self):
        accepted = (
            ("Kingdom25Repair.cpp", ("MsiGetPropertyW", "CustomActionData")),
            ("Kingdom36WmiProvider.cs", ("WmiConfiguration", "ManagementTask")),
            ("Kingdom40LocalRpc.idl", ("interface Kingdom40LocalRpc", "handle_t")),
        )
        for filename, expected in accepted:
            with self.subTest(filename=filename):
                body = (SRC / filename).read_text(encoding="utf-8")
                for token in expected:
                    self.assertIn(token, body)
                self.assertNotIn("GOAD-WS01", body)
        self.assertFalse((SRC / "Kingdom38DcomServer.cpp").exists())

    def test_gate_document_preserves_native_mechanisms(self):
        text = (ROOT / "docs/WSLPE45_FINAL_FOUR_SOURCE_BATCH.md").read_text()
        for string in ("#25", "#36", "#38", "#40", "NOT DEPLOYABLE",
                       "21/25", "ncalrpc", "MSI", "DCOM", "WMI"):
            self.assertIn(string, text)


if __name__ == "__main__":
    unittest.main()
