"""Offline tests of the exact, read-only WSLPE40 staging failure auditor."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("wslpe40_stage_audit",ROOT/"scripts/wslpe40-stage-audit.py")
assert SPEC and SPEC.loader
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

def good(**extra):
    exact=[{"name":name,"present":False,"linked":False,"size":0,"sha256":""}
           for name in MODULE.NAMES]
    data={"machine":"WSLPE-WS01","token_elevated_admin":True,
          "library_acl_protected":True,"rpc_host_count":0,
          "exact_files":exact,"partial_files":[]}
    data.update(extra)
    return (MODULE.MARKER+json.dumps(data)+"\n").encode()

class StageAuditTests(unittest.TestCase):
    def test_accepts_exact_read_only_evidence(self):
        d=MODULE.parse_record(good())
        self.assertEqual(len(d["exact_files"]),3)
        self.assertTrue(d["token_elevated_admin"])
        self.assertEqual(d["rpc_host_count"],0)

    def test_rejects_ambiguous_or_invalid_evidence(self):
        invalid=(good()+good(),good(machine="GOAD-WS01"),
                 good(token_elevated_admin="true"),
                 good(library_acl_protected="yes"),
                 good(rpc_host_count=-1),good(exact_files=[]),
                 good(partial_files=[{"target":"OTHER","size":1,"linked":False,
                                      "directory":False}]))
        for case in invalid:
            with self.subTest(case=case[:50]),self.assertRaises(ValueError):
                MODULE.parse_record(case)

    def test_read_only_exact_guest_no_command_execution(self):
        ps=MODULE.READ_ONLY
        for token in ("Get-LocalUser","Get-Acl","Get-FileHash",
                      "Get-CimInstance","Win32_Process","WSLPE-WS01",
                      "Kingdom40LocalRpcServer.exe","token_elevated_admin",
                      "WSLPE40_STAGE_AUDIT_JSON="):
            self.assertIn(token,ps)
        for banned in ("Set-Acl","New-Item","Remove-Item","Start-Process",
                       "Stop-Process","Invoke-Expression","Set-LocalUser",
                       "msiexec","Register-PSSessionConfiguration"):
            self.assertNotIn(banned,ps)

    def test_pinned_tls_and_no_sensitive_logging(self):
        text=(ROOT/"scripts/wslpe40-stage-audit.py").read_text(encoding="utf-8")
        self.assertIn('server_cert_validation="validate"',text)
        self.assertIn("auth.scoped_wslpe_resolution(address)",text)
        self.assertNotIn("server_cert_validation=\"ignore\"",text)
        self.assertNotIn("print(password)",text)
        self.assertNotIn("print(user)",text)

if __name__=="__main__":
    unittest.main()
