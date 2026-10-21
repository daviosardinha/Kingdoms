"""Fail-closed foundation handoff for the existing KINGDOMS native WSLPE guest.

This orchestrates existing playbooks and independent provider attestations.
It never creates a guest, fabricates attestation or enables --execute.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from kingdoms.wslpe41_foundation_executor import FoundationStageProof, run_foundation_stage
from kingdoms.wslpe41_install_flow import (
    FreshGuestAttestation, FreshGuestIdentity, InstallBlocked, verify_attestation,
)
from kingdoms.wslpe41_stage_executor import AnsibleStageContext


@dataclass(frozen=True)
class FoundationHandoff:
    learner: FoundationStageProof
    operator: FoundationStageProof
    attestation: FreshGuestAttestation


def prepare_native_foundation(
    context: AnsibleStageContext, *,
    operator_handoff_approved: bool,
    console_recovery_check: Callable[[FreshGuestIdentity], bool],
    attest_fresh_guest: Callable[[FreshGuestIdentity], FreshGuestAttestation],
    authenticate_operator: Callable[[FreshGuestIdentity], bool],
) -> FoundationHandoff:
    """Apply existing learner/operator foundations, then independently attest.

    Creation and isolation must already have been proven by the native provider.
    No stage runs if recovery approval or attestors are missing. The operator
    foundation's CREATED_NOT_AUTHENTICATED marker cannot satisfy the handoff.
    """
    identity = context.identity
    if operator_handoff_approved is not True:
        raise InstallBlocked("Operator handoff approval required before Windows mutation")
    if (not callable(console_recovery_check) or not callable(attest_fresh_guest)
            or not callable(authenticate_operator)):
        raise InstallBlocked("Independent console recovery and fresh guest attestors required")
    # The pre-mutation callback must be an actual provider-backed console check.
    if console_recovery_check(identity) is not True:
        raise InstallBlocked("Independent VMware console recovery unavailable")
    learner = run_foundation_stage(context, "learner")
    if learner.passed is not True or learner.instance_id != identity.instance_id or learner.vmx != identity.vmx:
        raise InstallBlocked("Existing learner foundation did not prove this instance")
    operator = run_foundation_stage(
        context, "operator", operator_handoff_approved=True,
        console_recovery_check=console_recovery_check,
    )
    if operator.passed is not True or operator.instance_id != identity.instance_id or operator.vmx != identity.vmx:
        raise InstallBlocked("Existing operator foundation did not prove this instance")
    # Require a separate authenticated operator-management probe, not a
    # CREATED_NOT_AUTHENTICATED playbook marker or an attestor boolean.
    if authenticate_operator(identity) is not True:
        raise InstallBlocked("Independent authenticated operator management probe failed")
    # The operator playbook only creates an account; this independent attestor
    # must prove authenticated operator access, TLS, isolation and fresh origin.
    attestation = attest_fresh_guest(identity)
    verify_attestation(identity, attestation)
    return FoundationHandoff(learner, operator, attestation)
