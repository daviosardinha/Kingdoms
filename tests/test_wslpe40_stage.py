"""Source-only tests for the TLS-pinned, copy-only WSLPE40 runtime handoff."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("wslpe40_staging",ROOT/"scripts/wslpe40-stage.py")
assert SPEC and SPEC.loader
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

def baseline(**values):
    d={k:False for k in (
        "library_linked","rpc_fixture_present","rpc_proof_present",
        "rpc_operator_staged","rpc_server_staged","rpc_client_staged",
        "rpc_fixture_linked","rpc_proof_linked")}
    d.update({"jea_endpoint_count":1,"jea_module_present":True,
        "library_present":True,"library_acl_protected":True,"rpc_host_count":0})
    d.update(values)
    return d

class StageContractTests(unittest.TestCase):
    def test_clean_is_accepted_and_existing_state_refused(self):
        MODULE.ensure_safe_guest(baseline())
        for bad in ({"jea_endpoint_count":0},{"rpc_host_count":1},
                    {"rpc_fixture_present":True},{"rpc_server_staged":True},
                    {"library_acl_protected":False},{"rpc_proof_linked":True}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                MODULE.ensure_safe_guest(baseline(**bad))

    def test_exact_provenance_and_fixed_paths(self):
        self.assertEqual(MODULE.REPO,"daviosardinha/Kingdoms")
        self.assertEqual(MODULE.BRANCH,"feature/windows-lpe-45-batch")
        self.assertEqual(MODULE.SNAPSHOT,"KINGDOMS-WSLPE-PRE-LPE40-20261018")
        self.assertEqual(MODULE.PIN,"C773EC26D02940F559FE715B83628FEDAE2AA92D")
        self.assertEqual(MODULE.EXPECTED["transport"],"ncalrpc")
        self.assertEqual(set(MODULE.NAME_MAP),{
            "Kingdom40LocalRpcServer.exe","Kingdom40LocalRpcClient.exe"})

    def test_failed_winrm_step_keeps_only_fixed_status_and_step_id(self):
        class Failure:
            status_code = 1
            std_out = b""
            std_err = b"UNSAFE-SENSITIVE-REMOTE-ERROR"
        class Remote:
            def run_ps(self, source):
                return Failure()
        with self.assertRaisesRegex(
            ValueError,
            r"^Guest rejected stage step: APPEND_WSLPE40RPCOPERATOR_PSM1_CHUNK_1 \\(status=1\\)$",
        ) as error:
            MODULE.ps_checked(Remote(), "$null=1",
                              step="APPEND_WSLPE40RPCOPERATOR_PSM1_CHUNK_1")
        self.assertNotIn("UNSAFE-SENSITIVE", str(error.exception))
        with self.assertRaisesRegex(ValueError, "Unsafe stage identifier"):
            MODULE.ps_checked(Remote(), "$null=1", step="stage-unsafe")

    def test_winrm_transport_failure_reports_only_class(self):
        class Remote:
            def run_ps(self, source):
                raise RuntimeError("secret remote connection details")
        with self.assertRaisesRegex(
            ValueError,
            r"^WinRM transport rejected stage step: APPEND_TEST_CHUNK_1 \\(RuntimeError\\)$",
        ) as error:
            MODULE.ps_checked(Remote(), "$null=1", step="APPEND_TEST_CHUNK_1")
        self.assertNotIn("secret", str(error.exception))

    def test_no_unreviewed_guest_action_or_tls_bypass(self):
        source=(ROOT/"scripts/wslpe40-stage.py").read_text(encoding="utf-8")
        for required in (
            "server_cert_validation=\"validate\"",
            "auth.scoped_wslpe_resolution(address)",
            "preflight.query(auth,address,cert,user,password)",
            "run_data.get(\"conclusion\")!=\"success\"",
            "server_sha256","client_sha256",
            "STAGE WSLPE40 SOURCE ONLY",
            "FileMode]::CreateNew",
            "WSLPE40_SOURCE_STAGED=TRUE",
        ):
            self.assertIn(required,source)
        for forbidden in (
            "server_cert_validation=\"ignore\"",
            "Unregister-PSSessionConfiguration",
            "Register-PSSessionConfiguration",
            "Start-Process",
            "Stop-Process",
            "RpcServerListen(",
            "GOAD-WS01",
            "Set-LocalUser",
        ):
            self.assertNotIn(forbidden,source)

if __name__=="__main__":
    unittest.main()
