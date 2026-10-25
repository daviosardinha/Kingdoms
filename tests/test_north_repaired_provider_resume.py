"""One-shot repaired NORTH provider → first build.yml pre-AD resume.

Source-only tests. All VMware guest, router and WinRM proof calls are mocked.
"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from goad.course1_pre_ad_resume import (
    EXPECTED_GUESTS, PreADResumeError, REPAIRED_PROVIDER_INSTANCE,
    REPAIRED_PROVIDER_ATTEMPT, REPAIRED_PROVIDER_RESUME_MARKER,
    assert_repaired_provider_north_resume, consume_repaired_provider_resume,
)
from goad.course1_direct_winrm import NorthGuestRecoveryBlocked

ROOT = Path(__file__).resolve().parents[1]
MODULE = "goad.course1_direct_winrm.prove_canonical_guest"


class FakeProvider:
    lab_name = "NORTH"
    goad_nomad_windows = ["GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"]

    def __init__(self, provider):
        self.path = str(provider)
        self.mode = "unknown"
        self.running = list(EXPECTED_GUESTS)

    def get_runtime_mode(self):
        return self.mode

    def _running_instance_vms(self):
        return self.running

    def _vmx_path(self, name):
        marker = Path(self.path) / ".vagrant/machines" / name / "vmware_desktop/id"
        return marker.read_text().strip() if marker.is_file() else None


class RepairedProviderResumeTests(unittest.TestCase):
    manifest = ["build.yml", "ad-servers.yml", "ad-parent_domain.yml"]

    def fixture(self, tmp):
        instance = Path(tmp) / REPAIRED_PROVIDER_INSTANCE
        provider = instance / "provider"
        provider.mkdir(parents=True)
        meta = instance / "instance.json"
        meta.write_text(json.dumps({
            "id": REPAIRED_PROVIDER_INSTANCE, "lab": "NORTH",
            "provider": "vmware", "status": "not provided"
        }))
        receipts = instance / "install-timings"
        receipts.mkdir()
        receipt_path = receipts / (REPAIRED_PROVIDER_ATTEMPT + ".json")
        receipt_path.write_text(json.dumps({
            "attempt_id": REPAIRED_PROVIDER_ATTEMPT,
            "instance_id": REPAIRED_PROVIDER_INSTANCE,
            "status": "failed", "provider_success": False, "ansible_phases": [],
            "phases": [
                {"label": "GOAD-ROUTER bring-up", "outcome": "succeeded"},
                {"label": "Vagrant first creation GOAD-WS01", "outcome": "succeeded"},
                {"label": "GOAD-WS01 VMware Tools / forwarded WinRM readiness",
                 "outcome": "succeeded"},
            ],
        }))
        for name in EXPECTED_GUESTS:
            guest = provider / ".vagrant/machines" / name / "vmware_desktop"
            guest.mkdir(parents=True)
            vmx = guest / "original.vmx"
            vmx.write_text("displayName = \"original\"\n")
            (guest / "id").write_text(str(vmx))
        return FakeProvider(provider), instance, receipt_path

    def test_exact_receipt_all_guests_and_four_authenticated_windows(self):
        with TemporaryDirectory() as tmp:
            provider, _, _ = self.fixture(tmp)
            with patch(MODULE, return_value="192.168.213.133") as proof:
                markers = assert_repaired_provider_north_resume(
                    provider, self.manifest, "build.yml"
                )
            self.assertEqual(len(markers), 3)
            self.assertEqual([c.args[1] for c in proof.call_args_list], [
                "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"
            ])
            self.assertTrue(all(c.kwargs == {"timeout": 45}
                                for c in proof.call_args_list))

    def test_explicit_no_repeat_after_consume(self):
        with TemporaryDirectory() as tmp:
            provider, instance, _ = self.fixture(tmp)
            with patch(MODULE):
                assert_repaired_provider_north_resume(
                    provider, self.manifest, "build.yml"
                )
            self.assertIn("consumed", consume_repaired_provider_resume(provider))
            marker = instance / REPAIRED_PROVIDER_RESUME_MARKER
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
            with patch(MODULE) as proof, self.assertRaises(PreADResumeError):
                assert_repaired_provider_north_resume(
                    provider, self.manifest, "build.yml"
                )
            proof.assert_not_called()
            with self.assertRaises(PreADResumeError):
                consume_repaired_provider_resume(provider)

    def test_reject_non_exact_instance_or_playbook_before_guest_contact(self):
        with TemporaryDirectory() as tmp:
            provider, instance, _ = self.fixture(tmp)
            for bad in ("ad-servers.yml", "ws01.yml"):
                with patch(MODULE) as proof, self.assertRaises(PreADResumeError):
                    assert_repaired_provider_north_resume(provider, self.manifest, bad)
                proof.assert_not_called()
            provider.mode = "exercise"
            with patch(MODULE) as proof, self.assertRaises(PreADResumeError):
                assert_repaired_provider_north_resume(provider, self.manifest, "build.yml")
            proof.assert_not_called()
            provider.mode = "unknown"
            provider.path = str(Path(tmp) / "other-north-vmware" / "provider")
            with patch(MODULE) as proof, self.assertRaises(PreADResumeError):
                assert_repaired_provider_north_resume(provider, self.manifest, "build.yml")
            proof.assert_not_called()

    def test_receipt_or_metadata_tampering_blocks(self):
        with TemporaryDirectory() as tmp:
            provider, instance, receipt_path = self.fixture(tmp)
            original = json.loads(receipt_path.read_text())
            for change in (
                {"provider_success": True}, {"ansible_phases": [{"label": "build.yml"}]},
                {"status": "completed"}, {"attempt_id": "foreign-attempt"},
                {"instance_id": "foreign-north-vmware"},
                {"phases": original["phases"][:-1]},
                {"phases": original["phases"] + [original["phases"][0]]},
            ):
                with self.subTest(change=change):
                    receipt_path.write_text(json.dumps({**original, **change}))
                    with patch(MODULE) as proof, self.assertRaises(PreADResumeError):
                        assert_repaired_provider_north_resume(
                            provider, self.manifest, "build.yml"
                        )
                    proof.assert_not_called()
            receipt_path.write_text(json.dumps(original))
            meta = instance / "instance.json"
            metadata = json.loads(meta.read_text())
            meta.write_text(json.dumps({**metadata, "status": "installed"}))
            with patch(MODULE) as proof, self.assertRaises(PreADResumeError):
                assert_repaired_provider_north_resume(
                    provider, self.manifest, "build.yml"
                )
            proof.assert_not_called()

    def test_missing_guest_or_unready_windows_blocks(self):
        with TemporaryDirectory() as tmp:
            provider, _, _ = self.fixture(tmp)
            provider.running.remove("GOAD-WS01")
            with patch(MODULE) as proof, self.assertRaises(PreADResumeError):
                assert_repaired_provider_north_resume(
                    provider, self.manifest, "build.yml"
                )
            proof.assert_not_called()
            provider.running.append("GOAD-WS01")
            with patch(MODULE, side_effect=[
                "192.168.213.133",
                NorthGuestRecoveryBlocked("Windows Tools unavailable")
            ]) as proof, self.assertRaisesRegex(
                PreADResumeError, "Live canonical guest verification failed: GOAD-DC02"
            ):
                assert_repaired_provider_north_resume(
                    provider, self.manifest, "build.yml"
                )
            self.assertEqual(proof.call_count, 2)

    def test_source_routes_only_this_instance_no_vagrant_replay(self):
        src = (ROOT / "goad_nomad.py").read_text()
        self.assertIn("assert_repaired_provider_north_resume(", src)
        self.assertIn("consume_repaired_provider_resume(provider)", src)
        self.assertLess(
            src.index("consume_repaired_provider_resume(provider)"),
            src.index("result = provisioner.run_from(start_playbook)"),
        )
        self.assertIn("assert_pre_ad_north_resume(", src)
        self.assertIn("result = provisioner.run_from(start_playbook)", src)
        self.assertIn('provider._north_pre_ad_resume_authorized = True', src)


if __name__ == "__main__":
    unittest.main()
