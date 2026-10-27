"""No-touch KINGSLANDING transport evidence contract for NORTH.

This diagnostic must not repair certificates, alter accounts, open host routes,
reconnect NAT or modify either guest's WinRM configuration.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ansible/north-parent-transport-evidence-readonly.yml"


class NorthParentTransportEvidenceTests(unittest.TestCase):
    def test_child_only_and_no_mutation(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("hosts: dc02", text)
        self.assertIn("gather_facts: false", text)
        self.assertIn("$Ansible.Changed = $false", text)
        self.assertIn("changed_when: false", text)
        for prohibited in (
            "Set-ItemProperty", "New-ItemProperty", "Restart-Service",
            "Set-WSManInstance", "New-WSManInstance",
            "netsh ", "vmrun ", "w32tm.exe /config",
        ):
            self.assertNotIn(prohibited, text)

    def test_exact_parent_credential_and_private_transport(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("kingslanding.sevenkingdoms.local", text)
        self.assertIn("10.4.20.10", text)
        self.assertIn("5986", text)
        self.assertIn("NORTH_PARENT_TLS_VALIDITY=", text)
        self.assertIn("NORTH_PARENT_DOMAIN_ACCOUNT=", text)
        self.assertIn('hostvars["dc01"].ansible_user', text)
        self.assertNotIn("ParentCredential.Password", text)
        self.assertNotIn("GetNetworkCredential()", text)

    def test_certificate_handshake_is_inspection_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("RemoteCertificateValidationCallback", text)
        self.assertIn("The real WinRS connector retains its existing TLS policy.", text)
        self.assertNotIn("ServicePointManager", text)
        self.assertNotIn("LocalAccountTokenFilterPolicy", text)


if __name__ == "__main__":
    unittest.main()
