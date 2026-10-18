"""Offline fail-closed coverage for a single orphaned WSLPE40 transfer file."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "wslpe40_recover_empty",ROOT/"scripts/wslpe40-recover-empty.py")
assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

def evidence(**changes):
    state={
        "token_elevated_admin":True,
        "library_acl_protected":True,
        "rpc_host_count":0,
        "exact_files":[{"present":False} for _ in range(3)],
        "partial_files":[{"target":"Wslpe40RpcOperator.psm1",
                          "size":0,"linked":False,"directory":False}],
    }
    state.update(changes)
    return state

class RecoveryContractTests(unittest.TestCase):
    def test_allows_only_exact_empty_temp_file(self):
        MOD.validate_audit(evidence())
        bad=[
            {"token_elevated_admin":False},
            {"library_acl_protected":False},
            {"rpc_host_count":1},
            {"exact_files":[{"present":True}]},
            {"partial_files":[]},
            {"partial_files":[{"target":"Kingdom40LocalRpcServer.exe",
                               "size":0,"linked":False,"directory":False}]},
            {"partial_files":[{"target":"Wslpe40RpcOperator.psm1",
                               "size":12,"linked":False,"directory":False}]},
            {"partial_files":[{"target":"Wslpe40RpcOperator.psm1",
                               "size":0,"linked":True,"directory":False}]},
            {"partial_files":[{"target":"Wslpe40RpcOperator.psm1",
                               "size":0,"linked":False,"directory":True}]},
            {"partial_files":evidence()["partial_files"]*2},
        ]
        for case in bad:
            with self.subTest(case=case),self.assertRaises(ValueError):
                MOD.validate_audit(evidence(**case))

    def test_exact_windows_guard_and_consent_no_broad_delete(self):
        ps=MOD.RECOVER_ONLY
        for token in (
            "WSLPE-WS01","$machine.PartOfDomain",
            "WindowsBuiltInRole]::Administrator",
            "AreAccessRulesProtected","Get-Item -LiteralPath",
            "Wslpe40RpcOperator[.]psm1[.]wslpe40-stage-[0-9a-f]{24}",
            "$entry.Length -ne 0","$allPartial.Count -ne 1",
            "Kingdom40LocalRpcServer.exe","[IO.File]::Delete($target)",
            "WSLPE40_EMPTY_PARTIAL_REMOVED=PASS",
        ):
            self.assertIn(token,ps)
        for forbidden in (
            "Remove-Item","Get-ChildItem -Recurse","Start-Process",
            "Stop-Process","Invoke-Expression","Set-Acl",
            "Register-PSSessionConfiguration","Unregister-PSSessionConfiguration",
            "GOAD-WS01","exit 1",
        ):
            self.assertNotIn(forbidden,ps)
        code=(ROOT/"scripts/wslpe40-recover-empty.py").read_text(encoding="utf-8")
        self.assertIn("REMOVE WSLPE40 EMPTY PARTIAL",code)
        self.assertIn("stage.verify_vm_snapshot(preflight)",code)
        self.assertIn("stage.ensure_safe_guest(state)",code)
        self.assertIn("auth.checked_certificate(",code)
        self.assertIn("stage.ps_checked(session,RECOVER_ONLY",code)
        self.assertNotIn("server_cert_validation=\"ignore\"",code)

if __name__=="__main__":
    unittest.main()
