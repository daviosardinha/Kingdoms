"""No-VM, no-Windows tests for the private native one-shot WSLPE41 composition."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from kingdoms.wslpe41_install_flow import (
    FreshGuestAttestation, FreshGuestIdentity, InstallBlocked,
)
from kingdoms.wslpe41_native_stage1_bridge import NativeCreationEvidence
from kingdoms.wslpe41_native_orchestrator import (
    NativeRuntimeCapabilities, install_native_wslpe41,
)
from kingdoms.wslpe41_stage_executor import AnsibleStageContext


class NativeOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.instance = self.root / "workspace" / "fresh-wslpe"
        self.identity = FreshGuestIdentity(
            instance_id="fresh-wslpe", workspace=str(self.instance.parent),
            vmx=str(self.instance / "provider" / "guest.vmx"),
            subnet="172.28.232.0/24", source_commit="a" * 40,
        )
        self.creation = NativeCreationEvidence(
            identity=self.identity, previously_running=("/north.vmx",),
            previous_instance_ids=("other-guest",),
            newly_running_vmx=self.identity.vmx,
        )
        self.context = AnsibleStageContext(
            identity=self.identity, instance_dir=self.instance,
            ansible=self.root / "venv" / "ansible-playbook",
            inventory=self.instance / "ansible" / "inventory",
            private_vars=self.instance / "ansible" / "secrets",
            expected_address="172.28.232.31",
        )
        self.proof = FreshGuestAttestation(
            instance_id=self.identity.instance_id, vmx=self.identity.vmx,
            source_commit=self.identity.source_commit, created_by_this_install=True,
            standalone_workgroup=True, learner_ready=True,
            operator_recovery_ready=True, management_isolated=True,
            fresh_tls_identity=True,
        )
        self.manager = object()
        self.capabilities = NativeRuntimeCapabilities(
            prepare_management=Mock(return_value=self.context),
            console_recovery_check=Mock(return_value=True),
            attest_guest=Mock(return_value=self.proof),
            activate_jea_console=Mock(),
        )

    def _run(self, **kwargs):
        return install_native_wslpe41(
            self.manager, source_commit=self.identity.source_commit,
            approved_prefix="172.28.232",
            workspaces=(self.instance.parent, self.root / "existing"),
            state_root=self.root / "journal",
            capabilities=self.capabilities,
            confirmed=True, **kwargs,
        )

    def test_compose_once_with_provenance_bound_guest(self):
        order = []
        def creation(*args, **kwargs):
            order.append("creation")
            self.assertIs(args[0], self.manager)
            self.assertEqual(kwargs["approved_prefix"], "172.28.232")
            self.assertTrue(kwargs["confirmed"])
            return self.creation
        def foundation(context, **kwargs):
            order.append("foundation")
            self.assertIs(context, self.context)
            self.assertTrue(kwargs["operator_handoff_approved"])
            self.assertIs(kwargs["console_recovery_check"],
                          self.capabilities.console_recovery_check)
            self.assertEqual(kwargs["attest_fresh_guest"](self.identity), self.proof)
            return "foundation-proof"
        def install(identity, runner, state):
            order.append("41-stages")
            self.assertEqual(identity, self.identity)
            self.assertIs(runner.context, self.context)
            self.assertIs(runner.activate_jea_console,
                          self.capabilities.activate_jea_console)
            self.assertEqual(runner.attest_fresh_guest(identity), self.proof)
            self.assertEqual(state, self.root / "journal")
            return state / "fresh-install.json"
        with patch("kingdoms.wslpe41_native_orchestrator.create_guarded_native_guest",
                   side_effect=creation), \
             patch("kingdoms.wslpe41_native_orchestrator._guest") as exact_guest, \
             patch("kingdoms.wslpe41_native_orchestrator.prepare_native_foundation",
                   side_effect=foundation), \
             patch("kingdoms.wslpe41_native_orchestrator.install_41",
                   side_effect=install):
            result = self._run()
        self.assertEqual(order, ["creation", "foundation", "41-stages"])
        self.assertEqual(result.creation, self.creation)
        self.assertEqual(result.foundation, "foundation-proof")
        self.assertEqual(result.journal, self.root / "journal" / "fresh-install.json")
        exact_guest.assert_called_once_with(self.context)
        self.capabilities.prepare_management.assert_called_once_with(self.creation)
        self.capabilities.attest_guest.assert_called_with(self.creation)
        self.assertEqual(self.capabilities.attest_guest.call_count, 2)

    def test_unconfirmed_or_missing_runtime_capabilities_never_creates(self):
        with patch("kingdoms.wslpe41_native_orchestrator.create_guarded_native_guest") as create:
            with self.assertRaises(InstallBlocked):
                install_native_wslpe41(
                    self.manager, source_commit="a" * 40,
                    approved_prefix="172.28.232",
                    workspaces=(self.instance.parent,), state_root=self.root,
                    capabilities=self.capabilities, confirmed=False)
            for name in ("prepare_management", "console_recovery_check",
                         "attest_guest", "activate_jea_console"):
                missing = NativeRuntimeCapabilities(**{
                    field: (None if field == name else getattr(self.capabilities, field))
                    for field in ("prepare_management", "console_recovery_check",
                                  "attest_guest", "activate_jea_console")
                })
                with self.subTest(capability=name), self.assertRaises(InstallBlocked):
                    install_native_wslpe41(
                        self.manager, source_commit="a" * 40,
                        approved_prefix="172.28.232",
                        workspaces=(self.instance.parent,), state_root=self.root,
                        capabilities=missing, confirmed=True)
            create.assert_not_called()

    def test_management_context_mismatch_blocks_before_foundation(self):
        for field, value in (
            ("expected_address", "172.28.231.31"),
            ("inventory", self.root / "foreign" / "inventory"),
            ("instance_dir", self.root / "other"),
        ):
            with self.subTest(field=field):
                context = AnsibleStageContext(**{
                    **vars(self.context), field: value,
                })
                self.capabilities.prepare_management.return_value = context
                with patch("kingdoms.wslpe41_native_orchestrator.create_guarded_native_guest",
                           return_value=self.creation), \
                     patch("kingdoms.wslpe41_native_orchestrator.prepare_native_foundation") as foundation, \
                     patch("kingdoms.wslpe41_native_orchestrator.install_41") as install:
                    with self.assertRaisesRegex(InstallBlocked, "context differs"):
                        self._run()
                    foundation.assert_not_called()
                    install.assert_not_called()

    def test_creation_failure_stops_all_guest_mutation(self):
        with patch("kingdoms.wslpe41_native_orchestrator.create_guarded_native_guest",
                   side_effect=InstallBlocked("source mismatch")), \
             patch("kingdoms.wslpe41_native_orchestrator.prepare_native_foundation") as foundation, \
             patch("kingdoms.wslpe41_native_orchestrator.install_41") as install:
            with self.assertRaisesRegex(InstallBlocked, "source mismatch"):
                self._run()
            foundation.assert_not_called()
            install.assert_not_called()
            self.capabilities.prepare_management.assert_not_called()

    def test_failed_console_handoff_never_reaches_41_stages(self):
        with patch("kingdoms.wslpe41_native_orchestrator.create_guarded_native_guest",
                   return_value=self.creation), \
             patch("kingdoms.wslpe41_native_orchestrator._guest"), \
             patch("kingdoms.wslpe41_native_orchestrator.prepare_native_foundation",
                   side_effect=InstallBlocked("console unavailable")) as foundation, \
             patch("kingdoms.wslpe41_native_orchestrator.install_41") as install:
            with self.assertRaisesRegex(InstallBlocked, "console unavailable"):
                self._run()
            foundation.assert_called_once()
            install.assert_not_called()

    def test_attestor_refuses_other_native_vm_identity(self):
        foreign = FreshGuestIdentity(
            "another-vm", self.identity.workspace,
            self.identity.vmx, self.identity.subnet, self.identity.source_commit,
        )
        def foundation(context, **kwargs):
            kwargs["attest_fresh_guest"](foreign)
        with patch("kingdoms.wslpe41_native_orchestrator.create_guarded_native_guest",
                   return_value=self.creation), \
             patch("kingdoms.wslpe41_native_orchestrator._guest"), \
             patch("kingdoms.wslpe41_native_orchestrator.prepare_native_foundation",
                   side_effect=foundation), \
             patch("kingdoms.wslpe41_native_orchestrator.install_41") as install:
            with self.assertRaisesRegex(InstallBlocked, "another guest"):
                self._run()
            install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
