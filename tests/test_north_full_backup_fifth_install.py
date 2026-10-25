"""Source-only coverage: full offline backup and fifth clean install safety."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from goad import course1_full_backup as backup

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/north-fifth-clean-install.sh"


class FullOfflineBackupTests(unittest.TestCase):
    def fixture(self, tmp):
        root = Path(tmp) / "Kingdoms"
        inst = root / "workspace" / backup.OLD
        provider = inst / "provider"
        provider.mkdir(parents=True)
        (inst / "instance.json").write_text(json.dumps({
            "id": backup.OLD, "lab": "NORTH", "provider": "vmware",
            "status": "installed"
        }))
        (provider / ".goad-nomad-mode").write_text("exercise\n")
        vmxs = {}
        for name in backup.GUESTS:
            machine = provider / ".vagrant/machines" / name / "vmware_desktop"
            machine.mkdir(parents=True)
            vmx = machine / (name + ".vmx")
            vmx.write_text('displayName = "' + name + '"\n')
            (machine / (name + "-flat.vmdk")).write_bytes(b"original-disk")
            (machine / (name + "-Snapshot1.vmsn")).write_bytes(b"snapshot")
            (machine / "id").write_text(str(vmx))
            vmxs[name] = str(vmx)
        home = Path(tmp) / "home"
        (home / ".vagrant.d/boxes/original").mkdir(parents=True)
        (home / ".vagrant.d/boxes/original/disk.vmdk").write_bytes(b"base box")
        return root, inst, home, vmxs

    def test_identical_vm_registrations_are_proven_before_shutdown(self):
        with TemporaryDirectory() as d:
            root, inst, _, vmxs = self.fixture(d)
            with patch.object(backup, "running_vms",
                              return_value=set(vmxs.values())):
                self.assertEqual(backup.preflight(root)[0], inst)
            with patch.object(backup, "running_vms", return_value=set()):
                with self.assertRaises(backup.BackupBlocked):
                    backup.preflight(root)
                self.assertEqual(backup.offline(root)[0], inst)
            with patch.object(backup, "running_vms",
                              return_value=set(vmxs.values()) | {"/foreign.vmx"}):
                with self.assertRaises(backup.BackupBlocked):
                    backup.preflight(root)

    def test_registered_foreign_powered_off_guest_cannot_share_north_vmnets(self):
        with TemporaryDirectory() as d:
            root, _, home, vmxs = self.fixture(d)
            ui = home / ".vmware"
            ui.mkdir()
            guest = home / "other-range.vmx"
            guest.write_text('ethernet1.vnet = "vmnet10"\n')
            (ui / "inventory.vmls").write_text(
                'vmlist4.config = "' + str(guest) + '"\n'
            )
            with patch.object(Path, "home", return_value=home), \
                 patch.object(backup, "running_vms", return_value=set(vmxs.values())), \
                 self.assertRaises(backup.BackupBlocked):
                backup.preflight(root)
            guest.write_text('ethernet1.vnet = "vmnet2"\n')
            with patch.object(Path, "home", return_value=home), \
                 patch.object(backup, "running_vms", return_value=set(vmxs.values())):
                backup.preflight(root)

    def test_full_backup_sha256_mismatch_or_missing_disk_blocks(self):
        with TemporaryDirectory() as d:
            root, inst, home, _ = self.fixture(d)
            archive = Path(d) / "safe-backup"
            archive.mkdir()
            shutil.copytree(inst, archive / "instance", symlinks=True)
            shutil.copytree(home / ".vagrant.d", archive / "vagrant-home", symlinks=True)
            with patch.object(backup, "running_vms", return_value=set()), \
                 patch.object(Path, "home", return_value=home):
                backup.verify_copy(root, archive)
            self.assertTrue((archive / "instance-sha256-manifest.json").is_file())
            self.assertTrue((archive / "vagrant-home-sha256-manifest.json").is_file())
            (archive / "instance-sha256-manifest.json").unlink()
            (archive / "vagrant-home-sha256-manifest.json").unlink()
            guest = archive / "instance" / "provider" / ".vagrant/machines" / backup.GUESTS[0] / "vmware_desktop"
            (guest / (backup.GUESTS[0] + "-flat.vmdk")).write_bytes(b"tampered")
            with patch.object(backup, "running_vms", return_value=set()), \
                 patch.object(Path, "home", return_value=home), \
                 self.assertRaises(backup.BackupBlocked):
                backup.verify_copy(root, archive)

    def test_post_destroy_does_not_require_deleted_guest_registrations(self):
        with TemporaryDirectory() as d:
            root, inst, _, _ = self.fixture(d)
            for machine in backup.GUESTS:
                shutil.rmtree(inst / "provider/.vagrant/machines" / machine)
            with patch.object(backup, "running_vms", return_value=set()):
                backup.post_destroy(root)

    def test_deleting_old_workspace_requires_offline_and_backup_marker(self):
        with TemporaryDirectory() as d:
            root, inst, home, _ = self.fixture(d)
            dest = Path(d) / "saved"
            dest.mkdir()
            (dest / "instance").mkdir()
            shutil.copy2(inst / "instance.json", dest / "instance/instance.json")
            for machine in backup.GUESTS:
                shutil.rmtree(inst / "provider/.vagrant/machines" / machine)
            with patch.object(backup, "running_vms", return_value=set()), \
                 self.assertRaises(backup.BackupBlocked):
                backup.delete_old_workspace(root, dest)
            (dest / "backup-verified.marker").write_text("verified")
            with patch.object(backup, "running_vms", return_value=set()):
                backup.delete_old_workspace(root, dest)
            self.assertFalse(inst.exists())

    def test_runner_explicitly_refuses_no_confirmation(self):
        for args in ([], ["--run"],
                     ["--run", "--wrong-confirmation"]):
            p = subprocess.run(["bash", str(RUNNER), *args],
                               text=True, capture_output=True)
            self.assertEqual(p.returncode, 2)
            self.assertIn("confirm-retire-installed-north-after-backup", p.stderr)

    def test_shell_syntax_and_ordered_guarded_destructive_phases(self):
        p = subprocess.run(["bash", "-n", str(RUNNER)],
                           text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        src = RUNNER.read_text()
        required = [
            "verify-test-source.sh",
            "helper preflight", # check inside source for helpers
        ]
        self.assertIn('goad.course1_full_backup preflight', src)
        self.assertIn('stage 02-offline-stop', src)
        self.assertIn('stage 03-confirm-offline helper offline', src)
        self.assertIn('stage 04-space-preflight helper space', src)
        self.assertIn('stage 10-byte-verify helper verify-copy', src)
        self.assertIn('BACKUP_VERIFIED=1', src)
        self.assertIn('stage 13-destroy-original', src)
        self.assertIn('stage 15-retirement-plan', src)
        self.assertIn('stage 16-retire-owned-vmnets', src)
        self.assertIn('stage 18-fifth-fresh-install', src)
        self.assertIn('stage 20-new-runtime-validation', src)
        self.assertLess(src.index('stage 10-byte-verify'),
                        src.index('stage 13-destroy-original'))
        self.assertLess(src.index('BACKUP_VERIFIED=1'),
                        src.index('stage 13-destroy-original'))
        self.assertLess(src.index('stage 13-destroy-original'),
                        src.index('stage 16-retire-owned-vmnets'))
        self.assertIn('rsync -aH --sparse', src)
        self.assertIn('git bundle create', src)
        self.assertIn('NORTH_UNINTERRUPTED_FIFTH_INSTALL_AND_RUNTIME=PASS', src)
        self.assertNotIn("vagrant snapshot pop", src)
        self.assertNotIn("-t reset", src)
        self.assertNotIn("rm -rf", src)


if __name__ == "__main__":
    unittest.main()
