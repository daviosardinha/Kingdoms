"""Original NORTH WS01 Tools repair: offline unit and source safeguards.

Never reaches VMware, WinRM, sudo, Vagrant or changes the host.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch, call
from types import SimpleNamespace
import importlib.util
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/north-ws01-vmtools-repair.py"
spec = importlib.util.spec_from_file_location("north_tools_repair", SOURCE)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class NorthToolsRepairTests(unittest.TestCase):
    def test_missing_tools_is_the_only_writable_state(self):
        repair.require_uninstalled_tools({
            "ToolsService": [],
            "InstalledVmwareTools": [],
            "ToolsProcessCount": 0,
            "ToolsExecutableExists": False,
        })
        for value in (
            {"ToolsService": [{"Name": "VMTools"}]},
            {"InstalledVmwareTools": ["VMware Tools"]},
            {"ToolsProcessCount": 1},
            {"ToolsExecutableExists": True},
        ):
            payload = {
                "ToolsService": [], "InstalledVmwareTools": [],
                "ToolsProcessCount": 0, "ToolsExecutableExists": False,
            }
            payload.update(value)
            with self.subTest(value=value), self.assertRaises(repair.RepairBlocked):
                repair.require_uninstalled_tools(payload)

    def test_guest_mac_and_exact_lab_ip_must_prove_before_tools_call(self):
        diag = SimpleNamespace(
            parse_winrm_port=Mock(return_value=2207),
            verify_identity=Mock(),
            SCRIPT="Write-Output 'evidence'",
        )
        payload = {
            "Adapters": [{"Mac": "005056201031", "IPv4": ["10.4.10.31"]}],
            "ToolsService": [], "InstalledVmwareTools": [],
            "ToolsProcessCount": 0, "ToolsExecutableExists": False,
        }
        msg = json.dumps(payload).encode()
        session = SimpleNamespace(run_ps=Mock(return_value=SimpleNamespace(
            status_code=0, std_out=msg, std_err=b""
        )))
        with patch.object(repair, "_authenticated_session", return_value=session):
            actual = repair.collect_verified_state(
                diag, Path("/owned/provider"), {"ethernet0.generatedaddress": "a"}, 2207
            )
        self.assertEqual(actual, payload)
        diag.verify_identity.assert_called_once()
        payload["Adapters"][0]["IPv4"] = ["169.254.24.33"]
        session.run_ps.return_value.std_out = json.dumps(payload).encode()
        with patch.object(repair, "_authenticated_session", return_value=session), \
             self.assertRaises(repair.RepairBlocked):
            repair.collect_verified_state(diag, Path("/owned/provider"), {}, 2207)

    def test_identity_failure_prevents_tools_installation(self):
        diag = SimpleNamespace(parse_winrm_port=Mock(return_value=2207))
        original = (
            Path("/original/ws01.vmx"), {"address": "10.4.10.31"},
            {"ethernet0.generatedaddress": "00:0c:29:69:10:40"}
        )
        with patch.object(repair, "owned_guest", return_value=original), \
             patch.object(repair, "run_checked", return_value=""), \
             patch.object(repair, "collect_verified_state",
                          side_effect=repair.RepairBlocked("wrong MAC")), \
             patch.object(repair, "new_runtime") as vm:
            with self.assertRaisesRegex(repair.RepairBlocked, "wrong MAC"):
                repair.repair_one_guest(diag, Path("/owned/provider"))
            vm.assert_not_called()

    def test_exact_one_existing_install_and_strict_postcheck(self):
        diag = SimpleNamespace(parse_winrm_port=Mock(return_value=2207))
        original = (
            Path("/original/ws01.vmx"), {"address": "10.4.10.31"},
            {"ethernet0.generatedaddress": "00:0c:29:69:10:40"}
        )
        before = {
            "ToolsService": [], "InstalledVmwareTools": [],
            "ToolsProcessCount": 0, "ToolsExecutableExists": False,
        }
        after = {
            "ToolsService": [{"Name": "VMTools", "State": "Running"}],
            "InstalledVmwareTools": ["VMware Tools"],
            "ToolsProcessCount": 1, "ToolsExecutableExists": True,
        }
        runtime = Mock()
        runtime._install_vmware_tools.return_value = True
        runtime._north_post_rearm_guest_ready.return_value = True
        with patch.object(repair, "owned_guest", return_value=original), \
             patch.object(repair, "run_checked", return_value=""), \
             patch.object(repair, "collect_verified_state",
                          side_effect=[before, after]) as proof, \
             patch.object(repair, "new_runtime",
                          return_value=runtime):
            repair.repair_one_guest(diag, Path("/owned/provider"))
        runtime.set_instance_path.assert_called_once_with("/owned/provider")
        runtime._install_vmware_tools.assert_called_once_with(
            "GOAD-WS01", "/original/ws01.vmx", 2207
        )
        runtime._north_post_rearm_guest_ready.assert_called_once_with(
            "GOAD-WS01", timeout=180
        )
        self.assertEqual(proof.call_count, 2)

    def test_failed_or_ambiguous_tools_state_is_never_installed(self):
        diag = SimpleNamespace(parse_winrm_port=Mock(return_value=2207))
        original = (
            Path("/original/ws01.vmx"), {"address": "10.4.10.31"}, {}
        )
        state = {
            "ToolsService": [], "InstalledVmwareTools": ["VMware Tools"],
            "ToolsProcessCount": 0, "ToolsExecutableExists": False,
        }
        with patch.object(repair, "owned_guest", return_value=original), \
             patch.object(repair, "run_checked", return_value=""), \
             patch.object(repair, "collect_verified_state", return_value=state), \
             patch.object(repair, "new_runtime") as vm:
            with self.assertRaises(repair.RepairBlocked):
                repair.repair_one_guest(diag, Path("/owned/provider"))
            vm.assert_not_called()

    def test_pre_anisble_failed_receipt_must_match_exact_attempt(self):
        with TemporaryDirectory() as folder:
            d = Path(folder)/"8aafc9-north-vmware"
            (d/"install-timings").mkdir(parents=True)
            (d/"instance.json").write_text(json.dumps({
                "id":repair.INSTANCE_ID,"lab":"NORTH","provider":"vmware",
                "status":"not provided"}))
            receipt = {
                "attempt_id":"20261024T231210Z-e678c23cc64a",
                "instance_id": repair.INSTANCE_ID,
                "status":"failed","provider_success":False,"ansible_phases":[]
            }
            p = d/"install-timings"/"receipt.json"
            p.write_text(json.dumps(receipt))
            repair.exact_failed_instance(d)
            receipt["provider_success"] = True
            p.write_text(json.dumps(receipt))
            with self.assertRaises(repair.RepairBlocked):
                repair.exact_failed_instance(d)

    def test_no_replication_or_auto_repair_at_install(self):
        src = SOURCE.read_text()
        self.assertIn("runtime._install_vmware_tools(MACHINE, str(vmx), port)", src)
        self.assertIn("runtime._north_post_rearm_guest_ready(MACHINE, timeout=180)", src)
        self.assertIn("diag.verify_identity(payload, values)", src)
        self.assertIn("fcntl.LOCK_EX | fcntl.LOCK_NB", src)
        self.assertIn('CONFIRMATION = "--confirm-vmtools-repair"', src)
        self.assertNotIn("vagrant\", \"up\"", src)
        self.assertNotIn("slmgr", src)
        self.assertNotIn("ansible-playbook", src)
        self.assertNotIn("vmrun\", \"start\"", src)
        self.assertNotIn("rm -rf", src)


if __name__ == "__main__":
    unittest.main()
