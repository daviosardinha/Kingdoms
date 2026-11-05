"""PURPLE installed-guest startup must mirror KINGDOMS: no Vagrant NAT/WinRM boot.

Offline AST-isolated tests; no VMware guest is started in CI.
"""
import ast
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "goad/purple_existing_start.py"
PROVIDER = ROOT / "goad/provider/vagrant/vmware.py"
ROSTER = (
    ("PURPLE-DC01", "172.28.233.30", "windows"),
    ("PURPLE-WS01", "172.28.233.31", "windows"),
    ("PURPLE-LX01", "172.28.233.32", "linux"),
    ("PURPLE-WAZUH", "172.28.233.51", "linux"),
    ("PURPLE-C2", "172.28.233.60", "linux"),
)


class PurpleStartBlocked(RuntimeError):
    pass


def isolated_starter():
    code = ast.parse(MODULE.read_text())
    cls = next(n for n in code.body if isinstance(n, ast.ClassDef)
               and n.name == "ExistingPurpleStarter")
    outputs = []
    logger = SimpleNamespace(
        info=lambda msg: outputs.append(("info", msg)),
        warning=lambda msg: outputs.append(("warning", msg)),
        error=lambda msg: outputs.append(("error", msg)),
        success=lambda msg: outputs.append(("success", msg)),
    )
    env = {"__name__": "offline_purple", "ROSTER": ROSTER,
           "Log": logger, "PurpleStartBlocked": PurpleStartBlocked,
           "subprocess": subprocess, "Path": Path}
    exec(compile(ast.Module(body=[cls], type_ignores=[]),
                 str(MODULE), "exec"), env)
    return env["ExistingPurpleStarter"], outputs


class PurpleExistingStartTests(unittest.TestCase):
    def test_source_uses_vmware_direct_without_vagrant_start(self):
        module = MODULE.read_text()
        provider = PROVIDER.read_text()
        self.assertIn('"vmrun", "-T", "ws"', module)
        self.assertNotIn('["vagrant", "up"', module)
        self.assertNotIn('run_vagrant(', module)
        self.assertIn("if self.lab_name == 'PURPLE':", provider)
        self.assertIn("from goad.purple_existing_start import start_existing_purple",
                      provider)
        self.assertIn("return start_existing_purple(self.path, vm_name=vm_name)",
                      provider)
        self.assertIn("return self.start(vm_name=vm_name)", provider)
        self.assertIn("owned_vmx(self.provider, machine)", module)

    def fake(self, *, fails=None, power_fails=None):
        klass, output = isolated_starter()
        instance = klass.__new__(klass)
        events = []
        fails = set(fails or ())
        power_fails = set(power_fails or ())

        def power(machine, running):
            events.append(("power", machine))
            if machine in power_fails:
                raise PurpleStartBlocked("VMware power-on blocked")

        def ready(machine, address, kind, timeout):
            events.append(("ready", machine))
            if machine in fails:
                raise PurpleStartBlocked("WinRM not ready")

        instance.running_vmxs = Mock(return_value=set())
        instance.power_on = power
        instance.wait_ready = ready
        return instance, events, output

    def test_ws01_winrm_timeout_cannot_prevent_rest_of_purple_powering_on(self):
        instance, events, output = self.fake(fails={"PURPLE-WS01"})
        self.assertFalse(instance.start())
        powered = [e[1] for e in events if e[0] == "power"]
        self.assertEqual(powered, [r[0] for r in ROSTER])
        ready = [e[1] for e in events if e[0] == "ready"]
        self.assertEqual(ready, [r[0] for r in ROSTER])
        self.assertEqual(events[:5], [("power", r[0]) for r in ROSTER])
        self.assertTrue(any("WS01" in message for level, message in output
                            if level == "error"))
        self.assertFalse(any("WinRM boot" in e[1] for e in events))

    def test_one_vmware_power_failure_does_not_skip_other_machines(self):
        instance, events, output = self.fake(power_fails={"PURPLE-WS01"})
        self.assertFalse(instance.start())
        self.assertEqual([e[1] for e in events if e[0] == "power"],
                         [r[0] for r in ROSTER])
        self.assertEqual([e[1] for e in events if e[0] == "ready"],
                         [r[0] for r in ROSTER if r[0] != "PURPLE-WS01"])

    def test_all_healthy_returns_success_and_preserves_sequence(self):
        instance, events, output = self.fake()
        self.assertTrue(instance.start())
        self.assertEqual([e[1] for e in events if e[0] == "power"],
                         [r[0] for r in ROSTER])
        self.assertEqual([e[1] for e in events if e[0] == "ready"],
                         [r[0] for r in ROSTER])

    def test_one_guest_start_includes_only_dc_dependency(self):
        instance, events, _ = self.fake()
        self.assertTrue(instance.start("PURPLE-C2"))
        self.assertEqual([e[1] for e in events if e[0] == "power"],
                         ["PURPLE-DC01", "PURPLE-C2"])

    def test_unknown_guest_blocked_before_any_start(self):
        instance, events, _ = self.fake()
        with self.assertRaises(PurpleStartBlocked):
            instance.start("GOAD-WS01")
        self.assertEqual(events, [])
        instance.running_vmxs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
