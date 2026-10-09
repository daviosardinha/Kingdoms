"""Static regression guards for the Course 1 SQL linked-server audit."""

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-course1-mssql-readonly.sh"
QUERIES = ROOT / "scripts/mssql/course1-linked-readonly.sql"


class Course1MssqlReadonlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.queries = QUERIES.read_text(encoding="utf-8")

    def test_shell_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_queries_are_fixed_read_only_statements(self):
        statements = [s.strip() for s in self.queries.splitlines()
                      if s.strip() and not s.lstrip().startswith("--")]
        self.assertGreaterEqual(len(statements), 5)
        self.assertTrue(all(s.endswith(";") for s in statements))
        self.assertTrue(all(re.match(r"^(SELECT|EXEC master\.dbo\.sp_enum_oledb_providers\b)", s, re.I)
                            for s in statements))
        self.assertNotRegex(self.queries, r"(?im)^\s*(?:INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|MERGE|TRUNCATE|GRANT|REVOKE|DENY|BACKUP|RESTORE)\b")

    def test_no_direct_connection_to_essos_or_admin_secrets(self):
        self.assertNotIn("10.4.30.23", self.script)
        self.assertNotIn("/p:vagrant", self.script)
        self.assertNotIn("ADMINISTRATOR", self.script.upper())
        self.assertIn("NORTH/jon.snow@", self.script)
        self.assertIn("-windows-auth", self.script)

    def verify_fixture(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "sql.log"
            fixture.write_text(text, encoding="utf-8")
            return subprocess.run(
                ["bash", str(SCRIPT), "--verify-log", str(fixture)],
                capture_output=True,
                text=True,
            )

    def test_impacket_bytes_representation_is_accepted(self):
        text = (
            "SQL> SELECT 'KINGDOMS_LOCAL_PROOF_OK' AS Probe;\n"
            " b'KINGDOMS_LOCAL_PROOF_OK'  CASTELBLACK\\\\SQLEXPRESS  NORTH\\\\jon.snow  1\n"
            "SQL> SELECT 'KINGDOMS_REMOTE_PROOF_OK' AS Probe FROM OPENQUERY(...);\n"
            " b'KINGDOMS_REMOTE_PROOF_OK' BRAAVOS\\\\SQLEXPRESS sa 1\n"
        )
        result = self.verify_fixture(text)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("BRAAVOS OPENQUERY returned a remote SQL result row", result.stdout)

    def test_plain_text_rows_are_accepted(self):
        result = self.verify_fixture(
            "KINGDOMS_LOCAL_PROOF_OK CASTELBLACK\\\\SQLEXPRESS\n"
            "KINGDOMS_REMOTE_PROOF_OK BRAAVOS\\\\SQLEXPRESS sa 1\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_echoed_sql_does_not_count_as_evidence(self):
        result = self.verify_fixture(
            "SQL> SELECT 'KINGDOMS_LOCAL_PROOF_OK' AS Probe;\n"
            "SQL> SELECT 'KINGDOMS_REMOTE_PROOF_OK' AS Probe FROM OPENQUERY(...);\n"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_only_local_proof_does_not_pass(self):
        result = self.verify_fixture(
            " b'KINGDOMS_LOCAL_PROOF_OK' CASTELBLACK\\\\SQLEXPRESS\n"
            "SQL> SELECT 'KINGDOMS_REMOTE_PROOF_OK' AS Probe FROM OPENQUERY(...);\n"
            "[*] ERROR(BRAAVOS): Line 1: Linked server unavailable\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BRAAVOS linked-server query did not return", result.stderr)

    def test_remote_proof_requires_actual_result_row(self):
        self.assertIn("OPENQUERY([BRAAVOS]", self.queries)
        self.assertIn("KINGDOMS_LOCAL_PROOF_OK", self.queries)
        self.assertIn("KINGDOMS_REMOTE_PROOF_OK", self.queries)
        self.assertIn("b'KINGDOMS_REMOTE_PROOF_OK'", self.script)
        self.assertIn("client_rc", self.script)


if __name__ == "__main__":
    unittest.main()
