"""Tests for the consolidated WSLPE operator preboot gate.

No subprocess in these tests is allowed to actually run Vagrant/VMware,
or connect to a Windows guest.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-acceptance.py"
SPEC = importlib.util.spec_from_file_location("wslpe_acceptance", SCRIPT)
assert SPEC and SPEC.loader
ACCEPTANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCEPTANCE)


class WslpeConsolidatedAcceptanceTests(unittest.TestCase):
    def test_expected_offline_stages_all_present(self):
        steps = ACCEPTANCE.commands("python3", "ansible-playbook", "172.28.231")
        names = [name for name, _args, _timeout in steps]
        self.assertEqual(len(names), 13)
        self.assertEqual(len(set(names)), len(names))
        for topic in ("WSLPE native", "NORTH isolation", "Windows LPE",
                      "Windows foundation", "VMware", "subnet collision",
                      "Pinned Windows"):
            self.assertTrue(any(topic in name for name in names), topic)
        self.assertTrue(all(timeout > 0 for _name, _args, timeout in steps))

    def test_all_stages_are_non_deployment_commands(self):
        for name, args, _timeout in ACCEPTANCE.commands(
            "python3", "ansible-playbook", "172.28.231"
        ):
            joined = " ".join(args)
            self.assertNotIn("vagrant up", joined)
            self.assertNotIn("vagrant destroy", joined)
            self.assertNotIn("vmrun start", joined)
            self.assertNotIn("vmrun stop", joined)
            self.assertNotIn("winrm", args[0].lower())
            if "ansible-playbook" in args[0]:
                self.assertIn("--syntax-check", args)
            if "unittest" in args:
                self.assertIn("discover", args)
            if name == "Native WSLPE Vagrantfile and inventory render + Ruby syntax":
                self.assertIn("--ruby-check", args)

    def test_plugin_and_box_presence_are_proven_not_inferred_from_exit_zero(self):
        name = "VMware Vagrant provider/plugin availability"
        self.assertIsNotNone(ACCEPTANCE.verify_output(name, "vagrant-vbguest (1.0)"))
        self.assertIsNone(ACCEPTANCE.verify_output(
            name, "vagrant-vmware-desktop (3.0.5, global)"
        ))
        name = "Pinned Windows 10 VMware box availability"
        self.assertIsNotNone(ACCEPTANCE.verify_output(
            name, "other/windows (vmware_desktop, 2024.01.06)"
        ))
        self.assertIsNone(ACCEPTANCE.verify_output(
            name, "mayfly/windows10 (vmware_desktop, 2024.01.06)"
        ))

    def test_existing_vm_and_unexpected_vmrun_output_block(self):
        name = "Existing VMware VM inventory (read-only)"
        self.assertIsNotNone(ACCEPTANCE.verify_output(name, "unexpected success"))
        self.assertIsNone(ACCEPTANCE.verify_output(
            name, "Total running VMs: 1\n/home/host/NORTH.vmx"
        ))
        self.assertIsNotNone(ACCEPTANCE.verify_output(
            name, "Total running VMs: 1\n/home/operator/WSLPE/WSLPE-WS01.vmx"
        ))
        self.assertIsNotNone(ACCEPTANCE.verify_output(
            name, "Total running VMs: 1\n/home/host/kingdoms-lpe-ws01.vmx"
        ))

    def test_preview_and_network_require_explicit_success_evidence(self):
        name = "Native WSLPE Vagrantfile and inventory render + Ruby syntax"
        self.assertIsNotNone(ACCEPTANCE.verify_output(name, "status: success"))
        self.assertIsNone(ACCEPTANCE.verify_output(name, (
            "[PASS] Rendered native Kingdoms Vagrantfile Ruby syntax\n"
            "KINGDOMS WSLPE NATIVE INSTANCE RENDER: SOURCE PREVIEW PASS"
        )))
        name = "Live host/VPN/VMware candidate subnet collision inspection"
        self.assertIsNotNone(ACCEPTANCE.verify_output(name, "no output"))
        self.assertIsNone(ACCEPTANCE.verify_output(
            name, "[PASS] No candidate collision found in inspected Linux IPv4"
        ))

    def test_failed_subprocess_is_not_retried_or_cleaned_up(self):
        result = SimpleNamespace(returncode=1, stdout="failure", stderr="error")
        with patch.object(ACCEPTANCE.subprocess, "run", return_value=result) as call:
            ok, detail = ACCEPTANCE.run_check(
                "Dummy", ["python3", "-c", "pass"], 12
            )
        self.assertFalse(ok)
        self.assertIn("Exit code 1", detail)
        call.assert_called_once()
        self.assertTrue(call.call_args.kwargs["capture_output"])
        self.assertTrue(call.call_args.kwargs["check"] is False)

    def test_successful_subprocess_returns_success_without_mutation(self):
        result = SimpleNamespace(returncode=0, stdout="output", stderr="")
        with patch.object(ACCEPTANCE.subprocess, "run", return_value=result) as call:
            ok, detail = ACCEPTANCE.run_check(
                "Dummy", ["python3", "-c", "pass"], 12
            )
        self.assertTrue(ok)
        self.assertEqual(detail, "output")
        call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
