"""Contract tests: native WSLPE foundation reuses existing playbooks."""
from unittest.mock import patch
import unittest

from kingdoms.wslpe41_install_flow import FreshGuestIdentity, FreshGuestAttestation, InstallBlocked
from kingdoms.wslpe41_native_foundation_handoff import prepare_native_foundation

IDENTITY = FreshGuestIdentity("abcd1234", "/tmp/workspace", "/tmp/workspace/guest.vmx",
                              "172.28.232.0/24", "a" * 40)


def attestation(**overrides):
    fields = dict(instance_id=IDENTITY.instance_id, vmx=IDENTITY.vmx,
                  source_commit=IDENTITY.source_commit, created_by_this_install=True,
                  standalone_workgroup=True, learner_ready=True,
                  operator_recovery_ready=True, management_isolated=True,
                  fresh_tls_identity=True)
    fields.update(overrides)
    return FreshGuestAttestation(**fields)


class FoundationHandoffTests(unittest.TestCase):
    def setUp(self):
        self.context = type("Context", (), {"identity": IDENTITY})()
        p = patch("kingdoms.wslpe41_native_foundation_handoff.authenticate_native_operator", return_value=True)
        self.probe = p.start()
        self.addCleanup(p.stop)

    def test_no_approval_or_recovery_prevents_mutation(self):
        with patch("kingdoms.wslpe41_native_foundation_handoff.run_foundation_stage") as run:
            for approved, recovery in ((False, lambda _: True), (True, lambda _: False)):
                with self.subTest(approved=approved):
                    with self.assertRaises(InstallBlocked):
                        prepare_native_foundation(self.context,
                            operator_handoff_approved=approved,
                            console_recovery_check=recovery,
                            attest_fresh_guest=lambda _: attestation())
            run.assert_not_called()

    def test_missing_attestor_prevents_mutation(self):
        with patch("kingdoms.wslpe41_native_foundation_handoff.run_foundation_stage") as run:
            with self.assertRaises(InstallBlocked):
                prepare_native_foundation(self.context, operator_handoff_approved=True,
                    console_recovery_check=lambda _: True, attest_fresh_guest=None)
            run.assert_not_called()

    def test_existing_playbooks_run_in_order(self):
        def run(context, stage, **kwargs):
            return type("Proof", (), dict(stage=stage, passed=True,
                instance_id=IDENTITY.instance_id, vmx=IDENTITY.vmx))()
        with patch("kingdoms.wslpe41_native_foundation_handoff.run_foundation_stage", side_effect=run) as mocked:
            result = prepare_native_foundation(self.context,
                operator_handoff_approved=True, console_recovery_check=lambda _: True,
                attest_fresh_guest=lambda _: attestation())
        self.assertEqual([call.args[1] for call in mocked.call_args_list], ["learner", "operator"])
        self.assertTrue(result.attestation.operator_recovery_ready)

    def test_account_creation_does_not_replace_operator_attestation(self):
        def run(context, stage, **kwargs):
            return type("Proof", (), dict(passed=True, instance_id=IDENTITY.instance_id,
                vmx=IDENTITY.vmx, operator_authenticated=False))()
        with patch("kingdoms.wslpe41_native_foundation_handoff.run_foundation_stage", side_effect=run):
            with self.assertRaises(InstallBlocked):
                prepare_native_foundation(self.context,
                    operator_handoff_approved=True, console_recovery_check=lambda _: True,
                    attest_fresh_guest=lambda _: attestation(operator_recovery_ready=False),
                    authenticate_operator=lambda _: True)

    def test_operator_authentication_failure_blocks_attestation(self):
        def run(context, stage, **kwargs):
            return type("Proof", (), dict(passed=True,
                instance_id=IDENTITY.instance_id, vmx=IDENTITY.vmx))()
        self.probe.return_value = False
        with patch("kingdoms.wslpe41_native_foundation_handoff.run_foundation_stage", side_effect=run), \
             patch("kingdoms.wslpe41_native_foundation_handoff.verify_attestation") as verify:
            with self.assertRaises(InstallBlocked):
                prepare_native_foundation(self.context,
                    operator_handoff_approved=True, console_recovery_check=lambda _: True,
                    attest_fresh_guest=lambda _: attestation())
            verify.assert_not_called()

    def test_missing_operator_authenticator_prevents_mutation(self):
        self.probe.side_effect = InstallBlocked("operator probe unavailable")
        with patch("kingdoms.wslpe41_native_foundation_handoff.run_foundation_stage") as run:
            with self.assertRaises(InstallBlocked):
                prepare_native_foundation(self.context,
                    operator_handoff_approved=True, console_recovery_check=lambda _: True,
                    attest_fresh_guest=lambda _: attestation())
            run.assert_not_called()

    def test_mismatched_foundation_proof_blocks(self):
        with patch("kingdoms.wslpe41_native_foundation_handoff.run_foundation_stage",
                   return_value=type("Proof", (), dict(passed=True,
                       instance_id="other", vmx=IDENTITY.vmx))()) as run:
            with self.assertRaises(InstallBlocked):
                prepare_native_foundation(self.context,
                    operator_handoff_approved=True, console_recovery_check=lambda _: True,
                    attest_fresh_guest=lambda _: attestation())
            run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
