"""NORTH snapshot restore safety regressions; no VM or host writes."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from goad.course1_snapshot_restore import (
    NORTH_VMS, NorthSnapshotRestoreError,
    restore_north_offline_snapshots, select_north_snapshot_targets,
)


class SnapshotVmwareFixture:
    def __init__(self, root):
        self.provider = Path(root) / "93fd1b-north-vmware" / "provider"
        self.provider.mkdir(parents=True)
        self.paths = {}
        self.results = []
        self.running = set()
        self.names = {}
        for i, name in enumerate(NORTH_VMS):
            parent = self.provider / ".vagrant" / "machines" / name / "vmware_desktop"
            vmx_dir = parent / "uuid123"
            vmx_dir.mkdir(parents=True)
            vmx = vmx_dir / "guest.vmx"
            vmx.write_text('ethernet0.startConnected = "FALSE"\n')
            (parent / "id").write_text(str(vmx))
            self.paths[name] = str(vmx)
            self.names[str(vmx)] = [
                f"push_{1792834947+i}_{600+i}",
                f"push_{1792835371+i}_{900+i}",
            ]
    def lookup(self, machine):
        return self.paths[machine]
    def __call__(self, command, **kwargs):
        self.results.append(command)
        if command[:3] != ["vmrun", "-T", "ws"]:
            raise AssertionError(f"Non-VMware command issued: {command}")
        action = command[3]
        if action == "list":
            stdout = (f"Total running VMs: {len(self.running)}\n" +
                      "".join(p + "\n" for p in sorted(self.running)))
        elif action == "listSnapshots":
            stdout = f"Total snapshots: {len(self.names[command[4]])}\n"
            stdout += "".join(name + "\n" for name in self.names[command[4]])
        elif action == "revertToSnapshot":
            if command[5] not in self.names[command[4]]:
                return subprocess.CompletedProcess(command, 1, "", "not found")
            stdout = ""
        else:
            raise AssertionError(f"Unexpected VMware action: {command}")
        return subprocess.CompletedProcess(command, 0, stdout, "")


class NorthExactOfflineSnapshotTests(unittest.TestCase):
    def test_exact_newest_snapshot_selected_for_all_five(self):
        with TemporaryDirectory() as tmp:
            fake = SnapshotVmwareFixture(tmp)
            selected = select_north_snapshot_targets(
                fake.provider, fake.lookup, runner=fake
            )
            self.assertEqual([r[0] for r in selected], list(NORTH_VMS))
            for machine, vmx, newest in selected:
                self.assertEqual(newest, fake.names[vmx][-1])
            self.assertFalse(any("revertToSnapshot" in c for c in fake.results))

    def test_restore_latest_only_offline_and_without_vagrant(self):
        with TemporaryDirectory() as tmp:
            fake = SnapshotVmwareFixture(tmp)
            notes = []
            self.assertTrue(restore_north_offline_snapshots(
                fake.provider, fake.lookup, runner=fake, log=notes.append
            ))
            applied = [cmd for cmd in fake.results if cmd[3] == "revertToSnapshot"]
            self.assertEqual(len(applied), 5)
            for cmd in applied:
                self.assertEqual(cmd[5], fake.names[cmd[4]][-1])
            self.assertEqual(len(notes), 10)

    def test_missing_second_generation_refuses_all_vm_writes(self):
        with TemporaryDirectory() as tmp:
            fake = SnapshotVmwareFixture(tmp)
            vmx = fake.paths["GOAD-WS01"]
            fake.names[vmx].pop()
            with self.assertRaisesRegex(NorthSnapshotRestoreError, "counts disagree"):
                restore_north_offline_snapshots(fake.provider, fake.lookup, runner=fake)
            self.assertFalse(any(c[3] == "revertToSnapshot" for c in fake.results))

    def test_newest_snapshot_gap_refuses_mixed_generation(self):
        with TemporaryDirectory() as tmp:
            fake = SnapshotVmwareFixture(tmp)
            vmx = fake.paths["GOAD-WS01"]
            fake.names[vmx][-1] = "push_1792849001_3333"
            with self.assertRaisesRegex(NorthSnapshotRestoreError, "do not align"):
                restore_north_offline_snapshots(fake.provider, fake.lookup, runner=fake)
            self.assertFalse(any(c[3] == "revertToSnapshot" for c in fake.results))

    def test_running_machine_refused_before_any_revert(self):
        with TemporaryDirectory() as tmp:
            fake = SnapshotVmwareFixture(tmp)
            fake.running.add(fake.paths["GOAD-DC02"])
            with self.assertRaisesRegex(NorthSnapshotRestoreError, "running"):
                restore_north_offline_snapshots(fake.provider, fake.lookup, runner=fake)
            self.assertFalse(any(c[3] == "revertToSnapshot" for c in fake.results))

    def test_foreign_or_missing_vmx_refused(self):
        with TemporaryDirectory() as tmp:
            fake = SnapshotVmwareFixture(tmp)
            orig = fake.paths["GOAD-WS01"]
            foreign = str(Path(tmp) / "foreign.vmx")
            Path(foreign).write_text('guest')
            fake.paths["GOAD-WS01"] = foreign
            with self.assertRaisesRegex(NorthSnapshotRestoreError, "Foreign or missing VMX"):
                select_north_snapshot_targets(fake.provider, fake.lookup, runner=fake)
            fake.paths["GOAD-WS01"] = orig
            Path(orig).unlink()
            with self.assertRaisesRegex(NorthSnapshotRestoreError, "Foreign or missing VMX"):
                select_north_snapshot_targets(fake.provider, fake.lookup, runner=fake)

    def test_partial_failure_is_fail_closed_no_remaining_reverts(self):
        with TemporaryDirectory() as tmp:
            fake = SnapshotVmwareFixture(tmp)
            def fail_second(command, **kw):
                if command[3] == "revertToSnapshot" and command[4] == fake.paths["GOAD-DC01"]:
                    fake.results.append(command)
                    return subprocess.CompletedProcess(command, 1, "", "locked")
                return fake(command, **kw)
            with self.assertRaisesRegex(NorthSnapshotRestoreError, "locked"):
                restore_north_offline_snapshots(fake.provider, fake.lookup, runner=fail_second)
            applied = [c for c in fake.results if c[3] == "revertToSnapshot"]
            self.assertEqual(len(applied), 2)
            self.assertFalse(any(c[4] == fake.paths["GOAD-WS01"] for c in applied))

    def test_provider_north_uses_direct_restore_full_kingdoms_retains_legacy(self):
        repo = Path(__file__).resolve().parents[1]
        source = (repo / "goad/provider/vagrant/vmware_kingdoms.py").read_text()
        self.assertIn("if self.lab_name == 'NORTH':\n            # Vagrant pop", source)
        self.assertIn("restore_north_offline_snapshots(", source)
        self.assertIn("['snapshot', 'pop', '--no-delete', '--no-start']", source)
        self.assertIn("if not self._restore_exercise_nic_contract_offline():", source)


if __name__ == "__main__":
    unittest.main()
