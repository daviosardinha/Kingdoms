"""NORTH Windows 10 evaluation maintenance; source and no-write gates."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/north-ws01-eval-maintenance.py"
spec = importlib.util.spec_from_file_location("north_ws01_eval", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Ws01EvaluationGateTests(unittest.TestCase):
    def fixture(self, temp):
        root = Path(temp) / "93fd1b-north-vmware" / "provider"
        location = root / ".vagrant/machines/GOAD-WS01/vmware_desktop/fake-uuid"
        location.mkdir(parents=True)
        vmx = location / "windows_10.vmx"
        vmx.write_text(
            'ethernet0.connectionType = "nat"\n'
            'ethernet1.present = "TRUE"\n'
            'ethernet1.connectionType = "custom"\n'
            'ethernet1.vnet = "vmnet10"\n'
            'ethernet1.address = "00:50:56:20:10:31"\n',
            encoding="utf-8",
        )
        (location.parent / "id").write_text(str(vmx), encoding="utf-8")
        return root, vmx

    def test_exact_vmware_registration_and_winrm_port(self):
        with TemporaryDirectory() as temp:
            root, vmx = self.fixture(temp)
            self.assertEqual(mod.vmx_identity(root), (root, vmx))
            self.assertEqual(mod.forwarded_winrm_port(
                "5985 (guest) => 2207 (host)\n"
                "5986 (guest) => 2208 (host)\n"
                "22 (guest) => 2209 (host)\n"
            ), 2207)

    def test_reject_wrong_guest_network_or_vm_registration(self):
        with TemporaryDirectory() as temp:
            root, vmx = self.fixture(temp)
            for bad in (
                'ethernet1.vnet = "vmnet20"',
                'ethernet1.address = "00:50:56:20:10:22"',
            ):
                with self.subTest(bad=bad):
                    original = vmx.read_text()
                    lines = original.splitlines()
                    if "vnet" in bad:
                        modified = original.replace('ethernet1.vnet = "vmnet10"', bad)
                    else:
                        modified = original.replace(
                            'ethernet1.address = "00:50:56:20:10:31"', bad)
                    vmx.write_text(modified)
                    with self.assertRaisesRegex(ValueError, "NIC contract"):
                        mod.vmx_identity(root)
                    vmx.write_text(original)
            for value in (
                "", "5985 (guest) => 2207 (host)\n5985 (guest) => 2211 (host)",
                "5985 (guest) => 80 (host)"
            ):
                with self.assertRaises(ValueError):
                    mod.forwarded_winrm_port(value)

    def test_off_guest_refused_before_ansible_without_explicit_start(self):
        with TemporaryDirectory() as temp:
            root, vmx = self.fixture(temp)
            first = SimpleNamespace(returncode=0, stdout="")
            stopped = SimpleNamespace(returncode=0, stdout="Total running VMs: 0\n")
            with patch.object(mod, "checked", side_effect=[first, stopped]) as runner:
                with self.assertRaisesRegex(ValueError, "powered off"):
                    mod.main(["--provider-dir", str(root)])
                self.assertEqual(runner.call_count, 2)
                self.assertEqual(runner.call_args_list[0].args[0][:3],
                                 ["sudo", "-n", "bash"])

    def test_reuse_original_kingdoms_role_and_verify_rearm(self):
        role = (ROOT / "ansible/roles/settings/eval_rearm/tasks/main.yml").read_text()
        playbook = (ROOT / "ansible/north-ws01-eval-maintenance.yml").read_text()
        provider = (ROOT / "goad/provider/vagrant/vmware_kingdoms.py").read_text()
        for marker in (
            "TIMEBASED_EVAL", "GracePeriodRemaining", "ansible.windows.win_reboot",
            "WINDOWS_EVAL_READY=PASS",
        ):
            self.assertIn(marker, role)
        self.assertIn("name: settings/eval_rearm", playbook)
        self.assertIn("hosts: ws01", playbook)
        self.assertIn("NORTH_WS01_LICENSE_READY=PASS", playbook)
        self.assertIn("north-ws01-eval-maintenance.py", provider)
        self.assertLess(
            provider.index("north-ws01-eval-maintenance.py"),
            provider.index("if self.lab_name == 'NORTH':\n            # Native reduced topology")
        )
        for banned in ("Stop-Service WLMS", "SkipRearm", "Set-NetFirewallProfile -Enabled False"):
            self.assertNotIn(banned, role + playbook + PATH.read_text())


if __name__ == "__main__":
    unittest.main()
