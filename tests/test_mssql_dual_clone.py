"""Source checks for clone-only dual MSSQL test (does not start any VM)."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/mssql/prove-course1-dual-instance-clone.ps1"
README=ROOT/"scripts/mssql/README-dual-instance-clone.md"

class DualInstanceCloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=SCRIPT.read_text(encoding="utf-8")
        cls.doc=README.read_text(encoding="utf-8")

    def test_clone_guard(self):
        self.assertIn("CloneConfirmed", self.s)
        self.assertIn("Get-NetAdapter", self.s)
        self.assertIn("ABORT: active NIC detected", self.s)

    def test_required_elements(self):
        for s in ("KINGDOMS2","1444","COURSE1_LOW","COURSE1_LINK_ADMIN","OPENQUERY([KINGDOMS2]","sp_addlinkedsrvlogin"):
            self.assertIn(s, self.s)

    def test_no_static_privileged_identity_or_ip(self):
        for s in ("10.4.30.23","10.4.10.11","vagrant:vagrant","NORTH\\sql_svc"):
            self.assertNotIn(s, self.s)

    def test_temp_credential_security(self):
        self.assertIn("SQLCMDPASSWORD", self.s)
        self.assertIn("Random-Password", self.s)
        self.assertIn("Remove-Item -LiteralPath $tmp", self.s)
        self.assertIn("icacls.exe", self.s)

    def test_documentation_warns_of_clone(self):
        self.assertIn("DO NOT EXECUTE ON ORIGINAL", self.doc)
        self.assertIn("BEFORE FIRST START", self.doc)

if __name__=="__main__": unittest.main()
