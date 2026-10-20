"""Verify the reduced NORTH roster uses the original Kingdoms mode controller.

The Bash roster is executed independently of main(): no VMware, sudo,
Vagrant, networking, or guest action is used during these tests.
"""
import ast
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODE = ROOT / "scripts/lab-mode.sh"
PROVIDER = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"


class Course1NativeLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = MODE.read_text(encoding="utf-8")
        cls.provider = PROVIDER.read_text(encoding="utf-8")

    def roster(self, profile):
        script = self.script
        start = script.index("# An explicit profile selection")
        end = script.index("\ndeclare -A DC_DOMAIN=(", start)
        source = script[start:end]
        command = source + """
printf 'DC=%s\\n' "${DOMAIN_CONTROLLERS[*]}"
printf 'EXERCISE_DC=%s\\n' "${EXERCISE_DOMAIN_CONTROLLERS[*]}"
printf 'MEMBERS=%s\\n' "${DOMAIN_MEMBERS[*]}"
printf 'WINDOWS=%s\\n' "${WINDOWS_VMS[*]}"
"""
        result = subprocess.run(
            ["bash", "-c", command],
            env={**os.environ, "GOAD_LAB_PROFILE": profile},
            cwd=ROOT, capture_output=True, text=True, timeout=8, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return dict(line.split("=", 1) for line in result.stdout.splitlines())

    def test_default_goad_has_six_windows_and_essos(self):
        data = self.roster("GOAD")
        self.assertEqual(data["WINDOWS"].split(), [
            "GOAD-DC01", "GOAD-DC02", "GOAD-DC03",
            "GOAD-SRV02", "GOAD-SRV03", "GOAD-WS01",
        ])
        self.assertEqual(data["EXERCISE_DC"].split(),
                         ["GOAD-DC02", "GOAD-DC03", "GOAD-DC01"])

    def test_north_has_four_windows_without_essos(self):
        data = self.roster("NORTH")
        self.assertEqual(data["WINDOWS"].split(),
                         ["GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"])
        self.assertEqual(data["DC"].split(), ["GOAD-DC01", "GOAD-DC02"])
        self.assertEqual(data["MEMBERS"].split(), ["GOAD-SRV02", "GOAD-WS01"])
        self.assertEqual(data["EXERCISE_DC"].split(),
                         ["GOAD-DC02", "GOAD-DC01"])
        self.assertNotIn("GOAD-DC03", data["WINDOWS"])
        self.assertNotIn("GOAD-SRV03", data["WINDOWS"])

    def test_original_mode_controller_selects_profile_router_and_routes(self):
        self.assertIn('ad/${GOAD_LAB_PROFILE}/providers/vmware/router/nftables',
                      self.script)
        self.assertIn('bash "${ROUTES}" --north enable --provider-dir "${PROVIDER}"',
                      self.script)
        self.assertIn('bash "${ROUTES}" --north disable --provider-dir "${PROVIDER}"',
                      self.script)
        self.assertIn('bash "${ROUTES}" --north status --provider-dir "${PROVIDER}"',
                      self.script)
        self.assertIn('sudo bash "${ROUTES}" enable', self.script)
        self.assertIn('sudo bash "${ROUTES}" disable', self.script)
        for name in ("configure_windows_nat_provisioning()",
                     "configure_windows_nat_exercise()",
                     "preflight_domain_health()"):
            self.assertIn(name, self.script)

    def test_north_runtime_remains_guarded_until_host_contract_complete(self):
        # Parse executable statements, not a fixed 700-character slice:
        # reset() has a long docstring describing VMware snapshot recovery.
        tree = ast.parse(self.provider)
        cls = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef)
                   and node.name == "GoadKingdomsVmwareProvider")
        methods = {node.name: node for node in cls.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        guard = methods["_course1_unwired"]
        self.assertIn("if self.lab_name != 'NORTH':",
                      ast.get_source_segment(self.provider, guard))
        for name in ("install", "prepare_install", "start", "start_vm",
                     "stop", "stop_vm", "reset", "prepare_provisioning",
                     "set_runtime_mode"):
            with self.subTest(method=name):
                body = methods[name].body
                # Python AST keeps the docstring as the first Expr node.
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                    body = body[1:]
                self.assertTrue(body, name)
                check = body[0]
                self.assertIsInstance(check, ast.If, name)
                self.assertIsInstance(check.test, ast.Call, name)
                self.assertIsInstance(check.test.func, ast.Attribute, name)
                self.assertIsInstance(check.test.func.value, ast.Name, name)
                self.assertEqual(check.test.func.value.id, "self", name)
                self.assertEqual(check.test.func.attr, "_course1_unwired", name)
                self.assertEqual(check.test.args, [], name)
                self.assertEqual(len(check.body), 1, name)
                self.assertIsInstance(check.body[0], ast.Return, name)
                self.assertIsInstance(check.body[0].value, ast.Constant, name)
                self.assertIs(check.body[0].value.value, False, name)


if __name__ == "__main__":
    unittest.main()
