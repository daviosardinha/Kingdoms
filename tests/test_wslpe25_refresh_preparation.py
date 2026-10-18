"""Source-only regression for exact WSLPE25 PowerShell 5.1 owned recovery."""
from pathlib import Path
import importlib.util
import unittest
import hashlib

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"scripts/wslpe25-refresh-preparation.py"
spec=importlib.util.spec_from_file_location("wslpe25_source_refresh",P)
assert spec and spec.loader
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Wslpe25SourceRecoveryTests(unittest.TestCase):
    def test_contract_exact_source_only(self):
        self.assertEqual(mod.BASE_COMMIT,"920684e585676b567beb391b74fe373b322e01f3")
        self.assertEqual(mod.RELATIVE,"ansible/files/wslpe45/Wslpe25RepairPreparation.psm1")
        self.assertEqual(mod.CHUNK,512)
        self.assertEqual(mod.sha(b"x"),hashlib.sha256(b"x").hexdigest().upper())
        src=(ROOT/mod.RELATIVE).read_text("utf-8")
        self.assertIn("ValidateSet('Inspect','Prepare','Resume')",src)
        self.assertIn("New-Item -Path $request -ItemType File",src)
        self.assertNotIn("New-Item -LiteralPath $request",src)
        self.assertIn("WSLPE25_FIXTURE_RESUMED=PASS",src)

    def test_guest_guard_requires_exact_owned_marker_only(self):
        x=mod.GUARD
        for token in (
            "WSLPE-WS01", "lpe.trainee", "Get-LocalUser",
            "AreAccessRulesProtected", "Assert",
            ".kingdoms-owned.json","kingdoms.wslpe.fixture-owner.v1",
            "msi_repair_custom_action","Get-ChildItem",
            "WSLPE25_PARTIAL_MARKER_ONLY=PASS"
        ):
            if token=="Assert":
                continue
            self.assertIn(token,x)
        for forbidden in (
            "Remove-Item","New-Item","Set-Acl",
            "Start-Process","New-Service","msiexec /i","msiexec /x"
        ):
            self.assertNotIn(forbidden,x)

    def test_source_refresh_is_not_an_installer(self):
        x=P.read_text("utf-8")
        for token in (
            "stage.local_source_head()","stage.verify_vm_snapshot(pre)",
            "auth.checked_certificate(auth.tls_audit_module(),stage.PIN)",
            "if not args.apply:","[IO.FileMode]::CreateNew",
            "Get-FileHash -LiteralPath",
            "MoveFileExW","WSLPE25_ATOMIC_COMMIT",
            "WSLPE25_PREPARATION_REFRESH=PASS"
        ):
            self.assertIn(token,x)
        for forbidden in (
            "input(", "sys.stdin", "subprocess.Popen",
            "Start-Process","Remove-Item","Set-Acl","New-Service",
            "Register-ScheduledTask"
        ):
            self.assertNotIn(forbidden,x)

    def test_inspect_is_read_only_two_stage(self):
        class Stage:
            def __init__(self):
                self.steps=[]
            def ps_checked(self,session,source,step):
                self.steps.append(step)
                if step=="WSLPE25_OWNED_PARTIAL_GUARD":
                    return "WSLPE25_PARTIAL_MARKER_ONLY=PASS"
                if step=="WSLPE25_OLD_MODULE_HASH":
                    return "WSLPE25_OLD_PREPARATION_HASH=PASS"
                raise AssertionError("Unexpected remote step")
        fake=Stage()
        mod.verify(None,fake,"A"*64)
        self.assertEqual(fake.steps,[
            "WSLPE25_OWNED_PARTIAL_GUARD","WSLPE25_OLD_MODULE_HASH"
        ])

if __name__=="__main__":
    unittest.main()
