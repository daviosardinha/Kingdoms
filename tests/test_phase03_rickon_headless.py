"""Offline source contract for the Phase 03 Rickon/WS01 victim client."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "phase03" / "rickon-headless.sh"
CHECK = ROOT / "scripts" / "phase03" / "check-rickon-prereqs.sh"
INSTALL = ROOT / "scripts" / "phase03" / "install-rickon-headless.sh"
UNIT = ROOT / "ops" / "systemd" / "kingdoms-phase03-rickon.service"
CERT_READ = ROOT / "scripts" / "phase03" / "read-ws01-rdp-cert.sh"
CERT_PLAYBOOK = ROOT / "ansible" / "phase03-read-ws01-rdp-cert.yml"
CERT_PROBE = ROOT / "scripts" / "phase03" / "probe-ws01-rdp-cert.py"
CERT_SYNC = ROOT / "scripts" / "phase03" / "sync-ws01-rdp-pin.sh"
SESSION_VALIDATE = ROOT / "scripts" / "phase03" / "validate-rickon-session.sh"
SESSION_PLAYBOOK = ROOT / "ansible" / "phase03-validate-rickon-session.yml"
RESTART_TEST = ROOT / "scripts" / "phase03" / "test-rickon-restart.sh"


class Phase03RickonHeadlessTests(unittest.TestCase):
    def test_required_files_exist_and_parse(self):
        for path in (RUNNER, CHECK, INSTALL, UNIT, CERT_READ, CERT_PLAYBOOK, CERT_PROBE, CERT_SYNC, SESSION_VALIDATE, SESSION_PLAYBOOK, RESTART_TEST):
            self.assertTrue(path.is_file(), path)
        for path in (RUNNER, CHECK, INSTALL, CERT_READ, CERT_SYNC, SESSION_VALIDATE, RESTART_TEST):
            result = subprocess.run(
                ["bash", "-n", str(path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_runner_scope_and_identity(self):
        text = RUNNER.read_text()
        for expected in (
            "TARGET_FQDN='ws01.north.sevenkingdoms.local'",
            "TARGET_IP='10.4.10.31'",
            "EXPECTED_INTERFACE='vmnet10'",
            "EXPECTED_SOURCE='10.4.10.254'",
            "'/d:NORTH'",
            "'/u:rickon.stark'",
            "/args-from:stdin",
            "rickon-rdp.password",
            "ws01-rdp.sha256",
            "fingerprint:sha256",
            "-clipboard",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_runner_fails_closed_on_duplicate_and_certificate(self):
        text = RUNNER.read_text()
        self.assertIn("refusing a duplicate victim session", text)
        self.assertIn("state established", text)
        self.assertIn("^[0-9a-f]{64}$", text)
        self.assertIn("/v:$TARGET_FQDN", text)
        self.assertIn("getent ahostsv4", text)
        self.assertNotIn("/cert:ignore", text)
        self.assertNotIn("/p:Winter", text)

    def test_unit_retries_with_backoff_without_permanent_start_limit(self):
        text = UNIT.read_text()
        self.assertIn("Restart=always", text)
        self.assertIn("RestartSec=120", text)
        self.assertIn("StartLimitIntervalSec=0", text)
        self.assertNotIn("StartLimitBurst=3", text)
        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn("WantedBy=default.target", text)
        self.assertNotIn("/p:", text)

    def test_installer_does_not_start_or_enable_service(self):
        text = INSTALL.read_text()
        self.assertIn("--confirm", text)
        self.assertIn("daemon-reload", text)
        self.assertNotIn("systemctl --user start", text)
        self.assertNotIn("systemctl --user enable", text)
        self.assertIn("service was NOT enabled or started", text)

    def test_certificate_probe_is_read_only_and_emits_sha256(self):
        text = CERT_PLAYBOOK.read_text()
        self.assertIn("hosts: ws01", text)
        self.assertIn("register: ws01_rdp_cert", text)
        self.assertIn("RDP_SHA256=", text)
        self.assertIn("changed_when: false", text)
        self.assertIn("ws01_rdp_cert.output", text)

    def test_certificate_pin_sync_requires_management_and_network_agreement(self):
        text = CERT_SYNC.read_text()
        self.assertIn("read-ws01-rdp-cert.sh", text)
        self.assertIn("probe-ws01-rdp-cert.py", text)
        self.assertIn("management_sha", text)
        self.assertIn("network_sha", text)
        self.assertIn("management_sha\" != \"$network_sha", text)
        self.assertIn("PHASE03_WS01_RDP_PIN_SYNC_COMPLETE=True", text)
        self.assertNotIn("/cert:ignore", text)

    def test_network_certificate_probe_is_non_authenticating(self):
        text = CERT_PROBE.read_text()
        self.assertIn('DEFAULT_HOST = "10.4.10.31"', text)
        self.assertIn("RDP_NEGOTIATION_REQUEST", text)
        self.assertIn("getpeercert(binary_form=True)", text)
        self.assertIn("hashlib.sha256", text)
        self.assertIn("RDP_SHA256=", text)
        self.assertNotIn("username", text.lower())
        self.assertNotIn("password", text.lower())

    def test_session_validator_checks_live_windows_state(self):
        shell = SESSION_VALIDATE.read_text()
        playbook = SESSION_PLAYBOOK.read_text()
        self.assertIn("Exactly one established WS01 RDP socket", shell)
        self.assertIn("state established", shell)
        self.assertIn("password is absent from process argv", shell)
        self.assertIn("PHASE03_RICKON_ACTIVE=TRUE", shell)
        self.assertIn("hosts: ws01", playbook)
        self.assertIn("quser.exe", playbook)
        self.assertIn("rickon\\.stark", playbook)
        self.assertIn("Active", playbook)
        self.assertIn("changed_when: false", playbook)
        self.assertIn("$($LASTEXITCODE):", playbook)
        self.assertNotIn("$LASTEXITCODE:", playbook)

    def test_restart_validator_proves_cleanup_and_reconnect(self):
        text = RESTART_TEST.read_text()
        self.assertIn("systemctl --user restart", text)
        self.assertIn("old Xvfb PID still exists", text)
        self.assertIn("old FreeRDP PID still exists", text)
        self.assertIn("Runner_PID=", text)
        self.assertIn("Xvfb_PID=", text)
        self.assertIn('pgrep -P "$old_main"', text)
        self.assertIn('awk -v p="$old_runner"', text)
        self.assertIn("validate-rickon-session.sh", text)
        self.assertIn("state established", text)
        self.assertIn("state established", CHECK.read_text())
        self.assertNotIn("sudo ss", text)

        session_text = SESSION_VALIDATE.read_text()
        self.assertNotIn("sudo ss", session_text)

    def test_no_known_lab_passwords(self):
        corpus = "\n".join(p.read_text(errors="replace") for p in (RUNNER, CHECK, INSTALL, UNIT)).lower()
        for forbidden in (
            "winter2022",
            "sexywolfy",
            "fightp3aceandhonor!",
            "youwillnotkerboroast1ngmeeeeee",
        ):
            self.assertNotIn(forbidden, corpus)


if __name__ == "__main__":
    unittest.main()
