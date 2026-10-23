"""Read-only vmnet4 rollback postmortem guards; no host modification."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/wslpe-vmnet4-postmortem.py"
SPEC = importlib.util.spec_from_file_location("wslpe_vmnet4_postmortem", PATH)
assert SPEC and SPEC.loader
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class PostmortemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "journal.json"
        self.original = hashlib.sha256(b"original").hexdigest()
        self.proposed = hashlib.sha256(b"proposed").hexdigest()
        self.data = {
            "version": 1, "status": "rolled_back",
            "original_sha256": self.original,
            "proposed_sha256": self.proposed,
            "original_b64": "REDACT_ME_I_AM_SENSITIVE",
        }
        self.path.write_text(json.dumps(self.data))
        self.stat = type("Stat", (), {
            "st_uid": 0, "st_mode": stat.S_IFREG | 0o600, "st_nlink": 1
        })()

    def inspect(self, sha=None):
        with mock.patch.object(APP, "_read_regular",
                               return_value=(self.path.read_bytes(), self.stat)):
            return APP.journal_summary(self.path, sha or self.original)

    def test_rolled_back_status_and_original_hash_summarized(self):
        output = self.inspect()
        self.assertEqual(output["status"], "rolled_back")
        self.assertTrue(output["current_matches_original"])
        self.assertFalse(output["current_matches_candidate"])

    def test_original_network_drift_is_reported(self):
        output = self.inspect("0" * 64)
        self.assertFalse(output["current_matches_original"])

    def test_journal_original_bytes_never_disclosed(self):
        output = self.inspect()
        self.assertNotIn("original_b64", output)
        self.assertNotIn("REDACT_ME", str(output))
        self.assertFalse(output["original_failure_captured"])

    def test_missing_journal_is_reported_not_assumed_safe(self):
        self.path.unlink()
        result = APP.journal_summary(self.path, self.original)
        self.assertEqual(result, {"exists": False})

    def test_invalid_status_refused(self):
        self.data["status"] = "arbitrary"
        self.path.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(APP.NetworkTransactionBlocked, "invalid"):
            self.inspect()

    def test_untrusted_journal_permissions_refused(self):
        self.stat.st_mode = stat.S_IFREG | 0o644
        with self.assertRaisesRegex(APP.NetworkTransactionBlocked, "ownership"):
            self.inspect()

    def test_postmortem_has_no_write_or_vmware_action(self):
        source = PATH.read_text()
        for forbidden in ("vmware-networks", ".recover()", ".apply(",
                          "_atomic_replace(", "os.unlink(", "os.replace(",
                          "vmrun stop", "vmrun start"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
