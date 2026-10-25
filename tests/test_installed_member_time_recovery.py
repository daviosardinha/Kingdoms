"""Safe installed-VMware NT5DS recovery: source-only, no WinRM or guest effects."""
import ast
import base64
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from goad import installed_member_time_recovery as time_recovery
from goad.installed_member_time_recovery import (
    TIME_PENDING, TIME_REPAIRED, TIME_REPAIR_FAILED,
    build_time_recovery_script, is_authenticated_repair,
    is_time_only_pending,
)

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
NOMAD = ROOT / "goad/provider/vagrant/vmware_nomad.py"


def load_provider_method(name, namespace):
    tree = ast.parse(PROVIDER.read_text())
    method = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(PROVIDER), 'exec'), namespace)
    return namespace[name]


class FakeClock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def result(marker, status=0):
    return SimpleNamespace(
        status_code=status,
        std_out=marker.encode(),
        std_err=b"",
    )


class ScriptContract(unittest.TestCase):
    DC = "winterfell.north.sevenkingdoms.local"

    def test_recovery_script_preserves_domain_hierarchy_and_identity(self):
        script = build_time_recovery_script("north.sevenkingdoms.local", self.DC)
        for required in (
            "Test-ComputerSecureChannel", "/sc_query:",
            "/timeserv /force", "/stripchart", "/samples:2",
            "/syncfromflags:domhier /update", "Restart-Service W32Time",
            "/resync /rediscover /nowait", "SignatureAuthenticated",
            "Last Sync Error:", "Leap Indicator:", "KINGDOMS_INSTALLED_MEMBER_TIME_REPAIRED",
        ):
            self.assertIn(required, script)
        for forbidden in (
            "Reset-ComputerMachinePassword", "Test-ComputerSecureChannel -Repair",
            "netdom reset", "/manualpeerlist", "Add-Computer", "ip route",
            "ethernet0.startConnected", "vagrant up",
        ):
            self.assertNotIn(forbidden, script)
        self.assertIn("winterfell.north.sevenkingdoms.local", script)
        self.assertNotIn("__BUDGET__", script)

    def test_cross_forest_essos_remains_explicitly_supported(self):
        script = build_time_recovery_script(
            "essos.local", "meereen.essos.local", budget=75
        )
        self.assertIn("$budget=75", script)
        self.assertIn("$dc='meereen.essos.local'", script)

    def test_unknown_and_unbounded_recovery_rejected(self):
        for domain, dc in (
            ("malicious.example", self.DC),
            ("north.sevenkingdoms.local", "localhost"),
        ):
            with self.assertRaises(ValueError):
                build_time_recovery_script(domain, dc)
        for budget in (0, 29, 91, 500, True):
            with self.assertRaises(ValueError):
                build_time_recovery_script(
                    "north.sevenkingdoms.local", self.DC, budget
                )

    def test_windows_winrm_encoded_command_fits_cmdline_limit(self):
        # Regression: prior recovery was ~10k characters after UTF-16LE
        # encoding; Windows rejected it with "The command line is too long."
        for domain, dc in sorted(time_recovery.DOMAINS):
            for budget in (30, 60, 90):
                with self.subTest(domain=domain, budget=budget):
                    script = build_time_recovery_script(domain, dc, budget)
                    encoded = base64.b64encode(script.encode("utf-16le"))
                    self.assertLessEqual(len(encoded), 6500)
                    # Leave safe headroom for pywinrm's powershell prefix.
                    self.assertLess(len(encoded) + 250, 8191)

    def test_encoded_command_size_guard_rejects_script_regression(self):
        with patch.object(time_recovery, "_SCRIPT",
                          time_recovery._SCRIPT + "\n" + ("#" * 1800)):
            with self.assertRaisesRegex(ValueError,
                                        "WinRM recovery command exceeds safe size"):
                build_time_recovery_script(
                    "north.sevenkingdoms.local", self.DC
                )

    def test_time_only_pending_marker_is_exact(self):
        correct = TIME_PENDING + "expected=" + self.DC
        self.assertTrue(is_time_only_pending(0, correct.encode(), self.DC))
        for rc, marker in (
            (1, correct),
            (0, "PowerShell status 1"),
            (0, TIME_PENDING + "expected=other.domain"),
            (0, "W32Time source is 'Local CMOS Clock'"),
        ):
            self.assertFalse(is_time_only_pending(rc, marker.encode(), self.DC))

    def test_repair_requires_authenticated_source_marker(self):
        good = TIME_REPAIRED + "source=" + self.DC + "|attempt=4|authenticated=true"
        self.assertTrue(is_authenticated_repair(0, good.encode(), self.DC))
        for rc, marker in (
            (1, good),
            (0, good.replace("authenticated=true", "authenticated=false")),
            (0, good.replace(self.DC, "other.dc")),
            (0, TIME_REPAIR_FAILED + "stage=rediscover"),
        ):
            self.assertFalse(is_authenticated_repair(rc, marker.encode(), self.DC))

    def test_member_probe_qualifies_time_only_after_secure_session(self):
        source = PROVIDER.read_text()
        probe = source.split("        else:\n            script = f", 1)[1].split(
            "        deadline = time.monotonic()", 1
        )[0]
        for required in (
            "Resolve-DnsName", "Test-ComputerSecureChannel",
            "/sc_query:", "/timeserv /force",
            "KINGDOMS_INSTALLED_MEMBER_TIME_PENDING",
        ):
            self.assertIn(required, probe)
        self.assertLess(
            probe.index("Test-ComputerSecureChannel"),
            probe.index("KINGDOMS_INSTALLED_MEMBER_TIME_PENDING"),
        )
        self.assertLess(
            probe.index("/sc_query:"),
            probe.index("KINGDOMS_INSTALLED_MEMBER_TIME_PENDING"),
        )

    def test_winrm_normal_read_budget_unchanged_and_repair_bounded(self):
        tree = ast.parse(NOMAD.read_text())
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                      and n.name == "_lab_winrm_session")
        self.assertEqual(method.args.defaults[0].value, 45)
        code = ast.get_source_segment(NOMAD.read_text(), method)
        self.assertIn("read_timeout_sec=read_timeout_sec", code)
        source = PROVIDER.read_text()
        self.assertIn("host, read_timeout_sec=budget + 35", source)


