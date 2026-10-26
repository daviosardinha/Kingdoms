"""NORTH runtime acceptance dispatch and safety gates (source-only unit tests)."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
NORTH = ROOT / "scripts/validate-north-runtime.sh"
LEGACY = ROOT / "scripts/validate-network-segmentation.sh"
PROVIDER = ROOT / "goad/provider/vagrant/vmware_nomad.py"
CONTROLLER = ROOT / "goad_nomad.py"
PLAYBOOK = ROOT / "ansible/north-exercise-health-readonly.yml"


def compile_method(path, class_name, function_name, globals=None):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == class_name)
    method = next(x for x in cls.body
                  if isinstance(x, ast.FunctionDef) and x.name == function_name)
    scope = dict(globals or {})
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), scope)
    return scope[function_name]


class NorthRuntimeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.north = NORTH.read_text(encoding="utf-8")
        cls.legacy = LEGACY.read_text(encoding="utf-8")
        cls.playbook = PLAYBOOK.read_text(encoding="utf-8")

    def test_bash_syntax_and_inline_python_compile(self):
        subprocess.run(["bash", "-n", str(NORTH)], check=True)
        fragments = re.findall(r"<<'PY'\n(.*?)\nPY(?:\n|$)", self.north, re.S)
        self.assertEqual(len(fragments), 3)
        for i, fragment in enumerate(fragments):
            with self.subTest(fragment=i):
                ast.parse(fragment)

    def test_no_unintentional_provisioning_or_host_mutation(self):
        for forbidden in (
            "lab-mode.sh\" provisioning", "lab-mode.sh provisioning",
            "vagrant up", "vagrant destroy", "vmrun -T ws start",
            "vmrun -T ws stop", "connectNamedDevice", "disconnectNamedDevice",
            "ip route add", "ip route del", "Reset-ComputerMachinePassword",
            "w32tm.exe /resync", "Restart-Service", "clear-dns",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.north)
                self.assertNotIn(forbidden, self.playbook)
        self.assertIn("GOAD_LAB_PROFILE", self.north)
        self.assertIn("sudo -n bash", self.north)
        self.assertIn("vmnet20", self.north)
        self.assertIn("policy drop;", self.north)
        self.assertIn('NORTH_EXERCISE_MODE_PRESERVED', self.north)
        self.assertIn("NORTH_RUNTIME_ACCEPTANCE=PASS", self.north)
        self.assertIn("changed_when: false", self.playbook)

    def test_guest_roster_and_runtime_ad_only_north(self):
        self.assertIn('"GOAD-ROUTER"', self.north)
        for guest in ("GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"):
            self.assertIn(guest, self.north)
        self.assertNotIn("GOAD-DC03", self.north)
        self.assertNotIn("GOAD-SRV03", self.north)
        self.assertNotIn("essos.local", self.north.lower())
        self.assertIn("hosts: dc02:srv02:ws01", self.playbook)
        self.assertNotIn("hosts: all", self.playbook)
        self.assertIn("Test-ComputerSecureChannel", self.playbook)
        self.assertIn("kingslanding.sevenkingdoms.local", self.playbook)


    def test_parent_root_dc_requires_guest_side_authenticated_proof(self):
        # No host vmnet20 route or NAT fallback: hop is DC02 -> DC01.
        self.assertIn("hosts: dc02:srv02:ws01", self.playbook)
        self.assertIn("hosts: dc02\n", self.playbook)
        self.assertIn("New-PSSession -ComputerName $target -Port 5986 -UseSSL", self.playbook)
        self.assertIn("-Credential $ParentCredential", self.playbook)
        self.assertIn("Invoke-Command -Session $session", self.playbook)
        self.assertIn("param([PSCredential]$ParentCredential)", self.playbook)
        self.assertIn("sensitive_parameters:", self.playbook)
        self.assertIn('password: "{{ ansible_password }}"', self.playbook)
        self.assertIn("Remove-PSSession -Session $session", self.playbook)
        for expected in (
            "NTDS','DNS','ADWS','Netlogon','Kdc','W32Time",
            "SYSVOL','NETLOGON",
            "Get-CimInstance Win32_ComputerSystem",
            "DomainRole -ne 5",
            "Get-SmbShare -Name $name",
            "_ldap._tcp.dc._msdcs.sevenkingdoms.local",
            "nltest.exe '/dsgetdc:sevenkingdoms.local' /timeserv /force",
            "w32tm.exe /query /source",
            "w32tm.exe /query /status",
        ):
            self.assertIn(expected, self.playbook)
        self.assertIn(
            'NORTH_PARENT_DC_AD_HEALTH=PASS host=KINGSLANDING',
            self.north,
        )
        self.assertIn('NORTH_PARENT_DC_AD_HEALTH_READY', self.north)
        self.assertLess(
            self.north.index('NORTH_PARENT_DC_AD_HEALTH_READY'),
            self.north.index('NORTH_RUNTIME_ACCEPTANCE=PASS'),
        )

    def test_parent_direct_proof_has_no_fallback_or_guest_modification(self):
        parent = self.playbook.split(
            "- name: Verify KINGSLANDING directly through the permitted inter-DC path",
            1
        )[1]
        self.assertIn("changed_when: false", parent)
        self.assertIn("'NORTH_PARENT_DC_AD_HEALTH=PASS host=KINGSLANDING'", parent)
        for forbidden in (
            "Reset-ComputerMachinePassword", "Restart-Service",
            "Start-Service", "Set-ItemProperty", "New-ItemProperty",
            "w32tm.exe /config", "w32tm.exe /resync",
            "ip route", "ethernet0.startConnected", "vagrant",
            "Set-NetFirewallRule", "New-NetFirewallRule",
            "Add-Computer", "New-PSSession -ComputerName 10.4.20.10",
        ):
            self.assertNotIn(forbidden, parent)
        self.assertNotIn("ignore_errors: true", parent)
        self.assertNotIn("failed_when: false", parent)
        self.assertNotIn("rescue:", parent)


class NorthRuntimeProviderDispatchTests(unittest.TestCase):
    def setUp(self):
        self.logger = Mock()
        self.subprocess = Mock()
        self.subprocess.run.return_value.returncode = 0
        self.method = compile_method(
            PROVIDER, "GoadNomadVmwareProvider", "validate_runtime",
            {"Log": self.logger, "subprocess": self.subprocess}
        )

    def provider(self, lab):
        p = SimpleNamespace(
            lab_name=lab,
            path="/owned/provider",
            is_goad_nomad_segmented=lambda: True,
            _script=lambda name: "/repo/scripts/" + name,
            _project_root_from_script=lambda path: "/repo",
            _provider_env=lambda: {"GOAD_PROVIDER_DIR": "/owned/provider"},
        )
        return p

    def test_north_uses_read_only_profile_specific_script(self):
        p = self.provider("NORTH")
        self.assertTrue(self.method(p))
        args = self.subprocess.run.call_args
        self.assertEqual(args.args[0], ["bash", "/repo/scripts/validate-north-runtime.sh"])
        self.assertEqual(args.kwargs["env"], p._provider_env())

    def test_full_kingdoms_keeps_its_existing_validator(self):
        p = self.provider("GOAD")
        self.assertTrue(self.method(p))
        self.assertEqual(
            self.subprocess.run.call_args.args[0],
            ["bash", "/repo/scripts/validate-network-segmentation.sh"],
        )

    def test_validator_fails_closed(self):
        self.subprocess.run.return_value.returncode = 1
        self.assertFalse(self.method(self.provider("NORTH")))


class ValidateCLIExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.logger = Mock()
        self.validate = compile_method(
            CONTROLLER, "GoadNomad", "do_validate",
            {"Log": self.logger, "READY": "installed"}
        )
        tree = ast.parse(CONTROLLER.read_text(encoding="utf-8"))
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_dispatch_task")
        ns = {"Log": self.logger}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(CONTROLLER), "exec"), ns)
        self.dispatch = ns["_dispatch_task"]

    def test_console_reports_success_only_after_proof(self):
        provider = Mock()
        provider.validate_runtime.return_value = True
        current = Mock()
        console = SimpleNamespace(
            _nomad_provider=lambda require_instance: provider,
            lab_manager=SimpleNamespace(get_current_instance=lambda: current)
        )
        self.assertTrue(self.validate(console))
        current.set_status.assert_called_once_with("installed")

    def test_console_never_marks_ready_on_failure(self):
        provider = Mock()
        provider.validate_runtime.return_value = False
        current = Mock()
        console = SimpleNamespace(
            _nomad_provider=lambda require_instance: provider,
            lab_manager=SimpleNamespace(get_current_instance=lambda: current)
        )
        self.assertFalse(self.validate(console))
        current.set_status.assert_not_called()

    def test_cli_success_and_failure_exit_codes(self):
        args = SimpleNamespace(
            task="validate", instance="57bbec-north-vmware",
            run_playbook=None, ansible_only=None
        )
        for success, expected in ((True, 0), (False, 1)):
            with self.subTest(success=success):
                console = Mock()
                console.do_validate.return_value = success
                self.assertEqual(self.dispatch(console, args), expected)
                console.do_load.assert_called_once_with(args.instance)


if __name__ == "__main__":
    unittest.main()
