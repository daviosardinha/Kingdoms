"""One-installation, 41/41 behavior; all Windows stages are mocked."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from kingdoms import wslpe41_install_flow as flow


class FakeRunner:
    def __init__(self, *, fail_number=None, fail_stage=None, bad_jea=False,
                 attested=True, bad_proof=False):
        self.calls = []
        self.fail_number = fail_number
        self.fail_stage = fail_stage
        self.bad_jea = bad_jea
        self.attested = attested
        self.bad_proof = bad_proof

    def preflight(self, identity):
        return flow.FreshGuestAttestation(
            identity.instance_id, identity.vmx, identity.source_commit,
            self.attested, True, True, True, True, True,
        )

    def run_stage(self, scenario, stage):
        self.calls.append((scenario.number, stage))
        channel = "guest_console" if scenario.number == 30 and stage == "activate" else "ansible"
        if self.bad_jea:
            channel = "ansible"
        number = 999 if self.bad_proof else scenario.number
        return flow.StageProof(
            number, stage, channel,
            f"wslpe41.{scenario.number:02d}.{stage}.evidence",
            not (scenario.number == self.fail_number and stage == self.fail_stage),
        )


class SingleInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private-state"
        self.identity = flow.FreshGuestIdentity(
            "wslpe41-fresh-0001",
            "/operator/workspace/wslpe41-fresh-0001",
            "/operator/workspace/wslpe41-fresh-0001/provider/WSLPE-WS01.vmx",
            "172.28.232.0/24", "a" * 40,
        )

    def read_report(self):
        path = self.root / self.identity.instance_id / "fresh-install.json"
        return json.loads(path.read_text()), path

    def test_single_pass_all_41_without_two_batch_handoffs(self):
        runner = FakeRunner()
        result = flow.install_41(self.identity, runner, self.root)
        report, path = self.read_report()
        self.assertEqual(result, path)
        self.assertEqual(len(runner.calls), 82)
        self.assertEqual([n for n, stage in runner.calls if stage in ("apply", "activate")],
                         [s.number for s in flow.fresh_scenario_manifest()])
        self.assertEqual(report["configuration_validated"], 41)
        self.assertEqual(report["status"], "CONFIGURATION_VALIDATED")
        self.assertEqual(report["course_release"], "NOT_AUTHORIZED")
        self.assertEqual(report["learner_exploitation"], "NOT_PROVEN")
        self.assertEqual(len(report["scenarios"]), 41)
        self.assertTrue(all(s["install"] == s["validation"] == "PASS"
                            for s in report["scenarios"]))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertFalse((path.parent / ".incomplete").exists())

    def test_jea_activates_through_independent_guest_console(self):
        runner = FakeRunner()
        flow.install_41(self.identity, runner, self.root)
        self.assertIn((30, "activate"), runner.calls)
        self.assertNotIn((30, "apply"), runner.calls)
        record = next(r for r in self.read_report()[0]["scenarios"] if r["number"] == 30)
        self.assertEqual(record["proofs"][0]["transport"], "guest_console")
        self.assertEqual(record["proofs"][1]["transport"], "ansible")

    def test_remote_jea_activation_never_counts_as_pass(self):
        runner = FakeRunner(bad_jea=True)
        with self.assertRaisesRegex(flow.InstallBlocked, "missing exact runtime proof"):
            flow.install_41(self.identity, runner, self.root)
        report, path = self.read_report()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["configuration_validated"], 28)
        self.assertEqual(report["inflight"], {"number": 30, "stage": "activate"})
        self.assertTrue((path.parent / ".incomplete").exists())
        self.assertNotIn((31, "apply"), runner.calls)

    def test_first_failed_scenario_stops_every_later_stage(self):
        runner = FakeRunner(fail_number=27, fail_stage="validate")
        with self.assertRaisesRegex(flow.InstallBlocked, "missing exact runtime proof"):
            flow.install_41(self.identity, runner, self.root)
        report, path = self.read_report()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["failure"]["number"], 27)
        self.assertTrue((path.parent / ".incomplete").exists())
        self.assertFalse(any(n > 27 for n, _ in runner.calls))
        self.assertEqual(report["configuration_validated"], 25)
        with self.assertRaisesRegex(flow.InstallBlocked, "Existing installation evidence"):
            flow.install_41(self.identity, FakeRunner(), self.root)

    def test_mismatched_guest_identity_fails_before_any_state_write(self):
        runner = FakeRunner(attested=False)
        with self.assertRaisesRegex(flow.InstallBlocked, "not proven"):
            flow.install_41(self.identity, runner, self.root)
        self.assertFalse(self.root.exists())
        self.assertEqual(runner.calls, [])

    def test_false_stage_identity_fails_closed(self):
        with self.assertRaisesRegex(flow.InstallBlocked, "missing exact runtime proof"):
            flow.install_41(self.identity, FakeRunner(bad_proof=True), self.root)
        self.assertTrue((self.root / self.identity.instance_id / ".incomplete").exists())

    def test_complete_instance_cannot_be_reinstalled_by_replay(self):
        flow.install_41(self.identity, FakeRunner(), self.root)
        with self.assertRaisesRegex(flow.InstallBlocked, "Existing installation evidence"):
            flow.install_41(self.identity, FakeRunner(), self.root)

    def test_symlinked_private_state_is_rejected(self):
        destination = Path(self.temp.name) / "other"
        destination.mkdir()
        self.root.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(flow.InstallBlocked, "symlink"):
            flow.install_41(self.identity, FakeRunner(), self.root)

    def test_cli_execute_is_locked_until_native_runner_is_implemented(self):
        source = Path(__file__).resolve().parents[1] / "scripts/wslpe41-install.py"
        spec = importlib.util.spec_from_file_location("wslpe41_cli", source)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        output = io.StringIO()
        with redirect_stdout(output):
            result = mod.main(["--execute"])
        self.assertEqual(result, 2)
        self.assertIn("[BLOCKED]", output.getvalue())
        self.assertNotIn("41/41 CONFIGURATION VALIDATED", output.getvalue())


if __name__ == "__main__":
    unittest.main()
