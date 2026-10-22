"""Source-only validation for the single WSLPE41 read-only operator batch."""
import importlib.util
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "wslpe41-readiness-batch.py"
SPEC = importlib.util.spec_from_file_location("wslpe41_readiness_batch_cli", PATH)
assert SPEC and SPEC.loader
CLI = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CLI
SPEC.loader.exec_module(CLI)


class ReadinessBatchTests(unittest.TestCase):
    def setUp(self):
        self.checks = CLI.commands(
            root=Path("/testrepo"), home=Path("/testhome"), python="/test/python"
        )

    def test_one_batch_contains_all_required_checks(self):
        self.assertEqual(len(self.checks), 6)
        names = [x.title for x in self.checks]
        self.assertEqual(len(set(names)), 6)
        self.assertIn("Management source regressions", names)
        self.assertIn("41-scenario installer manifest", names)
        self.assertIn("Existing native WSLPE instance", names)
        self.assertIn("Native vmnet4/subnet proposal", names)
        self.assertIn("Running VMware ownership", names)
        self.assertIn("Registered and offline VMX ownership", names)

    def test_four_known_workspaces_always_included(self):
        for check in self.checks[3:]:
            args = check.command
            self.assertIn("/testrepo/workspace", args)
            self.assertIn("/testhome/kingdoms-lpe-standalone/workspace", args)
            self.assertIn("/testhome/kingdoms-rebuild/workspace", args)
            self.assertIn("/testhome/vmware/KINGDOMS-WSLPE41-LEARNER-TEST", args)

    def test_maintenance_mode_replaces_running_guest_checks_with_offline_proof(self):
        checks = CLI.maintenance_commands(
            root=Path("/testrepo"), home=Path("/testhome"), python="/test/python"
        )
        self.assertEqual(len(checks), 5)
        self.assertEqual(checks[2].title, "Powered-off native VMX and exercise NIC")
        self.assertEqual(checks[3].title, "Running VMware ownership")
        self.assertEqual(checks[4].title, "Registered and offline VMX ownership")
        self.assertNotIn("--native-status", str(checks))
        self.assertNotIn("--native-workspace", str(checks))
        self.assertIn("wslpe-management-vmnet-offline-native.py", str(checks))

    def test_zero_vm_maintenance_evidence_is_success_without_deferred(self):
        checks = CLI.maintenance_commands(
            root=Path("/testrepo"), home=Path("/testhome"), python="/test/python"
        )
        results = {c.command: (0, "\n".join(c.required) +
                   ("\nRan 100 tests" if c.required_pattern else "")) for c in checks}
        # Source tests require an OK completion marker.
        first = checks[0]
        results[first.command] = (0, "\n".join(first.required) + "\nRan 100 tests")
        status, messages = CLI.perform(checks, runner=lambda cmd: results[cmd])
        self.assertEqual(status, 0)
        self.assertTrue(any("[BATCH PASS]" in msg for msg in messages))
        self.assertFalse(any(msg.startswith("[DEFERRED]") for msg in messages))

    def test_verified_two_running_guests_are_deferred_not_a_failure(self):
        results = {
            x.command: (0, "\n".join(x.required) + "\n" +
                        ("Ran 52 tests\n" if x.required_pattern else ""))
            for x in self.checks
        }
        for chk in self.checks[3:]:
            results[chk.command] = (2, "\n".join(chk.required) + "\n[DEFERRED] 2 guests running")
        invocations = []
        def runner(command):
            invocations.append(command)
            return results[command]
        status, lines = CLI.perform(self.checks, runner=runner)
        self.assertEqual(status, 0)
        self.assertEqual(len(invocations), 6)
        self.assertEqual(sum(line.startswith("[DEFERRED]") for line in lines), 3)
        self.assertIn("[BATCH PASS] Read-only checks pass; VMware maintenance is DEFERRED", lines)
        self.assertTrue(lines[-1].startswith("[NOT INSTALLED]"))

    def test_blocker_is_not_masked_by_deferred_and_other_checks_still_run(self):
        fake = iter([
            (0, "Ran 52 tests\nOK"),
            (0, "[PLAN ONLY] 41/41"),
            (2, "[BLOCKED] native guest missing"),
            (2, "\n".join(self.checks[3].required) + "\n[DEFERRED]"),
            (2, "\n".join(self.checks[4].required) + "\n[DEFERRED]"),
            (2, "\n".join(self.checks[5].required) + "\n[DEFERRED]"),
        ])
        invoked = []
        def runner(c):
            invoked.append(c)
            return next(fake)
        status, lines = CLI.perform(self.checks, runner=runner)
        self.assertEqual(status, 2)
        self.assertEqual(len(invoked), 6)
        self.assertIn("[FAIL] Existing native WSLPE instance", lines)
        self.assertIn("[BATCH BLOCKED] Review failures together; no host or guest changes", lines)

    def test_unexplained_exit_two_is_failure(self):
        check = self.checks[3]
        self.assertEqual(CLI.classify(check, 2, "\n".join(check.required)), "FAIL")
        self.assertEqual(CLI.classify(check, 0, "[BLOCKED] " + "\n".join(check.required)), "FAIL")
        self.assertEqual(CLI.classify(check, 0, "\n".join(check.required)), "PASS")

    def test_source_only_never_reads_vmware_or_restarts_network(self):
        with (mock.patch.object(CLI, "_trusted_binary", side_effect=AssertionError("binary audit called")),
              mock.patch.object(CLI, "perform", return_value=(0, ("[BATCH PASS] source",))) as perform,
              redirect_stdout(StringIO()) as stdout):
            rc = CLI.main(["--source-only"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(perform.call_args.args[0]), 2)
        self.assertIn("[NO CHANGES]", stdout.getvalue())
        source = PATH.read_text()
        self.assertNotIn("vmware-networks --stop", source)
        self.assertNotIn('add_argument("--apply"', source)


if __name__ == "__main__":
    unittest.main()
