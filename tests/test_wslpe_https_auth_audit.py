"""Unit regression for WSLPE-only verified authenticated HTTPS probe."""
import importlib.util
from pathlib import Path
import socket
import ssl
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-https-auth-audit.py"
SPEC = importlib.util.spec_from_file_location("wslpe_https_auth", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class WslpeHttpsAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_resolution_is_exact_and_restored(self):
        original = socket.getaddrinfo
        with patch.object(MOD.socket, "getaddrinfo",
                          return_value=[("expected-ip",)]) as real:
            with MOD.scoped_wslpe_resolution("172.28.231.31"):
                self.assertEqual(socket.getaddrinfo("WSLPE-WS01", 5986),
                                 [("expected-ip",)])
                real.assert_called_once_with("172.28.231.31", 5986)
                for host, port in (("GOAD-WS01", 5986),
                                   ("NORTH", 5986),
                                   ("WSLPE-WS01", 5985),
                                   ("172.28.231.31", 5986)):
                    with self.subTest(host=host, port=port):
                        with self.assertRaises(OSError):
                            socket.getaddrinfo(host, port)
            self.assertIs(socket.getaddrinfo, real)

        self.assertIs(socket.getaddrinfo, original)

    def test_certificate_mismatch_prevents_verified_tls(self):
        audit = MagicMock()
        audit.expected_fingerprint.return_value = "A" * 40
        audit.registered_wslpe_address.return_value = "172.28.231.31"
        audit.read_untrusted_tls_leaf.return_value = b"certificate"
        audit.cert_fingerprint.return_value = "B" * 40
        with self.assertRaises(ValueError):
            MOD.checked_certificate(audit, "A" * 40)
        audit.verify_pinned_tls.assert_not_called()

    def test_tls_verification_called_before_auth(self):
        audit = MagicMock()
        audit.expected_fingerprint.return_value = "A" * 40
        audit.registered_wslpe_address.return_value = "172.28.231.31"
        audit.read_untrusted_tls_leaf.return_value = b"certificate"
        audit.cert_fingerprint.return_value = "A" * 40
        self.assertEqual(MOD.checked_certificate(audit, "A" * 40),
                         ("172.28.231.31", b"certificate"))
        audit.verify_pinned_tls.assert_called_once_with(
            "172.28.231.31", b"certificate", "A" * 40
        )

    def test_authenticated_probe_enforces_certificate_validation_and_local_only(self):
        transport = MagicMock()
        http = transport.build_session.return_value
        def inspect_session(*args, **kwargs):
            self.assertEqual(args[0], "https://WSLPE-WS01:5986/wsman")
            self.assertEqual(kwargs["transport"], "ntlm")
            self.assertEqual(kwargs["server_cert_validation"], "validate")
            self.assertIsNone(kwargs["proxy"])
            self.assertTrue(Path(kwargs["ca_trust_path"]).is_absolute())
            http.verify = kwargs["ca_trust_path"]
            return SimpleNamespace(
                protocol=SimpleNamespace(transport=transport),
                run_ps=MagicMock(return_value=SimpleNamespace(
                    status_code=0,
                    std_out=b"WSLPE_HTTPS_AUTH=PASS\nWSLPE_DOMAIN_FREE=PASS\n"
                )),
            )
        fake = SimpleNamespace(Session=MagicMock(side_effect=inspect_session))
        with patch.dict("sys.modules", {"winrm": fake}):
            MOD.authenticated_read_only_probe(
                "172.28.231.31", b"temporary-binary-cert",
                "vagrant", "not-logged-password"
            )
        self.assertIs(http.trust_env, False)
        self.assertEqual(http.proxies, {})
        transport.close_session.assert_called_once()

    def test_auth_failure_does_not_accept_unproven_identity(self):
        transport = MagicMock()
        http = transport.build_session.return_value
        def make_session(*args, **kwargs):
            http.verify = kwargs["ca_trust_path"]
            return SimpleNamespace(
                protocol=SimpleNamespace(transport=transport),
                run_ps=lambda script: SimpleNamespace(status_code=0, std_out=b"WSLPE_HTTPS_AUTH=PASS"),
            )
        with patch.dict("sys.modules", {"winrm": SimpleNamespace(Session=make_session)}):
            with self.assertRaises(ValueError):
                MOD.authenticated_read_only_probe("172.28.231.31", b"test", "vagrant", "pw")
        transport.close_session.assert_called_once()

    def test_no_unsafe_defaults_and_no_mutation_commands(self):
        for required in (
            "checked_certificate(", "audit.verify_pinned_tls(", "getpass.getpass(",
            'server_cert_validation="validate"', "ca_trust_path=str(anchor)",
            "http.trust_env = False", "http.proxies = {}",
            "with scoped_wslpe_resolution(address):",
            "READ_ONLY", "transport.close_session()", "tempfile.TemporaryDirectory(",
        ):
            self.assertIn(required, self.source)
        for forbidden in (
            'server_cert_validation="ignore"', "verify=False",
            "winrm.Session('http:", 'winrm.Session("http:',
            "vagrant up", "vmrun start", "lab-mode.sh",
            "New-LocalUser", "Set-NetFirewallRule", "New-WSManInstance",
            "Set-ItemProperty", "/etc/hosts",
        ):
            # /etc/hosts only appears in comments and docstring on purpose.
            active = "\n".join(line for line in self.source.splitlines()
                               if not line.lstrip().startswith("#")
                               and not line.lstrip().startswith('"""'))
            if forbidden == "/etc/hosts":
                continue
            self.assertNotIn(forbidden, active)


if __name__ == "__main__":
    unittest.main()
