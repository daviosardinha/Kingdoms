"""Timeout regressions: an inherited process group must not kill a VMware VM."""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def provider_class(namespace):
    path = ROOT / 'goad/provider/vagrant/vmware_kingdoms.py'
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    namespace.update(GoadNomadVmwareProvider=object, re=re, signal=signal)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['GoadKingdomsVmwareProvider']


class ProcessError(Exception):
    pass


class ProcessGone(ProcessError):
    pass


class FakeProcess:
    def __init__(self, table, pid):
        self.table, self.pid = table, pid
        self.row()

    def row(self):
        if self.pid not in self.table.rows:
            raise ProcessGone(self.pid)
        return self.table.rows[self.pid]

    def create_time(self):
        return self.row().created

    def exe(self):
        if self.row().denied:
            raise ProcessError('access denied')
        return '/test/bin/' + self.row().name

    def ppid(self):
        return self.row().parent

    def status(self):
        return self.row().status

    def send_signal(self, sig):
        self.table.signals.append((self.pid, sig))
        if sig not in self.row().ignore:
            del self.table.rows[self.pid]


class ProcessTable:
    def __init__(self):
        self.rows, self.signals = {}, []
        self.psutil = SimpleNamespace(
            pids=lambda: list(self.rows), Process=lambda pid: FakeProcess(self, pid),
            STATUS_ZOMBIE='zombie', Error=ProcessError, NoSuchProcess=ProcessGone,
        )

    def add(self, pid, name, parent=100, group=100, **kwargs):
        row = dict(name=name, parent=parent, group=group, created=float(pid),
                   denied=False, status='running', ignore=())
        row.update(kwargs)
        self.rows[pid] = SimpleNamespace(**row)

    def group(self, pid):
        if pid not in self.rows:
            raise ProcessLookupError(pid)
        return self.rows[pid].group


