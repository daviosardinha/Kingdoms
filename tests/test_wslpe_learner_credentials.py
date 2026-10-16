"""WSLPE-only local learner credential lifecycle, no Windows/network changes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import stat
import unittest

from kingdoms.wslpe_learner_credentials import (
    ENV, USERNAME, learner_password, read_local_access,
)

class WslpeLearnerCredentialsTests(unittest.TestCase):
    def test_generate_once_reuse_noninteractive_and_show_explicit(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "learner" / "credential"
            password = learner_password(bootstrap=True, path=path, environ={})
            self.assertEqual(len(password), 32)
            self.assertTrue(any(x.isupper() for x in password))
            self.assertTrue(any(x.islower() for x in password))
            self.assertTrue(any(x.isdigit() for x in password))
            self.assertTrue(any(not x.isalnum() for x in password))
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(learner_password(bootstrap=False, path=path, environ={}), password)
            self.assertEqual(read_local_access(path=path), (USERNAME, password))

    def test_without_bootstrap_or_env_does_not_create_password(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "learner" / "credential"
            with self.assertRaisesRegex(ValueError, "bootstrap-learner"):
                learner_password(bootstrap=False, path=path, environ={})
            self.assertFalse(path.exists())

    def test_manual_secret_can_be_supplied_and_reused_but_not_rotated(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "learner" / "credential"
            user_secret = "ExampleTemporary!Password45"
            self.assertEqual(learner_password(bootstrap=True, path=path,
                                              environ={ENV:user_secret}), user_secret)
            self.assertEqual(learner_password(bootstrap=False, path=path,
                                              environ={ENV:user_secret}), user_secret)
            with self.assertRaisesRegex(ValueError, "no password rotation"):
                learner_password(bootstrap=True, path=path,
                                 environ={ENV:"OtherSecure!Password678"})
            self.assertEqual(read_local_access(path=path)[1], user_secret)

    def test_existing_symlink_or_unsafe_permissions_are_rejected(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp) / "learner"
            path = folder / "credential"
            learner_password(bootstrap=True, path=path, environ={})
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "0600"):
                learner_password(bootstrap=False, path=path, environ={})
            path.chmod(0o600)
            folder.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "0700"):
                learner_password(bootstrap=False, path=path, environ={})
            folder.chmod(0o700)
            linked = folder / "linked"
            linked.symlink_to(path)
            with self.assertRaises(ValueError):
                learner_password(bootstrap=False, path=linked, environ={})

    def test_environment_password_must_have_minimum_strength(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "credential"
            for bad in ("short", "a"*12+"\n", ""):
                if not bad:
                    continue
                with self.subTest(bad=repr(bad)), self.assertRaises(ValueError):
                    learner_password(bootstrap=True, path=path, environ={ENV:bad})

if __name__ == "__main__":
    unittest.main()
