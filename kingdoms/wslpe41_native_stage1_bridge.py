"""Bridge existing KINGDOMS Stage 1 to the WSLPE41 identity contract.

Only the native LabManager/VMware provider creates the guest. This does NOT
attest Windows, credentials, TLS, recovery or authorize scenario execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked
from kingdoms.wslpe41_native_identity import inspect_native_registration
from kingdoms.wslpe41_host_preflight import (
    HostEvidenceBlocked, host_plan, read_only_command, running_vm_count,
)
from goad.goadpath import GoadPath
from kingdoms.wslpe_stage1 import bootstrap_native_wslpe, valid_prefix


def create_native_guest_identity(manager, prefix: str, source_commit: str, *,
                                 confirmed: bool = False) -> FreshGuestIdentity:
    """Create once using the existing provider; verify exact new registration.

    No retries after a failed or partial creation. The caller must separately
    prove guest freshness, management and recovery before calling install_41.
    """
    if confirmed is not True:
        raise InstallBlocked("Explicit WSLPE native creation approval required")
    if not valid_prefix(prefix):
        raise InstallBlocked("Invalid WSLPE native network prefix")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise InstallBlocked("Exact source commit required")
    if manager.get_current_instance() is not None:
        raise InstallBlocked("Existing instance loaded; refusing creation")
    if not bootstrap_native_wslpe(manager, prefix, confirmed=True):
        raise InstallBlocked("Native KINGDOMS Stage 1 failed; inspect partial state, never retry")
    instance = manager.get_current_instance()
    if instance is None:
        raise InstallBlocked("Native provider did not register a new instance")
    instance_dir = Path(instance.instance_path)
    if not instance_dir.is_absolute() or instance_dir.is_symlink():
        raise InstallBlocked("Native instance path unsafe")
    try:
        registration = inspect_native_registration(
            instance_dir, read_only_command("vmrun", "-T", "ws", "list")
        )
    except (OSError, ValueError) as exc:
        raise InstallBlocked("Native provider registration not independently verified") from exc
    if (registration.instance_id != instance.instance_id
            or registration.subnet != prefix + ".0/24"):
        raise InstallBlocked("Native guest identity differs from selected instance/network")
    return FreshGuestIdentity(
        instance_id=registration.instance_id,
        workspace=str(instance_dir.parent),
        vmx=registration.vmx,
        subnet=registration.subnet,
        source_commit=source_commit,
    )


@dataclass(frozen=True)
class NativeCreationEvidence:
    """Runtime provenance of one new native VMX, NOT a Windows attestation."""

    identity: FreshGuestIdentity
    previously_running: tuple[str, ...]
    previous_instance_ids: tuple[str, ...]
    newly_running_vmx: str
    source: str = "native provider newly registered VMX (NOT guest freshness/TLS proof)"


def _running_vmx_paths(output: str) -> frozenset[str]:
    """Treat VMware inventory as a complete, absolute, non-aliased snapshot."""
    try:
        count = running_vm_count(output)
    except HostEvidenceBlocked as exc:
        raise InstallBlocked("VMware running inventory is not trustworthy") from exc
    lines = [line.strip() for line in output.splitlines() if line.strip()][1:]
    paths: list[str] = []
    for line in lines:
        path = Path(line)
        if not path.is_absolute() or path.is_symlink():
            raise InstallBlocked("VMware inventory contains linked or relative VMX")
        paths.append(str(path.resolve()))
    if len(paths) != count or len(set(paths)) != count:
        raise InstallBlocked("VMware inventory contains duplicate VMX identities")
    return frozenset(paths)


def _workspace_instance_ids(workspace: Path) -> frozenset[str]:
    """Inventory native instance directories before the first provider mutation."""
    if workspace.is_symlink():
        raise InstallBlocked("WSLPE workspace is symlinked")
    if not workspace.exists():
        return frozenset()
    if not workspace.is_dir():
        raise InstallBlocked("WSLPE workspace is not a directory")
    children = list(workspace.iterdir())
    if len(children) > 500:
        raise InstallBlocked("WSLPE workspace inventory is unbounded")
    if any(child.is_symlink() for child in children):
        raise InstallBlocked("WSLPE workspace contains a symlink")
    return frozenset(child.name for child in children if child.is_dir())


def create_guarded_native_guest(
    manager,
    source_commit: str,
    *,
    workspaces: tuple[Path, ...],
    approved_prefix: str,
    confirmed: bool = False,
) -> NativeCreationEvidence:
    """One approved native Stage 1 creation after a fresh, exact subnet audit.

    Keep the GOAD/KINGDOMS provider as the sole creator. Recheck immediately
    before any mutation, compare pre/post registered instance and running VMX
    inventories, and fail closed if a co-tenant changed during the operation.
    This does not provision Windows, prove TLS, or authorize the 83 stages.
    """
    if confirmed is not True:
        raise InstallBlocked("Explicit native WSLPE41 creation approval required")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise InstallBlocked("Exact source commit required")
    if not valid_prefix(approved_prefix):
        raise InstallBlocked("Invalid approved native WSLPE41 subnet")
    if manager.get_current_instance() is not None:
        raise InstallBlocked("Cannot create over an existing native instance")
    native_workspace = Path(GoadPath.get_workspace_path())
    if (native_workspace.is_symlink() or
            native_workspace.parent.resolve() != Path(GoadPath.get_project_path()).resolve()):
        raise InstallBlocked("Native workspace belongs to another checkout")
    if (not isinstance(workspaces, tuple) or not workspaces
            or not all(isinstance(root, Path) for root in workspaces)
            or workspaces[0] != native_workspace):
        raise InstallBlocked("Explicit native checkout and peer workspace inventory required")

    # The creation receipt must name the actual checkout revision, not an
    # arbitrary 40-character string supplied by a caller.
    source_root = Path(GoadPath.get_project_path()).resolve()
    try:
        actual_commit = read_only_command(
            "git", "-C", str(source_root), "rev-parse", "HEAD"
        ).strip()
        tracked_changes = read_only_command(
            "git", "-C", str(source_root), "status", "--porcelain",
            "--untracked-files=normal"
        )
    except HostEvidenceBlocked as exc:
        raise InstallBlocked("Cannot verify native KINGDOMS source revision") from exc
    if actual_commit != source_commit or tracked_changes.strip():
        raise InstallBlocked("WSLPE41 source checkout is not clean or revision differs")

    before_ids = _workspace_instance_ids(native_workspace)
    try:
        before_running = _running_vmx_paths(read_only_command("vmrun", "-T", "ws", "list"))
        selected = host_plan(workspaces=workspaces)
        after_plan = _running_vmx_paths(read_only_command("vmrun", "-T", "ws", "list"))
    except HostEvidenceBlocked as exc:
        raise InstallBlocked("Fresh WSLPE41 host allocation evidence unavailable") from exc
    if before_running != after_plan or len(after_plan) != selected.running_vm_count:
        raise InstallBlocked("VMware inventory changed during the host preflight")
    if _workspace_instance_ids(native_workspace) != before_ids:
        raise InstallBlocked("Native instance inventory changed during the host preflight")
    if selected.prefix != approved_prefix:
        raise InstallBlocked("Approved WSLPE41 prefix is stale or has collided")

    identity = create_native_guest_identity(
        manager, approved_prefix, source_commit, confirmed=True
    )
    # Reject an identity from another checkout even when a caller's mock or
    # misconfigured manager registered a plausible instance name.
    new_instance = native_workspace / identity.instance_id
    if (identity.workspace != str(native_workspace)
            or not new_instance.is_dir() or new_instance.is_symlink()
            or not Path(identity.vmx).is_relative_to(new_instance / "provider")):
        raise InstallBlocked("New WSLPE41 guest does not belong to this native workspace")
    # This only attests that a previously unregistered native instance and VMX
    # appeared, not that its Windows OS or credentials are clean.
    after_ids = _workspace_instance_ids(native_workspace)
    after_running = _running_vmx_paths(read_only_command("vmrun", "-T", "ws", "list"))
    if (identity.instance_id in before_ids
            or after_ids - before_ids != {identity.instance_id}
            or before_ids - after_ids
            or identity.vmx in before_running
            or after_running - before_running != {identity.vmx}
            or before_running - after_running):
        raise InstallBlocked("Fresh native creation provenance or co-tenant isolation unproven")
    return NativeCreationEvidence(
        identity=identity,
        previously_running=tuple(sorted(before_running)),
        previous_instance_ids=tuple(sorted(before_ids)),
        newly_running_vmx=identity.vmx,
    )
