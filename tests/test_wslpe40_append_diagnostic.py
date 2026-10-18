"""Offline fail-closed checks for the non-writing WSLPE40 first-chunk probe."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("appendprobe",ROOT/"scripts/wslpe40-append-diagnostic.py")
assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

def evidence(**values):
    data={
        "machine":"WSLPE-WS01","orphan_count":1,"before_bytes":0,
        "after_bytes":0,"can_reopen_write":False,
        "open_failure":"UnauthorizedAccessException","open_hresult":-2147024891,
        "base64_decode_ok":True
    }
    data.update(values)
    return (MOD.MARKER+json.dumps(data)+"\n").encode()

class AppendDiagnosticTests(unittest.TestCase):
    def test_expected_permission_rejection_is_reportable(self):
        self.assertEqual(MOD.parse(evidence())["before_bytes"],0)
        self.assertFalse(MOD.parse(evidence())["can_reopen_write"])

    def test_rejects_modified_or_malformed_evidence(self):
        for case in (
            evidence()+evidence(),
            evidence(machine="GOAD-WS01"),
            evidence(orphan_count=2),
            evidence(before_bytes=1),
            evidence(after_bytes=1),
            evidence(can_reopen_write="false"),
            evidence(open_failure="ArbitraryException"),
            evidence(can_reopen_write=True),
            evidence(open_hresult="0"),
        ):
            with self.subTest(case=case[:50]),self.assertRaises(ValueError):
                MOD.parse(case)

    def test_classified_guest_failure_is_bounded_and_not_raw_error(self):
        valid = {
            "phase":"FILE_OPEN",
            "exception_type":"MethodInvocationException",
            "hresult":-2146233087,
        }
        raw=(MOD.FAILURE_MARKER+json.dumps(valid)+"\n").encode()
        self.assertEqual(MOD.parse_failure(raw), valid)
        invalid = (
            raw+raw,
            (MOD.FAILURE_MARKER+json.dumps({**valid,"phase":"NORTH"})).encode(),
            (MOD.FAILURE_MARKER+json.dumps({**valid,"exception_type":"Bad/path"})).encode(),
            (MOD.FAILURE_MARKER+json.dumps({**valid,"hresult":"access denied"})).encode(),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate[:50]),self.assertRaises(ValueError):
                MOD.parse_failure(candidate)

    def test_nonwriting_powershell_has_fixed_phase_error_envelope(self):
        ps=MOD.REMOTELY_NONWRITING
        for item in (
            "$diagPhase='IDENTITY'",
            "$diagPhase='LIBRARY'",
            "$diagPhase='ORPHAN'",
            "$diagPhase='FILE_OPEN'",
            "$diagPhase='EMIT'",
            "WSLPE40_APPEND_FAILURE_JSON=",
            "exception_type=$kind",
            "hresult=[int]$_.Exception.HResult",
        ):
            self.assertIn(item,ps)
        code=(ROOT/"scripts/wslpe40-append-diagnostic.py").read_text("utf-8")
        self.assertIn("recovery.validate_audit(audit.parse_record(after.std_out))",code)
        self.assertIn("[PASS] Postdiagnostic zero-byte orphan still unchanged",code)
        self.assertNotIn("print(response.std_err)",code)

    def test_nonzero_winrm_status_preserves_structured_remote_failure(self):
        class Result:
            status_code=1
            std_out=(MOD.FAILURE_MARKER+json.dumps({
                "phase":"FILE_OPEN","exception_type":"MethodInvocationException",
                "hresult":-2146233087})+"\n").encode()
            std_err=b"private domain credential should never appear"
        kind,details=MOD.classify_remote_response(Result())
        self.assertEqual(kind,"classified_failure")
        self.assertEqual(details["phase"],"FILE_OPEN")
        self.assertNotIn("private",str(details))

    def test_nonzero_winrm_without_marker_reports_only_bounded_metadata(self):
        class Result:
            status_code=1
            std_out=b"some remote secret"
            std_err=(b"error with secret\\r\\n"+
                     b"FullyQualifiedErrorId : RuntimeException\\r\\n")
        kind,details=MOD.classify_remote_response(Result())
        self.assertEqual(kind,"unclassified_failure")
        self.assertEqual(details["status"],1)
        self.assertEqual(details["error_id"],"RuntimeException")
        self.assertNotIn("secret",str(details))

    def test_no_unsafe_remote_mutation_and_exact_owned_file(self):
        ps=MOD.REMOTELY_NONWRITING
        for item in (
            "WSLPE-WS01","AreAccessRulesProtected","Wslpe40RpcOperator",
            "orphan_count=1","can_reopen_write","FileMode]::Open",
            "IO.FileAccess]::Write","Write-Output","Base64String('QUJD')",
            "Kingdom40LocalRpcServer.exe",
        ):
            self.assertIn(item,ps)
        for bad in (
            "CreateNew","AppendAll","WriteAll","Remove-Item","Set-Content",
            ".Write(","Start-Process","Stop-Process","Set-Acl",
            "Invoke-Expression","msiexec","GOAD-WS01",
        ):
            self.assertNotIn(bad,ps)

    def test_source_only_reuses_pinned_winrm_and_zero_file_audit(self):
        source=(ROOT/"scripts/wslpe40-append-diagnostic.py").read_text("utf-8")
        for required in (
            "stage.local_source_head()","stage.verify_vm_snapshot(preflight)",
            "recovery.validate_audit(audit.parse_record(before.std_out))",
            "recovery.validate_audit(audit.parse_record(after.std_out))",
            "stage.managed_session(auth,address,cert,user,password)",
            "NO FILE CONTENT WRITES",
        ):
            self.assertIn(required,source)

if __name__=="__main__":
    unittest.main()
