"""WSLPE recovery timer: digest pin, owner, exact VMX and no-default-write tests."""
from hashlib import sha256
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from kingdoms.wslpe_exact_restore import prepare_plan
from kingdoms.wslpe_recovery_bundle import encode_bundle, write_private_bundle
from kingdoms.wslpe_rollback_worker import (
    check_pinned_digest, validated_recovery_plan, recover_from_pinned_bundle
)
from kingdoms.wslpe_rollback_timer_plan import make_timer_preview, approve_arming

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-p1c-rollback-worker.py"
SPEC = importlib.util.spec_from_file_location("wslpe_rollback_cli", SCRIPT)
assert SPEC and SPEC.loader
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)

SAMPLE = (
    'displayName = "WSLPE-WS01"\n'
    'ethernet0.present = "TRUE"\n'
    'ethernet0.connectionType = "nat"\n'
    'ethernet0.generatedAddress = "00:0c:29:01:bb:77"\n'
    'ethernet1.present = "TRUE"\n'
    'ethernet1.connectionType = "custom"\n'
    'ethernet1.vnet = "vmnet2"\n'
    'ethernet1.generatedAddress = "00:0c:29:01:bb:81"\n'
)

def dummy_stage(vmx):
    return SimpleNamespace(
        WORKSPACE=vmx.parent,
        find_instance=lambda _path: ("wslpe-only", {"lab": "WSLPE"}),
        locate_registered_vm=lambda _instance: vmx,
    )

class WslpeRollbackTimerTests(unittest.TestCase):
    def test_sha256_pin_rejects_malformed(self):
        self.assertEqual(check_pinned_digest("f" * 64), "f" * 64)
        for bad in ("F" * 64, "deadbeef", None, "z" * 64):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check_pinned_digest(bad)

    @unittest.skipIf(os.geteuid() == 0, "requires nonroot VMware owner")
    def test_owner_signed_source_pin_verifies_exact_registered_vmx(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            vmx = base / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            plan = prepare_plan(vmx, vmx, "vmnet2", os.geteuid())
            private = base / "private"
            private.mkdir(mode=0o700)
            bundle = private / "recovery.json"
            write_private_bundle(bundle, plan)
            digest = sha256(bundle.read_bytes()).hexdigest()
            verified, registered = validated_recovery_plan(
                bundle=bundle, digest=digest, stage=dummy_stage(vmx),
                vmx_owner=os.geteuid())
            self.assertEqual(verified, plan)
            self.assertEqual(registered, vmx)
            with self.assertRaises(ValueError):
                validated_recovery_plan(
                    bundle=bundle, digest="0"*64, stage=dummy_stage(vmx),
                    vmx_owner=os.geteuid())
            foreign = base / "GOAD-WS01.vmx"
            foreign.write_text(SAMPLE)
            with self.assertRaises(ValueError):
                validated_recovery_plan(
                    bundle=bundle, digest=digest, stage=dummy_stage(foreign),
                    vmx_owner=os.geteuid())
            stage = dummy_stage(vmx)
            stage.find_instance = lambda path: (None, {"lab": "NORTH"})
            with self.assertRaises(ValueError):
                validated_recovery_plan(
                    bundle=bundle, digest=digest, stage=stage,
                    vmx_owner=os.geteuid())

    @unittest.skipIf(os.geteuid() == 0, "requires nonroot VMware owner")
    def test_default_recovery_worker_performs_vmrun_list_only(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            vmx = base / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            plan = prepare_plan(vmx, vmx, "vmnet2", os.geteuid())
            private = base / "private"
            private.mkdir(mode=0o700)
            bundle = private / "recovery.json"
            write_private_bundle(bundle, plan)
            vmrun = base / "vmrun"
            vmrun.write_text("fixture")
            vmrun.chmod(0o700)
            calls = []
            def runner(argv, **kwargs):
                calls.append(argv)
                return SimpleNamespace(
                    returncode=0, stdout=f"Total running VMs: 1\n{vmx}\n"
                )
            result = recover_from_pinned_bundle(
                bundle=bundle, digest=sha256(bundle.read_bytes()).hexdigest(),
                stage=dummy_stage(vmx), vmrun=str(vmrun),
                owner=os.geteuid(), authorized=False, runner=runner)
            self.assertEqual(result, "VERIFIED_RUNNING")
            self.assertEqual(calls, [[str(vmrun), "-T", "ws", "list"]])
            self.assertEqual(vmx.read_bytes(), plan.original)

    def test_timer_plan_fails_closed_and_does_not_arm(self):
        args = dict(
            owner="stark", vmx=Path("/tmp/wslpe/windows_10.vmx"),
            bundle=Path("/tmp/wslpe/private/recovery.json"),
            pin="a" * 64, python=Path("/usr/bin/python3"),
            worker=Path("/tmp/wslpe/rollback-worker.py"),
            unit="kingdoms-wslpe-restore-0123456789abcdef",
        )
        plan = make_timer_preview(**args)
        self.assertFalse(plan.arm_authorized)
        self.assertIn("--on-active=240s", plan.argv)
        self.assertIn("--property=User=stark", plan.argv)
        self.assertEqual(plan.argv[-1], "--restore")
        for bad in (
            {"owner": "root space"},
            {"vmx": Path("/tmp/NORTH/windows_10.vmx") / "x"},
            {"bundle": Path("/tmp/wslpe/foreign.json")},
            {"pin": "broken"},
            {"unit": "arbitrary.service"},
            {"delay_seconds": 60},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                make_timer_preview(**(args | bad))

    def test_timer_release_requires_all_independent_evidence(self):
        keys = dict(
            boot_guard_reboot_verified=True,
            management_return_route_verified=True,
            exact_workstation_vm_owner_verified=True,
            recovery_live_test_verified=True,
            host_l2_isolation_verified=True,
        )
        self.assertEqual(approve_arming(**keys), [])
        keys["host_l2_isolation_verified"] = False
        self.assertEqual(len(approve_arming(**keys)), 1)

    def test_local_development_cannot_promote_learner_isolation(self):
        base = dict(
            boot_guard_reboot_verified=True,
            management_return_route_verified=True,
            exact_workstation_vm_owner_verified=True,
            recovery_live_test_verified=True,
            host_l2_isolation_verified=False,
        )
        self.assertEqual(
            approve_arming(**base, deployment_scope="local_dev"), [])
        self.assertEqual(len(approve_arming(
            **base, deployment_scope="learner")), 1)
        self.assertEqual(len(approve_arming(**base)), 1)
        with self.assertRaises(ValueError):
            approve_arming(**base, deployment_scope="NORTH")
        unsafe = dict(base, boot_guard_reboot_verified=False)
        self.assertTrue(approve_arming(**unsafe, deployment_scope="local_dev"))

    def test_restore_cli_requires_armed_systemd_context_before_vmware_calls(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import sys
        for invocation in ("", "spoofed-host-unit"):
            with self.subTest(invocation=invocation), patch.dict(os.environ, {
                "INVOCATION_ID": invocation,
                "KINGDOMS_WSLPE_ROLLBACK_ENABLED": "TRUE"
            }), patch.object(sys, "argv", [
                "rollback.py", "--bundle", "/tmp/example/recovery.json",
                "--approved-sha256", "f"*64, "--restore"
            ]), patch.object(CLI, "stage_module") as stage, redirect_stdout(StringIO()):
                self.assertEqual(CLI.main(), 1)
                stage.assert_not_called()

if __name__ == "__main__":
    unittest.main()
