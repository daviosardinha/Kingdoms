"""Fail-closed regression tests for PURPLE installed-VM shutdown.

KINGDOMS policy: direct VMware soft shutdown, bounded grace, last-resort
hard fallback, no Vagrant WinRM halt, verify actual VM power state.
Tests never run vmrun or alter a VM.
"""
import ast
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "goad/purple_existing_start.py"
PROVIDER = ROOT / "goad/provider/vagrant/vmware.py"
NAMES = ["PURPLE-DC01", "PURPLE-WS01", "PURPLE-LX01",
         "PURPLE-WAZUH", "PURPLE-C2"]
ROSTER = tuple((n, "", "windows" if n.endswith(("DC01", "WS01")) else "linux")
               for n in NAMES)


class PurpleStartBlocked(RuntimeError):
    pass


def isolated_starter():
    module = ast.parse(SOURCE.read_text())
    cls = next(n for n in module.body if isinstance(n, ast.ClassDef)
               and n.name == "ExistingPurpleStarter")
    logs = []
    logger = SimpleNamespace(
        info=lambda msg: logs.append(("info", msg)),
        warning=lambda msg: logs.append(("warning", msg)),
        error=lambda msg: logs.append(("error", msg)),
        success=lambda msg: logs.append(("success", msg)),
    )
    env = {"__name__": "purple_stop_isolated",
           "ROSTER": ROSTER,
           "Log": logger,
           "PurpleStartBlocked": PurpleStartBlocked,
           "subprocess": subprocess,
           "Path": Path,
           "time": __import__("time"),
           "psutil": SimpleNamespace()}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(SOURCE), "exec"), env)
    return env["ExistingPurpleStarter"], logs


def simulated(*, failed=()):
    cls, log = isolated_starter()
    obj = cls.__new__(cls)
    obj.provider = Path("/opt/kingdoms/workspace/ef5c0b-purple-vmware/provider")
    obj.vmx = {n: Path(f"/guest/{n}.vmx") for n in NAMES}
    running = set(str(vmx) for vmx in obj.vmx.values())
    actions = []
    failures = set(failed)
    obj.ensure_no_competing_vagrant = Mock()
    obj.running_vmxs = Mock(side_effect=lambda: set(running))

    def stop_one(machine):
        actions.append(machine)
        if machine in failures:
            return False
        running.remove(str(obj.vmx[machine]))
        return True

    obj.stop_one = stop_one
    return obj, running, actions, log


