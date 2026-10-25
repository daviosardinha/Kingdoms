"""WS01 signed Tools orphan must recover before Vagrant on existing NORTH resume."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from goad.course1_tools_transition import NorthToolsTransitionBlocked
from tests.test_north_provider_canonical_resume import isolated_method
from tests.test_north_tools_transition import isolated_method as isolated_gate


class Ws01PreVagrantRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.probe = isolated_method("_north_existing_ws01_orphan_before_vagrant")
        self.runtime = SimpleNamespace(
            lab_name="NORTH", path="/owned/north/provider",
            _vmx_path=Mock(return_value="/owned/ws01.vmx"),
            _winrm_forwarded_port=Mock(return_value=2204),
            _wait_winrm_ready=Mock(return_value=True),
            _winrm_session=Mock(return_value=object()),
            _north_tools_transition_gate=Mock(return_value=True),
            _north_existing_canonical_ready=Mock(return_value=True),
        )

    def test_signed_orphan_is_recovered_before_any_vagrant_up(self):
        with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                   return_value=("/owned/ws01.vmx", "partial")):
            self.assertIs(self.probe(self.runtime, "GOAD-WS01"), True)
        self.runtime._north_tools_transition_gate.assert_called_once_with(
            "GOAD-WS01", "pre-vagrant-ws01-resume")
        self.runtime._north_existing_canonical_ready.assert_called_once_with("GOAD-WS01")

    def test_guest_without_registered_vmx_follows_ordinary_vagrant(self):
        self.runtime._vmx_path.return_value = None
        with patch("goad.course1_tools_transition.inspect_owned_guest_tools") as inspect:
            self.assertIsNone(self.probe(self.runtime, "GOAD-WS01"))
        inspect.assert_not_called()
        self.runtime._north_tools_transition_gate.assert_not_called()

    def test_running_guest_with_healthy_tools_still_requires_normal_canonical_gate(self):
        with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                   return_value=("/owned/ws01.vmx", "healthy")):
            self.assertIsNone(self.probe(self.runtime, "GOAD-WS01"))
        self.runtime._north_tools_transition_gate.assert_not_called()

    def test_foreign_or_unverified_guest_blocks_before_repair(self):
        with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                   side_effect=NorthToolsTransitionBlocked("wrong MAC")):
            self.assertIs(self.probe(self.runtime, "GOAD-WS01"), False)
        self.runtime._north_tools_transition_gate.assert_not_called()

    def test_unverified_post_repair_canonical_proof_blocks_vagrant(self):
        self.runtime._north_existing_canonical_ready.return_value = None
        with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                   return_value=("/owned/ws01.vmx", "partial")):
            self.assertIs(self.probe(self.runtime, "GOAD-WS01"), False)

    def test_unavailable_forwarded_winrm_allows_original_vagrant_path(self):
        self.runtime._winrm_forwarded_port.return_value = None
        with patch("goad.course1_tools_transition.inspect_owned_guest_tools") as inspect:
            self.assertIsNone(self.probe(self.runtime, "GOAD-WS01"))
        inspect.assert_not_called()

    def test_scope_is_exact_north_ws01(self):
        self.assertIsNone(self.probe(self.runtime, "GOAD-SRV02"))
        self.runtime.lab_name = "GOAD"
        self.assertIsNone(self.probe(self.runtime, "GOAD-WS01"))
        self.runtime._winrm_forwarded_port.assert_not_called()


class EarlyVagrantGateTests(unittest.TestCase):
    def test_one_existing_signed_orphan_install_never_replayed_post_rearm(self):
        with TemporaryDirectory() as temp:
            provider = Path(temp)/"ab12cd-north-vmware"/"provider"
            provider.mkdir(parents=True)
            runtime = Mock()
            runtime.lab_name = "NORTH"
            runtime.path = str(provider)
            runtime._winrm_forwarded_port.return_value = 2204
            runtime._wait_winrm_ready.return_value = True
            runtime._authenticated_guest_install_ready.return_value = True
            runtime._install_vmware_tools.return_value = False
            gate = isolated_gate("_north_tools_transition_gate", logger=Mock())
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       side_effect=[("/owned/ws01.vmx","partial"),
                                    ("/owned/ws01.vmx","healthy")]), \
                 patch("goad.course1_tools_transition.prove_idle_signed_original_ws01_orphan",
                       return_value=True) as fingerprint:
                self.assertTrue(gate(runtime,"GOAD-WS01","pre-vagrant-ws01-resume"))
            fingerprint.assert_called_once()
            runtime._install_vmware_tools.assert_called_once_with(
                "GOAD-WS01","/owned/ws01.vmx",2204)
            marker = provider.parent/".north-vmtools-GOAD-WS01-post-ws01-eval.attempted"
            self.assertTrue(marker.exists())
            entries=[json.loads(x) for x in
                     (provider.parent/".north-install-recovery.jsonl").read_text().splitlines()]
            self.assertIn("pre-vagrant-ws01-resume",
                          [x["phase"] for x in entries])
            self.assertIn("VMTOOLS_REPAIR_VERIFIED",
                          [x["signature"] for x in entries])
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       return_value=("/owned/ws01.vmx","partial")), \
                 patch("goad.course1_tools_transition.prove_idle_signed_original_ws01_orphan",
                       return_value=True), patch("time.sleep"):
                self.assertFalse(gate(runtime,"GOAD-WS01","post-ws01-eval"))
            runtime._install_vmware_tools.assert_called_once()

    def test_provider_checks_early_orphan_before_vagrant(self):
        source = (Path(__file__).resolve().parents[1] /
                  "goad/provider/vagrant/vmware_kingdoms.py").read_text()
        self.assertLess(
            source.index("north_direct = self._north_existing_ws01_orphan_before_vagrant("),
            source.index("first_up = self.command.run_vagrant(['up', machine], self.path)")
        )
        self.assertIn(
            "if north_direct is False:\n                        return False",
            source
        )
        self.assertIn("if north_direct is True:", source)
        self.assertIn("post-ws01-eval' if machine == 'GOAD-WS01'", source)
        self.assertIn("original canonical identity", source)
        self.assertIn("north-ws01-eval-maintenance.py", source)


if __name__=="__main__":
    unittest.main()
