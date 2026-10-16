"""Safe WSLPE-only host owner recovery gate, with mocked independent timer."""
import os
import pwd
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
import unittest

from kingdoms.wslpe_owner_recovery import owner_identity, rehearse_owner_timer

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wslpe_owner_check", ROOT / "scripts/wslpe-p1c-owner-recovery-check.py"
)
assert SPEC and SPEC.loader
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def completed(rc=0, stdout=""):
    return SimpleNamespace(returncode=rc, stdout=stdout)


class WslpeOwnerRecoveryTests(unittest.TestCase):
    def test_owner_rejects_root_wrong_owner_or_symlink(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "windows_10.vmx"
            path.write_text('displayName = "WSLPE-WS01"\n')
            with self.assertRaises(ValueError):
                owner_identity(path, current_uid=0)
            wrong = path.stat().st_uid + 1
            with self.assertRaises(ValueError):
                owner_identity(path, current_uid=wrong)
            link = Path(tmp) / "linked.vmx"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                owner_identity(link, current_uid=wrong)

    def test_rehearsal_requires_nonroot_valid_user(self):
        for uid, username in ((0, "stark"), (1000, "ROOT USER"),
                              (-1, "stark"), (1000, "root;rm")):
            with self.subTest(uid=uid, user=username):
                with self.assertRaises(ValueError):
                    rehearse_owner_timer(uid, username)

    @unittest.skipIf(os.getuid() == 0, "owner uid test requires nonroot process")
    def test_systemd_argv_runs_as_vmware_owner_and_cleans_marker(self):
        calls = []
        def runner(argv, timeout=20):
            calls.append(argv)
            if argv[:3] == ["sudo", "-n", "systemd-run"]:
                marker = Path(argv[-1])
                self.assertEqual(marker.name, "fired")
                self.assertEqual(marker.parent.stat().st_uid, os.getuid())
                self.assertIn(
                    f"--property=User={pwd.getpwuid(os.getuid()).pw_name}", argv
                )
                marker.touch()
                return completed()
            if argv[:4] == ["sudo", "-n", "systemctl", "is-active"]:
                return completed(stdout="active\n")
            return completed(rc=1)
        username = pwd.getpwuid(os.getuid()).pw_name
        unit = rehearse_owner_timer(os.getuid(), username, runner, lambda _: None)
        self.assertRegex(unit, r"^kingdoms-wslpe-owner-check-[a-f0-9]{16}$")
        self.assertFalse(Path(calls[0][-1]).exists())

    def test_script_never_calls_mutating_north_or_vmware_commands(self):
        source = (ROOT / "scripts/wslpe-p1c-owner-recovery-check.py").read_text()
        owner_source = (ROOT / "kingdoms/wslpe_owner_recovery.py").read_text()
        for token in ("owner_identity(", "rehearse_owner_timer(",
                      "stage.locate_registered_vm(", "preview.running_exact("):
            self.assertIn(token, source)
        for forbidden in (
            "vmrun -T ws stop", "vmrun -T ws start", "vmx.write_bytes(",
            "vmx.write_text(", "vagrant up", "nft -f", "flush ruleset",
            "lab-mode.sh", "10.4.10.11", "vmnet10", "Set-NetAdapter",
        ):
            self.assertNotIn(forbidden, source + owner_source)

    def test_recovery_check_has_no_automatic_cutover_mode(self):
        cli = (ROOT / "scripts/wslpe-p1c-owner-recovery-check.py").read_text()
        self.assertIn('parser.add_argument("--rehearse"', cli)
        self.assertNotIn('--execute', cli)
        self.assertNotIn('--apply', cli)


if __name__ == "__main__":
    unittest.main()
