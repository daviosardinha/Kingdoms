"""NORTH fifth installation cleanup diagnostic is strictly observational."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from goad.course1_direct_winrm import NorthGuestRecoveryBlocked
from scripts.diagnostics import diagnose_north_dc02_bootstrap as diag


class FifthDC02DiagnosticTests(unittest.TestCase):
    def test_probe_pins_target_and_contains_no_mutating_commands(self):
        self.assertEqual(diag.INSTANCE, "bb3baf-north-vmware")
        self.assertEqual(diag.MACHINE, "GOAD-DC02")
        source = diag.READONLY_SCRIPT.lower()
        for prohibited in (
            "remove-item", "start-process", "set-net", "new-net",
            "restart-", "stop-service", "start-service",
            "shutdown.exe", "invoke-expression", "add-net",
            "powershell.exe -file", "winrm quickconfig",
        ):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, source)
        self.assertIn("get-filehash", source)
        self.assertIn("get-netadapter", source)
        self.assertIn("get-netroute", source)

    def test_port_is_advisory_not_authorization(self):
        with patch.object(diag.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout="5985 (guest) => 2201 (host)\n"
        )):
            self.assertEqual(diag.forwarded_winrm_port(Path("/tmp")), 2201)
        with patch.object(diag.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout="5985 (guest) => 2201 (host)\n5985 (guest) => 55985 (host)"
        )):
            self.assertIsNone(diag.forwarded_winrm_port(Path("/tmp")))

    def test_probe_requires_exact_authenticated_identity_and_never_replays(self):
        guest = {"address": "10.4.10.11", "gateway": "10.4.10.1"}
        inventory = '{"KingdomsStageFiles":[],"Hostname":"VAGRANT"}'
        with patch.object(diag, "owned_guest", return_value=(
            Path("/owned/WindowsServer2019.vmx"), guest,
            {"ethernet0.generatedaddress": "00:0c:29:01:02:03"}
        )) as owned, patch.object(diag, "prove_guest", return_value=(
            object(), "192.168.213.134", guest
        )) as proof, patch.object(diag, "forwarded_winrm_port", return_value=2201), \
             patch.object(diag, "_run", side_effect=[
                 inventory, "NORTH_DIRECT_FIRST_BOOT_READY"
             ]) as run:
            result = diag.probe()
        self.assertEqual(result["Instance"], diag.INSTANCE)
        self.assertTrue(result["CanonicalFirstBootReady"])
        self.assertFalse(result["StateChangesAttempted"])
        self.assertFalse(result["SourceScriptsReplayed"])
        owned.assert_called_once()
        proof.assert_called_once()
        self.assertEqual(run.call_count, 2)

    def test_unknown_staged_script_identity_blocks_diagnostic(self):
        guest = {"address": "10.4.10.11", "gateway": "10.4.10.1"}
        inventory = '{"KingdomsStageFiles":[{"Name":"not-owned.ps1","Sha256":"ABC"}]}'
        with patch.object(diag, "owned_guest", return_value=(
            Path("/owned/WindowsServer2019.vmx"), guest, {}
        )), patch.object(diag, "prove_guest", return_value=(
            object(), "192.168.213.134", guest
        )), patch.object(diag, "forwarded_winrm_port", return_value=2201), \
             patch.object(diag, "_run", return_value=inventory), \
             self.assertRaises(NorthGuestRecoveryBlocked):
            diag.probe()


if __name__ == "__main__":
    unittest.main()
