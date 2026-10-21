"""WSLPE41 Ansible stage execution contract; no VMware or Windows access."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kingdoms.wslpe41_fresh_contract import fresh_scenario_manifest
from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked
from kingdoms.wslpe41_stage_executor import (
    AnsibleStageContext, _guest, _inventory, run_ansible_stage,
)


class AnsibleStageExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.instance = self.workspace / "wslpe41-new-test"
        self.instance.mkdir(parents=True)
        (self.instance / "ansible").mkdir()
        self.venv = self.root / "venv" / "bin"
        self.venv.mkdir(parents=True)
        self.ansible = self.venv / "ansible-playbook"
        self.inventory_tool = self.venv / "ansible-inventory"
        for tool in (self.ansible, self.inventory_tool):
            tool.write_text("#!/bin/sh\n")
            tool.chmod(0o700)
        self.inventory = self.instance / "ansible" / "inventory"
        self.inventory.write_text("[wslpe]\nws01\n")
        self.private_vars = self.instance / "ansible" / "private-vars.yml"
        self.private_vars.write_text("[all:vars]\n")
        self.private_vars.chmod(0o600)
        self.vmx = self.instance / "provider" / "WSLPE-WS01.vmx"
        self.vmx.parent.mkdir()
        self.vmx.write_text("config.version = \"8\"\n")
        vmid = (self.instance / "provider" / ".vagrant" / "machines"
                / "WSLPE-WS01" / "vmware_desktop" / "id")
        vmid.parent.mkdir(parents=True)
        vmid.write_text(str(self.vmx))
        (self.instance / "instance.json").write_text(json.dumps({
            "id": self.instance.name, "lab": "WSLPE", "provider": "vmware",
            "provisioner": "local", "status": "ready for provisioning",
            "extensions": [], "ip_range": "172.28.232",
        }))
        self.identity = FreshGuestIdentity(
            instance_id=self.instance.name, workspace=str(self.workspace),
            vmx=str(self.vmx), subnet="172.28.232.0/24",
            source_commit="a" * 40,
        )
        self.context = AnsibleStageContext(
            identity=self.identity, instance_dir=self.instance,
            ansible=self.ansible, inventory=self.inventory,
            private_vars=self.private_vars, expected_address="172.28.232.31",
        )
        self.scenario = fresh_scenario_manifest()[0]
        self.env = {
            "KINGDOMS_WSLPE_INSTANCE_ID": self.instance.name,
            "KINGDOMS_WSLPE_LEARNER_PASSWORD": "private-learner-password",
            "KINGDOMS_WSLPE_OPERATOR_PASSWORD": "private-operator-password-very-long",
            "KINGDOMS_WSLPE_FIXTURE_VARS_FILE": str(self.private_vars),
        }

    def inventory_json(self, *, scheme="https", guest="172.28.232.31"):
        return json.dumps({
            "_meta": {"hostvars": {"ws01": {
                "ansible_host": guest, "ansible_connection": "winrm",
                "ansible_winrm_scheme": scheme, "ansible_port": 5986,
                "ansible_winrm_server_cert_validation": "validate",
                "domain_name": "WSLPE",
            }}},
            "wslpe": {"hosts": ["ws01"]},
            "windows_lpe_standalone": {"hosts": ["ws01"]},
        })

    def test_native_registration_checks_exact_vmx_not_global_zero_running(self):
        output = ("Total running VMs: 2\n"
                  "/some-other-north/GOAD-DC01.vmx\n" + str(self.vmx) + "\n")
        with patch("kingdoms.wslpe41_stage_executor.read_only_command", return_value=output):
            _guest(self.context)
        with patch("kingdoms.wslpe41_stage_executor.read_only_command",
                   return_value="Total running VMs: 1\n/some-other-north/GOAD-DC01.vmx\n"):
            with self.assertRaisesRegex(InstallBlocked, "not running"):
                _guest(self.context)

    def test_inventory_requires_pinned_https_and_exact_guest(self):
        with patch("kingdoms.wslpe41_stage_executor.subprocess.run",
                   return_value=SimpleNamespace(returncode=0, stdout=self.inventory_json())):
            _inventory(self.context, self.env)
        for payload in (self.inventory_json(scheme="http"),
                        self.inventory_json(guest="10.4.10.31")):
            with patch("kingdoms.wslpe41_stage_executor.subprocess.run",
                       return_value=SimpleNamespace(returncode=0, stdout=payload)):
                with self.assertRaisesRegex(InstallBlocked, "isolated HTTPS"):
                    _inventory(self.context, self.env)

    def test_runs_one_real_stage_and_requires_windows_marker(self):
        marker = f"WSLPE41_STAGE={self.scenario.identifier}:apply:PASS"
        completed = SimpleNamespace(returncode=0, stdout=marker + "\n", stderr="")
        with (patch.dict(os.environ, self.env),
              patch("kingdoms.wslpe41_stage_executor._guest") as guest,
              patch("kingdoms.wslpe41_stage_executor._inventory"),
              patch("kingdoms.wslpe41_stage_executor.subprocess.run",
                    return_value=completed) as run):
            proof = run_ansible_stage(self.context, self.scenario, "apply")
        self.assertTrue(proof.passed)
        self.assertEqual(proof.transport, "ansible")
        self.assertEqual(guest.call_count, 2)
        args, kwargs = run.call_args
        self.assertEqual(args[0][0], str(self.ansible))
        self.assertEqual(kwargs["stdin"], __import__("subprocess").DEVNULL)
        self.assertNotIn(self.env["KINGDOMS_WSLPE_LEARNER_PASSWORD"], str(args[0]))

    def test_rejects_fake_stage_result_and_failed_ansible(self):
        for code, stdout in ((0, "no Windows proof"), (1, "WSLPE41_STAGE=irrelevant:apply:PASS")):
            with (patch.dict(os.environ, self.env),
                  patch("kingdoms.wslpe41_stage_executor._guest"),
                  patch("kingdoms.wslpe41_stage_executor._inventory"),
                  patch("kingdoms.wslpe41_stage_executor.subprocess.run",
                        return_value=SimpleNamespace(returncode=code, stdout=stdout, stderr=""))):
                with self.assertRaisesRegex(InstallBlocked, "runtime proof missing"):
                    run_ansible_stage(self.context, self.scenario, "apply")

    def test_rejects_jea_activation_without_guest_console(self):
        jea = next(s for s in fresh_scenario_manifest() if s.number == 30)
        with (patch.dict(os.environ, self.env),
              patch("kingdoms.wslpe41_stage_executor._guest"),
              patch("kingdoms.wslpe41_stage_executor._inventory")):
            with self.assertRaisesRegex(InstallBlocked, "independent guest console"):
                run_ansible_stage(self.context, jea, "activate")

    def test_private_vars_and_instance_secrets_are_mandatory(self):
        self.private_vars.chmod(0o644)
        with self.assertRaisesRegex(InstallBlocked, "owner-only"):
            run_ansible_stage(self.context, self.scenario, "apply")
        self.private_vars.chmod(0o600)
        with patch("kingdoms.wslpe41_stage_executor._guest"):
            with self.assertRaisesRegex(InstallBlocked, "private environment"):
                run_ansible_stage(self.context, self.scenario, "apply")


if __name__ == "__main__":
    unittest.main()