class TimeoutCleanupTests(unittest.TestCase):
    def setUp(self):
        self.table = ProcessTable()
        self.table.add(100, 'ruby', parent=1)
        self.table.add(101, 'vmrun')
        self.table.add(102, 'vmware-vmx')
        self.table.add(103, 'bash', parent=102)  # VM helper, not a controller
        self.table.add(201, 'ruby', parent=1, group=201)  # unrelated operation
        self.clock = SimpleNamespace(now=0)
        self.clock.monotonic = lambda: self.clock.now
        self.clock.sleep = lambda duration: setattr(self.clock, 'now', self.clock.now + duration)
        self.child = Mock(pid=100)
        self.child.poll.side_effect = lambda: None if 100 in self.table.rows else -15
        self.child.wait.side_effect = subprocess.TimeoutExpired('vagrant', 600)
        self.subprocess = Mock()
        self.subprocess.Popen.return_value = self.child
        self.subprocess.TimeoutExpired = subprocess.TimeoutExpired
        self.log = Mock()
        cls = provider_class(dict(
            psutil=self.table.psutil, os=SimpleNamespace(path=os.path, getpgid=self.table.group),
            time=self.clock, subprocess=self.subprocess, Log=self.log,
        ))
        self.provider = cls()
        self.provider.command = SimpleNamespace(vagrant_bin='vagrant')
        self.provider.path = '/provider'

    def run_timeout(self):
        return self.provider._run_vagrant_bounded(['up', 'GOAD-SRV02', '--provision'], 600)

    def test_timeout_reaps_controller_and_helper_but_preserves_vm_and_unrelated_work(self):
        self.assertFalse(self.run_timeout())  # cleanup cannot turn a failed up into success
        self.assertTrue(self.provider._last_bounded_vagrant_reaped)
        self.assertEqual(set(self.table.rows), {102, 103, 201})
        self.assertEqual(self.table.signals, [(100, signal.SIGTERM), (101, signal.SIGTERM)])

    def test_forced_cleanup_targets_only_controllers_that_ignore_term(self):
        self.table.rows[101].ignore = (signal.SIGTERM,)
        self.assertFalse(self.run_timeout())
        self.assertTrue(self.provider._last_bounded_vagrant_reaped)
        self.assertEqual(set(self.table.rows), {102, 103, 201})
        self.assertEqual(self.table.signals[-1], (101, signal.SIGKILL))

    def test_unknown_process_blocks_cleanup_and_subsequent_bringup(self):
        self.table.add(104, 'unidentified-helper')
        self.assertFalse(self.run_timeout())
        self.assertFalse(self.provider._last_bounded_vagrant_reaped)
        self.assertEqual(self.table.signals, [])
        self.assertFalse(self.run_timeout())
        self.subprocess.Popen.assert_called_once()
        self.provider.lab_name = 'GOAD'
        self.provider.prepare_install = Mock()
        self.assertFalse(self.provider.install())
        self.provider.prepare_install.assert_not_called()

    def test_unreadable_process_never_triggers_a_broad_kill(self):
        self.table.rows[102].denied = True
        self.assertFalse(self.run_timeout())
        self.assertFalse(self.provider._last_bounded_vagrant_reaped)
        self.assertEqual(self.table.signals, [])

    def test_pid_reuse_during_cleanup_is_not_signaled(self):
        original = self.provider._signal_vagrant_controller
        def replace(pid, identity, pgid, sig):
            self.table.rows[pid].created += 1
            return original(pid, identity, pgid, sig)
        self.provider._signal_vagrant_controller = replace
        self.assertFalse(self.run_timeout())
        self.assertFalse(self.provider._last_bounded_vagrant_reaped)
        self.assertEqual(self.table.signals, [])

    def test_helper_that_execs_vm_monitor_before_signal_is_preserved(self):
        original = self.provider._signal_vagrant_controller
        def replace(pid, identity, pgid, sig):
            self.table.rows[pid].name = 'vmware-vmx'
            return original(pid, identity, pgid, sig)
        self.provider._signal_vagrant_controller = replace
        self.assertFalse(self.run_timeout())
        self.assertFalse(self.provider._last_bounded_vagrant_reaped)
        self.assertEqual(self.table.signals, [])

    def test_process_that_moves_out_of_group_before_signal_is_not_touched(self):
        original = self.provider._signal_vagrant_controller
        def move(pid, identity, pgid, sig):
            self.table.rows[pid].group = 999
            return original(pid, identity, pgid, sig)
        self.provider._signal_vagrant_controller = move
        self.assertFalse(self.run_timeout())
        self.assertFalse(self.provider._last_bounded_vagrant_reaped)
        self.assertEqual(self.table.signals, [])

    def test_new_controller_child_is_found_after_leader_exits(self):
        original_sleep = self.clock.sleep
        def spawn(duration):
            if self.clock.now == 0:
                self.table.add(104, 'ruby3.3', parent=1)
            original_sleep(duration)
        self.clock.sleep = spawn
        self.assertFalse(self.run_timeout())
        self.assertTrue(self.provider._last_bounded_vagrant_reaped)
        self.assertIn((104, signal.SIGTERM), self.table.signals)
        self.assertEqual(set(self.table.rows), {102, 103, 201})

    def test_vm_descendant_remains_protected_after_reparenting(self):
        self.table.rows[101].ignore = (signal.SIGTERM,)
        original_sleep = self.clock.sleep
        def reparent(duration):
            self.table.rows[103].parent = 1
            original_sleep(duration)
        self.clock.sleep = reparent
        self.assertFalse(self.run_timeout())
        self.assertTrue(self.provider._last_bounded_vagrant_reaped)
        self.assertIn(103, self.table.rows)
        self.assertFalse(any(pid == 103 for pid, _ in self.table.signals))

    def test_surviving_controller_leaves_cleanup_incomplete(self):
        self.table.rows[101].ignore = (signal.SIGTERM, signal.SIGKILL)
        self.assertFalse(self.run_timeout())
        self.assertFalse(self.provider._last_bounded_vagrant_reaped)
        self.assertIn(102, self.table.rows)
        self.assertLess(self.clock.now, 11)

    def test_zombie_helper_does_not_block_cleanup(self):
        self.table.rows[101].status = 'zombie'
        self.assertFalse(self.run_timeout())
        self.assertTrue(self.provider._last_bounded_vagrant_reaped)
        self.assertEqual(self.table.signals, [(100, signal.SIGTERM)])

    def test_missing_but_still_live_leader_is_not_declared_reaped(self):
        self.table.rows[100].group = 200
        self.assertFalse(self.run_timeout())
        self.assertFalse(self.provider._last_bounded_vagrant_reaped)

    def test_completed_command_never_enters_cleanup(self):
        self.child.wait.side_effect = None
        self.child.wait.return_value = 0
        self.assertTrue(self.run_timeout())
        self.assertEqual(self.table.signals, [])


class VMwareShutdownGraceTests(unittest.TestCase):
    def setUp(self):
        self.subprocess = SimpleNamespace(
            run=Mock(),
            PIPE=subprocess.PIPE,
            TimeoutExpired=subprocess.TimeoutExpired,
        )
        self.log = Mock()
        cls = provider_class(dict(
            psutil=Mock(),
            os=os,
            time=time,
            subprocess=self.subprocess,
            Log=self.log,
        ))
        self.provider = cls()
        self.provider._vmx_path = Mock(return_value='/tmp/GOAD-SRV02.vmx')
        self.provider._running_instance_vms = Mock(return_value=['GOAD-SRV02'])

    def test_soft_stop_timeout_gets_full_guest_grace_before_hard_fallback(self):
        self.subprocess.run.side_effect = subprocess.TimeoutExpired(
            cmd=['vmrun', 'stop'], timeout=45
        )
        self.provider._wait_machine_stopped = Mock(return_value=True)

        self.assertTrue(self.provider._stop_machine_via_vmware('GOAD-SRV02'))

        self.provider._wait_machine_stopped.assert_called_once_with(
            'GOAD-SRV02', 120
        )
        self.assertEqual(self.subprocess.run.call_count, 1)
        self.log.warning.assert_any_call(
            'GOAD Kingdoms: VMware soft-stop host command timed out for '
            'GOAD-SRV02; the guest may still be shutting down, allowing up to '
            '120s before hard fallback'
        )

    def test_hard_stop_remains_last_resort_after_guest_grace_expires(self):
        self.subprocess.run.side_effect = [
            subprocess.TimeoutExpired(cmd=['vmrun', 'stop'], timeout=45),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
        ]
        self.provider._wait_machine_stopped = Mock(side_effect=[False, True])

        self.assertTrue(self.provider._stop_machine_via_vmware('GOAD-SRV02'))

        self.assertEqual(self.subprocess.run.call_count, 2)
        hard_call = self.subprocess.run.call_args_list[1]
        self.assertEqual(
            hard_call.args[0],
            ['vmrun', '-T', 'ws', 'stop', '/tmp/GOAD-SRV02.vmx', 'hard'],
        )
        self.assertEqual(
            self.provider._wait_machine_stopped.call_args_list[0].args,
            ('GOAD-SRV02', 120),
        )
        self.assertEqual(
            self.provider._wait_machine_stopped.call_args_list[1].args,
            ('GOAD-SRV02', 30),
        )


