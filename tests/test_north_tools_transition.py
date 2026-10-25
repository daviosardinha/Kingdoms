"""NORTH VMware Tools transition regression tests; no live VM or Windows work."""
import ast
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from goad.course1_direct_winrm import EXPECTED, NorthGuestRecoveryBlocked
from goad.course1_tools_transition import (
    NorthToolsTransitionBlocked, inspect_owned_guest_tools
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"


def isolated_method(name, *, logger=None, fake_time=None):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    klass = next(x for x in tree.body if isinstance(x, ast.ClassDef)
                 and x.name == "GoadKingdomsVmwareProvider")
    method = next(x for x in klass.body if isinstance(x, ast.FunctionDef)
                  and x.name == name)
    ns = {"Log": logger or Mock(), "os": os, "time": fake_time or __import__("time")}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns[name]


class GuestToolsInventoryTests(unittest.TestCase):
    def make_guest(self, *, machine="GOAD-SRV02", tools="missing"):
        nat_mac = "000C29691040"
        lab_mac = EXPECTED[machine].replace(":", "").upper()
        lab_addr = {
            "GOAD-DC01": "10.4.20.10", "GOAD-DC02": "10.4.10.11",
            "GOAD-SRV02": "10.4.10.22", "GOAD-WS01": "10.4.10.31",
        }[machine]
        data = {
            "Windows": True, "Hostname": "CASTELBLACK",
            "Adapters": [
                {"Mac": nat_mac, "IPv4": ["192.168.213.135"]},
                {"Mac": lab_mac, "IPv4": [lab_addr]}
            ],
            "ToolsService": [], "ToolsExecutableExists": False,
            "ToolsProcessCount": 0, "InstalledVmwareTools": []
        }
        if tools == "healthy":
            data.update(
                ToolsService=[{"Name": "VMTools", "State": "Running"}],
                ToolsExecutableExists=True, ToolsProcessCount=2,
                InstalledVmwareTools=[]
            )
        elif tools == "partial":
            data["ToolsExecutableExists"] = True
        result = SimpleNamespace(status_code=0, std_out=json.dumps(data).encode(),
                                 std_err=b"")
        session = SimpleNamespace(run_ps=Mock(return_value=result))
        guest = {"address": lab_addr}
        vmx = {"ethernet0.generatedaddress": "00:0c:29:69:10:40"}
        return data, session, guest, vmx

    def test_all_missing_tools_markers_prove_single_installable_state(self):
        for case, state in (("missing", "missing"), ("healthy", "healthy"),
                            ("partial", "partial")):
            data, session, guest, settings = self.make_guest(tools=case)
            with self.subTest(case=case), patch(
                "goad.course1_tools_transition.owned_guest",
                return_value=(Path("/tmp/original.vmx"), guest, settings)
            ):
                vmx, result = inspect_owned_guest_tools("/owned/provider", "GOAD-SRV02", session)
                self.assertEqual(result, state)
                self.assertEqual(vmx, "/tmp/original.vmx")

    def test_wrong_mac_or_lab_ip_fails_before_tools_state(self):
        data, session, guest, settings = self.make_guest()
        for mutate in (
            lambda x: x["Adapters"][0].update(Mac="001122334455"),
            lambda x: x["Adapters"][1].update(IPv4=["169.254.10.22"]),
            lambda x: x["Adapters"].append(x["Adapters"][1]),
            lambda x: x.update(Windows=False)
        ):
            other = json.loads(json.dumps(data))
            mutate(other)
            session.run_ps.return_value.std_out = json.dumps(other).encode()
            with patch("goad.course1_tools_transition.owned_guest",
                       return_value=(Path("/tmp/original.vmx"), guest, settings)), \
                 self.assertRaises(NorthToolsTransitionBlocked):
                inspect_owned_guest_tools("/owned/provider", "GOAD-SRV02", session)

    def test_unverified_tools_inventory_blocks(self):
        data, session, guest, settings = self.make_guest()
        data.pop("ToolsProcessCount")
        session.run_ps.return_value.std_out = json.dumps(data).encode()
        with patch("goad.course1_tools_transition.owned_guest",
                   return_value=(Path("/tmp/original.vmx"), guest, settings)), \
             self.assertRaises(NorthToolsTransitionBlocked):
            inspect_owned_guest_tools("/owned/provider", "GOAD-SRV02", session)


class NorthPostBootRepairTests(unittest.TestCase):
    def setUp(self):
        self.log = Mock()
        self.gate = isolated_method("_north_tools_transition_gate", logger=self.log)

    def guest(self, provider):
        return SimpleNamespace(
            lab_name="NORTH", path=str(provider),
            _winrm_forwarded_port=Mock(return_value=2207),
            _wait_winrm_ready=Mock(return_value=True),
            _winrm_session=Mock(return_value=Mock()),
            _authenticated_guest_install_ready=Mock(return_value=True),
            _install_vmware_tools=Mock(return_value=False),
        )

    def test_healthy_guest_never_installs_or_writes_marker(self):
        with TemporaryDirectory() as tmp:
            provider = Path(tmp)/"instance"/"provider"
            provider.mkdir(parents=True)
            guest = self.guest(provider)
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       return_value=("/owned/guest.vmx", "healthy")):
                self.assertTrue(self.gate(guest, "GOAD-WS01", "post-ws01-eval"))
            guest._install_vmware_tools.assert_not_called()
            self.assertFalse(list(provider.parent.glob("*.attempted")))

    def test_missing_tools_repaired_even_if_vmware_ip_telemetry_fails(self):
        with TemporaryDirectory() as tmp:
            provider = Path(tmp)/"instance"/"provider"
            provider.mkdir(parents=True)
            guest = self.guest(provider)
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       side_effect=[("/owned/guest.vmx", "missing"),
                                    ("/owned/guest.vmx", "healthy")]) as proof:
                self.assertTrue(self.gate(
                    guest, "GOAD-SRV02", "pre-exercise-isolation"
                ))
            self.assertEqual(proof.call_count, 2)
            guest._install_vmware_tools.assert_called_once_with(
                "GOAD-SRV02", "/owned/guest.vmx", 2207
            )
            self.assertTrue((provider.parent /
                             ".north-vmtools-GOAD-SRV02-pre-exercise-isolation.attempted").is_file())

    def test_missing_tools_with_failed_readiness_blocks_any_replay(self):
        class FastClock:
            def __init__(self): self.now = 0
            def monotonic(self): self.now += 250; return self.now
            def sleep(self, _): pass
        with TemporaryDirectory() as tmp:
            provider = Path(tmp)/"instance"/"provider"
            provider.mkdir(parents=True)
            guest = self.guest(provider)
            guest._authenticated_guest_install_ready.return_value = False
            gate = isolated_method("_north_tools_transition_gate",
                                   logger=self.log, fake_time=FastClock())
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       return_value=("/owned/guest.vmx", "missing")):
                self.assertFalse(gate(guest, "GOAD-DC01", "pre-exercise-isolation"))
                self.assertFalse(gate(guest, "GOAD-DC01", "pre-exercise-isolation"))
            guest._install_vmware_tools.assert_called_once()

    def test_partial_or_foreign_guest_refuses_any_install(self):
        with TemporaryDirectory() as tmp:
            provider = Path(tmp)/"instance"/"provider"
            provider.mkdir(parents=True)
            guest = self.guest(provider)
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       return_value=("/owned/guest.vmx", "partial")):
                self.assertFalse(self.gate(guest, "GOAD-SRV02", "pre-exercise-isolation"))
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       side_effect=NorthGuestRecoveryBlocked("wrong VMX")):
                self.assertFalse(self.gate(guest, "GOAD-SRV02", "pre-exercise-isolation"))
            guest._install_vmware_tools.assert_not_called()

    def test_north_scope_and_eval_phase_are_restricted(self):
        guest = self.guest("/owned/provider")
        for machine, phase in (
            ("GOAD-SRV03", "pre-exercise-isolation"),
            ("GOAD-SRV02", "post-ws01-eval"),
            ("GOAD-WS01", "unexpected")
        ):
            self.assertFalse(self.gate(guest, machine, phase))
        guest.lab_name = "GOAD"
        self.assertFalse(self.gate(guest, "GOAD-WS01", "post-ws01-eval"))
        guest._winrm_forwarded_port.assert_not_called()

    def test_installer_scopes_postrearm_and_preisolation_without_changing_goad(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("self._north_tools_transition_gate(machine, 'post-ws01-eval')", source)
        self.assertIn("self._north_post_rearm_guest_ready(machine, timeout=180)", source)
        self.assertLess(
            source.index("self._north_tools_transition_gate(machine, 'post-ws01-eval')"),
            source.index("self._north_post_rearm_guest_ready(machine, timeout=180)")
        )
        self.assertIn("self._north_tools_transition_gate(machine, 'pre-exercise-isolation')", source)
        self.assertIn("return super().finalize_install()", source)
        self.assertIn("if self.lab_name != 'NORTH':", source)
        self.assertIn("self.get_runtime_mode() != 'provisioning'", source)
        self.assertNotIn("vagrant up", source.split("def _north_tools_transition_gate",1)[1].split(
            "def _authenticated_guest_install_ready", 1
        )[0])
        self.assertNotIn("ansible-playbook", source.split("def _north_tools_transition_gate",1)[1].split(
            "def _authenticated_guest_install_ready", 1
        )[0])


if __name__ == "__main__":
    unittest.main()
