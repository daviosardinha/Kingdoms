"""Private bridge from the 41-scenario journal to exact guest transports.

Not exposed by scripts/wslpe41-install.py. A native installer must first
produce independently verified creation/foundation/TLS/recovery attestation.
This adapter never creates a guest, changes VMware networking or infers
freshness from a pre-existing VMX/instance.json.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from kingdoms.wslpe41_fresh_contract import FreshScenario
from kingdoms.wslpe41_install_flow import (
    FreshGuestAttestation, FreshGuestIdentity, InstallBlocked, StageProof,
    verify_attestation,
)
from kingdoms.wslpe41_runtime_proof import (
    ObservedStageResult, RuntimeProofBlocked, verify_observed_stage,
)
from kingdoms.wslpe41_stage_commands import StagePlanBlocked, build_stage_invocation
from kingdoms.wslpe41_stage_executor import (
    AnsibleStageContext, _environment, _guest, _inventory, run_ansible_stage,
)


@dataclass
class NativeStageRunner:
    context: AnsibleStageContext
    # Both callbacks are mandatory external attestations, NOT booleans guessed
    # from source checks, inventory presence or old golden-master evidence.
    attest_fresh_guest: Callable[[FreshGuestIdentity], FreshGuestAttestation]
    activate_jea_console: Callable[[FreshGuestIdentity], ObservedStageResult] | None = None

    def preflight(self, identity: FreshGuestIdentity) -> FreshGuestAttestation:
        if identity != self.context.identity:
            raise InstallBlocked("Fresh WSLPE41 runner is bound to a different instance")
        _guest(self.context)
        env = _environment(self.context)
        _inventory(self.context, env)
        if not callable(self.attest_fresh_guest):
            raise InstallBlocked("Independent fresh creation attestor is missing")
        attestation = self.attest_fresh_guest(identity)
        verify_attestation(identity, attestation)
        # Freshness and recovery must come from the provider, not a file
        # copied from the golden master or a successful Ansible stage.
        _guest(self.context)
        return attestation

    def run_stage(self, scenario: FreshScenario, stage: str) -> StageProof:
        if scenario.number != 30 or stage != "activate":
            return run_ansible_stage(self.context, scenario, stage)
        if not callable(self.activate_jea_console):
            raise InstallBlocked("JEA #30 requires an independent VMware guest-console executor")
        _guest(self.context)
        try:
            invocation = build_stage_invocation(
                scenario, stage, ansible=self.context.ansible,
                inventory=self.context.inventory, varsfile=self.context.private_vars,
                expected_address=self.context.expected_address,
                instance_id=self.context.identity.instance_id,
                management_address=self.context.management_address,
            )
        except StagePlanBlocked as exc:
            raise InstallBlocked("JEA #30 invocation is not approved") from exc
        if invocation.transport != "guest_console" or invocation.argv:
            raise InstallBlocked("JEA #30 cannot activate through Ansible")
        # The callback MUST execute from the independently recovered guest
        # console and return its actual observation, not an operator-pasted log.
        observation = self.activate_jea_console(self.context.identity)
        _guest(self.context)
        try:
            return verify_observed_stage(
                invocation, observation,
                expected_instance_id=self.context.identity.instance_id,
                expected_vmx=self.context.identity.vmx,
            )
        except RuntimeProofBlocked as exc:
            raise InstallBlocked("JEA #30 independent console/recovery proof missing") from exc