class KingdomsSnapshotResetTests(unittest.TestCase):
    def setUp(self):
        self.log = Mock()
        cls = provider_class(dict(
            psutil=Mock(),
            os=os,
            time=time,
            subprocess=Mock(),
            Log=self.log,
        ))
        self.provider = cls()
        self.provider.lab_name = 'GOAD'
        self.provider._last_bounded_vagrant_reaped = True
        self.provider._run_vagrant_bounded = Mock(return_value=True)
        self.provider._running_instance_vms = Mock(return_value=[])

    def test_reset_restores_snapshot_without_starting_guests(self):
        self.assertTrue(self.provider.reset())

        self.provider._run_vagrant_bounded.assert_called_once_with(
            ['snapshot', 'pop', '--no-delete', '--no-start'],
            timeout=900,
        )
        self.provider._running_instance_vms.assert_called_once_with()

    def test_reset_fails_if_vagrant_started_any_restored_guest(self):
        self.provider._running_instance_vms.return_value = ['GOAD-DC01']

        self.assertFalse(self.provider.reset())
        self.log.error.assert_any_call(
            'GOAD Kingdoms: snapshot restore violated --no-start; '
            'restored guests are already running: GOAD-DC01'
        )

    def test_reset_does_not_claim_success_when_snapshot_restore_fails(self):
        self.provider._run_vagrant_bounded.return_value = False

        self.assertFalse(self.provider.reset())
        self.provider._running_instance_vms.assert_not_called()


class LiveProcessCleanupTests(unittest.TestCase):    def test_vm_monitor_in_inherited_group_survives_real_controller_cleanup(self):
        try:
            import psutil
        except ImportError:
            self.skipTest('live process regression requires the existing GOAD psutil dependency')
        if os.name != 'posix' or not shutil.which('sleep'):
            self.skipTest('live process regression requires POSIX and sleep')
        try:
            psutil.Process(os.getpid()).exe()
        except psutil.Error:
            self.skipTest('this runtime cannot inspect its own OS process')

        cls = provider_class(dict(psutil=psutil, os=os, time=time, subprocess=subprocess, Log=Mock()))
        provider = cls()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vmx, vmrun = root / 'vmware-vmx', root / 'vmrun'
            for executable in (vmx, vmrun):
                shutil.copy2(shutil.which('sleep'), executable)
            ready = root / 'children.json'
            script = (
                'import json, subprocess, sys, time\n'
                'from pathlib import Path\n'
                'vm = subprocess.Popen([sys.argv[1], "30"])\n'
                'helper = subprocess.Popen([sys.argv[2], "30"])\n'
                'ready = Path(sys.argv[3])\n'
                'pending = ready.with_suffix(".tmp")\n'
                'pending.write_text(json.dumps([vm.pid, helper.pid]))\n'
                'pending.replace(ready)\n'
                'time.sleep(30)\n'
            )
            child = subprocess.Popen(
                [sys.executable, '-c', script, str(vmx), str(vmrun), str(ready)],
                start_new_session=True, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            owned = [psutil.Process(child.pid)]
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(ready.exists(), 'simulated Vagrant did not start its helpers')
                vm_pid, helper_pid = json.loads(ready.read_text())
                owned.extend([psutil.Process(vm_pid), psutil.Process(helper_pid)])
                self.assertEqual(os.getpgid(vm_pid), child.pid)
                self.assertEqual(os.getpgid(helper_pid), child.pid)
                self.assertTrue(provider._reap_vagrant_controller(child, ['simulated-vagrant']))
                self.assertIsNotNone(child.poll())
                self.assertTrue(owned[1].is_running())
                self.assertNotEqual(owned[1].status(), psutil.STATUS_ZOMBIE)
                try:
                    helper_running = owned[2].is_running() and owned[2].status() != psutil.STATUS_ZOMBIE
                except psutil.NoSuchProcess:
                    helper_running = False
                self.assertFalse(helper_running)
            finally:
                for proc in owned:
                    try:
                        proc.kill()
                    except psutil.NoSuchProcess:
                        pass
                child.wait(timeout=5)
                psutil.wait_procs(owned, timeout=2)


if __name__ == '__main__':
    unittest.main()
