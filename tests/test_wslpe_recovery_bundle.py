"""WSLPE recovery bundle tests: disposable private file and in-memory VMX only."""
from dataclasses import replace
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kingdoms.wslpe_exact_restore import prepare_plan
from kingdoms.wslpe_recovery_bundle import (
    encode_bundle, decode_bundle, write_private_bundle, read_private_bundle,
)

SAMPLE = (
    'ethernet0.present = "TRUE"\n'
    'ethernet0.connectionType = "nat"\n'
    'ethernet0.generatedAddress = "00:0c:29:01:bb:77"\n'
    'ethernet1.present = "TRUE"\n'
    'ethernet1.connectionType = "custom"\n'
    'ethernet1.vnet = "vmnet2"\n'
    'ethernet1.generatedAddress = "00:0c:29:01:bb:81"\n'
)


class WslpeRecoveryBundleTests(unittest.TestCase):
    @unittest.skipIf(os.geteuid() == 0, "nonroot VMware owner required")
    def test_exact_original_and_candidate_survive_private_roundtrip(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            vmx = base / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            plan = prepare_plan(vmx, vmx, "vmnet2", os.geteuid())
            folder = base / "approved"
            folder.mkdir(mode=0o700)
            path = folder / "recovery.json"
            write_private_bundle(path, plan)
            recovered = read_private_bundle(
                path, registered_vmx=vmx, owner_uid=os.geteuid())
            self.assertEqual(recovered, plan)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(vmx.read_text(), SAMPLE)
            with self.assertRaises(ValueError):
                write_private_bundle(path, plan)

    @unittest.skipIf(os.geteuid() == 0, "nonroot VMware owner required")
    def test_mismatch_and_modified_manifest_fail_closed(self):
        with TemporaryDirectory() as tmp:
            vmx = Path(tmp) / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            plan = prepare_plan(vmx, vmx, "vmnet2", os.geteuid())
            raw = encode_bundle(plan)
            decoded = decode_bundle(raw, registered_vmx=vmx, owner_uid=os.geteuid())
            self.assertEqual(decoded, plan)
            other = Path(tmp) / "foreign.vmx"
            other.write_text(SAMPLE)
            with self.assertRaises(ValueError):
                decode_bundle(raw, registered_vmx=other, owner_uid=os.geteuid())
            with self.assertRaises(ValueError):
                decode_bundle(raw, registered_vmx=vmx, owner_uid=os.geteuid()+1)
            record = json.loads(raw)
            record["candidate_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                decode_bundle(json.dumps(record).encode(), registered_vmx=vmx,
                              owner_uid=os.geteuid())
            with self.assertRaises(ValueError):
                encode_bundle(replace(plan, candidate=b"tampered"))

    @unittest.skipIf(os.geteuid() == 0, "nonroot VMware owner required")
    def test_refuse_insecure_storage_and_symlinks(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            vmx = base / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            plan = prepare_plan(vmx, vmx, "vmnet2", os.geteuid())
            folder = base / "too_open"
            # The consolidated launcher sets umask 077, so mkdir(0755)
            # alone creates a secure 0700 directory. Force the actual
            # prohibited permissions and assert the negative fixture.
            folder.mkdir(mode=0o700)
            folder.chmod(0o755)
            self.assertEqual(folder.stat().st_mode & 0o777, 0o755)
            with self.assertRaises(ValueError):
                write_private_bundle(folder / "recovery.json", plan)
            self.assertFalse((folder / "recovery.json").exists())
            folder.chmod(0o700)
            target = folder / "a.json"
            target.write_text("foreign")
            (folder / "recovery.json").symlink_to(target)
            with self.assertRaises(ValueError):
                write_private_bundle(folder / "recovery.json", plan)
            with self.assertRaises(ValueError):
                read_private_bundle(folder / "recovery.json",
                                    registered_vmx=vmx, owner_uid=os.geteuid())
            self.assertEqual(target.read_text(), "foreign")

    @unittest.skipIf(os.geteuid() == 0, "nonroot VMware owner required")
    def test_reader_refuses_permissions_changed_after_bundle_creation(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            vmx = base / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            plan = prepare_plan(vmx, vmx, "vmnet2", os.geteuid())
            folder = base / "approved"
            folder.mkdir(mode=0o700)
            path = folder / "recovery.json"
            write_private_bundle(path, plan)

            folder.chmod(0o755)
            self.assertEqual(folder.stat().st_mode & 0o777, 0o755)
            with self.assertRaises(ValueError):
                read_private_bundle(path, registered_vmx=vmx,
                                    owner_uid=os.geteuid())

            folder.chmod(0o700)
            path.chmod(0o644)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            with self.assertRaises(ValueError):
                read_private_bundle(path, registered_vmx=vmx,
                                    owner_uid=os.geteuid())

            path.chmod(0o600)
            self.assertEqual(read_private_bundle(
                path, registered_vmx=vmx, owner_uid=os.geteuid()), plan)

    def test_untrusted_payload_schema_and_owner_fail_closed(self):
        with TemporaryDirectory() as tmp:
            vmx = Path(tmp) / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            for payload in (b"not-json", b"{}", b"{\"format\":\"wrong\"}"):
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):
                        decode_bundle(payload, registered_vmx=vmx, owner_uid=1000)
            with self.assertRaises(ValueError):
                decode_bundle(b"{}", registered_vmx=vmx, owner_uid=0)


if __name__ == "__main__":
    unittest.main()
