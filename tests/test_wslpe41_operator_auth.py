"""Fail-closed operator HTTPS probe contract; no VMware guest required."""
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_operator_auth import authenticate_native_operator


class OperatorAuthTests(unittest.TestCase):
    def setUp(self):
        self.context = SimpleNamespace(
            instance_dir=Path("/tmp/native-instance"),
            inventory=Path("/tmp/native-instance/ansible/hosts.yml"),
            private_vars=Path("/tmp/native-instance/ansible/private.yml"),
            ansible=Path("/tmp/venv/bin/ansible-playbook"),
            expected_address="172.28.232.31",
            timeout_seconds=900,
        )
        self.env = {
            "KINGDOMS_WSLPE_OPERATOR_PASSWORD": "operator-very-long-secret-password",
            "KINGDOMS_WSLPE_LEARNER_PASSWORD": "learner-secret-password",
        }

    def test_probes_operator_over_pinned_https_without_argv_secret(self):
        def fake_run(argv, **kwargs):
            self.assertIn("ansible.windows.win_ping", argv)
            self.assertIn("ws01", argv)
            self.assertNotIn(self.env["KINGDOMS_WSLPE_OPERATOR_PASSWORD"], " ".join(argv))
            path = Path(argv[argv.index("-e") + 1][1:])
            import json
            data = json.loads(path.read_text())
            self.assertEqual(data["ansible_user"], r".\kingdom.operator")
            self.assertEqual(data["ansible_winrm_scheme"], "https")
            self.assertEqual(data["ansible_winrm_server_cert_validation"], "validate")
            self.assertEqual(data["ansible_port"], 5986)
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            return SimpleNamespace(returncode=0, stdout='ws01 | SUCCESS => {\n    "changed": false,\n    "ping": "pong"\n}')
        with patch("kingdoms.wslpe41_operator_auth._regular"), \
             patch("kingdoms.wslpe41_operator_auth.os.access", return_value=True), \
             patch("kingdoms.wslpe41_operator_auth._guest"), \
             patch("kingdoms.wslpe41_operator_auth._inventory"), \
             patch("kingdoms.wslpe41_operator_auth._environment", return_value=self.env), \
             patch("kingdoms.wslpe41_operator_auth.subprocess.run", side_effect=fake_run):
            self.assertTrue(authenticate_native_operator(self.context))

    def test_failed_authentication_blocks(self):
        with patch("kingdoms.wslpe41_operator_auth._regular"), \
             patch("kingdoms.wslpe41_operator_auth.os.access", return_value=True), \
             patch("kingdoms.wslpe41_operator_auth._guest"), \
             patch("kingdoms.wslpe41_operator_auth._inventory"), \
             patch("kingdoms.wslpe41_operator_auth._environment", return_value=self.env), \
             patch("kingdoms.wslpe41_operator_auth.subprocess.run",
                   return_value=SimpleNamespace(returncode=1, stdout="UNREACHABLE")):
            with self.assertRaises(InstallBlocked):
                authenticate_native_operator(self.context)

    def test_rejects_reused_learner_password(self):
        env = dict(self.env, KINGDOMS_WSLPE_LEARNER_PASSWORD=self.env["KINGDOMS_WSLPE_OPERATOR_PASSWORD"])
        with patch("kingdoms.wslpe41_operator_auth._regular"), \
             patch("kingdoms.wslpe41_operator_auth.os.access", return_value=True), \
             patch("kingdoms.wslpe41_operator_auth._guest"), \
             patch("kingdoms.wslpe41_operator_auth._inventory"), \
             patch("kingdoms.wslpe41_operator_auth._environment", return_value=env), \
             patch("kingdoms.wslpe41_operator_auth.subprocess.run") as run:
            with self.assertRaises(InstallBlocked):
                authenticate_native_operator(self.context)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