class ControllerTests(unittest.TestCase):
    DC = "winterfell.north.sevenkingdoms.local"
    DOMAIN = "north.sevenkingdoms.local"

    def setUp(self):
        self.clock = FakeClock()
        self.log = Mock()
        self.wait = load_provider_method("_wait_installed_ad_ready", {
            "time": self.clock, "Log": self.log,
        })
        self.repair = load_provider_method("_recover_installed_member_time", {
            "Log": self.log,
        })
        self.provider = Mock()
        self.provider._recover_installed_member_time.return_value = True
        self.session = Mock()
        self.provider._lab_winrm_session.return_value = self.session

    def call_wait(self, machine="GOAD-SRV02", timeout=120):
        return self.wait(self.provider, machine, "10.4.10.22", timeout=timeout)

    def test_healthy_start_does_not_repair(self):
        self.session.run_ps.return_value = result("KINGDOMS_INSTALLED_AD_READY")
        self.assertTrue(self.call_wait())
        self.provider._recover_installed_member_time.assert_not_called()

    def test_sustained_authenticated_time_only_failure_repairs_once(self):
        pending = TIME_PENDING + "expected=" + self.DC
        self.session.run_ps.side_effect = (
            [result(pending) for _ in range(7)] +
            [result("KINGDOMS_INSTALLED_AD_READY")]
        )
        self.assertTrue(self.call_wait())
        self.provider._recover_installed_member_time.assert_called_once()
        args, kwargs = self.provider._recover_installed_member_time.call_args
        self.assertEqual(args[:2], ("GOAD-SRV02", "10.4.10.22"))
        self.assertEqual(args[2]["dc"], self.DC)
        self.assertLessEqual(kwargs["budget"], 90)
        self.assertGreaterEqual(self.clock.now, 30)

    def test_no_repair_when_dns_netlogon_or_transport_fails(self):
        for response in (
            result("W32Time source is 'Local CMOS Clock'", status=1),
            result("Netlogon secure session is not ready", status=1),
            result(TIME_PENDING + "expected=wrong.dc"),
        ):
            with self.subTest(response=response):
                self.setUp()
                self.session.run_ps.return_value = response
                self.assertFalse(self.call_wait(timeout=37))
                self.provider._recover_installed_member_time.assert_not_called()

    def test_short_time_only_flap_does_not_repair(self):
        pending = result(TIME_PENDING + "expected=" + self.DC)
        ready = result("KINGDOMS_INSTALLED_AD_READY")
        self.session.run_ps.side_effect = [pending, pending, ready]
        self.assertTrue(self.call_wait())
        self.provider._recover_installed_member_time.assert_not_called()

    def test_non_time_failure_resets_repair_qualification(self):
        pending = result(TIME_PENDING + "expected=" + self.DC)
        wrong = result("Netlogon failure", 1)
        self.session.run_ps.side_effect = (
            [pending for _ in range(4)] + [wrong] +
            [pending for _ in range(3)] + [result("KINGDOMS_INSTALLED_AD_READY")]
        )
        self.assertTrue(self.call_wait())
        self.provider._recover_installed_member_time.assert_not_called()

    def test_repair_failure_halts_before_retry_or_fallback(self):
        pending = result(TIME_PENDING + "expected=" + self.DC)
        self.session.run_ps.return_value = pending
        self.provider._recover_installed_member_time.return_value = False
        self.assertFalse(self.call_wait())
        self.provider._recover_installed_member_time.assert_called_once()
        self.assertLess(self.clock.now, 90)

    def test_repaired_marker_alone_never_counts_as_ad_readiness(self):
        pending = result(TIME_PENDING + "expected=" + self.DC)
        self.session.run_ps.return_value = pending
        self.assertFalse(self.call_wait(timeout=95))
        self.provider._recover_installed_member_time.assert_called_once()
        self.assertGreater(self.session.run_ps.call_count, 7)

    def test_member_time_recovery_not_available_to_domain_controller(self):
        self.session.run_ps.return_value = result(
            TIME_PENDING + "expected=kingslanding.sevenkingdoms.local"
        )
        self.assertFalse(self.call_wait(machine="GOAD-DC02", timeout=35))
        self.provider._recover_installed_member_time.assert_not_called()

    def test_correct_essos_member_uses_essos_contract(self):
        pending = result(TIME_PENDING + "expected=meereen.essos.local")
        self.session.run_ps.side_effect = (
            [pending] * 7 + [result("KINGDOMS_INSTALLED_AD_READY")]
        )
        self.assertTrue(self.call_wait(machine="GOAD-SRV03"))
        self.assertEqual(
            self.provider._recover_installed_member_time.call_args.args[2]["dc"],
            "meereen.essos.local",
        )

    def test_recovery_transport_and_unverified_marker_fail_closed(self):
        for outcome in (
            result(TIME_REPAIRED + "source=other.dc|attempt=1|authenticated=true"),
            result(TIME_REPAIRED + "source=" + self.DC +
                   "|attempt=1|authenticated=true", status=1),
            result(TIME_REPAIR_FAILED + "stage=ntp_path"),
        ):
            with self.subTest(marker=outcome.std_out):
                session = Mock()
                session.run_ps.return_value = outcome
                provider = Mock()
                provider._lab_winrm_session.return_value = session
                contract = {"kind": "member", "domain": self.DOMAIN, "dc": self.DC}
                self.assertFalse(
                    self.repair(provider, "GOAD-SRV02", "10.4.10.22", contract, 90)
                )
                provider._lab_winrm_session.assert_called_once_with(
                    "10.4.10.22", read_timeout_sec=125
                )

    def test_verified_repair_accepted_only_for_expected_dc(self):
        session = Mock()
        session.run_ps.return_value = result(
            TIME_REPAIRED + "source=" + self.DC + "|attempt=4|authenticated=true"
        )
        provider = Mock()
        provider._lab_winrm_session.return_value = session
        contract = {"kind": "member", "domain": self.DOMAIN, "dc": self.DC}
        self.assertTrue(self.repair(provider, "GOAD-SRV02", "10.4.10.22", contract, 90))

    def test_bad_recovery_scope_does_not_open_winrm(self):
        contract = {"kind": "dc", "domain": self.DOMAIN, "dc": self.DC}
        self.assertFalse(self.repair(self.provider, "GOAD-DC02", "10.4.10.11", contract, 90))
        self.provider._lab_winrm_session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
