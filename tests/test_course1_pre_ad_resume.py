"""Read-only first-NORTH-playbook recovery tests; no VMware or Ansible calls."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from goad.course1_pre_ad_resume import (
    EXPECTED_GUESTS, PreADResumeError, assert_pre_ad_north_resume,
)


class FakeProvider:
    lab_name = "NORTH"
    goad_nomad_windows = ["GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"]
    def __init__(self, path):
        self.path = str(path)
        self.mode = "unknown"
        self.running = list(EXPECTED_GUESTS)
    def get_runtime_mode(self):
        return self.mode
    def _running_instance_vms(self):
        return self.running
    def _vmx_path(self, name):
        p = Path(self.path) / ".vagrant" / "machines" / name / "vmware_desktop" / "id"
        return p.read_text().strip() if p.is_file() else None


class PreADResumeGateTests(unittest.TestCase):
    manifest = ["build.yml", "ad-servers.yml", "ad-parent_domain.yml"]

    def fixture(self, root):
        instance = Path(root) / "93fd1b-north-vmware"
        provider_path = instance / "provider"
        provider_path.mkdir(parents=True)
        instance.joinpath("instance.json").write_text(json.dumps({
            "id": instance.name, "lab": "NORTH",
            "provider": "vmware", "status": "ready for provisioning",
        }))
        timings = instance / "install-timings"
        timings.mkdir()
        timings.joinpath("20261023T174252Z-e02fef706132.json").write_text(json.dumps({
            "status": "failed", "provider_success": True,
            "ansible_phases": [{
                "label": "Provisioning management-plane preparation",
                "outcome": "failed", "kind": "phase",
            }],
        }))
        for name in EXPECTED_GUESTS:
            machine = provider_path / ".vagrant" / "machines" / name / "vmware_desktop" / "UUID"
            machine.mkdir(parents=True)
            vmx = machine / "guest.vmx"
            vmx.write_text("encoding = UTF-8")
            machine.parent.joinpath("id").write_text(str(vmx))
        return FakeProvider(provider_path), instance, timings

    def test_exact_oct23_initial_failure_can_prepare_first_playbook(self):
        with TemporaryDirectory() as root:
            provider, instance, _ = self.fixture(root)
            result = assert_pre_ad_north_resume(provider, self.manifest, "build.yml")
            self.assertEqual(len(result), 2)

    def test_block_unsupported_mode_lab_or_playbook(self):
        with TemporaryDirectory() as root:
            provider, instance, _ = self.fixture(root)
            for name, attr, value in (
                ("wrong lab", "lab_name", "GOAD"),
                ("already provisioning", "mode", "provisioning"),
                ("exercise mode", "mode", "exercise"),
            ):
                with self.subTest(case=name):
                    old = getattr(provider, attr)
                    setattr(provider, attr, value)
                    with self.assertRaises(PreADResumeError):
                        assert_pre_ad_north_resume(provider, self.manifest, "build.yml")
                    setattr(provider, attr, old)
            with self.assertRaises(PreADResumeError):
                assert_pre_ad_north_resume(provider, self.manifest, "ad-servers.yml")
            with self.assertRaises(PreADResumeError):
                assert_pre_ad_north_resume(provider, ["ad-servers.yml"], "ad-servers.yml")

    def test_block_wrong_instance_or_metadata_status(self):
        with TemporaryDirectory() as root:
            provider, instance, _ = self.fixture(root)
            p = instance / "instance.json"
            valid = json.loads(p.read_text())
            for key, change in (
                ("lab", "GOAD"),
                ("id", "another-north-vmware"),
                ("provider", "virtualbox"),
                ("status", "installed"),
                ("status", "not provided"),
            ):
                with self.subTest(field=key, value=change):
                    p.write_text(json.dumps({**valid, key: change}))
                    with self.assertRaises(PreADResumeError):
                        assert_pre_ad_north_resume(provider, self.manifest, "build.yml")
            p.write_text(json.dumps(valid))

    def test_reject_completed_playbook_and_ambiguous_receipts(self):
        with TemporaryDirectory() as root:
            provider, instance, timings = self.fixture(root)
            path = next(timings.glob("*.json"))
            correct = json.loads(path.read_text())
            for corrupted in (
                {**correct, "provider_success": False},
                {**correct, "status": "completed"},
                {**correct, "ansible_phases": []},
                {**correct, "ansible_phases": [
                    correct["ansible_phases"][0],
                    {"label": "Playbook build.yml", "outcome": "succeeded"},
                ]},
                {**correct, "ansible_phases": [{
                    "label": "Provisioning management-plane preparation",
                    "outcome": "succeeded",
                }]},
            ):
                with self.subTest(receipt=corrupted):
                    path.write_text(json.dumps(corrupted))
                    with self.assertRaises(PreADResumeError):
                        assert_pre_ad_north_resume(provider, self.manifest, "build.yml")
            path.write_text(json.dumps(correct))
            other = timings / "another.json"
            other.write_text(json.dumps(correct))
            with self.assertRaises(PreADResumeError):
                assert_pre_ad_north_resume(provider, self.manifest, "build.yml")

    def test_missing_or_unrelated_guest_blocks_without_provision(self):
        with TemporaryDirectory() as root:
            provider, instance, _ = self.fixture(root)
            vm = provider._vmx_path("GOAD-WS01")
            Path(vm).unlink()
            with self.assertRaises(PreADResumeError):
                assert_pre_ad_north_resume(provider, self.manifest, "build.yml")
            Path(vm).write_text("encoding = UTF-8")
            provider.running = [n for n in provider.running if n != "GOAD-WS01"]
            with self.assertRaises(PreADResumeError):
                assert_pre_ad_north_resume(provider, self.manifest, "build.yml")

    def test_symlink_guest_or_receipt_blocks(self):
        with TemporaryDirectory() as root:
            provider, instance, timings = self.fixture(root)
            receipt = next(timings.glob("*.json"))
            real = timings / "real"
            receipt.rename(real)
            receipt.symlink_to(real)
            with self.assertRaises(PreADResumeError):
                assert_pre_ad_north_resume(provider, self.manifest, "build.yml")


if __name__ == "__main__":
    unittest.main()
