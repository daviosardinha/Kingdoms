"""Single WSLPE41 native orchestration seam (private, NOT a production CLI).

Owns no Vagrant instance, VMware vmnet, Windows identity or scenario fixture.
Delegates to the existing KINGDOMS manager and existing 41-stage journal.
Live management/TLS, independent guest console, and attestation providers are
not yet implemented: no public install entry point is authorized.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from pathlib import Path
from typing import Callable

from kingdoms.wslpe41_install_flow import (
    FreshGuestAttestation, FreshGuestIdentity, InstallBlocked, install_41,
)
from kingdoms.wslpe41_native_stage1_bridge import (
    NativeCreationEvidence, create_guarded_native_guest,
)
from kingdoms.wslpe41_native_foundation_handoff import (
    FoundationHandoff, prepare_native_foundation,
)
from kingdoms.wslpe41_native_stage_runner import NativeStageRunner
from kingdoms.wslpe41_runtime_proof import ObservedStageResult
from kingdoms.wslpe41_stage_executor import AnsibleStageContext, _guest


@dataclass(frozen=True)
class NativeRuntimeCapabilities:
    """Required real provider-backed functions, not source or mock evidence."""

    # Creates only this guest's private inventory, credentials, fresh TLS trust
    # and management channel; must not clone the golden master's TLS pin.
    prepare_management: Callable[[NativeCreationEvidence], AnsibleStageContext]
    # Independent guest console, NOT a Vagrant/WinRM or VMware Tools IP check.
    console_recovery_check: Callable[[FreshGuestIdentity], bool]
    # Independent Windows/workgroup/operator/TLS/isolation/recovery attestor.
    attest_guest: Callable[[NativeCreationEvidence], FreshGuestAttestation]
    # Executes JEA #30 only through independently recovered guest console.
    activate_jea_console: Callable[[FreshGuestIdentity], ObservedStageResult]


@dataclass(frozen=True)
class NativeInstallResult:
    creation: NativeCreationEvidence
    foundation: FoundationHandoff
    journal: Path


def _validate_context(
    context: AnsibleStageContext, creation: NativeCreationEvidence,
) -> None:
    identity = creation.identity
    instance = Path(identity.workspace) / identity.instance_id
    expected_ip = str(ipaddress.IPv4Network(identity.subnet).network_address + 31)
    if (not isinstance(context, AnsibleStageContext)
            or context.identity != identity
            or context.instance_dir != instance
            or context.expected_address != expected_ip
            or context.inventory.parent != instance / "ansible"
            or context.private_vars.parent != instance / "ansible"):
        raise InstallBlocked("Fresh WSLPE41 management context differs from new VM")


def install_native_wslpe41(
    manager,
    *,
    source_commit: str,
    approved_prefix: str,
    workspaces: tuple[Path, ...],
    state_root: Path,
    capabilities: NativeRuntimeCapabilities,
    confirmed: bool = False,
) -> NativeInstallResult:
    """One-shot native creation → foundation → 41-scenario journal.

    The callback implementations must be independently reviewed and bound to
    the exact new native VM. They are NOT presently implemented or exported.
    No retry after any failed stage or partial Windows mutation.
    """
    if confirmed is not True:
        raise InstallBlocked("Explicit full WSLPE41 creation approval required")
    if not isinstance(capabilities, NativeRuntimeCapabilities) or not all(
        callable(operation) for operation in (
            capabilities.prepare_management,
            capabilities.console_recovery_check,
            capabilities.attest_guest,
            capabilities.activate_jea_console,
        )
    ):
        raise InstallBlocked("Independent WSLPE41 runtime capabilities are absent")
    if (not isinstance(state_root, Path) or not state_root.is_absolute()
            or state_root.is_symlink()):
        raise InstallBlocked("WSLPE41 private journal root must be absolute and nonlinked")

    creation = create_guarded_native_guest(
        manager, source_commit, workspaces=workspaces,
        approved_prefix=approved_prefix, confirmed=True,
    )
    identity = creation.identity
    context = capabilities.prepare_management(creation)
    _validate_context(context, creation)
    _guest(context)

    # The attestor is called after management and again at the 41-stage
    # preflight. The creation receipt alone cannot prove any Windows or TLS
    # property, nor may a callback infer JEA recovery from WinRM success.
    def attest(exact_identity: FreshGuestIdentity) -> FreshGuestAttestation:
        if exact_identity != identity:
            raise InstallBlocked("Native WSLPE41 attestor requested for another guest")
        return capabilities.attest_guest(creation)

    foundation = prepare_native_foundation(
        context,
        operator_handoff_approved=True,
        console_recovery_check=capabilities.console_recovery_check,
        attest_fresh_guest=attest,
    )
    runner = NativeStageRunner(
        context=context,
        attest_fresh_guest=attest,
        activate_jea_console=capabilities.activate_jea_console,
    )
    journal = install_41(identity, runner, state_root)
    return NativeInstallResult(creation, foundation, journal)
