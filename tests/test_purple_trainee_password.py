"""Offline tests for host-private PURPLE-LX01 fixed-password lifecycle."""
from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "purple_trainee_password",
    ROOT / "scripts/purple-trainee-password.py",
)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
FAKE_HASH = "$6$abcdefghij012345$" + "A" * 86


class TraineePasswordTests(unittest.TestCase):
    def test_hash_format_rejects_plaintext_and_unrecognized_formats(self):
        self.assertTrue(helper.SHA512_CRYPT.fullmatch(FAKE_HASH))
        self.assertFalse(helper.SHA512_CRYPT.fullmatch("plain-text-password"))
        self.assertFalse(helper.SHA512_CRYPT.fullmatch("$1$salt$not-sha512"))
        self.assertFalse(helper.SHA512_CRYPT.fullmatch(FAKE_HASH + " extra"))

    def test_init_is_private_and_idempotent_without_printing_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "kingdoms" / "purple-lx01-trainee.sha512"
            with patch.object(helper, "HASH_PATH", dest), \
                 patch.object(helper.getpass, "getpass", side_effect=["StrongOpaqueTestPw!42"] * 2), \
                 patch.object(helper.subprocess, "run", return_value=SimpleNamespace(stdout=FAKE_HASH + "\n")):
                output = io.StringIO()
                with redirect_stdout(output):
                    helper.init_password()
                    helper.init_password()
                self.assertTrue(dest.is_file())
                self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(dest.parent.stat().st_mode), 0o700)
                self.assertEqual(helper.check_hash_file(dest), FAKE_HASH)
                self.assertNotIn("StrongOpaqueTestPw!42", output.getvalue())
                self.assertNotIn(FAKE_HASH, output.getvalue())

    def test_secret_file_wrong_permissions_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "secret.sha512"
            p.write_text(FAKE_HASH + "\n")
            os.chmod(p, 0o644)
            with self.assertRaises(helper.PasswordConfigurationError):
                helper.check_hash_file(p)
            os.chmod(p, 0o600)
            self.assertEqual(helper.check_hash_file(p), FAKE_HASH)
            link = Path(folder) / "secret-link.sha512"
            link.symlink_to(p)
            with self.assertRaises(helper.PasswordConfigurationError):
                helper.check_hash_file(link)

    def test_existing_guest_apply_targets_only_lx01_without_plaintext(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            secret = base / "purple-lx01-trainee.sha512"
            secret.write_text(FAKE_HASH + "\n")
            os.chmod(secret, 0o600)
            provider = base / "workspace" / "ef5c0b-purple-vmware" / "provider"
            provider.mkdir(parents=True)
            (provider / "Vagrantfile").write_text(
                'Vagrant.configure("2") do |config|\n'
                'boxes = [{ :name => "PURPLE-LX01" }]\nend\n'
            )
            identity = provider / ".vagrant/machines/PURPLE-LX01/vmware_desktop/id"
            identity.parent.mkdir(parents=True)
            identity.write_text("/mock/PURPLE-LX01.vmx\n")
            executed = []
            def fake_run(command, **kwargs):
                executed.append(command)
                self.assertEqual(kwargs["cwd"], provider)
            with patch.object(helper, "HASH_PATH", secret), \
                 patch.object(helper.subprocess, "run", side_effect=fake_run):
                helper.apply_existing(provider)
            self.assertEqual(len(executed), 4)
            self.assertIn("install -d -o vagrant -g vagrant -m 0700", executed[0][-1])
            self.assertTrue(all("PURPLE-LX01" in c for c in executed))
            self.assertFalse(any("PURPLE-WS01" in str(c) or "PURPLE-C2" in str(c)
                                 for c in executed))
            self.assertFalse(any(FAKE_HASH in str(c) for c in executed))
            self.assertIn("--ensure", executed[-1][-1])
            self.assertIn("--verify", executed[-1][-1])


if __name__ == "__main__":
    unittest.main()
