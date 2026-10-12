"""Release gates for NORTH native cold-start and snapshot restoration."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts/course1-restart-preflight.sh"
RUN = ROOT / "scripts/course1-restart-acceptance.sh"
GOAD = ROOT / "goad.py"
PROVIDER = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"


class Course1RestartAcceptanceTests(unittest.TestCase):
    def test_shell_syntax(self):
        for path in (PREFLIGHT, RUN):
            with self.subTest(path=path):
                result = subprocess.run(["bash", "-n", str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_implicit_vm_action(self):
        for argv in ([], ["ac9fda-north-vmware", "--run"],
                     ["ac9fda-north-vmware", "--inspect"]):
            with self.subTest(argv=argv):
                result = subprocess.run(["bash", str(RUN), *argv],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
        self.assertIn("--confirm-restore-data-loss", RUN.read_text())

    def test_uses_native_lifecycle_and_hard_stop_on_failure(self):
        source = RUN.read_text()
        for marker in (
            ".course1-phase03-acceptance.lock",
            "flock -n 9", "sudo -n -v",
            "scripts/course1-rollout.sh --installed",
            "scripts/course1-phase03-preflight.sh",
            "PHASE03_READONLY_ACCEPTANCE=PASS",
            "for cycle in 1 2;",
            'native stop "cold-$cycle-stop"',
            'native start "cold-$cycle-start"',
            "native reset snapshot-restore",
            "-t \"$task\" -l NORTH -p vmware -i \"$INSTANCE\"",
            "RESTART_RESTORE_RELIABILITY=PASS",
            "RESTART_RESTORE_RELIABILITY=NOT_CERTIFIED",
            "NORTH_REPEATED_COLD_START=PASS",
            "NORTH_SNAPSHOT_RESTORE=PASS",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)
        self.assertNotIn("native start post-restore", source)
        self.assertNotIn("native start restored", source)
        self.assertNotIn("vmrun -T ws revertToSnapshot", source)
        self.assertNotIn("vmrun -T ws snapshot", source)

    def test_native_lifecycle_cannot_kill_vmware_process_group_on_timeout(self):
        source = RUN.read_text()
        # Any native start/stop/reset failure is owned by provider's bounded
        # VMware/Vagrant implementation, not a surrounding GNU timeout group.
        native = source.split("native() {", 1)[1].split("\n}", 1)[0]
        self.assertIn('bash ./goad.sh -t "$task"', native)
        self.assertNotIn('timeout ', native)
        self.assertNotIn('kill -', native)
        self.assertNotIn('step "$name"', native)
        # Probes are still bounded, but no VM lifecycle is run via step().
        self.assertIn('step "$name-readiness" 900', source)

    def test_refuses_missing_or_ambiguous_snapshots(self):
        source = RUN.read_text()
        self.assertIn("for machine in GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01 GOAD-ROUTER;", source)
        self.assertNotIn("GOAD-DC03", source)
        self.assertNotIn("GOAD-SRV03", source)
        self.assertIn("vmrun -T ws listSnapshots", source)
        self.assertIn('[[ "$count" == 1 ]] || fail', source)

    def test_native_reset_already_includes_its_own_start(self):
        source = GOAD.read_text()
        start = source.index("    def do_reset(")
        body = source[start:source.index("\n    def ", start + 6)]
        self.assertIn("self.do_stop()", body)
        self.assertIn("provider.reset()", body)
        self.assertIn("self.do_start()", body)
        provider = PROVIDER.read_text()
        self.assertIn("['snapshot', 'pop', '--no-delete', '--no-start']", provider)
