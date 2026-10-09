"""Offline tests for the native isolated Course 1 Ansible inventory gate."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts/course1/check-isolated-artifacts.py"
SPEC = importlib.util.spec_from_file_location("course1_native_isolated_gate", MODULE)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

ADDR = {"dc01": "10.41.20.10", "dc02": "10.41.10.11",
        "srv02": "10.41.10.22", "ws01": "10.41.10.31"}


def inventory_response(kind: str, *, bad_address=False, bad_creds=False):
    hosts = {name: {"ansible_host": ip} for name, ip in ADDR.items()}
    if bad_address:
        hosts["ws01"]["ansible_host"] = "10.4.10.31"
    if kind == "provider":
        hosts["ws01"]["lab_gateway"] = "10.41.10.1"
    if kind == "post":
        hosts["srv02"].update({"ansible_user": "test-user",
                               "ansible_password": "test-password"})
        hosts["ws01"].update({"ansible_user": "test-user",
                              "ansible_password": ("incorrect" if bad_creds
                                                   else "test-password")})
    response = {"_meta": {"hostvars": hosts}, "default": {"hosts": list(ADDR)}}
    if kind == "provision":
        response.update({
            "domain": {"hosts": list(ADDR)},
            "dc": {"hosts": ["dc01", "dc02"]},
            "parent_dc": {"hosts": ["dc01"]},
            "child_dc": {"hosts": ["dc02"]},
            "trust": {"hosts": []},
        })
    return json.dumps(response)


class IsolatedNativeInventoryTests(unittest.TestCase):
    def check(self, kind, *, bad_address=False, bad_creds=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            file = path / "inventory"
            file.write_text("[default]\n", encoding="utf-8")
            fake = SimpleNamespace(
                returncode=0,
                stdout=inventory_response(kind, bad_address=bad_address,
                                          bad_creds=bad_creds),
                stderr="",
            )
            with patch.object(gate.subprocess, "run", return_value=fake):
                gate.check_inventory(path, "/bin/true", "inventory", ADDR,
                                     kind, "10.41.10.1")

    def test_all_three_native_inventory_shapes_accepted(self):
        for kind in ("provision", "post", "provider"):
            with self.subTest(kind=kind):
                self.check(kind)

    def test_old_ws01_address_refused(self):
        with self.assertRaisesRegex(gate.OfflineGateError, "address mismatch"):
            self.check("post", bad_address=True)

    def test_post_credential_mismatch_refused(self):
        with self.assertRaisesRegex(gate.OfflineGateError, "credentials inconsistent"):
            self.check("post", bad_creds=True)

    def test_native_parser_failures_do_not_echo_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "inventory"
            file.write_text("[default]\n", encoding="utf-8")
            fake = SimpleNamespace(returncode=1, stdout="",
                                   stderr="SECRET-FIXTURE-PASSWORD")
            with patch.object(gate.subprocess, "run", return_value=fake):
                with self.assertRaises(gate.OfflineGateError) as raised:
                    gate.check_inventory(Path(directory), "ansible-inventory",
                                         "inventory", ADDR, "post", "10.41.10.1")
            self.assertNotIn("SECRET-FIXTURE-PASSWORD", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
