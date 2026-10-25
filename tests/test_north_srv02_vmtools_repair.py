"""Source-only safety tests for exact NORTH SRV02 VMware Tools repair."""
from pathlib import Path
import importlib.util
import json
from types import SimpleNamespace
from unittest.mock import patch, Mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/north-srv02-vmtools-repair.py"
spec = importlib.util.spec_from_file_location("north_srv02_tools_repair", SOURCE)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


class SRV02ToolsRepairTests(unittest.TestCase):
    def test_missing_service_file_process_product_requires_all_absent(self):
        bare = {"ToolsService": [], "InstalledVmwareTools": [],
                "ToolsProcessCount": 0, "ToolsExecutableExists": False}
        self.assertTrue(script.absent_tools(bare))
        for change in (
            {"ToolsService": [{"Name": "VMTools"}]},
            {"InstalledVmwareTools": ["VMware Tools"]},
            {"ToolsProcessCount": 1},
            {"ToolsExecutableExists": True},
        ):
            self.assertFalse(script.absent_tools({**bare, **change}))
        for key in bare:
            wrong = dict(bare)
            wrong.pop(key)
            with self.assertRaises(script.RepairBlocked):
                script.absent_tools(wrong)

    def test_both_mac_and_lab_ip_are_required_on_live_winrm(self):
        original = {
            "Hostname": "CASTELBLACK",
            "Adapters": [
                {"Mac": "000C29999940", "IPv4": ["192.168.213.135"]},
                {"Mac": "005056201022", "IPv4": ["10.4.10.22"]},
            ],
            "ToolsService": [], "InstalledVmwareTools": [],
            "ToolsProcessCount": 0, "ToolsExecutableExists": False,
        }
        def session_for(record):
            result = SimpleNamespace(
                status_code=0, std_out=json.dumps(record).encode(), std_err=b""
            )
            return SimpleNamespace(run_ps=Mock(return_value=result))
        vmx = {"ethernet0.generatedaddress": "00:0c:29:99:99:40"}
        with patch.object(script, "_authenticated_session", return_value=session_for(original)):
            got = script.guest_evidence(Path("/owned"), vmx, 2207, "diagnostic")
        self.assertEqual(got, original)
        for change in (
            {"Adapters": [original["Adapters"][0]]},
            {"Adapters": [
                original["Adapters"][0],
                {"Mac": "005056201022", "IPv4": ["169.254.10.22"]},
            ]},
            {"Adapters": [original["Adapters"][0], original["Adapters"][0]]},
        ):
            with self.subTest(change=change):
                with patch.object(script, "_authenticated_session",
                                  return_value=session_for({**original, **change})):
                    with self.assertRaises(script.RepairBlocked):
                        script.guest_evidence(Path("/owned"), vmx, 2207, "diagnostic")

    def test_scope_and_no_unintended_mutation(self):
        text = SOURCE.read_text()
        for marker in (
            'IDENTITY = "8aafc9-north-vmware"',
            'MACHINE = "GOAD-SRV02"',
            'EXPECTED_IP = "10.4.10.22"',
            '("--confirm-srv02-repair", action="store_true"',
            'os.O_EXCL',
            'owned_guest(provider, MACHINE)',
            'require(absent_tools(before)',
            'runtime._install_vmware_tools(MACHINE, str(vmx), port)',
            'prove_canonical_guest(provider, MACHINE, timeout=12)',
            'NORTH_SRV02_VMTOOLS_REPAIR=PASS',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        for excluded in (
            'run_vagrant(["up"', 'vagrant", "up"', 'ansible-playbook',
            'vmrun", "-T", "ws", "start"', 'vmrun", "-T", "ws", "stop"',
            "shutil.rmtree", "slmgr.vbs", "set_runtime_mode(",
        ):
            self.assertNotIn(excluded, text)

    def test_installer_is_after_live_guest_proof_and_one_shot_marker(self):
        text = SOURCE.read_text()
        self.assertLess(text.index('before = guest_evidence('),
                        text.index('require(absent_tools(before)'))
        self.assertLess(text.index('require(absent_tools(before)'),
                        text.index('descriptor = os.open(marker,'))
        self.assertLess(text.index('descriptor = os.open(marker,'),
                        text.index('runtime._install_vmware_tools('))


if __name__ == "__main__":
    unittest.main()
