"""No-guest regression tests for source-pinned 25/36/38 artifact handoff."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest
import tempfile
import hashlib

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/wslpe45-stage-native-batch.py"
spec=importlib.util.spec_from_file_location("stage_all_native",SCRIPT)
assert spec and spec.loader
MOD=importlib.util.module_from_spec(spec)
spec.loader.exec_module(MOD)

class NativeBatchStageTests(unittest.TestCase):
    def test_exact_allowlist_and_not_native_execution(self):
        self.assertEqual(len(MOD.SOURCE_MAP)+sum(len(t) for t in MOD.ARTIFACTS.values()),8)
        self.assertEqual(
            set(MOD.ARTIFACTS["wslpe36-38-native-source-review-"]),
            {"Kingdom36WmiProvider.exe","Kingdom38DcomServer.exe",
             "Kingdom38DcomClient.exe"}
        )
        self.assertEqual(MOD.DEST,r"C:\ProgramData\KingdomsWSLPE45\lib")
        self.assertIn("WSLPE-WS01",MOD.REMOTE_GUARD)
        self.assertIn("Win32_ComputerSystem",MOD.REMOTE_GUARD)
        self.assertIn("AreAccessRulesProtected",MOD.REMOTE_GUARD)
        self.assertIn("Kingdom40LocalRpcServer.exe",MOD.REMOTE_GUARD)
        for forbidden in ("Start-Process","Remove-Item","Set-Acl",
                          "msiexec","reg.exe","New-Service"):
            self.assertNotIn(forbidden,MOD.REMOTE_GUARD)

    def test_native_archive_flat_layout_matches_strict_stage_inventory(self):
        workflow=(ROOT/".github/workflows/wslpe-45-batch-source.yml").read_text("utf-8")
        self.assertIn("wslpe36-38-flat/",workflow)
        self.assertIn("Flattened native artifact digest mismatch",workflow)
        self.assertIn("Expected four flat native artifact leaves",workflow)
        self.assertIn("Copy-Item -LiteralPath $manifest",workflow)
        # Do not reintroduce mixed-root upload-artifact paths. They cause
        # wslpe40-midl/ nested zip members rejected before guest contact.
        block=workflow.split(
            "      - name: Archive unqualified WSLPE36 WMI and WSLPE38 DCOM binaries",
            1)[1].split("      - name:",1)[0]
        self.assertIn("wslpe36-38-flat/",block)
        self.assertNotIn("wslpe40-midl/",block)

    def test_provenance_parser_rejects_duplicates_and_malformed_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"proof.txt"
            p.write_text("commit=abc\ncommit=def\n")
            with self.assertRaises(ValueError): MOD.manifest(p)
            p.write_text("novalue\n")
            with self.assertRaises(ValueError): MOD.manifest(p)
            p.write_text("commit=abc\nstate=unqualified-not-deployable\n")
            self.assertEqual(MOD.manifest(p)["commit"],"abc")

    def test_source_is_copy_only_and_requires_explicit_flag(self):
        s=SCRIPT.read_text("utf-8")
        for key in ("stage.local_source_head()",
                    "stage.verify_vm_snapshot(pre)",
                    "auth.checked_certificate(auth.tls_audit_module(),stage.PIN)",
                    "stage.managed_session(auth,addr,cert,user,password)",
                    "if not args.apply:",
                    "Source/artifact retrieval",
                    "FileMode]::CreateNew",
                    "Get-FileHash -LiteralPath",
                    "NO AUTOMATIC RETRY"):
            self.assertIn(key,s)
        for bad in ("input(", "sys.stdin", "subprocess.Popen", "Start-Process",
                    "Stop-Process", "Invoke-Expression", "New-Service",
                    "Register-ScheduledTask", "Set-Acl", "Remove-Item"):
            self.assertNotIn(bad,s)

    def test_reject_existing_native_partial_before_creation(self):
        class Session:
            calls=[]
        class Stage:
            WINRM_CHUNK_BYTES=512
            calls=[]
            def ps_checked(self,session,source,step):
                self.calls.append((step,source))
                if step=="CREATE_WSLPE45_NATIVE":
                    raise ValueError("Refused existing temp")
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"Kingdom38DcomClient.exe"
            file.write_bytes(b"PE-test")
            stage=Stage()
            with self.assertRaises(ValueError):
                MOD.staged(Session(),stage,file.name,file)
            self.assertEqual(len(stage.calls),1)
            self.assertIn("*.wslpe45-native-*",stage.calls[0][1])

if __name__ == "__main__":
    unittest.main()
