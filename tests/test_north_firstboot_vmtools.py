"""NORTH first-boot VMware Tools regression tests.

Purely synthetic inputs. These tests never contact VMware, WinRM or Windows.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from goad.course1_firstboot_vmtools import (
    FIRSTBOOT_INVENTORY,
    NorthFirstbootToolsBlocked,
    classify_firstboot_inventory,
    inspect_firstboot_guest_tools,
)

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_SOURCE = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
VMWARE_SOURCE = ROOT / "goad/provider/vagrant/vmware.py"


def inventory(*, service=None, binary=False, process=0, product=None,
              installing=False, msi=0):
    return {
        "ToolsService": [] if service is None else [
            {"Name": "VMTools", "State": service}
        ],
        "ToolsExecutableExists": binary,
        "ToolsProcessCount": process,
        "InstalledVmwareTools": [] if product is None else [product],
        "InstallerInProgress": installing,
        "MsiExecProcessCount": msi,
        "Windows": True,
        "Hostname": "WINTERFELL",
        "Adapters": [
            {"Mac": "000C29010203", "IPv4": ["192.168.213.133"]},
            {"Mac": "005056201011", "IPv4": []},
        ],
    }


class FirstbootInventoryTests(unittest.TestCase):
    def test_exact_fully_missing_is_only_installable_state(self):
        self.assertEqual(classify_firstboot_inventory(inventory()), "missing")
        self.assertEqual(
            classify_firstboot_inventory(inventory(
                service="Running", binary=True, process=1)),
            "healthy",
        )
        self.assertEqual(
            classify_firstboot_inventory(inventory(
                service="Stopped", binary=True, process=0)),
            "partial",
        )
        self.assertEqual(
            classify_firstboot_inventory(inventory(binary=True)),
            "partial",
        )
        self.assertEqual(
            classify_firstboot_inventory(inventory(product="VMware Tools")),
            "partial",
        )
        self.assertEqual(
            classify_firstboot_inventory(inventory(installing=True)),
            "partial",
        )
        self.assertEqual(
            classify_firstboot_inventory(inventory(msi=1)),
            "partial",
        )

    def test_malformed_inventory_fails_closed(self):
        for record in (None, {}, {"ToolsService": [], "ToolsProcessCount": "0"}):
            with self.subTest(record=record), self.assertRaises(
                    NorthFirstbootToolsBlocked):
                classify_firstboot_inventory(record)

    def test_first_boot_proves_two_macs_not_lab_ip(self):
        record = inventory()
        response = SimpleNamespace(
            status_code=0,
            std_out=json.dumps(record).encode(),
            std_err=b"",
        )
        with patch("goad.course1_firstboot_vmtools.owned_guest",
                   return_value=(
                       Path("/exact/GOAD-DC02.vmx"), {},
                       {"ethernet0.generatedaddress": "00:0c:29:01:02:03"},
                   )) as identity:
            vmx, state = inspect_firstboot_guest_tools(
                Path("/owned/abcdef-north-vmware/provider"),
                "GOAD-DC02",
                Mock(run_ps=Mock(return_value=response)),
            )
        self.assertEqual(state, "missing")
        self.assertEqual(vmx, "/exact/GOAD-DC02.vmx")
        identity.assert_called_once()

    def test_wrong_forwarded_endpoint_cannot_authorize_install(self):
        record = inventory()
        record["Adapters"][0]["Mac"] = "DEADBEEF1234"
        response = SimpleNamespace(
            status_code=0,
            std_out=json.dumps(record).encode(),
            std_err=b"",
        )
        with patch("goad.course1_firstboot_vmtools.owned_guest",
                   return_value=(
                       Path("/original/guest.vmx"), {},
                       {"ethernet0.generatedaddress": "00:0c:29:01:02:03"},
                   )), self.assertRaises(NorthFirstbootToolsBlocked):
            inspect_firstboot_guest_tools(
                Path("/original/provider"), "GOAD-DC02",
                Mock(run_ps=Mock(return_value=response)),
            )

    def test_inventory_does_not_change_windows(self):
        script = FIRSTBOOT_INVENTORY.lower()
        for forbidden in (
            "start-process", "remove-item", "set-service", "start-service",
            "restart-service", "shutdown.exe", "set-netadapter",
            "new-netipaddress", "invoke-expression",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)


def isolated_north_bootstrap():
    tree = ast.parse(PROVIDER_SOURCE.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "GoadKingdomsVmwareProvider")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_north_firstboot_ensure_tools")
    namespace = {"Log": Mock(), "os": os, "subprocess": subprocess,
                 "time": __import__("time")}
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(PROVIDER_SOURCE), "exec"), namespace)
    return namespace["_north_firstboot_ensure_tools"]


class OneShotBootstrapTests(unittest.TestCase):
    def make_provider(self, root):
        provider_path = root / "abcdef-north-vmware" / "provider"
        provider_path.mkdir(parents=True)
        return SimpleNamespace(
            lab_name="NORTH",
            path=str(provider_path),
            _winrm_forwarded_port=Mock(return_value=55895),
            _wait_winrm_ready=Mock(return_value=True),
            _winrm_session=Mock(return_value=object()),
            _install_vmware_tools=Mock(return_value=False),
        )

    def test_healthy_vm_never_installs_or_marks(self):
        with TemporaryDirectory() as tmp:
            provider = self.make_provider(Path(tmp))
            with patch("goad.course1_firstboot_vmtools.inspect_firstboot_guest_tools",
                       return_value=("/original/dc02.vmx", "healthy")):
                self.assertTrue(isolated_north_bootstrap()(
                    provider, "GOAD-DC02"))
            provider._install_vmware_tools.assert_not_called()
            self.assertFalse(list(Path(tmp).rglob("*.attempted")))

    def test_missing_installs_once_and_rechecks_actual_guest(self):
        with TemporaryDirectory() as tmp:
            provider = self.make_provider(Path(tmp))
            inspect = Mock(side_effect=[
                ("/original/dc02.vmx", "missing"),
                ("/original/dc02.vmx", "healthy"),
                ("/original/dc02.vmx", "missing"),
            ])
            with patch("goad.course1_firstboot_vmtools.inspect_firstboot_guest_tools",
                       inspect):
                bootstrap = isolated_north_bootstrap()
                self.assertTrue(bootstrap(provider, "GOAD-DC02"))
                provider._install_vmware_tools.assert_called_once_with(
                    "GOAD-DC02", "/original/dc02.vmx", 55895
                )
                marker = Path(tmp) / "abcdef-north-vmware" / (
                    ".north-firstboot-vmtools-GOAD-DC02.attempted")
                self.assertTrue(marker.exists())
                self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
                self.assertFalse(bootstrap(provider, "GOAD-DC02"))
            provider._install_vmware_tools.assert_called_once()

    def test_partial_or_msi_busy_never_installs(self):
        with TemporaryDirectory() as tmp:
            provider = self.make_provider(Path(tmp))
            with patch("goad.course1_firstboot_vmtools.inspect_firstboot_guest_tools",
                       return_value=("/original/dc02.vmx", "partial")):
                self.assertFalse(isolated_north_bootstrap()(
                    provider, "GOAD-DC02"))
            provider._install_vmware_tools.assert_not_called()
            self.assertFalse(list(Path(tmp).rglob("*.attempted")))

    def test_wrong_vm_target_never_contacts_winrm(self):
        with TemporaryDirectory() as tmp:
            provider = self.make_provider(Path(tmp))
            self.assertFalse(isolated_north_bootstrap()(
                provider, "GOAD-DC03"))
            provider._winrm_forwarded_port.assert_not_called()


class ProviderSourceContracts(unittest.TestCase):
    def test_existing_provider_override_kept_with_north_only_dispatch(self):
        text = PROVIDER_SOURCE.read_text()
        self.assertEqual(
            text.count("    def _ensure_vmware_tools(self, machine):"), 1)
        self.assertEqual(
            text.count("    def _north_firstboot_ensure_tools(self, machine):"), 1)
        self.assertIn("return self._north_firstboot_ensure_tools(machine)", text)
        self.assertIn("if self.lab_name == 'NORTH':", text)
        self.assertIn("super()._ensure_vmware_tools(machine)", text)
        self.assertIn("GOAD_KINGDOMS_GUEST_READY", text)
        self.assertIn("tools_service=$($toolsService)", text)
        self.assertIn("'Missing'", text)

    def test_base_installer_runs_only_setup_on_tools_media(self):
        source = VMWARE_SOURCE.read_text()
        self.assertIn("VolumeName -match '(?i)vmware", source)
        self.assertIn("Ambiguous VMware Tools installation media", source)
        self.assertIn("GOAD_VMTOOLS_POST_SETUP|service=", source)
        self.assertIn("REBOOT=ReallySuppress", source)


if __name__ == "__main__":
    unittest.main()
