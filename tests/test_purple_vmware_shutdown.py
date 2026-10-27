"""Offline scoped PURPLE VM power lifecycle tests (never call real vmrun)."""
import ast
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
CLI_SOURCE = ROOT / "goad.py"
STOP_ORDER = ("PURPLE-WS01", "PURPLE-LX01", "PURPLE-DC01", "PURPLE-WAZUH")
START_ORDER = ("PURPLE-DC01", "PURPLE-WAZUH", "PURPLE-LX01", "PURPLE-WS01")


class FakeVmrun:
    def __init__(self, vmx, running=None, accepts_soft=True):
        self.vmx = vmx
        self.running = set(STOP_ORDER if running is None else running)
        self.accepts_soft = accepts_soft
        self.commands = []
        self.other_guest = "/external/north/GOAD-DC02.vmx"

    def run(self, args, **kwargs):
        self.commands.append(tuple(args))
        if args[:4] == ['vmrun', '-T', 'ws', 'list']:
            files = [str(self.vmx[n]) for n in STOP_ORDER if n in self.running]
            files.append(self.other_guest)  # Another lab must NEVER be touched.
            return subprocess.CompletedProcess(
                args, 0, "Total running VMs: %d\n" % len(files) +
                "\n".join(files) + "\n", "",
            )
        if args[:4] == ['vmrun', '-T', 'ws', 'stop']:
            name = next(n for n, p in self.vmx.items() if str(p) == args[4])
            if self.accepts_soft:
                self.running.remove(name)
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:4] == ['vmrun', '-T', 'ws', 'start']:
            name = next(n for n, p in self.vmx.items() if str(p) == args[4])
            self.running.add(name)
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError("Unexpected command: " + repr(args))


def isolated_class_methods():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef)
               and x.name == "GoadKingdomsVmwareProvider")
    method_names = {
        "_purple_controller_busy", "_purple_power_action_ready",
        "_purple_registered_vmx", "_purple_running_vms",
        "_purple_wait_for_power", "_purple_soft_stop",
        "_purple_start_machine", "_stop_purple_vms", "_start_purple_vms",
    }
    methods = [x for x in cls.body if isinstance(x, ast.FunctionDef)
               and x.name in method_names]
    assert len(methods) == len(method_names), "Unexpected PURPLE lifecycle methods"
    events = []
    log = types.SimpleNamespace(
        error=lambda s: events.append(("error", s)),
        warning=lambda s: events.append(("warning", s)),
        info=lambda s: events.append(("info", s)),
        success=lambda s: events.append(("success", s)),
    )
    import time
    import psutil
    ns = {
        "Log": log, "os": os, "time": time,
        "psutil": psutil, "subprocess": subprocess,
    }
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns, events, method_names


class PurpleShutdownTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.provider = Path(self.temp.name) / "provider"
        self.provider.mkdir()
        self.vmx = {}
        for machine in STOP_ORDER:
            target = self.provider / ".vagrant" / "machines" / machine / "vmware_desktop" / "owned"
            target.mkdir(parents=True)
            path = target / "guest.vmx"
            path.write_text("fixture")
            self.vmx[machine] = path
        self.ns, self.events, names = isolated_class_methods()
        self.mock = FakeVmrun(self.vmx)
        self.ns["subprocess"] = types.SimpleNamespace(
            run=self.mock.run, TimeoutExpired=subprocess.TimeoutExpired,
        )
        self.ns["psutil"] = types.SimpleNamespace(
            process_iter=lambda _: [], NoSuchProcess=Exception, ZombieProcess=Exception,
            AccessDenied=PermissionError, Error=OSError,
        )
        self.lab = types.SimpleNamespace(
            lab_name="PURPLE", path=str(self.provider),
            _purple_start_order=START_ORDER, _purple_stop_order=STOP_ORDER,
            _last_bounded_vagrant_reaped=True,
            _vmx_path=lambda name: str(self.vmx.get(name)) if name in self.vmx else None,
        )
        for name in names:
            setattr(self.lab, name, types.MethodType(self.ns[name], self.lab))

    def test_full_stop_is_scoped_graceful_and_in_order(self):
        self.assertTrue(self.lab._stop_purple_vms())
        stops = [x for x in self.mock.commands if x[3] == "stop"]
        self.assertEqual([x[4] for x in stops], [str(self.vmx[x]) for x in STOP_ORDER])
        self.assertTrue(all(x[-1] == "soft" for x in stops))
        self.assertFalse(self.mock.running)
        self.assertNotIn(self.mock.other_guest, str(stops))

    def test_full_start_preserves_boot_order_and_does_not_provision(self):
        self.mock.running.clear()
        self.assertTrue(self.lab._start_purple_vms())
        starts = [x for x in self.mock.commands if x[3] == "start"]
        self.assertEqual([x[4] for x in starts], [str(self.vmx[x]) for x in START_ORDER])
        self.assertTrue(all(x[-1] == "nogui" for x in starts))

    def test_one_vm_stop_does_not_touch_other_guests(self):
        self.assertTrue(self.lab._purple_soft_stop("PURPLE-WS01"))
        self.assertEqual(self.mock.running, set(STOP_ORDER) - {"PURPLE-WS01"})
        self.assertEqual(len([x for x in self.mock.commands if x[3] == "stop"]), 1)

    def test_duplicate_vmx_registration_is_refused(self):
        self.vmx["PURPLE-WS01"] = self.vmx["PURPLE-DC01"]
        self.assertFalse(self.lab._stop_purple_vms())
        self.assertFalse(any(x[3] == "stop" for x in self.mock.commands))

    def test_foreign_vm_registration_is_refused(self):
        outsider = Path(self.temp.name) / "north.vmx"
        outsider.write_text("foreign guest")
        self.vmx["PURPLE-WS01"] = outsider
        self.assertFalse(self.lab._stop_purple_vms())
        self.assertFalse(any(x[3] == "stop" for x in self.mock.commands))

    def test_prior_unreaped_controller_blocks_power_changes(self):
        self.lab._last_bounded_vagrant_reaped = False
        self.assertFalse(self.lab._stop_purple_vms())
        self.assertFalse(self.lab._start_purple_vms())

    def test_live_stale_vagrant_halt_blocks_power_changes(self):
        proc = types.SimpleNamespace(
            info={"cmdline": ["/opt/vagrant/bin/vagrant", "halt"]},
            pid=1234,
            cwd=lambda: str(self.provider),
        )
        self.ns["psutil"].process_iter = lambda _: [proc]
        self.assertFalse(self.lab._stop_purple_vms())
        self.assertFalse(any(x[3] == "stop" for x in self.mock.commands))

    def test_non_purple_vagrant_controller_not_blocking(self):
        proc = types.SimpleNamespace(
            info={"cmdline": ["/opt/vagrant/bin/vagrant", "halt"]},
            pid=1234,
            cwd=lambda: str(Path(self.temp.name) / "north-provider"),
        )
        self.ns["psutil"].process_iter = lambda _: [proc]
        self.assertTrue(self.lab._purple_power_action_ready())

    def test_unresponsive_guest_never_hard_powers_off(self):
        self.mock.accepts_soft = False
        counter = iter((0, 999))
        self.ns["time"] = types.SimpleNamespace(
            monotonic=lambda: next(counter), sleep=lambda _: None)
        self.assertFalse(self.lab._stop_purple_vms())
        self.assertTrue(all(x[3] != "stop" or x[-1] == "soft"
                            for x in self.mock.commands))

    def test_running_state_uncertain_fails_closed(self):
        self.ns["subprocess"].run = lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "no")
        self.assertFalse(self.lab._stop_purple_vms())
        self.assertFalse(self.lab._start_purple_vms())

    def test_cli_restart_command_exists_and_checks_provider_result(self):
        text = CLI_SOURCE.read_text(encoding="utf-8")
        self.assertIn("def do_restart_vm(self, arg):", text)
        self.assertIn("return bool(provider.restart_vm(name))", text)

    def test_north_paths_preserved(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("if self.lab_name == 'PURPLE':\n            return self._stop_purple_vms()", text)
        self.assertIn("if self.lab_name not in ('GOAD', 'NORTH'):", text)
        self.assertIn("self._stop_machine_via_vmware(machine)", text)


if __name__ == "__main__":
    unittest.main()