class PurpleInstalledStopTests(unittest.TestCase):
    def test_provider_overrides_stop_and_stop_vm_without_vagrant_halt(self):
        src = PROVIDER.read_text()
        self.assertIn("from goad.purple_existing_start import stop_existing_purple", src)
        self.assertIn("return stop_existing_purple(self.path)", src)
        self.assertIn("return stop_existing_purple(self.path, vm_name=vm_name)", src)
        helper = SOURCE.read_text()
        self.assertIn("def stop_one(", helper)
        self.assertIn('"soft", timeout=45', helper)
        self.assertIn('timeout=120', helper)
        self.assertIn('"hard", timeout=30', helper)
        self.assertIn('self.ensure_no_competing_vagrant()', helper)
        self.assertIn('if vm_name is not None and vm_name not in names:', helper)
        self.assertNotIn('["vagrant", "halt"', helper)
        self.assertNotIn('run_vagrant(', helper)

    def test_shutdown_order_preserves_dc_until_ws01_has_stopped(self):
        obj, running, actions, logs = simulated()
        self.assertTrue(obj.stop())
        self.assertEqual(actions, list(reversed(NAMES)))
        self.assertFalse(running)
        obj.ensure_no_competing_vagrant.assert_called_once()
        self.assertTrue(any("power state verified" in msg
                            for level, msg in logs if level == "success"))

    def test_ws01_failed_shutdown_does_not_strand_other_guests(self):
        obj, running, actions, logs = simulated(failed={"PURPLE-WS01"})
        self.assertFalse(obj.stop())
        self.assertEqual(actions, ["PURPLE-C2", "PURPLE-WAZUH",
                                   "PURPLE-LX01", "PURPLE-WS01"])
        self.assertEqual(running, {str(obj.vmx["PURPLE-WS01"]),
                                    str(obj.vmx["PURPLE-DC01"])})
        self.assertTrue(any("preserving DC01" in msg
                            for level, msg in logs if level == "warning"))

    def test_single_guest_stop_has_no_other_vm_effect(self):
        obj, running, actions, _ = simulated()
        self.assertTrue(obj.stop("PURPLE-LX01"))
        self.assertEqual(actions, ["PURPLE-LX01"])
        self.assertEqual(len(running), 4)

    def test_dc_only_stop_refused_while_ws01_depends_on_it(self):
        obj, running, actions, _ = simulated()
        self.assertFalse(obj.stop("PURPLE-DC01"))
        self.assertEqual(actions, [])
        self.assertEqual(len(running), 5)

    def test_unknown_guest_rejected_before_any_vm_action(self):
        obj, running, actions, _ = simulated()
        with self.assertRaises(PurpleStartBlocked):
            obj.stop("GOAD-WS01")
        self.assertEqual(actions, [])
        obj.ensure_no_competing_vagrant.assert_not_called()

    def test_active_vagrant_halt_fences_shutdown(self):
        obj, running, actions, _ = simulated()
        obj.ensure_no_competing_vagrant.side_effect = PurpleStartBlocked(
            "Vagrant controller still active")
        with self.assertRaises(PurpleStartBlocked):
            obj.stop()
        self.assertEqual(actions, [])
        obj.running_vmxs.assert_not_called()

    def test_soft_shutdown_verified_without_hard_stop(self):
        cls, _ = isolated_starter()
        obj = cls.__new__(cls)
        obj.vmx = {n: Path(f"/guest/{n}.vmx") for n in NAMES}
        obj.running_vmxs = Mock(return_value={str(obj.vmx["PURPLE-WS01"])})
        obj.vmrun = Mock(return_value="")
        obj.wait_stopped = Mock(return_value=True)
        self.assertTrue(obj.stop_one("PURPLE-WS01"))
        obj.vmrun.assert_called_once_with(
            "stop", str(obj.vmx["PURPLE-WS01"]), "soft", timeout=45)
        obj.wait_stopped.assert_called_once_with("PURPLE-WS01", timeout=120)

    def test_timed_out_vmrun_soft_can_have_already_stopped_guest(self):
        cls, _ = isolated_starter()
        obj = cls.__new__(cls)
        obj.vmx = {n: Path(f"/guest/{n}.vmx") for n in NAMES}
        obj.running_vmxs = Mock(return_value={str(obj.vmx["PURPLE-WS01"])})
        obj.vmrun = Mock(side_effect=subprocess.TimeoutExpired("vmrun", 45))
        obj.wait_stopped = Mock(return_value=True)
        self.assertTrue(obj.stop_one("PURPLE-WS01"))
        obj.vmrun.assert_called_once()

    def test_hard_fallback_only_after_full_soft_grace(self):
        cls, _ = isolated_starter()
        obj = cls.__new__(cls)
        obj.vmx = {n: Path(f"/guest/{n}.vmx") for n in NAMES}
        obj.running_vmxs = Mock(return_value={str(obj.vmx["PURPLE-WS01"])})
        obj.vmrun = Mock(return_value="")
        obj.wait_stopped = Mock(side_effect=[False, True])
        self.assertTrue(obj.stop_one("PURPLE-WS01"))
        calls = obj.vmrun.call_args_list
        self.assertEqual([x.args[-1] for x in calls], ["soft", "hard"])
        self.assertEqual([x.kwargs["timeout"] for x in calls], [45, 30])
        self.assertEqual([x.kwargs["timeout"] for x in obj.wait_stopped.call_args_list],
                         [120, 30])

    def test_unknown_vmware_state_never_permits_hard_stop(self):
        cls, _ = isolated_starter()
        obj = cls.__new__(cls)
        obj.vmx = {n: Path(f"/guest/{n}.vmx") for n in NAMES}
        obj.running_vmxs = Mock(return_value={str(obj.vmx["PURPLE-WS01"])})
        obj.vmrun = Mock(return_value="")
        obj.wait_stopped = Mock(side_effect=PurpleStartBlocked("VMware list unavailable"))
        with self.assertRaises(PurpleStartBlocked):
            obj.stop_one("PURPLE-WS01")
        obj.vmrun.assert_called_once()
        self.assertEqual(obj.vmrun.call_args.args[-1], "soft")


if __name__ == "__main__":
    unittest.main()
