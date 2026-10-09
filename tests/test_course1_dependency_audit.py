"""Regression tests for credential-safe Course 1 dependency audit."""
import tempfile
import unittest
from pathlib import Path

from goad import course1_dependency_audit as audit


class Course1DependencyAuditTests(unittest.TestCase):
    def test_runtime_files_get_expected_priority(self):
        self.assertEqual(audit.classify("scripts/lab-mode.sh"),
                         "P0_MODE_AND_ROUTER")
        self.assertEqual(audit.classify("goad/instance.py"),
                         "P0_INSTALLER_BINDING")
        self.assertEqual(audit.classify("goad/provider/vagrant/vmware_kingdoms.py"),
                         "P0_VMWARE_LIFECYCLE")

    def test_sample_classification_counts_without_content_exposure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "scripts").mkdir()
            (root / "goad").mkdir()
            (root / "ansible").mkdir()
            (root / "scripts/lab-mode.sh").write_text(
                "10.4.10.11 vmnet10 GOAD-DC03 very-secret-password",
                encoding="utf-8"
            )
            (root / "ansible/roles").mkdir()
            (root / "ansible/roles/dummy.yml").write_text(
                "10.4.10.11", encoding="utf-8"
            )
            (root / "goad/instance.py").write_text(
                "all good", encoding="utf-8"
            )
            found = audit.collect(root)
            self.assertEqual([row["path"] for row in found],
                             ["scripts/lab-mode.sh", "ansible/roles/dummy.yml"])
            self.assertEqual(found[0]["references"]["reference_ipv4"], 1)
            self.assertEqual(found[0]["references"]["reference_vmnet"], 1)
            self.assertEqual(found[0]["references"]["essos_guests"], 1)
            text = str(audit.report(root))
            self.assertNotIn("very-secret-password", text)
            self.assertNotIn("10.4.10.11", text)
            self.assertNotIn("vmnet10", text)

    def test_no_mutation_or_remote_access(self):
        source = Path(audit.__file__).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "vmrun", "vagrant up", "os.system",
                          "Path.write_text", "ansible-playbook"):
            self.assertNotIn(forbidden, source)
        self.assertFalse(audit.report()["deployment_authorized"])


if __name__ == "__main__":
    unittest.main()
