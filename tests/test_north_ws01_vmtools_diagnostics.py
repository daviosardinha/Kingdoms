"""Read-only WS01 VMware Tools diagnostic source checks."""
from pathlib import Path
import importlib.util
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/diagnostics/diagnose-north-ws01-vmtools.py"
SPEC = importlib.util.spec_from_file_location("north_ws01_tools_diag", SCRIPT)
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


class Ws01ToolsIdentityTests(unittest.TestCase):
    def test_forwarded_port_requires_exactly_one_mapping(self):
        self.assertEqual(
            diag.parse_winrm_port("5985 (guest) => 2207 (host)\n"
                                  "5986 (guest) => 2208 (host)\n"), 2207
        )
        for bad in ("", "5985 (guest) => 2207 (host)\n5985 (guest) => 2208 (host)",
                    "5985 (guest) => 80 (host)"):
            with self.subTest(input=bad):
                with self.assertRaises(diag.DiagnosticBlocked):
                    diag.parse_winrm_port(bad)

    def test_missing_tools_is_not_identity_failure(self):
        data = {
            "Hostname": "WIN10",
            "OsCaption": "Microsoft Windows 10 Enterprise Evaluation",
            "Adapters": [
                {"Mac": "000C29991040", "IPv4": ["192.168.213.136"]},
                {"Mac": "005056201031", "IPv4": ["10.4.10.31"]},
            ],
            "ToolsService": [],
            "ToolsExecutableExists": False,
            "ToolsProcessCount": 0,
        }
        values = {"ethernet0.generatedaddress": "00:0c:29:99:10:40"}
        diag.verify_identity(data, values)  # May diagnose missing Tools.

    def test_foreign_forwarded_guest_blocks_without_tools_check(self):
        values = {"ethernet0.generatedaddress": "00:0c:29:99:10:40"}
        data = {
            "Hostname": "WRONG",
            "OsCaption": "Microsoft Windows 10",
            "Adapters": [
                {"Mac": "000C29991040"},
                {"Mac": "005056201022"},
            ],
        }
        with self.assertRaisesRegex(diag.DiagnosticBlocked, "not the exact"):
            diag.verify_identity(data, values)

    def test_orphaned_binary_fingerprint_is_evidence_not_repair_approval(self):
        base = {
            "ToolsService": [],
            "ToolsExecutableExists": True,
            "ToolsProcessCount": 0,
            "InstalledVmwareTools": [],
        }
        self.assertEqual(diag.classify_tools_state(base), "ORPHANED_TOOLS_EXECUTABLE")
        self.assertEqual(diag.classify_tools_state(
            {**base, "ToolsExecutableExists": False}), "FULLY_MISSING_TOOLS")
        self.assertEqual(diag.classify_tools_state(
            {**base, "ToolsService": [{"Name": "VMTools", "State": "Running"}],
             "ToolsProcessCount": 1}), "HEALTHY")
        self.assertEqual(diag.classify_tools_state(
            {**base, "InstalledVmwareTools": ["VMware Tools"]}),
            "PARTIAL_OR_AMBIGUOUS_TOOLS")
        with self.assertRaises(diag.DiagnosticBlocked):
            diag.classify_tools_state({**base, "ToolsProcessCount": None})

    def test_orphaned_tools_forensics_reads_installer_signatures_only(self):
        src = "\n".join((diag.SCRIPT, diag.TOOLS_METADATA_SCRIPT, diag.MSI_EVENTS_SCRIPT))
        for required in (
            "Get-AuthenticodeSignature", "Get-FileHash",
            "VMToolsServiceRegistryKeyPresent",
            "VGAuthServiceRegistryKeyPresent",
            "MsiInstallerInProgressRegistryKeyPresent",
            "MsiExecProcessCount",
            "RecentVmwareInstallerEvents",
            "ToolsBinaryMetadata",
            "MsiInstaller",
        ):
            with self.subTest(required=required):
                self.assertIn(required, src)
        for mutating in (
            "Start-Service", "Stop-Service", "New-Service",
            "Remove-Item", "Set-Item", "Set-Service",
            "Invoke-Expression", "Start-Process",
            "msiexec.exe /", "Win32_Product",
        ):
            with self.subTest(mutating=mutating):
                self.assertNotIn(mutating, src)

    def test_all_winrm_scripts_fit_encoded_windows_command_limit(self):
        for label, script in (
            ("identity", diag.SCRIPT),
            ("binary-and-service-registry", diag.TOOLS_METADATA_SCRIPT),
            ("windows-installer-events", diag.MSI_EVENTS_SCRIPT),
        ):
            with self.subTest(stage=label):
                # WinRM powershell command is base64(UTF-16LE(script)).
                # Reserve headroom for Powershell.exe and pywinrm's wrapper.
                encoded_length = 4 * ((len(script.encode("utf-16le")) + 2) // 3)
                self.assertLess(encoded_length, 7500)
        self.assertNotIn("Get-AuthenticodeSignature", diag.SCRIPT)
        self.assertNotIn("Get-WinEvent", diag.TOOLS_METADATA_SCRIPT)
        self.assertNotIn("Get-NetAdapter", diag.MSI_EVENTS_SCRIPT)

    def test_forensics_queries_run_only_after_exact_identity(self):
        from types import SimpleNamespace
        identity = {
            "Hostname": "VAGRANT-10",
            "OsCaption": "Microsoft Windows 10 Enterprise Evaluation",
            "Adapters": [
                {"Mac": "000C29991040", "IPv4": ["192.168.213.136"]},
                {"Mac": "005056201031", "IPv4": ["10.4.10.31"]},
            ],
            "ToolsService": [],
            "ToolsExecutableExists": True,
            "ToolsProcessCount": 0,
            "InstalledVmwareTools": [],
        }
        values = {"ethernet0.generatedaddress": "00:0c:29:99:10:40"}
        metadata = {
            "ToolsBinaryMetadata": {"Length": 123, "Sha256": "A" * 64},
            "VMToolsServiceRegistryKeyPresent": False,
            "VGAuthServiceRegistryKeyPresent": True,
            "MsiInstallerInProgressRegistryKeyPresent": False,
            "MsiExecProcessCount": 0,
        }
        events = {"RecentVmwareInstallerEvents": []}
        with patch.object(diag, "owned_guest", return_value=(
            Path("/original/windows_10.vmx"), {"address": "10.4.10.31"}, values
        )), patch.object(diag.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout="5985 (guest) => 2203 (host)"
        )), patch.object(diag, "_authenticated_session", return_value=object()), \
             patch.object(diag, "_read_json_winrm", side_effect=[
                 identity, metadata, events
             ]) as fetch, patch("builtins.print"):
            self.assertEqual(diag.main(["--instance", "bb3baf-north-vmware"]), 0)
        self.assertEqual([call.args[1] for call in fetch.call_args_list], [
            diag.SCRIPT, diag.TOOLS_METADATA_SCRIPT, diag.MSI_EVENTS_SCRIPT
        ])

    def test_foreign_identity_blocks_before_additional_forensics(self):
        from types import SimpleNamespace
        bad = {
            "Hostname": "FOREIGN",
            "OsCaption": "Windows 10",
            "Adapters": [{"Mac": "001122334455"}],
        }
        with patch.object(diag, "owned_guest", return_value=(
            Path("/original/windows_10.vmx"), {"address": "10.4.10.31"},
            {"ethernet0.generatedaddress": "00:0c:29:99:10:40"}
        )), patch.object(diag.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout="5985 (guest) => 2203 (host)"
        )), patch.object(diag, "_authenticated_session", return_value=object()), \
             patch.object(diag, "_read_json_winrm", return_value=bad) as fetch:
            with self.assertRaises(diag.DiagnosticBlocked):
                diag.main(["--instance", "bb3baf-north-vmware"])
        self.assertEqual(fetch.call_count, 1)

    def test_winrm_forensic_transport_failure_blocks(self):
        from types import SimpleNamespace
        class BrokenSession:
            def run_ps(self, script):
                raise RuntimeError("transport gone")
        with self.assertRaisesRegex(diag.DiagnosticBlocked, "WinRM transport failed"):
            diag._read_json_winrm(BrokenSession(), diag.TOOLS_METADATA_SCRIPT, "Tools metadata")

    def test_source_does_not_run_guest_repairs(self):
        src = SCRIPT.read_text()
        for marker in ("owned_guest(provider, \"GOAD-WS01\")",
                       "verify_identity(payload, values)",
                       "Get-CimInstance Win32_Service",
                       "Get-NetAdapter", "RecentServiceEvents"):
            self.assertIn(marker, src)
        for prohibited in ("Start-Service", "Stop-Service", "Repair-VM", "Install-WMF",
                           "slmgr.vbs", "Remove-Item ", "Set-NetIPAddress",
                           "vmrun\", \"-T\", \"ws\", \"start"):
            self.assertNotIn(prohibited, src)


if __name__ == "__main__":
    unittest.main()
