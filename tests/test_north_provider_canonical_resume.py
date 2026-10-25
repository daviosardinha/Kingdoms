"""NORTH interrupted-provider resume: canonical guest proof is the only Vagrant skip.

Pure unit tests: no VMware, guest, network or Ansible operations.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch
import unittest

from goad.course1_direct_winrm import (
    NorthGuestIdentityMismatch, NorthGuestRecoveryBlocked,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "goad/provider/vagrant/vmware_kingdoms.py"
)


def isolated_method(name, *, logger=None):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(
        item for item in tree.body
        if isinstance(item, ast.ClassDef)
        and item.name == "GoadKingdomsVmwareProvider"
    )
    method = next(
        item for item in cls.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    ns = {"Log": logger or Mock()}
    exec(
        compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"),
        ns,
    )
    return ns[name]


class CanonicalGuestPreflightTests(unittest.TestCase):
    def setUp(self):
        self.log = Mock()
        self.preflight = isolated_method(
            "_north_existing_canonical_ready", logger=self.log
        )
        self.provider = SimpleNamespace(
            lab_name="NORTH", path="/owned/north/provider",
            _vmx_path=Mock(return_value="/owned/guest.vmx"),
        )

    def test_exact_authenticated_canonical_guest_skips_vagrant(self):
        with patch(
            "goad.course1_direct_winrm.prove_canonical_guest",
            return_value="192.168.213.133",
        ) as proof:
            self.assertIs(
                self.preflight(self.provider, "GOAD-DC01"), True
            )
        proof.assert_called_once_with(
            "/owned/north/provider", "GOAD-DC01", timeout=30
        )
        self.assertEqual(
            self.provider._north_first_boot_nat_addresses,
            {"GOAD-DC01": "192.168.213.133"},
        )

    def test_no_original_registered_vmx_runs_normal_vagrant(self):
        self.provider._vmx_path.return_value = None
        with patch(
            "goad.course1_direct_winrm.prove_canonical_guest"
        ) as proof:
            self.assertIsNone(
                self.preflight(self.provider, "GOAD-DC01")
            )
        proof.assert_not_called()

    def test_unavailable_guest_does_not_skip_vagrant(self):
        with patch(
            "goad.course1_direct_winrm.prove_canonical_guest",
            side_effect=NorthGuestRecoveryBlocked("no direct WinRM"),
        ):
            self.assertIsNone(
                self.preflight(self.provider, "GOAD-DC01")
            )
        self.assertFalse(
            hasattr(self.provider, "_north_first_boot_nat_addresses")
        )

    def test_authenticated_foreign_guest_fails_closed(self):
        with patch(
            "goad.course1_direct_winrm.prove_canonical_guest",
            side_effect=NorthGuestIdentityMismatch("wrong NIC MAC"),
        ):
            self.assertIs(
                self.preflight(self.provider, "GOAD-DC01"), False
            )
        self.assertFalse(
            hasattr(self.provider, "_north_first_boot_nat_addresses")
        )
        self.log.error.assert_called_once()

    def test_not_north_never_probes_guest(self):
        self.provider.lab_name = "GOAD"
        with patch(
            "goad.course1_direct_winrm.prove_canonical_guest"
        ) as proof:
            self.assertIsNone(
                self.preflight(self.provider, "GOAD-DC01")
            )
        self.provider._vmx_path.assert_not_called()
        proof.assert_not_called()


class ProviderInstallResumeTests(unittest.TestCase):
    def setUp(self):
        self.install = isolated_method("install")

    def provider(self, *, preflight):
        runtime = SimpleNamespace(
            lab_name="NORTH",
            path="/owned/north/provider",
            goad_nomad_windows=["GOAD-DC01", "GOAD-DC02"],
            _last_bounded_vagrant_reaped=True,
            command=SimpleNamespace(run_vagrant=Mock(return_value=True)),
            _course1_unwired=Mock(return_value=False),
            prepare_install=Mock(return_value=True),
            _sync_goad_nomad_inventories=Mock(return_value=True),
            _sync_goad_nomad_vagrantfile_compatibility=Mock(return_value=True),
            _bring_up_router=Mock(return_value=True),
            _north_existing_canonical_ready=Mock(side_effect=preflight),
            _north_existing_ws01_orphan_before_vagrant=Mock(return_value=None),
            _north_direct_first_boot_recovery=Mock(return_value=None),
            _ensure_vmware_tools=Mock(return_value=True),
            _recover_failed_windows_vagrant_up=Mock(return_value=True),
            _authenticated_guest_recovery_ready=Mock(return_value=False),
            _enable_provisioning_routes=Mock(return_value=True),
        )
        return runtime

    def test_recovered_dc01_is_not_repeated_and_dc02_still_created(self):
        provider = self.provider(
            preflight=lambda machine: True if machine == "GOAD-DC01" else None
        )
        self.assertTrue(self.install(provider))
        provider.command.run_vagrant.assert_called_once_with(
            ["up", "GOAD-DC02"], provider.path
        )
        provider._ensure_vmware_tools.assert_called_once_with("GOAD-DC02")
        provider._north_direct_first_boot_recovery.assert_not_called()
        provider._enable_provisioning_routes.assert_called_once()

    def test_unready_existing_guest_uses_normal_vagrant(self):
        provider = self.provider(preflight=lambda machine: None)
        self.assertTrue(self.install(provider))
        self.assertEqual(
            provider.command.run_vagrant.call_args_list,
            [call(["up", "GOAD-DC01"], provider.path),
             call(["up", "GOAD-DC02"], provider.path)],
        )
        self.assertEqual(provider._ensure_vmware_tools.call_count, 2)

    def test_mismatched_registered_guest_blocks_other_guest_changes(self):
        provider = self.provider(preflight=lambda machine: False)
        self.assertFalse(self.install(provider))
        provider.command.run_vagrant.assert_not_called()
        provider._ensure_vmware_tools.assert_not_called()
        provider._enable_provisioning_routes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
