"""Offline NORTH DC02 exercise-mode WinRM transport regression."""
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/north-exercise-winrm.py"
LAB = ROOT / "scripts/lab-mode.sh"

spec = importlib.util.spec_from_file_location("north_exercise_winrm", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DirectDc02ModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        workspace = Path(self.temp.name) / "workspace"
        self.p = workspace / "0da0a9-north-vmware" / "provider"
        d = self.p / ".vagrant/machines/GOAD-DC02/vmware_desktop" / "vm"
        d.mkdir(parents=True)
        vmx = d / "windows2019.vmx"
        vmx.write_text("fixture")
        (d.parent / "id").write_text(str(vmx))

    def test_installed_north_vm_identity_is_required(self):
        self.assertEqual(module.validate_provider(str(self.p)), self.p)
        with self.assertRaises(ValueError):
            module.validate_provider(str(self.p.parent))
        with self.assertRaises(ValueError):
            module.run("Write-Output 'OK'", timeout=15,
                       machine="PURPLE-WS01", provider=str(self.p))
        with self.assertRaises(ValueError):
            module.run("Write-Output 'OK'", timeout=15,
                       machine="GOAD-DC01", provider=str(self.p))
        with self.assertRaises(ValueError):
            module.run(" ", timeout=15, machine="GOAD-DC02",
                       provider=str(self.p))
        with self.assertRaises(ValueError):
            module.run("Write-Output 'OK'", timeout=0, machine="GOAD-DC02",
                       provider=str(self.p))

    def test_vmx_foreign_directory_blocked(self):
        pointer = self.p / ".vagrant/machines/GOAD-DC02/vmware_desktop/id"
        external = Path(self.temp.name) / "foreign.vmx"
        external.write_text("foreign")
        pointer.write_text(str(external))
        with self.assertRaises(ValueError):
            module.validate_provider(str(self.p))

    def test_pinned_https_ntlm_and_authenticated_return_code(self):
        session = Mock()
        session.run_ps.return_value = types.SimpleNamespace(
            std_out=b"GOAD_READY\r\n", std_err=b"", status_code=0)
        winrm = types.SimpleNamespace(Session=Mock(return_value=session))
        with patch.dict(sys.modules, {"winrm": winrm}), patch(
                "sys.stdout", new_callable=io.StringIO) as output:
            module.run("Write-Output 'GOAD_READY'", timeout=15,
                       machine="GOAD-DC02", provider=str(self.p))
            self.assertIn("GOAD_READY", output.getvalue())
        args, kw = winrm.Session.call_args
        self.assertEqual(args[0], "https://10.4.10.11:5986/wsman")
        self.assertEqual(kw["auth"], ("vagrant", "vagrant"))
        self.assertEqual(kw["transport"], "ntlm")
        self.assertEqual(kw["server_cert_validation"], "ignore")
        # The 75s NORTH/DC02 probe reuses the already-proven KINGDOMS
        # direct WinRM transport contract: operation 30s, HTTP read 45s.
        with patch.dict(sys.modules, {"winrm": winrm}):
            module.run("Write-Output 'GOAD_READY'", timeout=75,
                       machine="GOAD-DC02", provider=str(self.p))
        _, long_kw = winrm.Session.call_args
        self.assertEqual(long_kw["operation_timeout_sec"], 30)
        self.assertEqual(long_kw["read_timeout_sec"], 45)
        self.assertEqual(session.run_ps.call_args.args[0],
                         "Write-Output 'GOAD_READY'")
        session.run_ps.return_value = types.SimpleNamespace(
            std_out=b"", std_err=b"broken", status_code=1)
        with patch.dict(sys.modules, {"winrm": winrm}), patch(
                "sys.stderr", new_callable=io.StringIO):
            with self.assertRaisesRegex(RuntimeError, "returned 1"):
                module.run("Write-Output 'BAD'", timeout=15,
                           machine="GOAD-DC02", provider=str(self.p))

    def test_mode_controller_only_switches_north_dc02_transport(self):
        script = LAB.read_text()
        helpers = script[script.index("north_direct_dc02_capture()"):
                         script.index("ensure_child_dc_time_ready()")]
        self.assertEqual(helpers.count(
            '    [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]]'),
            1)
        self.assertEqual(helpers.count(
            'if [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]]'),
            2)
        self.assertEqual(helpers.count(
            'timeout "${timeout_seconds}" vagrant winrm "${vm}"'), 2)
        self.assertIn('timeout "${timeout_seconds}" "${python}"', helpers)
        self.assertIn('trap cleanup_runtime_nat EXIT', script)
        self.assertIn('wait_domain_controller_ready "${vm}"', script)
        self.assertIn('ensure_child_dc_time_ready "${vm}"', script)
        self.assertIn('apply_router_policy exercise', script)
        self.assertIn('verify_persistent_state FALSE', script)
        self.assertIn('GOAD_PROVIDER_DIR', script)
        self.assertIn('readonly NORTH_DC02_DIRECT_PROBE_TIMEOUT_SECONDS=75',
                      script)
        for function_name, stop_name in (
            ("ensure_child_dc_time_ready()", "wait_domain_controller_ready()"),
            ("wait_domain_controller_ready()", "wait_domain_member_ready()"),
        ):
            body = script[script.index(function_name):script.index(
                stop_name, script.index(function_name) + len(function_name))]
            self.assertIn(
                'probe_timeout="${NORTH_DC02_DIRECT_PROBE_TIMEOUT_SECONDS}"',
                body,
            )
            self.assertIn(
                'if [[ "${GOAD_LAB_PROFILE}" == NORTH && "${vm}" == GOAD-DC02 ]]',
                body,
            )


if __name__ == "__main__":
    unittest.main()
