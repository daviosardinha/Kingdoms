"""Unit tests for the read-only Windows LPE role dependency inventory."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "windows-lpe-standalone-audit.py"
)


class StandaloneSourceAuditTests(unittest.TestCase):
    def run_audit(self, root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--json", *extra],
            capture_output=True,
            text=True,
            check=False,
        )

    def make_role(self, root: Path, content: str) -> None:
        role = root / "ansible" / "roles" / "windows_lpe" / "defaults"
        role.mkdir(parents=True)
        (role / "main.yml").write_text(content, encoding="utf-8")

    def test_reports_domain_principal_and_learner_without_source_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_role(
                root,
                "target_account: 'NORTH\\rickon.stark'\n"
                "endpoint: '10.4.10.31'\n"
                "domain_name: 'north.sevenkingdoms.local'\n",
            )
            result = self.run_audit(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "source_dependencies_found")
            self.assertEqual(report["files_scanned"], 1)
            self.assertEqual(
                {item["rule"] for item in report["findings"]},
                {"domain_principal", "domain_learner", "north_network", "ad_dns_name"},
            )
            self.assertTrue(
                all(set(item) == {"path", "line", "rule"} for item in report["findings"])
            )
            self.assertNotIn("NORTH\\rickon.stark", result.stdout)

    def test_strict_fails_closed_when_domain_dependency_remains(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_role(root, "domain_username: Administrator\n")
            result = self.run_audit(root, "--strict")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(
                json.loads(result.stdout)["findings"][0]["rule"],
                "domain_configuration",
            )

    def test_clean_source_is_scan_clean_not_runtime_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_role(
                root,
                "# NORTH\\rickon.stark is only in a comment\n"
                "target_account: 'WS01\\lpe.trainee'\n"
                "local_service: 'KingdomUpdaterSvc'\n",
            )
            result = self.run_audit(root, "--strict")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["findings_count"], 0)
            self.assertEqual(report["status"], "source_scan_clean")
            self.assertEqual(report["scope"], "shared_role_source_only")
            self.assertIn("not proof", report["note"])

    def test_missing_role_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_audit(Path(td))
            self.assertEqual(result.returncode, 1)
            self.assertIn("Windows LPE role missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
