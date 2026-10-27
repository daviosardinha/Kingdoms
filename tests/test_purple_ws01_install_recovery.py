"""Offline tests for the PURPLE first-boot VMware Tools evaluation gate."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "goad/provider/vagrant/vmware.py"


def method_under_test(*, helper_exists=True, helper_exit=0):
    source = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(x for x in source.body if isinstance(x, ast.ClassDef)
               and x.name == "VmwareProvider")
    node = next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                and x.name == "_install_purple_with_eval_maintenance")
    events = []
    logger = SimpleNamespace(
        info=lambda *args: events.append(("log_info", args[0])),
        warning=lambda *args: events.append(("log_warning", args[0])),
        error=lambda *args: events.append(("log_error", args[0])),
        success=lambda *args: events.append(("log_success", args[0])),
    )
    runner = Mock(side_effect=lambda *args, **kwargs: (
        events.append(("eval", args[0], kwargs)),
        SimpleNamespace(returncode=helper_exit)
    )[1])
    globals_ = {
        "Log": logger,
        "GoadPath": SimpleNamespace(
            get_script_file=lambda _: "/repo/scripts/purple-ws01-vmware-eval.py",
            get_project_path=lambda: "/repo",
        ),
        "os": SimpleNamespace(path=SimpleNamespace(
            isfile=lambda p: helper_exists,
            realpath=lambda p: p,
        )),
        "subprocess": SimpleNamespace(
            run=runner,
            TimeoutExpired=TimeoutError,
        ),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 str(SOURCE), "exec"), globals_)
    return globals_[node.name], runner, events


class PurpleWs01InstallGateTests(unittest.TestCase):
    @staticmethod
    def provider(events, *, first_boot=True, provision=True, cleanup=True):
        def vagrant(args, path):
            events.append(("vagrant", args))
            return True

        def bounded(args, timeout):
            events.append(("bounded", args, timeout))
            if "--no-provision" in args:
                return first_boot
            return provision

        return SimpleNamespace(
            path="/repo/workspace/ef5c0b-purple-vmware/provider",
            command=SimpleNamespace(run_vagrant=vagrant),
            _run_vagrant_bounded=bounded,
            _last_bounded_vagrant_reaped=cleanup,
        )

    def test_expired_guest_winrm_stall_recovers_before_provision(self):
        gate, runner, events = method_under_test()
        self.assertTrue(gate(self.provider(events, first_boot=False)))
        sequence = [x[0] for x in events if x[0] in ("vagrant", "bounded", "eval")]
        self.assertEqual(sequence, ["vagrant", "bounded", "eval",
                                    "bounded", "vagrant", "vagrant"])
        actions = [e for e in events if e[0] in ("vagrant", "bounded", "eval")]
        self.assertEqual(actions[1][1], ["up", "PURPLE-WS01", "--no-provision"])
        self.assertIn("--fresh-install", runner.call_args.args[0])
        self.assertEqual(actions[3][1], ["up", "PURPLE-WS01", "--provision"])
        self.assertEqual(actions[4][1], ["up", "PURPLE-LX01"])
        self.assertEqual(actions[5][1], ["up", "PURPLE-WAZUH"])

    def test_healthy_guest_still_checks_eval_before_provision(self):
        gate, runner, events = method_under_test()
        self.assertTrue(gate(self.provider(events)))
        self.assertEqual(runner.call_count, 1)
        self.assertLess(
            next(i for i, e in enumerate(events) if e[0] == "eval"),
            next(i for i, e in enumerate(events) if e[0] == "bounded"
                 and "--provision" in e[1]),
        )

    def test_failed_cleanup_never_races_vmware_recovery(self):
        gate, runner, events = method_under_test()
        self.assertFalse(gate(self.provider(events, first_boot=False, cleanup=False)))
        runner.assert_not_called()
        self.assertFalse(any(e[0] == "bounded" and "--provision" in e[1]
                             for e in events))

    def test_failed_licensing_never_starts_windows_or_linux_provisioning(self):
        gate, runner, events = method_under_test(helper_exit=1)
        self.assertFalse(gate(self.provider(events, first_boot=False)))
        runner.assert_called_once()
        self.assertFalse(any(e[0] == "bounded" and "--provision" in e[1]
                             for e in events))
        self.assertFalse(any(e[0] == "vagrant" and "PURPLE-WAZUH" in e[1]
                             for e in events))

    def test_missing_helper_blocks_before_recovery(self):
        gate, runner, events = method_under_test(helper_exists=False)
        self.assertFalse(gate(self.provider(events)))
        runner.assert_not_called()

    def test_failed_winrm_provisioning_stops_before_linux(self):
        gate, runner, events = method_under_test()
        self.assertFalse(gate(self.provider(events, provision=False)))
        runner.assert_called_once()
        self.assertFalse(any(e[0] == "vagrant" and "PURPLE-LX01" in e[1]
                             for e in events))


if __name__ == "__main__":
    unittest.main()
