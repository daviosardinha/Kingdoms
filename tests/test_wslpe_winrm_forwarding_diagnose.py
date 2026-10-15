"""Fixture tests for the read-only WSLPE WinRM forwarding diagnostic."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/wslpe-winrm-forwarding-diagnose.py"
SPEC = importlib.util.spec_from_file_location("wslpe_forwarding_diag", SOURCE)
assert SPEC and SPEC.loader
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)


class WslpeForwardingDiagnosticTests(unittest.TestCase):
    def test_find_exact_port_without_confusing_remote_endpoint(self):
        text = (
            "LISTEN 0 4096 0.0.0.0:55985 0.0.0.0:*\n"
            "LISTEN 0 4096 127.0.0.1:55986 0.0.0.0:*\n"
        )
        result = DIAG.matching_listeners(text, 55985)
        self.assertEqual(len(result), 1)
        self.assertIn("0.0.0.0:55985", result[0])

    def test_recognize_safe_loopback_scope_including_ipv6(self):
        text = (
            "LISTEN 0 128 127.0.0.1:55985 0.0.0.0:*\n"
            "LISTEN 0 128 [::1]:55985 [::]:*\n"
        )
        self.assertEqual(len(DIAG.matching_listeners(text, 55985)), 2)
        self.assertEqual(DIAG.matching_listeners(text, 5985), [])

    def test_only_forwarding_network_source_lines_are_printed(self):
        raw = '''config.winrm.password = "SECRET_DO_NOT_PRINT"
target.vm.network :forwarded_port, guest: 5985, host: 55985, host_ip: "127.0.0.1", id: "winrm"
target.vm.network :private_network, ip: "172.28.231.31"
'''
        result = DIAG.vagrant_winrm_declarations(raw)
        self.assertEqual(len(result), 1)
        self.assertIn("host_ip:", result[0])
        self.assertNotIn("SECRET_DO_NOT_PRINT", "\n".join(result))

    def test_ss_inspection_never_modifies_vmware_or_reloads_vagrant(self):
        from types import SimpleNamespace
        result = SimpleNamespace(
            returncode=0,
            stdout="LISTEN 0 128 0.0.0.0:55985 0.0.0.0:* users:((\"vmware\",pid=100,fd=5))",
            stderr="",
        )
        with patch.object(DIAG.subprocess, "run", return_value=result) as invoke:
            lines = DIAG.get_listeners(55985)
        self.assertEqual(len(lines), 1)
        invoke.assert_called_once()
        self.assertEqual(invoke.call_args.args[0], ["ss", "-H", "-ltnp"])
        self.assertFalse(invoke.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
