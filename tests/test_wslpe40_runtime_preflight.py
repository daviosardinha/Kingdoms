"""Offline-only tests for pinned WSLPE40 read-only guest baseline."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/wslpe40-runtime-preflight.py"
SPEC=importlib.util.spec_from_file_location("wslpe40_runtime_preflight",SOURCE)
assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

def record(**changes):
    data={
        "machine":"WSLPE-WS01",
        "domain_joined":False,
        "learner_standard":True,
        "winrm_running":True,
        "jea_endpoint_count":1,
        "jea_module_present":True,
        "library_present":True,
        "library_acl_protected":True,
        "library_linked":False,
        "rpc_fixture_present":False,
        "rpc_fixture_linked":False,
        "rpc_proof_present":False,
        "rpc_proof_linked":False,
        "rpc_operator_staged":False,
        "rpc_server_staged":False,
        "rpc_client_staged":False,
        "rpc_host_count":0,
    }
    data.update(changes)
    return (MOD.MARKER+json.dumps(data)+"\n").encode()

class Wslpe40RuntimePreflightTests(unittest.TestCase):
    def test_accepts_only_exact_guest_and_standard_learner(self):
        evidence=MOD.parse_evidence(record())
        self.assertTrue(evidence["learner_standard"])
        self.assertFalse(evidence["rpc_fixture_present"])
        self.assertEqual(evidence["jea_endpoint_count"],1)

    def test_refuses_wrong_guest_or_privileged_learner(self):
        for case in (
            {"machine":"NORTH"},
            {"domain_joined":True},
            {"learner_standard":False},
            {"winrm_running":False},
            {"jea_endpoint_count":2},
            {"rpc_host_count":-1},
        ):
            with self.subTest(case=case),self.assertRaises(ValueError):
                MOD.parse_evidence(record(**case))

    def test_rejects_corrupted_or_duplicate_evidence(self):
        with self.assertRaises(ValueError):
            MOD.parse_evidence(record()+record())
        with self.assertRaises(ValueError):
            MOD.parse_evidence(b"WSLPE40_RUNTIME_PREFLIGHT_JSON={}")
        with self.assertRaises(ValueError):
            MOD.parse_evidence(record(rpc_host_count="0"))

    def test_guest_query_has_no_mutating_operations(self):
        source=MOD.READ_ONLY
        for token in (
            "WSLPE-WS01","lpe.trainee","Kingdoms45JEA",
            "Get-LocalUser","Get-PSSessionConfiguration","Get-Service",
            "Get-CimInstance","Get-Item","Get-Acl",
            "Kingdom40LocalRpcServer.exe",MOD.MARKER,
        ):
            self.assertIn(token,source)
        for token in (
            "Set-Acl","New-Item","Remove-Item","Stop-Process",
            "Start-Process","Register-PSSessionConfiguration",
            "Unregister-PSSessionConfiguration","Restart-Service",
            "Enable-LocalUser","Disable-LocalUser","msiexec",
            "ncacn_ip_tcp","GOAD-WS01",
        ):
            self.assertNotIn(token,source)

if __name__=="__main__":
    unittest.main()
