"""NORTH installs must serialize before sudo and provider/VM changes."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from goad_nomad import GoadNomad


class NorthExclusiveInstallTests(unittest.TestCase):
    def console(self, path, lab="NORTH"):
        obj = GoadNomad.__new__(GoadNomad)
        obj.lab_manager = Mock()
        obj.lab_manager.get_current_lab_name.return_value = lab
        obj._north_install_lock_path = lambda: path
        return obj

    def test_two_north_installers_cannot_acquire_same_host_lock(self):
        with TemporaryDirectory() as d:
            lock = Path(d) / ".north-install-exclusive.lock"
            first, second = self.console(lock), self.console(lock)
            fd = first._acquire_north_install_lock()
            self.assertIsInstance(fd, int)
            self.assertGreaterEqual(fd, 0)
            try:
                self.assertEqual(second._acquire_north_install_lock(), -1)
                self.assertEqual(lock.read_text(), str(os.getpid())+"\n")
                self.assertEqual(lock.stat().st_mode & 0o777, 0o600)
            finally:
                os.close(fd)
            nextfd = second._acquire_north_install_lock()
            self.assertGreaterEqual(nextfd, 0)
            os.close(nextfd)

    def test_lock_held_through_operation_and_released_even_on_exception(self):
        with TemporaryDirectory() as d:
            lock = Path(d) / "lock"
            a,b = self.console(lock),self.console(lock)
            def observe():
                self.assertEqual(b._acquire_north_install_lock(), -1)
                return True
            a._run_with_install_timer_locked = Mock(side_effect=observe)
            self.assertTrue(a._run_with_install_timer(lambda: True))
            fd = b._acquire_north_install_lock()
            self.assertGreaterEqual(fd,0)
            os.close(fd)
            a._run_with_install_timer_locked.side_effect = RuntimeError("installer crashed")
            with self.assertRaisesRegex(RuntimeError, "installer crashed"):
                a._run_with_install_timer(lambda: False)
            fd=b._acquire_north_install_lock()
            self.assertGreaterEqual(fd,0)
            os.close(fd)

    def test_busy_lock_returns_before_sudo_or_installer_operation(self):
        with TemporaryDirectory() as d:
            lock=Path(d)/"lock"
            a,b=self.console(lock),self.console(lock)
            fd=a._acquire_north_install_lock()
            called=Mock()
            b._run_with_install_timer_locked=called
            try:
                self.assertFalse(b._run_with_install_timer(lambda: True))
                called.assert_not_called()
            finally:
                os.close(fd)

    def test_foreign_labs_are_not_locked_by_north_only_gate(self):
        with TemporaryDirectory() as d:
            path=Path(d)/"lock"
            obj=self.console(path, lab="KINGDOMS")
            self.assertIsNone(obj._acquire_north_install_lock())
            self.assertFalse(path.exists())

    def test_symlinked_lock_is_rejected(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            target=root/"other"
            target.write_text("unchanged")
            lock=root/"lock"
            lock.symlink_to(target)
            obj=self.console(lock)
            self.assertEqual(obj._acquire_north_install_lock(),-1)
            self.assertEqual(target.read_text(),"unchanged")

    def test_sudo_reuses_ticket_or_prompts_once_without_invalidation(self):
        obj=self.console(Path("/unused"))
        with patch.object(obj,"_nomad_provider",return_value=object()):
            for initial in (0,1):
                calls=[]
                def run(args,**kwargs):
                    calls.append(list(args))
                    return SimpleNamespace(returncode=initial if len(calls)==1 else 0)
                stop=threading.Event()
                with patch("goad_nomad.subprocess.run",side_effect=run):
                    ok,lost,thread=obj._start_install_sudo_keepalive(stop)
                    self.assertTrue(ok)
                    self.assertIsNotNone(lost)
                    stop.set()
                    thread.join(timeout=1)
                self.assertEqual(calls[0],["sudo","-n","-v"])
                self.assertEqual(len(calls), 1 if initial==0 else 2)
                self.assertNotIn(["sudo","-k"],calls)
                if initial:
                    self.assertEqual(calls[1],["sudo","-v"])


if __name__=="__main__":
    unittest.main()
