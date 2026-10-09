"""Static regression guards for the Course 1 SQL linked-server audit."""

from pathlib import Path
import re
import subprocess
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

    def test_remote_proof_requires_actual_result_row(self):
        self.assertIn("OPENQUERY([BRAAVOS]", self.queries)
        self.assertIn("KINGDOMS_LOCAL_PROOF_OK", self.queries)
        self.assertIn("KINGDOMS_REMOTE_PROOF_OK", self.queries)
        self.assertIn("^[[:space:]]*KINGDOMS_REMOTE_PROOF_OK[[:space:]]", self.script)
        self.assertIn("client_rc", self.script)


if __name__ == "__main__":
    unittest.main()
