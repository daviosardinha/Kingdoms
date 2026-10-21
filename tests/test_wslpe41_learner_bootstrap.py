"""Mock-only native learner deployment: no VM, Ansible or Windows mutation."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from kingdoms import wslpe41_learner_bootstrap as learner


class NativeLearnerFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Kingdoms"
        self.home = Path(self.temp.name) / "home"
        self.root.mkdir()
        self.native = self.root / "workspace/bf5369-wslpe-vmware/inventory"
        self.native.parent.mkdir(parents=True)
        self.native.write_text("ws01\n", encoding="utf-8")
        self.defaults = self.root / "ad/WSLPE/data/inventory"
        self.defaults.parent.mkdir(parents=True)
        self.defaults.write_text("existing\n", encoding="utf-8")
        foundation = self.root / "ansible/wslpe-foundation.yml"
        foundation.parent.mkdir(parents=True)
        foundation.write_text("existing learner foundation\n", encoding="utf-8")
        playbook = self.home / ".goad/.venv/bin/ansible-playbook"
        playbook.parent.mkdir(parents=True)
        playbook.write_text("#!/bin/sh\n", encoding="utf-8")
        playbook.chmod(0o700)
        self.instance = SimpleNamespace(
            instance_id="bf5369-wslpe-vmware",
            ip_range="172.28.232",
            get_status=lambda: learner.PROVIDED,
        )
        self.winrm = Mock(return_value=SimpleNamespace(
            status_code=0, std_out=learner.RDP_MARKER + b"\r\n",
        ))
        self.provider = SimpleNamespace(
            _winrm_session=Mock(return_value=SimpleNamespace(run_ps=self.winrm)),
        )
        self.account = SimpleNamespace()
        self.auth = SimpleNamespace()
        self.snapshot = (
            self.instance, self.provider, self.root, self.native, self.defaults,
            2200, self.account, self.auth, "172.28.232.31", b"tls-der", "A" * 40,
        )
        self.rows = {
            "lpe.trainee": {"exists": True, "enabled": True, "admin": False},
            "kingdom.operator": {"exists": False},
        }

    def patches(self):
        return (
            patch.object(learner, "_preflight", return_value=self.snapshot),
            patch.object(learner.Path, "home", return_value=self.home),
            patch.object(learner, "learner_password",
                         return_value="PrivateUniqueTestPass1234!"),
            patch.object(learner, "inspect_vmware_guest", return_value=True),
            patch.object(learner, "_guest_proof", return_value=True),
            patch.object(learner, "_trusted_binding",
                         return_value=(self.auth, "172.28.232.31",
                                       b"tls-der", "A" * 40)),
            patch.object(learner, "_audit_accounts", return_value=self.rows),
            patch.object(learner.subprocess, "run",
                         return_value=SimpleNamespace(returncode=0)),
        )

    def test_runs_exact_existing_foundation_once_with_private_instance_secret(self):
        m = SimpleNamespace()
        a, b, c, d, e, f, g, h = self.patches()
        with a, b, c as secret, d, e, f, g, h as run:
            self.assertTrue(learner.bootstrap_native_wslpe_learner(
                m, confirmed=True,
            ))
        self.assertEqual(run.call_count, 1)
        command = run.call_args.args[0]
        self.assertEqual(command[0], str(self.home / ".goad/.venv/bin/ansible-playbook"))
        self.assertEqual(command[1:7], [
            "-i", str(self.native), "-i", str(self.defaults),
            "--limit", "ws01,localhost",
        ])
        self.assertEqual(command[7], str(self.root / "ansible/wslpe-foundation.yml"))
        overrides = json.loads(command[command.index("-e") + 1])
        self.assertEqual(overrides["ansible_host"], "127.0.0.1")
        self.assertEqual(overrides["ansible_port"], 2200)
        self.assertEqual(overrides["ansible_winrm_transport"], "ntlm")
        self.assertEqual(
            run.call_args.kwargs["env"]["KINGDOMS_WSLPE_LEARNER_PASSWORD"],
            "PrivateUniqueTestPass1234!",
        )
        self.assertNotIn("PrivateUniqueTestPass1234!", " ".join(command))
        secret.assert_called_once()
        credpath = secret.call_args.kwargs["path"]
        self.assertEqual(
            credpath,
            self.home / ".local/state/kingdoms-wslpe41-foundation"
            / "bf5369-wslpe-vmware/learner.credential",
        )
        self.assertEqual(secret.call_args.kwargs["environ"], {})
        self.assertEqual(self.winrm.call_count, 1)
        self.assertEqual(self.winrm.call_args.args[0], learner.READ_ONLY_RDP)

    def test_no_confirmation_never_touches_guest_or_creates_secret(self):
        a, b, c as_ignored = self.patches()[:3]
        with a as preflight, b, c as secret:
            self.assertFalse(learner.bootstrap_native_wslpe_learner(
                object(), confirmed=False,
            ))
            preflight.assert_not_called()
            secret.assert_not_called()

    def test_existing_secret_prevents_replay_without_mutation(self):
        location = (
            self.home / ".local/state/kingdoms-wslpe41-foundation"
            / "bf5369-wslpe-vmware"
        )
        location.mkdir(parents=True)
        (location / "learner.credential").write_text("exists\n")
        a, b, c, d, e, f, g, h = self.patches()
        with a, b, c as secret, d, e, f, g, h as run:
            self.assertFalse(learner.bootstrap_native_wslpe_learner(
                object(), confirmed=True,
            ))
            secret.assert_not_called()
            run.assert_not_called()

    def test_partial_playbook_failure_never_claims_foundation_pass(self):
        a, b, c, d, e, f, g, h = self.patches()
        with a, b, c, d, e, f, g, h as run:
            run.return_value.returncode = 2
            self.assertFalse(learner.bootstrap_native_wslpe_learner(
                object(), confirmed=True,
            ))
            self.assertEqual(run.call_count, 1)
        self.winrm.assert_not_called()

    def test_post_install_learner_admin_or_operator_present_rejected(self):
        for bad in (
            {"lpe.trainee": {"exists": True, "enabled": True, "admin": True},
             "kingdom.operator": {"exists": False}},
            {"lpe.trainee": {"exists": True, "enabled": True, "admin": False},
             "kingdom.operator": {"exists": True}},
        ):
            with self.subTest(rows=bad):
                a, b, c, d, e, f, g, h = self.patches()
                with a, b, c, d, e, f, g as rows, h:
                    rows.return_value = bad
                    self.assertFalse(learner.bootstrap_native_wslpe_learner(
                        object(), confirmed=True,
                    ))

    def test_guest_loses_registered_mac_or_https_pin_after_mutation(self):
        a, b, c, d, e, f, g, h = self.patches()
        with a, b, c, d, e as proof, f, g, h:
            proof.return_value = False
            self.assertFalse(learner.bootstrap_native_wslpe_learner(
                object(), confirmed=True,
            ))
        self.winrm.assert_not_called()
        a, b, c, d, e, f, g, h = self.patches()
        with a, b, c, d, e, f as pin, g, h:
            pin.return_value = (self.auth, "172.28.232.31", b"other", "B" * 40)
            self.assertFalse(learner.bootstrap_native_wslpe_learner(
                object(), confirmed=True,
            ))

    def test_preflight_fails_on_unexpected_accounts_or_license_regression(self):
        manager = object()
        fake_account = SimpleNamespace(
            FIXTURES=("kingdom.appsvc",),
        )
        rows = {
            "vagrant": {"exists": True, "enabled": True, "admin": True},
            "lpe.trainee": {"exists": False},
            "kingdom.operator": {"exists": False},
            "kingdom.appsvc": {"exists": False},
        }
        native = self.snapshot
        with patch.object(learner, "_exact_instance",
                          return_value=(self.instance, self.provider,
                                        self.root, self.native.parent)), \
             patch.object(self.provider, "_winrm_forwarded_port", create=True,
                          return_value=2200), \
             patch.object(learner, "inspect_vmware_guest", return_value=True), \
             patch.object(learner, "_guest_proof", return_value=True), \
             patch.object(learner, "_approved_inventory",
                          return_value=(self.native, self.defaults)), \
             patch.object(learner, "_read_only_result",
                          return_value=b"WSLPE_LICENSE_READY=PASS\r\n") as license_proof, \
             patch.object(learner, "_account_module",
                          return_value=fake_account), \
             patch.object(learner, "_trusted_binding",
                          return_value=(self.auth, "172.28.232.31",
                                        b"tls-der", "A" * 40)), \
             patch.object(learner, "_audit_accounts", return_value=rows):
            self.assertEqual(learner._preflight(manager)[0], self.instance)
            rows["kingdom.appsvc"]["exists"] = True
            with self.assertRaises(ValueError):
                learner._preflight(manager)
            rows["kingdom.appsvc"]["exists"] = False
            license_proof.return_value = b""
            with self.assertRaises(ValueError):
                learner._preflight(manager)

    def test_guest_pin_must_come_from_authenticated_windows_binding(self):
        account = SimpleNamespace(load_auth=lambda: SimpleNamespace(
            tls_audit_module=lambda: "tls-source",
            checked_certificate=lambda _, pin: ("172.28.232.31", b"cert"),
        ))
        with patch.object(learner, "_read_only_result",
                          return_value=b"WSLPE_HTTPS_THUMBPRINT=" + b"A" * 40 + b"\r\n"):
            auth, addr, cert, pin = learner._trusted_binding(
                object(), 2210, account, "172.28.232.31",
            )
            self.assertEqual(pin, "A" * 40)
            self.assertEqual(addr, "172.28.232.31")
            with self.assertRaises(ValueError):
                learner._trusted_binding(
                    object(), 2210, account, "172.28.231.31",
                )

    def test_winrm_bootstrap_and_proof_scripts_are_read_only(self):
        for script in (learner.READ_ONLY_RDP, learner.READ_ONLY_HTTPS_BINDING):
            for forbidden in (
                "New-LocalUser", "Set-LocalUser", "Disable-LocalUser",
                "Enable-LocalUser", "Restart-Computer", "Set-ItemProperty",
                "Set-NetFirewallProfile", "WSMan:\\localhost\\ClientCertificate",
            ):
                self.assertNotIn(forbidden, script)
        code = Path(learner.__file__).read_text()
        self.assertNotIn("ansible/wslpe-operator-foundation.yml", code)
        self.assertNotIn("ansible/wslpe-lpe-test.yml", code)
        self.assertNotIn("vmrun start", code)


if __name__ == "__main__":
    unittest.main()
