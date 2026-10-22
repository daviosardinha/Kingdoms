"""Provided VM runtime source tests: no guest/VM/network mutation."""
import json
import os
from pathlib import Path
import ssl
import stat
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import yaml
from kingdoms import wslpe41_provided_runtime as runtime
from kingdoms.wslpe41_install_flow import InstallBlocked


class ProvidedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.instance = self.home / "workspace" / runtime.INSTANCE
        self.instance.mkdir(parents=True)
        self.vmx = self.instance / "provider" / "windows_10.vmx"
        self.vmx.parent.mkdir()
        self.vmx.write_text('config.version = "8"\n')
        self.target = SimpleNamespace(instance=self.instance, vmx=self.vmx)
        self.management = self.home / "management.json"
        self.management.write_text('{"phase": "accepted"}')
        self.certificate = bytes.fromhex("30820100")
        self.operator = "O" * 32
        self.learner = "L" * 30

    def _context(self):
        with (patch.object(runtime, "existing_management",
                           return_value=(self.target, {}, self.certificate,
                                         self.operator, self.learner)),
              patch.object(runtime.management, "receipt_path",
                           return_value=self.management),
              patch.object(runtime.subprocess, "check_output",
                           return_value="f" * 40)):
            return runtime.prepare()

    def test_one_time_private_inventory_and_fixture_generation(self):
        context = self._context()
        folder = self.instance / "ansible"
        self.assertEqual(context.management_address, "172.28.233.31")
        self.assertEqual(context.expected_address, "172.28.232.31")
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        for name in ("inventory.yml", "private-vars.yml", "operator-ca.pem", "runtime.json"):
            self.assertEqual(stat.S_IMODE((folder / name).stat().st_mode), 0o600)
        private = yaml.safe_load((folder / "private-vars.yml").read_text())
        self.assertEqual(private["wslpe_fixture_instance_id"], runtime.INSTANCE)
        self.assertTrue(private["wslpe_fixture_private"])
        passwords = [private[x]["password"] for x in runtime.FIXTURE_NAMES]
        self.assertEqual(len(set(passwords)), 5)
        self.assertTrue(all(len(p) >= 24 for p in passwords))
        self.assertTrue(all(p not in (self.operator, self.learner) for p in passwords))
        inventory = yaml.safe_load((folder / "inventory.yml").read_text())
        self.assertEqual(inventory["all"]["vars"]["ansible_host"], "WSLPE-WS01")
        self.assertEqual(inventory["all"]["vars"]["ansible_port"], 5986)
        self.assertEqual(inventory["all"]["vars"]["ansible_winrm_server_cert_validation"], "validate")
        self.assertEqual(inventory["all"]["vars"]["ansible_password"], self.operator)
        self.assertNotIn("10.4.", (folder / "inventory.yml").read_text())
        self.assertEqual((folder / "operator-ca.pem").read_bytes(),
                         ssl.DER_cert_to_PEM_cert(self.certificate).encode())
        record = json.loads((folder / "runtime.json").read_text())
        self.assertEqual(record["status"], "committed")
        self.assertNotIn(self.operator, json.dumps(record))
        with self.assertRaisesRegex(InstallBlocked, "already exists"):
            self._context()

    def test_partial_or_foreign_inventory_refuses_regeneration(self):
        folder = self.instance / "ansible"
        folder.mkdir()
        (folder / "unrelated.yml").write_text("unrelated")
        with self.assertRaisesRegex(InstallBlocked, "not empty"):
            self._context()
        self.assertTrue((folder / "unrelated.yml").exists())

    def test_source_reuses_original_credential_profiles(self):
        values = runtime._fixture_variables()
        self.assertEqual(set(values), {"wslpe_fixture_private", "wslpe_fixture_instance_id",
                                      *runtime.FIXTURE_NAMES})
        for name in runtime.FIXTURE_NAMES:
            self.assertIn("user_name", values[name])
        self.assertEqual(values["windows_lpe_stored_runas_credentials"]["credential_target"],
                         r"WSLPE-WS01\kingdom.runas")


if __name__ == "__main__":
    unittest.main()
