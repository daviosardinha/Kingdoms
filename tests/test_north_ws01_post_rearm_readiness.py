"""NORTH post-evaluation reboot readiness: bounded source-only regressions.

The isolated methods use a virtual clock and fake WinRM. Nothing touches VMware.
"""
from pathlib import Path
import ast
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

SOURCE = (Path(__file__).resolve().parents[1] /
          "goad/provider/vagrant/vmware_kingdoms.py")


def isolated_method(name, *, fake_time=None, log=None):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef)
               and x.name == "GoadKingdomsVmwareProvider")
    method = next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                  and x.name == name)
    globals_ = {"Log": log or Mock()}
    if fake_time is not None:
        globals_["time"] = fake_time
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(SOURCE), "exec"), globals_)
    return globals_[name]


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert 0 < seconds <= 5
        self.sleeps.append(seconds)
        self.now += seconds


class NorthPostRearmTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.log = Mock()
        self.poll = isolated_method(
            "_north_post_rearm_guest_ready", fake_time=self.clock, log=self.log
        )

    def test_success_after_transient_post_reboot_failures(self):
        provider = SimpleNamespace(
            lab_name="NORTH",
            _authenticated_guest_install_ready=Mock(
                side_effect=[False, False, True]
            ),
        )
        self.assertTrue(self.poll(provider, "GOAD-WS01", timeout=16))
        self.assertEqual(
            provider._authenticated_guest_install_ready.call_count, 3
        )
        self.assertEqual(self.clock.sleeps, [5, 5])
        self.assertLess(self.clock.now, 16)
        self.log.success.assert_called_once()

    def test_timeout_never_claims_readiness(self):
        provider = SimpleNamespace(
            lab_name="NORTH",
            _authenticated_guest_install_ready=Mock(return_value=False),
        )
        self.assertFalse(self.poll(provider, "GOAD-WS01", timeout=12))
        self.assertGreaterEqual(self.clock.now, 12)
        self.assertLessEqual(self.clock.now, 12)
        self.assertEqual(
            provider._authenticated_guest_install_ready.call_count, 3
        )
        self.log.error.assert_called_once()

    def test_wrong_lab_or_guest_refused_without_contact(self):
        provider = SimpleNamespace(
            lab_name="GOAD",
            _authenticated_guest_install_ready=Mock(return_value=True),
        )
        self.assertFalse(self.poll(provider, "GOAD-WS01", timeout=180))
        provider.lab_name = "NORTH"
        self.assertFalse(self.poll(provider, "GOAD-DC02", timeout=180))
        provider._authenticated_guest_install_ready.assert_not_called()

    def test_existing_gate_and_no_admission_without_all_checks(self):
        src = SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "if not self._north_post_rearm_guest_ready(machine, timeout=180):",
            src,
        )
        self.assertIn("GOAD_KINGDOMS_GUEST_DIAG|tools_service=", src)
        self.assertIn("f'NORTH: {machine} WinRM responded but authenticated readiness '", src)
        self.assertIn("and b'GOAD_KINGDOMS_GUEST_READY' in result.std_out", src)
        self.assertIn("if not self._enable_provisioning_routes():", src)

    def test_guest_diagnostics_retains_strict_gate(self):
        log = Mock()
        gate = isolated_method("_authenticated_guest_install_ready", log=log)
        result = SimpleNamespace(
            status_code=0,
            std_out=(b"GOAD_KINGDOMS_GUEST_DIAG|tools_service=Running"
                     b"|tools_file=True|tools_process=True|canonical_ip=False\n"),
        )
        provider = SimpleNamespace(
            lab_name="NORTH",
            management_hosts={"GOAD-WS01": "10.4.10.31"},
            _winrm_forwarded_port=Mock(return_value=2207),
            _wait_winrm_ready=Mock(return_value=True),
            _winrm_session=Mock(return_value=SimpleNamespace(
                run_ps=Mock(return_value=result)
            )),
        )
        self.assertFalse(gate(provider, "GOAD-WS01", timeout=10))
        log.warning.assert_called_once()
        self.assertIn("canonical_ip=False", log.warning.call_args.args[0])
        provider._wait_winrm_ready.assert_called_once_with(2207, 10)


if __name__ == "__main__":
    unittest.main()
