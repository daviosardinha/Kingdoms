"""Unit tests for offline-only external Course 1 deployment artifact gates."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/course1/check-rendered-artifacts.py"
SPEC = importlib.util.spec_from_file_location("course1_external_artifacts", MODULE_PATH)
artifact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artifact)


def fixture(*, bad_ws01=False):
    result = {name: {"hosts": sorted(members)}
              for name, members in artifact.EXPECTED.items()}
    result["default"] = {"hosts": sorted(artifact.REQUIRED_DEFAULT)}
    result["_meta"] = {"hostvars": {
        name: {"ansible_host": {"dc01": "10.4.20.10",
                              "dc02": "10.4.10.11",
                              "srv02": "10.4.10.22",
                              "ws01": "10.4.10.31"}[name],
               "ansible_user": "north-user",
               "ansible_password": ("mismatched" if bad_ws01 and name == "ws01"
                                   else "fixture-password")}
        for name in artifact.REQUIRED_DEFAULT}}
    return json.dumps(result)


class ExternalArtifactTests(unittest.TestCase):
    def check(self, kind, *, bad_ws01=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory"
            path.write_text("[domain]\n", encoding="utf-8")
            with patch.object(artifact, "run_checked", return_value=fixture(bad_ws01=bad_ws01)):
                artifact.inventory_check("ansible-inventory", path, kind=kind)

    def test_provisioning_inventory_has_all_required_groups(self):
        self.check("provision")

    def test_post_vagrant_inventory_has_ws01_management(self):
        self.check("post")

    def test_provider_inventory_has_four_hosts(self):
        self.check("provider")

    def test_bad_post_vagrant_credentials_are_rejected(self):
        with self.assertRaisesRegex(artifact.ArtifactError, "credential"):
            self.check("post", bad_ws01=True)

    def test_unexpected_inventory_kind_is_rejected(self):
        with self.assertRaises(artifact.ArtifactError):
            self.check("unknown")

    def test_no_guest_mutation_commands_in_offline_check(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("[ruby, \"-c\",", source)
        self.assertIn('"-i", str(filename), "--list"', source)
        self.assertNotIn('["vagrant", "up"', source)
        self.assertNotIn('["vmrun",', source)
        self.assertNotIn('["ansible-playbook",', source)
        self.assertIn("PREVIEW_ONLY_NOT_INSTALLABLE", source)

    def test_fails_when_parser_reports_error(self):
        with patch.object(artifact.subprocess, "run") as subprocess_run:
            subprocess_run.return_value.returncode = 1
            subprocess_run.return_value.stdout = ""
            subprocess_run.return_value.stderr = "sensitive parser output"
            with self.assertRaisesRegex(artifact.ArtifactError, "Output withheld"):
                artifact.run_checked(["ruby", "-c", "invalid"], timeout=3)


if __name__ == "__main__":
    unittest.main()
