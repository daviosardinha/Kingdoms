"""Offline contract tests for independent #40 artifact/guest verification."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=spec_from_file_location("wslpe40_poststage",
    ROOT/"scripts/wslpe40-poststage-verify.py")
assert SPEC and SPEC.loader
MOD=module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

NAMES=("Wslpe40RpcOperator.psm1","Kingdom40LocalRpcServer.exe",
       "Kingdom40LocalRpcClient.exe")

def state(**changes):
    d={
        "machine":"WSLPE-WS01",
        "domain_joined":False,"learner_standard":True,"winrm_running":True,
        "jea_endpoint_count":1,"jea_module_present":True,
        "library_present":True,"library_acl_protected":True,"library_linked":False,
        "rpc_fixture_present":False,"rpc_fixture_linked":False,
        "rpc_proof_present":False,"rpc_proof_linked":False,
        "rpc_operator_staged":True,"rpc_server_staged":True,
        "rpc_client_staged":True,"rpc_host_count":0,
    }
    d.update(changes)
    return d

def inventory(**changes):
    d={"token_elevated_admin":True,"library_acl_protected":True,
       "rpc_host_count":0,"partial_files":[],
       "exact_files":[{"name":n,"present":True,"linked":False,
                       "size":200,"sha256":"A"*64} for n in NAMES]}
    d.update(changes)
    return d

class PoststageTests(unittest.TestCase):
    def test_accept_exact_native_staging(self):
        MOD.validate_runtime(state(),inventory(),{n:"A"*64 for n in NAMES})

    def test_fail_closed_guest_and_protection_mismatches(self):
        for bad in (
            {"jea_endpoint_count":0},{"learner_standard":False},
            {"rpc_host_count":1},{"library_acl_protected":False},
            {"rpc_fixture_present":True},{"rpc_server_staged":False},
            {"rpc_client_staged":False},{"rpc_operator_staged":False},
        ):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                MOD.validate_runtime(state(**bad),inventory(),
                                     {n:"A"*64 for n in NAMES})

    def test_fail_closed_provenance_or_transfer_mismatches(self):
        baseline={n:"A"*64 for n in NAMES}
        cases=(
            inventory(partial_files=[{"target":NAMES[0]}]),
            inventory(token_elevated_admin=False),
            inventory(exact_files=[]),
            inventory(exact_files=[{"name":n,"present":True,"linked":False,
                                   "size":200,"sha256":"B"*64} for n in NAMES]),
        )
        for sample in cases:
            with self.subTest(sample=sample),self.assertRaises(ValueError):
                MOD.validate_runtime(state(),sample,baseline)

    def test_read_only_and_pinned_build_guards(self):
        src=(ROOT/"scripts/wslpe40-poststage-verify.py").read_text("utf-8")
        for fragment in (
            "stage.verify_vm_snapshot(pre)","stage.local_source_head()",
            "stage.evidence_from_runner(args.run_id,sha,Path(temp))",
            "stage.managed_session(auth,address,certificate,user,password)",
            "response=session.run_ps(audit.READ_ONLY)",
            '"git","diff","--quiet",sha,"HEAD"',
            "if response.status_code!=0:",
            "WSLPE40_INDEPENDENT_POSTSTAGE_VERIFIED=TRUE",
        ):
            self.assertIn(fragment,src)
        for disallowed in (
            "Stop-Process","Start-Process","Set-Acl","Invoke-Wslpe40RpcOperator",
            " --stage"," --recover","server_cert_validation=\"ignore\"",
            "exit 1","set -e",
        ):
            self.assertNotIn(disallowed,src)

if __name__=="__main__":
    unittest.main()
