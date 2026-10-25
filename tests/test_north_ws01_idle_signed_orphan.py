"""Exact WS01 idle-signed orphan proof and one-shot installer regression."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from goad.course1_tools_transition import (
    WS01_ORPHAN_LENGTH, WS01_ORPHAN_SHA256, WS01_ORPHAN_VERSION,
    WS01_ORPHAN_PROOF, _is_known_idle_signed_ws01_orphan,
    NorthToolsTransitionBlocked, prove_idle_signed_original_ws01_orphan,
)
from tests.test_north_tools_transition import isolated_method


def evidence():
    return {
        "Length": WS01_ORPHAN_LENGTH, "Version": WS01_ORPHAN_VERSION,
        "Sha256": WS01_ORPHAN_SHA256, "SignatureStatus": "Valid",
        "VMToolsServiceRegistryKeyPresent": False,
        "VGAuthServiceRegistryKeyPresent": True,
        "MsiInstallerInProgressRegistryKeyPresent": False,
        "MsiExecProcessCount": 0,
    }


class OrphanProofTests(unittest.TestCase):
    def test_only_exact_authenticated_observed_fingerprint_qualifies(self):
        good = evidence()
        self.assertTrue(_is_known_idle_signed_ws01_orphan(good))
        cases = (
            {"Length": 0}, {"Version": "13.2.0.0"},
            {"Sha256": "0" * 64}, {"SignatureStatus": "NotSigned"},
            {"VMToolsServiceRegistryKeyPresent": True},
            {"VGAuthServiceRegistryKeyPresent": False},
            {"MsiInstallerInProgressRegistryKeyPresent": True},
            {"MsiExecProcessCount": 1},
            {"MsiExecProcessCount": False},
        )
        for changes in cases:
            bad = {**good, **changes}
            with self.subTest(changes=changes):
                self.assertFalse(_is_known_idle_signed_ws01_orphan(bad))
        bad = dict(good)
        bad["Injected"] = "ignore"
        self.assertFalse(_is_known_idle_signed_ws01_orphan(bad))

    def test_guest_proof_requires_original_vmx_and_winrm_success(self):
        data = json.dumps(evidence()).encode()
        session = SimpleNamespace(run_ps=Mock(return_value=SimpleNamespace(
            status_code=0, std_out=data, std_err=b""
        )))
        vmx = "/tmp/owned-ws01.vmx"
        with patch("goad.course1_tools_transition.owned_guest", return_value=(
            Path(vmx), {"address": "10.4.10.31"}, {}
        )):
            self.assertTrue(prove_idle_signed_original_ws01_orphan(
                "/owned/provider", "GOAD-WS01", vmx, session
            ))
            with self.assertRaises(NorthToolsTransitionBlocked):
                prove_idle_signed_original_ws01_orphan(
                    "/owned/provider", "GOAD-DC02", vmx, session
                )
            with self.assertRaises(NorthToolsTransitionBlocked):
                prove_idle_signed_original_ws01_orphan(
                    "/owned/provider", "GOAD-WS01", "/foreign.vmx", session
                )
        self.assertEqual(session.run_ps.call_count, 1)

    def test_script_is_bounded_and_observational(self):
        encoded = 4 * ((len(WS01_ORPHAN_PROOF.encode("utf-16le")) + 2) // 3)
        self.assertLess(encoded, 7500)
        for required in ("Get-AuthenticodeSignature", "Get-FileHash",
                         "MsiExecProcessCount", "MsiInstallerInProgressRegistryKeyPresent"):
            self.assertIn(required, WS01_ORPHAN_PROOF)
        for forbidden in ("Start-Service", "Stop-Service", "Start-Process",
                          "Remove-Item", "Set-Item", "msiexec /", "Win32_Product"):
            self.assertNotIn(forbidden, WS01_ORPHAN_PROOF)

    def test_original_fingerprint_auto_repairs_once_with_fresh_post_identity_proof(self):
        with TemporaryDirectory() as tmp:
            provider = Path(tmp)/"123abc-north-vmware"/"provider"
            provider.mkdir(parents=True)
            runtime = Mock()
            runtime.lab_name = "NORTH"
            runtime.path = str(provider)
            runtime._winrm_forwarded_port.return_value = 2203
            runtime._wait_winrm_ready.return_value = True
            runtime._authenticated_guest_install_ready.return_value = True
            runtime._install_vmware_tools.return_value = False  # VMware VIX IP telemetry failure
            gate = isolated_method("_north_tools_transition_gate", logger=Mock())
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       side_effect=[("/owned/ws01.vmx","partial")]*4 +
                                   [("/owned/ws01.vmx","healthy")]) as inspect, \
                 patch("goad.course1_tools_transition.prove_idle_signed_original_ws01_orphan",
                       return_value=True) as proof, patch("time.sleep"):
                self.assertTrue(gate(runtime, "GOAD-WS01", "post-ws01-eval"))
            self.assertEqual(inspect.call_count, 5)
            proof.assert_called_once()
            runtime._install_vmware_tools.assert_called_once_with(
                "GOAD-WS01", "/owned/ws01.vmx", 2203
            )
            marker = provider.parent / ".north-vmtools-GOAD-WS01-post-ws01-eval.attempted"
            self.assertTrue(marker.exists())
            records = [
                json.loads(line) for line in
                (provider.parent / ".north-install-recovery.jsonl").read_text().splitlines()
            ]
            self.assertIn("VMTOOLS_WS01_SIGNED_IDLE_ORPHAN",
                          [r["signature"] for r in records])
            self.assertIn("VMTOOLS_REPAIR_VERIFIED",
                          [r["signature"] for r in records])
            # Even if the same state reappears, the atomic marker forbids replay.
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       return_value=("/owned/ws01.vmx","partial")), \
                 patch("goad.course1_tools_transition.prove_idle_signed_original_ws01_orphan",
                       return_value=True), patch("time.sleep"):
                self.assertFalse(gate(runtime, "GOAD-WS01", "post-ws01-eval"))
            runtime._install_vmware_tools.assert_called_once()

    def test_idle_orphan_not_authorized_outside_post_eval_ws01(self):
        with TemporaryDirectory() as tmp:
            provider = Path(tmp)/"123abc-north-vmware"/"provider"
            provider.mkdir(parents=True)
            runtime = Mock()
            runtime.lab_name = "NORTH"
            runtime.path = str(provider)
            runtime._winrm_forwarded_port.return_value = 2203
            runtime._wait_winrm_ready.return_value = True
            gate = isolated_method("_north_tools_transition_gate", logger=Mock())
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       return_value=("/owned/ws01.vmx","partial")), \
                 patch("goad.course1_tools_transition.prove_idle_signed_original_ws01_orphan") as proof:
                self.assertFalse(gate(runtime, "GOAD-WS01", "pre-exercise-isolation"))
                self.assertFalse(gate(runtime, "GOAD-SRV02", "pre-exercise-isolation"))
            proof.assert_not_called()
            runtime._install_vmware_tools.assert_not_called()


if __name__ == "__main__":
    unittest.main()
