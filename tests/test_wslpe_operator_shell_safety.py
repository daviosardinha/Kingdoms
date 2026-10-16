"""Prevent unsafe interactive Kali shell examples in WSLPE operator runbooks."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/WSLPE_20_TECHNIQUE_FAST_TRACK.md"

class WslpeOperatorShellSafetyTests(unittest.TestCase):
    def test_exit_on_error_only_appears_inside_guarded_subshell(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        examples = re.findall(r"~~~bash\n(.*?)\n~~~", text, re.DOTALL)
        self.assertGreaterEqual(len(examples), 7)
        for example in examples:
            if "|| exit 1" not in example:
                continue
            self.assertIn("if (\n", example)
            self.assertIn("\n); then\n", example)
            self.assertIn("\nelse\n", example)
            self.assertTrue(example.rstrip().endswith("\nfi"))
            self.assertLess(example.index("if (\n"), example.index("|| exit 1"))
            self.assertLess(example.rindex("|| exit 1"), example.index("\n); then\n"))

    def test_no_external_mutation_in_source_review_checkpoint(self):
        from kingdoms.wslpe_fast_track_resume import resume_position
        source = (ROOT / "scripts/wslpe-fast-track-20.py").read_text()
        self.assertIn('if not args.execute:', source)
        self.assertIn('load_private_checkpoint(', source)
        self.assertIn('"validate", "vulnerable"', source)
        self.assertIn('"validate", "clean"', source)
        for unsafe in ('os.system(', 'shell=True', 'vagrant destroy',
                       'vmrun stop', 'nft flush'):
            self.assertNotIn(unsafe, source)

if __name__ == "__main__":
    unittest.main()
