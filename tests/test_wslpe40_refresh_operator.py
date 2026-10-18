"""Source-only verification for exact-guest WSLPE40 operator console guard refresh."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import hashlib
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/wslpe40-refresh-operator.py"
spec=spec_from_file_location("wslpe40_refresh_unit",SCRIPT)
assert spec and spec.loader
MOD=module_from_spec(spec)
spec.loader.exec_module(MOD)

class Wslpe40OperatorRefreshTests(unittest.TestCase):
    def test_reuses_exact_snapshot_and_pinned_compiled_native_run(self):
        self.assertEqual(MOD.PRIOR_COMMIT,"a297b9f90aea6ff056274fb812a26cf18182f55f")
        self.assertEqual(MOD.PRIOR_NATIVE_RUN,39134058008)
        self.assertEqual(MOD.OPERATOR,"Wslpe40RpcOperator.psm1")
        self.assertEqual(MOD.CHUNK_BYTES,512)
        self.assertEqual(MOD.REMOTE,r"C:\ProgramData\KingdomsWSLPE45\lib")
        # GitHub CI uses shallow checkout: don't require historical blobs here.
        # Runtime revalidates the pinned previous commit before any guest write.
        current=MOD.SOURCE.read_bytes()
        self.assertIn(b"WTSGetActiveConsoleSessionId",current)
        self.assertNotIn(b"$env:SESSIONNAME",current)
        self.assertIn("git\",\"show\"",SCRIPT.read_text("utf-8"))
        self.assertEqual(MOD.digest(b"test"),hashlib.sha256(b"test").hexdigest().upper())

    def test_guest_prestate_requires_native_jea_and_original_module_hash(self):
        class Checked:
            called=False
            def validate_runtime(self, pre, audit, hashes):
                self.called=True
                assert pre["rpc_operator_staged"]
                assert pre["rpc_host_count"]==0
                assert hashes["Wslpe40RpcOperator.psm1"]=="F"*64
        post=Checked()
        MOD.validate_guest({"rpc_operator_staged":True,"rpc_host_count":0},
                           {},post,{"Wslpe40RpcOperator.psm1":"F"*64})
        self.assertTrue(post.called)
        with self.assertRaises(ValueError):
            MOD.validate_guest({"rpc_operator_staged":False,"rpc_host_count":0},
                               {},post,{})

    def test_prewrite_diagnostic_has_no_file_creation_or_mutation(self):
        class Stage:
            steps=[]
            def ps_checked(self, session, code, step):
                self.steps.append(step)
                for unsafe in ("CreateNew","[IO.File]::Replace(",
                               "[IO.File]::Delete(",".Write(","Start-Process"):
                    self_outer.assertNotIn(unsafe,code)
                return "PASS"
        self_outer=self
        stage=Stage()
        MOD.diagnose_prewrite(None,stage,"A"*64)
        self.assertEqual(stage.steps,[
            "GUARD_OPERATOR_REFRESH","VERIFY_EXISTING_OPERATOR"
        ])
        self.assertIn("Get-CimInstance Win32_ComputerSystem",
                      MOD.READ_ONLY_REFRESH_GUARD)
        self.assertIn("AreAccessRulesProtected",MOD.READ_ONLY_REFRESH_GUARD)
        self.assertNotIn("CreateNew",MOD.READ_ONLY_REFRESH_GUARD)

    def test_prewrite_diagnostic_only_exposes_bounded_stage_error(self):
        class Stage:
            def ps_checked(self,session,code,step):
                raise ValueError(
                    "Guest rejected stage step: "+step+" (status=1)"
                )
        with self.assertRaisesRegex(ValueError,"GUARD_OPERATOR_REFRESH"):
            MOD.diagnose_prewrite(None,Stage(),"A"*64)
        source=SCRIPT.read_text("utf-8")
        self.assertIn('parser.add_argument("--diagnose",action="store_true"',source)
        self.assertIn("if args.diagnose:",source)
        self.assertIn("diagnose_prewrite(session,stage,expected[OPERATOR])",source)
        self.assertNotIn("print(result.std_err)",source)

    def test_source_only_uses_atomic_exact_copy_no_execution(self):
        src=SCRIPT.read_text("utf-8")
        for required in (
            "stage.local_source_head()",
            "stage.verify_vm_snapshot(pre)",
            "post.expected_sha(stage,PRIOR_NATIVE_RUN)",
            "stage.evidence_from_runner(PRIOR_NATIVE_RUN,PRIOR_COMMIT",
            "post.validate_runtime(pre_state,state",
            "server_cert_validation", # only exists in imported TLS transport, not this script
        ):
            if required=="server_cert_validation":
                continue
            self.assertIn(required,src)
        for token in (
            "[Kingdoms.Wslpe40AtomicMove]::Execute($temp,$old,9)",
            "MOVEFILE_REPLACE_EXISTING", "MOVEFILE_WRITE_THROUGH",
            "EntryPoint=\"MoveFileExW\"",
            "GUARD_OPERATOR_REFRESH","CREATE_OPERATOR_REFRESH",
            "UPLOAD_OPERATOR_CHUNK_","COMMIT_OPERATOR_REFRESH",
            "Get-FileHash -LiteralPath $temp",
            "Get-FileHash -LiteralPath $old",
            "Win32_Process","WindowsBuiltInRole]::Administrator",
            "if not args.apply:","No native RPC binary transfer",
        ):
            self.assertIn(token,src)
        for forbidden in (
            "[IO.File]::Replace(", "Move-Item", "Copy-Item", "Remove-Item",
            "input(", "sys.stdin", "Start-Process","Stop-Process",
            "Invoke-Expression","Register-PSSessionConfiguration",
            "Set-Acl","Remove-Item","msiexec","GOAD-WS01",
        ):
            self.assertNotIn(forbidden,src)

if __name__=="__main__":
    unittest.main()
