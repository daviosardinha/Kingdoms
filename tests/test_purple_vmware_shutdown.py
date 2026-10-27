"""Offline PURPLE-only shutdown regression tests; no real VMware guests touched."""
import ast
from pathlib import Path
import subprocess
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "goad" / "provider" / "vagrant" / "vmware_kingdoms.py"
NAMES = ("PURPLE-WS01", "PURPLE-LX01", "PURPLE-DC01", "PURPLE-WAZUH")


def isolated_methods():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "GoadKingdomsVmwareProvider")
    method_names = {"_purple_running_vms", "_stop_purple_vms"}
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef)
             and n.name in method_names]
    events = []
    logger = types.SimpleNamespace(
        error=lambda x: events.append(("error", x)),
        warning=lambda x: events.append(("warning", x)),
        info=lambda x: events.append(("info", x)),
        success=lambda x: events.append(("success", x)),
    )
    import os
    import time
    namespace = {"Log": logger, "os": os, "time": time,
                 "subprocess": subprocess}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE),
                 "exec"), namespace)
    return namespace, events


class FakeVmrun:
    def __init__(self, vmx, running=None, accepts_soft=True):
        self.vmx = vmx
        self.running = set(running if running is not None else NAMES)
        self.accepts_soft = accepts_soft
        self.commands = []

    def run(self, args, **kwargs):
        self.commands.append(tuple(args))
        if args[:4] == ['vmrun', '-T', 'ws', 'list']:
            paths = [str(self.vmx[name]) for name in NAMES if name in self.running]
            return subprocess.CompletedProcess(args, 0,
                "Total running VMs: %d\n" % len(paths) + "\n".join(paths) + "\n", "")
        if args[:4] == ['vmrun', '-T', 'ws', 'stop']:
            name = next(name for name, path in self.vmx.items() if str(path) == args[4])
            if self.accepts_soft:
                self.running.remove(name)
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError("Unexpected external command " + repr(args))


class PurpleStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.provider = Path(self.tmp.name) / "provider"
        self.provider.mkdir()
        self.vmx = {}
        for name in NAMES:
            d = self.provider / ".vagrant" / "machines" / name / "vmware_desktop" / "fixture"
            d.mkdir(parents=True)
            self.vmx[name] = d / "guest.vmx"
            self.vmx[name].write_text("fixture")
        self.ns, self.events = isolated_methods()
        self.lab = types.SimpleNamespace(
            lab_name="PURPLE",
            path=str(self.provider),
            _last_bounded_vagrant_reaped=True,
            _vmx_path=lambda name: str(self.vmx[name]),
        )
        self.lab._purple_running_vms = types.MethodType(
            self.ns["_purple_running_vms"], self.lab)
        self.lab._stop_purple_vms = types.MethodType(
            self.ns["_stop_purple_vms"], self.lab)

    def test_graceful_shutdown_is_scoped_and_ordered(self):
        mock = FakeVmrun(self.vmx)
        self.ns["subprocess"] = types.SimpleNamespace(
            run=mock.run, TimeoutExpired=subprocess.TimeoutExpired)
        self.assertTrue(self.lab._stop_purple_vms())
        commands = [x for x in mock.commands if x[3] == "stop"]
        self.assertEqual([x[4] for x in commands], [str(self.vmx[n]) for n in NAMES])
        self.assertTrue(all(x[5] == "soft" for x in commands))
        self.assertEqual(mock.running, set())

    def test_already_stopped_guests_are_idempotent(self):
        mock = FakeVmrun(self.vmx, running=[])
        self.ns["subprocess"] = types.SimpleNamespace(
            run=mock.run, TimeoutExpired=subprocess.TimeoutExpired)
        self.assertTrue(self.lab._stop_purple_vms())
        self.assertFalse(any(x[3] == "stop" for x in mock.commands))

    def test_foreign_vmx_registration_refused(self):
        outsider = Path(self.tmp.name) / "north.vmx"
        outsider.write_text("foreign")
        self.vmx["PURPLE-WS01"] = outsider
        mock = FakeVmrun(self.vmx)
        self.ns["subprocess"] = types.SimpleNamespace(
            run=mock.run, TimeoutExpired=subprocess.TimeoutExpired)
        self.assertFalse(self.lab._stop_purple_vms())
        self.assertFalse(any(x[3] == "stop" for x in mock.commands))

    def test_ambiguous_unreaped_vagrant_controller_refused(self):
        self.lab._last_bounded_vagrant_reaped = False
        self.assertFalse(self.lab._stop_purple_vms())

    def test_unresponsive_guest_does_not_trigger_hard_stop(self):
        mock = FakeVmrun(self.vmx, accepts_soft=False)
        self.ns["subprocess"] = types.SimpleNamespace(
            run=mock.run, TimeoutExpired=subprocess.TimeoutExpired)
        clock = iter((0, 1000))
        self.ns["time"] = types.SimpleNamespace(
            monotonic=lambda: next(clock), sleep=lambda _: None)
        self.assertFalse(self.lab._stop_purple_vms())
        self.assertTrue(all(x[3] != "stop" or x[5] == "soft" for x in mock.commands))
        self.assertTrue(any(x[0] == "error" and "refusing hard" in x[1]
                            for x in self.events))

    def test_north_stop_path_untouched(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("if self.lab_name == 'PURPLE':\n            return self._stop_purple_vms()", text)
        self.assertIn("if self.lab_name not in ('GOAD', 'NORTH'):", text)
        self.assertIn("self._stop_machine_via_vmware(machine)", text)


if __name__ == "__main__":
    unittest.main()
