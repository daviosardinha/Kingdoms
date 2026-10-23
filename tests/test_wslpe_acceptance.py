"""Tests for the consolidated WSLPE operator preboot gate.

No subprocess in these tests is allowed to actually run Vagrant/VMware,
or connect to a Windows guest.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
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

    def test_preboot_native_import_works_with_absolute_script_and_isolated_python(self):
        # Real operator invokes this script by absolute path from the repo's
        # goad_nomad console. A direct execution must not rely on PYTHONPATH
        # implicitly set by the unittest runner or current working directory.
        snippet = (
            "import runpy\n"
            f"source = runpy.run_path({str(SCRIPT)!r}, run_name='isolated_preboot_probe')\n"
            "result = source['verify_peer_wslpe_inventory']("
            "'Total running VMs: 0\\n', '172.28.232')\n"
            "assert result is None, result\n"
        )
        actual = subprocess.run(
            [sys.executable, "-I", "-c", snippet], cwd="/",
            capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(actual.returncode, 0, actual.stderr)

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

    def _registered_peer(self, root: Path, prefix: str = "172.28.231"):
        instance = root / "peer" / "workspace" / "d986ad-wslpe-vmware"
        machine = (instance / "provider" / ".vagrant" / "machines" /
                   "WSLPE-WS01" / "vmware_desktop")
        vmx = machine / "native-uuid" / "windows_10.vmx"
        vmx.parent.mkdir(parents=True)
        vmx.write_text('config.version = "8"\n')
        (machine / "id").write_text(str(vmx))
        (instance / "instance.json").write_text(json.dumps({
            "id": instance.name, "lab": "WSLPE", "provider": "vmware",
            "provisioner": "local", "status": "ready for provisioning",
            "extensions": [], "ip_range": prefix,
        }))
        return vmx, instance

    def test_existing_registered_peer_wslpe_can_coexist_on_separate_subnet(self):
        name = "Existing VMware VM inventory (read-only)"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vmx, instance = self._registered_peer(root)
            output = "Total running VMs: 2\n" + str(vmx) + "\n/north/GOAD-DC01.vmx\n"
            with patch.object(ACCEPTANCE, "ROOT", root / "fresh"):
                self.assertIsNone(ACCEPTANCE.verify_output(
                    name, output, candidate_prefix="172.28.232"))
                self.assertIsNotNone(ACCEPTANCE.verify_output(
                    name, output, candidate_prefix="172.28.231"))
                self.assertIsNotNone(ACCEPTANCE.verify_output(name, output))
                # Existing guest is accepted only through its exact Vagrant ID.
                (instance / "provider" / ".vagrant" / "machines" /
                 "WSLPE-WS01" / "vmware_desktop" / "id").write_text("/wrong.vmx")
                self.assertIsNotNone(ACCEPTANCE.verify_output(
                    name, output, candidate_prefix="172.28.232"))

    def test_unregistered_prototype_or_same_checkout_vm_is_blocked(self):
        name = "Existing VMware VM inventory (read-only)"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vmx, instance = self._registered_peer(root)
            output = "Total running VMs: 1\n" + str(vmx) + "\n"
            with patch.object(ACCEPTANCE, "ROOT", instance.parent.parent):
                self.assertIsNotNone(ACCEPTANCE.verify_output(
                    name, output, candidate_prefix="172.28.232"))
            for raw in (
                "/home/user/vmware/KINGDOMS-WSLPE41-LEARNER-TEST/test.vmx",
                "/home/user/WSLPE-WS01.vmx",
            ):
                with self.subTest(raw=raw):
                    suspicious = "Total running VMs: 1\n" + raw + "\n"
                    with patch.object(ACCEPTANCE, "ROOT", root / "fresh"):
                        self.assertIsNotNone(ACCEPTANCE.verify_output(
                            name, suspicious, candidate_prefix="172.28.232"))

    def test_vmware_inventory_must_be_complete_not_just_contain_header(self):
        name = "Existing VMware VM inventory (read-only)"
        for output in (
            "Total running VMs: 2\n/one.vmx\n",
            "Total running VMs: 2\n/one.vmx\n/one.vmx\n",
            "Total running VMs: 0\n/a.vmx\n",
        ):
            with self.subTest(output=output):
                self.assertIsNotNone(ACCEPTANCE.verify_output(
                    name, output, candidate_prefix="172.28.232"))

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
