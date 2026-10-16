"""Read-only unit contracts for WSLPE pinned WinRM HTTPS transport gate."""
from pathlib import Path
import importlib.util
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts/wslpe-https-trust-audit.py"
SPEC = importlib.util.spec_from_file_location("wslpe_https_trust", AUDIT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class WslpeHttpsTrustAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = AUDIT.read_text(encoding="utf-8")

    def test_requires_exact_windows_binding_fingerprint(self):
        sample = "C773EC26D02940F559FE715B83628FEDAE2AA92D"
        self.assertEqual(MOD.expected_fingerprint(sample.lower()), sample)
        self.assertEqual(MOD.expected_fingerprint(":".join(
            sample[n:n+2] for n in range(0, 40, 2))), sample)
        for wrong in ("", "XYZ", "0" * 40, "F" * 39, "F" * 41, "NORTH"):
            with self.subTest(wrong=wrong):
                with self.assertRaises(ValueError):
                    MOD.expected_fingerprint(wrong)

    def test_exact_dns_san_required_not_cn_or_wildcard(self):
        MOD.require_dns_san({"subjectAltName": (("DNS", "wslpe-ws01"),)})
        for cert in (
            {},
            {"subject": ((("commonName", "WSLPE-WS01"),),)},
            {"subjectAltName": (("DNS", "*.local"),)},
            {"subjectAltName": (("DNS", "GOAD-WS01"),)},
            {"subjectAltName": (("IP Address", "172.28.231.31"),)},
        ):
            with self.subTest(cert=cert):
                with self.assertRaises(ValueError):
                    MOD.require_dns_san(cert)

    def test_empty_certificate_fails_closed(self):
        with self.assertRaises(ValueError):
            MOD.cert_fingerprint(b"")

    def test_wrong_second_certificate_fails_without_auth(self):
        original = MOD.cert_fingerprint(b"first")
        with patch.object(MOD, "registered_wslpe_address", return_value="172.28.231.31"), \
             patch.object(MOD, "read_untrusted_tls_leaf", return_value=b"second"), \
             patch.object(MOD, "verify_pinned_tls") as verify:
            with patch("sys.argv", ["wslpe-https-trust-audit.py", "--expected-thumbprint", original]):
                self.assertEqual(MOD.main(), 1)
            verify.assert_not_called()

    def test_source_never_modifies_windows_or_vmware(self):
        for required in (
            "stage2.find_instance(", "stage2.locate_registered_vm(",
            "ssl.CERT_REQUIRED", "context.check_hostname = True",
            "context.load_verify_locations(cadata=pem)",
            "server_hostname=GUEST", "require_dns_san(",
            "verified_der", "cert_fingerprint(verified_der)",
            "No credentials", "--expected-thumbprint",
        ):
            self.assertIn(required, self.source)
        self.assertNotIn("winrm.Session", self.source)
        self.assertNotIn("server_cert_validation='ignore'", self.source)
        for forbidden in ("vagrant up", "vmrun start", "lab-mode.sh",
                          "sudo ", "os.system(", "run_ps(", "setx ",
                          "Set-NetFirewallRule", "New-WSManInstance"):
            self.assertNotIn(forbidden, self.source)

    def test_verified_tls_uses_certificate_pin_and_hostname(self):
        self.assertIn("ssl.PROTOCOL_TLS_CLIENT", self.source)
        self.assertIn("ssl.TLSVersion.TLSv1_2", self.source)
        self.assertIn("cert_fingerprint(discovered_der)", self.source)
        self.assertIn("if observed != fingerprint:", self.source)
        self.assertIn("return 1", self.source)


if __name__ == "__main__":
    unittest.main()
