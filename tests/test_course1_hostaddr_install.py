"""Offline proof of NORTH owned helper/service/timer installation and cleanup."""
import os
import tempfile
import unittest
from pathlib import Path

from goad.course1_hostaddrs import render_hostaddr_assets
from goad.course1_hostaddr_install import (
    HostaddrInstallError, install_owned_address_assets,
)
from goad.kingdoms_topology import load_course1_topology


class Course1AddressInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.paths = {name: root / name for name in ("helper", "service", "timer")}
        self.layout = load_course1_topology()
        self.expected = render_hostaddr_assets(self.layout)
        self.calls = []

    def apply(self, activate=None, verify=None):
        def start():
            self.calls.append("activate")
        def check():
            self.calls.append("verify")
        return install_owned_address_assets(
            self.layout, self.paths, activate or start,
            lambda: self.calls.append("disable"),
            lambda: self.calls.append("reload"), verify or check,
            owner_uid=os.getuid(),
        )

    def test_success_installs_only_owned_bytes_and_supports_rollback(self):
        lease = self.apply()
        self.assertEqual(self.calls, ["activate", "verify"])
        for name, path in self.paths.items():
            self.assertEqual(path.read_text(), self.expected[name])
            self.assertEqual(path.stat().st_mode & 0o777,
                             0o755 if name == "helper" else 0o644)
        lease.rollback()
        self.assertEqual(self.calls[-2:], ["disable", "reload"])
        self.assertTrue(all(not p.exists() for p in self.paths.values()))

    def test_existing_file_is_never_overwritten(self):
        self.paths["service"].write_text("another service")
        with self.assertRaisesRegex(HostaddrInstallError, "Existing"):
            self.apply()
        self.assertEqual(self.paths["service"].read_text(), "another service")
        self.assertFalse(self.paths["helper"].exists())

    def test_symlink_is_never_followed(self):
        foreign = self.paths["helper"].parent / "foreign"
        foreign.write_text("untouched")
        self.paths["helper"].symlink_to(foreign)
        with self.assertRaisesRegex(HostaddrInstallError, "Existing"):
            self.apply()
        self.assertEqual(foreign.read_text(), "untouched")

    def test_failed_activation_removes_new_assets(self):
        def fail():
            self.calls.append("activate")
            raise RuntimeError("systemd unavailable")
        with self.assertRaisesRegex(HostaddrInstallError, "rolled back"):
            self.apply(activate=fail)
        self.assertEqual(self.calls, ["activate", "disable", "reload"])
        self.assertTrue(all(not p.exists() for p in self.paths.values()))

    def test_failed_live_verification_is_rolled_back(self):
        def fail():
            self.calls.append("verify")
            raise RuntimeError("wrong vmnet address")
        with self.assertRaisesRegex(HostaddrInstallError, "rolled back"):
            self.apply(verify=fail)
        self.assertEqual(self.calls, ["activate", "verify", "disable", "reload"])
        self.assertTrue(all(not p.exists() for p in self.paths.values()))

    def test_foreign_edit_prevents_destructive_cleanup(self):
        lease = self.apply()
        self.paths["timer"].write_text("foreign timer")
        with self.assertRaisesRegex(HostaddrInstallError, "Manual reconciliation"):
            lease.rollback()
        self.assertEqual(self.paths["timer"].read_text(), "foreign timer")

    def test_failed_timer_disable_keeps_installed_units(self):
        def disable():
            raise RuntimeError("systemd did not stop")
        lease = install_owned_address_assets(
            self.layout, self.paths, lambda: None, disable, lambda: None,
            lambda: None, owner_uid=os.getuid(),
        )
        with self.assertRaisesRegex(HostaddrInstallError, "unable to stop"):
            lease.rollback()
        self.assertTrue(all(p.exists() for p in self.paths.values()))

    def test_unsafe_directory_and_missing_asset_paths_are_blocked(self):
        with self.assertRaisesRegex(HostaddrInstallError, "incomplete"):
            install_owned_address_assets(
                self.layout, {"helper": self.paths["helper"]},
                lambda: None, lambda: None, lambda: None, lambda: None,
                owner_uid=os.getuid(),
            )
        with self.assertRaisesRegex(HostaddrInstallError, "Unsafe"):
            install_owned_address_assets(
                self.layout, self.paths, lambda: None, lambda: None,
                lambda: None, lambda: None, owner_uid=-1,
            )


if __name__ == "__main__":
    unittest.main()
