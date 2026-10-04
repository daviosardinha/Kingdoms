"""Exercise the cleanup timer handoff without systemd, guests, or networking."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
PHASE03 = ROOT / "scripts" / "phase03"


class WpadWatchdogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "checkout with spaces"
        self.root.mkdir()
        self.active = self.root / "state" / "active"
        self.calls = self.root / "cleanup-calls"
        self.timer = self.root / "timer-command.json"
        self.env = dict(os.environ)
        self.env.update({
            "ROOT": str(self.root),
            "XDG_STATE_HOME": str(self.root / "state"),
            "WPAD_ACTIVE_MARKER": str(self.active),
            "WPAD_LOCK_FILE": str(self.root / "lifecycle.lock"),
            "WPAD_WATCHDOG_DELAY": "15m",
            "WPAD_TEST_TIMER": str(self.timer),
            "WPAD_TEST_CALLS": str(self.calls),
            "WPAD_TEST_FAIL": "",
            "PATH": str(self.root / "fake-bin") + os.pathsep + os.environ["PATH"],
        })

        # None of the real exercise setup or network helpers can run here.
        for name in (
            "assert-wpad-exercise-clean.sh",
            "check-wpad-permanent-prereqs.sh",
            "diagnostics/wpad-preflight.sh",
            "diagnostics/start-mitm6-ws01.sh",
            "diagnostics/start-wpad-observers.sh",
        ):
            self.write("scripts/phase03/" + name, "#!/bin/sh\nexit 0\n")

        for name, stage in (
            ("diagnostics/stop-wpad-runtime.sh", "stop"),
            ("rollback-wpad-runtime.sh", "network"),
            ("diagnostics/cleanup-wpad-rickon-session.sh", "fixture"),
        ):
            self.write("scripts/phase03/" + name, f"""
                #!/bin/sh
                printf '%s\\n' '{stage}' >> "$WPAD_TEST_CALLS"
                [ "$WPAD_TEST_FAIL" != '{stage}' ] || exit 23
                exit 0
            """)

        shutil.copyfile(
            PHASE03 / "watchdog-wpad-exercise-root.sh",
            self.root / "scripts/phase03/watchdog-wpad-exercise-root.sh",
        )
        self.write("fake-bin/sudo", """
            #!/usr/bin/env python3
            import json
            import os
            from pathlib import Path
            import sys
            if sys.argv[1] == 'systemd-run':
                Path(os.environ['WPAD_TEST_TIMER']).write_text(json.dumps(sys.argv[2:]))
            elif sys.argv[1] != 'systemctl':
                raise SystemExit('unexpected privileged command in test')
        """)
        self.write("fake-bin/runuser", """
            #!/bin/sh
            [ "$1" = '-u' ] && [ "$3" = '--' ] || exit 99
            shift 3
            exec "$@"
        """)

        armed = self.run_command(["bash", str(PHASE03 / "start-wpad-exercise.sh")])
        self.assertEqual(armed.returncode, 0, armed.stdout + armed.stderr)
        scheduled = json.loads(self.timer.read_text())
        self.assertIn("--on-active=15m", scheduled)
        self.command = scheduled[scheduled.index("/usr/bin/bash"):]

    def write(self, name, contents):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(contents).lstrip())
        path.chmod(0o700)

    def run_command(self, command):
        return subprocess.run(
            command, cwd=self.root, env=self.env,
            text=True, capture_output=True, timeout=10,
        )

    def test_scheduled_command_restores_and_disarms_its_own_session(self):
        result = self.run_command(self.command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), ["stop", "network", "fixture"])
        self.assertFalse(self.active.exists())
        self.assertIn("PHASE03_WPAD_WATCHDOG_ROLLBACK_COMPLETE=True", result.stdout)

    def test_old_timer_leaves_a_newer_session_untouched(self):
        newer = "status=armed\ntoken=newer-session\n"
        self.active.write_text(newer)
        result = self.run_command(self.command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.active.read_text(), newer)
        self.assertFalse(self.calls.exists())

    def test_timer_after_completed_session_does_no_cleanup(self):
        self.active.unlink()
        result = self.run_command(self.command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())

    def test_failed_cleanup_keeps_the_session_blocked(self):
        armed = self.active.read_text()
        for stage in ("stop", "network", "fixture"):
            with self.subTest(stage=stage):
                self.env["WPAD_TEST_FAIL"] = stage
                self.calls.unlink(missing_ok=True)
                result = self.run_command(self.command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("WPAD watchdog cleanup incomplete", result.stderr)
                self.assertEqual(self.active.read_text(), armed)
                self.assertEqual(self.calls.read_text().splitlines(), ["stop", "network", "fixture"])
                self.assertNotIn("PHASE03_WPAD_WATCHDOG_ROLLBACK_COMPLETE=True", result.stdout)


if __name__ == "__main__":
    unittest.main()
