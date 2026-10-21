"""Bridge existing KINGDOMS Stage 1 to the WSLPE41 identity contract.

Only the native LabManager/VMware provider creates the guest. This does NOT
attest Windows, credentials, TLS, recovery or authorize scenario execution.
"""
from __future__ import annotations

from pathlib import Path
import re

from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked
from kingdoms.wslpe41_native_identity import inspect_native_registration
from kingdoms.wslpe41_host_preflight import read_only_command
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
