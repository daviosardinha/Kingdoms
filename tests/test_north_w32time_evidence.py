"""Read-only post-failure W32Time diagnostics never alter VMs or host networking."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/diagnostics/north-installed-time-evidence.py"


class NorthTimeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.source = FILE.read_text(encoding="utf-8")
        tree = ast.parse(self.source)
        self.values = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                if isinstance(node.targets[0], ast.Name) and node.targets[0].id == "POWERSHELL":
                    self.values["script"] = ast.literal_eval(node.value)

    def test_command_fits_windows_encoded_command_length(self):
        import base64
        script = self.values["script"]
        self.assertLessEqual(len(base64.b64encode(script.encode("utf-16le"))), 6500)

    def test_read_only_windows_time_evidence(self):
        script = self.values["script"]
        for required in (
            "Get-Date", "nltest.exe /sc_query:",
            "w32tm.exe /query /source", "w32tm.exe /query /status /verbose",
            "w32tm.exe /query /peers /verbose",
            "w32tm.exe /query /configuration",
            "Get-NetUDPEndpoint -LocalPort 123",
            "Microsoft-Windows-Time-Service", "Get-WinEvent",
        ):
            self.assertIn(required, script)
        for forbidden in (
            "/resync", "w32tm.exe /config ", "/rediscover", "Restart-Service",
            "Start-Service", "Stop-Service", "Set-ItemProperty",
            "New-ItemProperty", "Set-NetFirewallRule",
            "Reset-ComputerMachinePassword", "Test-ComputerSecureChannel -Repair",
        ):
            self.assertNotIn(forbidden, script)

    def test_diagnostic_includes_previous_night_failure_window(self):
        script = self.values["script"]
        self.assertIn("AddHours(-24)", script)
        self.assertIn("SYSTEM TIME-SERVICE EVENTS (24H)", script)
        self.assertIn("OPERATIONAL TIME-SERVICE EVENTS (24H)", script)
        self.assertNotIn("AddHours(-6)", script)

    def test_nonterminating_errors_and_pywinrm_warnings_never_report_pass(self):
        tree = ast.parse(self.source)
        names = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "REQUIRED_SECTIONS"
        }
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "evidence_problems")
        namespace = names.copy()
        exec(compile(ast.Module(body=[fn], type_ignores=[]),
                     str(FILE), "exec"), namespace)
        problems = namespace["evidence_problems"]
        stdout = "\\n".join(names["REQUIRED_SECTIONS"]) + (
            "\\n==== SOURCE ====\\nwinterfell.north.sevenkingdoms.local\\n"
            "==== PEERS ====\\nPeer: winterfell\\n"
            "==== STATUS ====\\nLeap Indicator: 0\\n"
            "==== EFFECTIVE CONFIGURATION ====\\n"
        )
        self.assertEqual(problems(0, stdout, "", []), [])
        self.assertIn("PowerShell stderr is nonempty",
                      problems(0, stdout, "nonterminating error", []))
        self.assertIn("pywinrm emitted parsing/runtime warnings",
                      problems(0, stdout, "", ["XML error parsing failed"]))
        self.assertIn("PowerShell exit=1", problems(1, stdout, "", []))
        self.assertTrue(problems(0, "", "", []))

    def test_host_source_requires_exact_owner_and_no_guest_start(self):
        for required in (
            "is_symlink()", '"installed"', '"exercise"',
            '"vmrun", "-T", "ws", "list"',
            "vmx not in running", "GoadNomadVmwareProvider._lab_winrm_session",
        ):
            self.assertIn(required, self.source)
        for forbidden in (
            '"vmrun", "-T", "ws", "start"',
            '"vmrun", "-T", "ws", "stop"',
            "set_runtime_mode(", "set_runtime_mode='",
            "subprocess.run(['sudo'", "ethernet0.startConnected",
        ):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
