"""WSLPE-only rollback-worker source, never called by default.

Accepts one root-scheduled digest-pinned private manifest and the exact
registered VMX. The digest must come from a separate approval/arming step,
not be read from the mutable bundle itself. Never reconstructs a baseline
from the NAT-disabled VMX. NORTH is never imported or contacted.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import importlib.util
import os
import re
import shutil

from kingdoms.wslpe_recovery_bundle import read_private_bundle
from kingdoms.wslpe_vmware_recover import owner_recover, vmrun_list, parse_inventory

MAX_BUNDLE_BYTES = 1_500_000

def check_pinned_digest(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Expected a separately pinned SHA256 recovery-bundle digest")
    return value


def validated_recovery_plan(*, bundle: Path, digest: str, stage, vmx_owner: int):
    """Never trust bundle's claimed VMX registration or owner as authority."""
    digest = check_pinned_digest(digest)
    if vmx_owner <= 0 or vmx_owner != os.geteuid():
        raise ValueError("Recovery worker is not the exact nonroot VMware owner")
    instance, meta = stage.find_instance(stage.WORKSPACE)
    if meta.get("lab") != "WSLPE":
        raise ValueError("Current native instance is not WSLPE")
    registered = stage.locate_registered_vm(instance)
    if registered.is_symlink() or registered.stat().st_uid != vmx_owner:
        raise ValueError("Registered WSLPE VMX ownership invalid")
    if bundle.is_symlink() or not bundle.is_file() or bundle.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Recovery bundle path invalid")
    wire = bundle.read_bytes()
    if sha256(wire).hexdigest() != digest:
        raise ValueError("Recovery bundle differs from independently approved digest")
    plan = read_private_bundle(
        bundle, registered_vmx=registered, owner_uid=vmx_owner,
    )
    if plan.vmx.resolve(strict=True) != registered.resolve(strict=True):
        raise ValueError("Manifest attempted to redirect exact VMX identity")
    return plan, registered


def recover_from_pinned_bundle(*, bundle: Path, digest: str, stage,
                               vmrun: str, owner: int, authorized: bool,
                               runner=None, pause=None) -> str:
    """Default is inventory-only. Real restore requires explicit approval."""
    plan, vmx = validated_recovery_plan(
        bundle=bundle, digest=digest, stage=stage, vmx_owner=owner
    )
    if not vmrun or Path(vmrun).name != "vmrun":
        raise ValueError("Untrusted VMware binary")
    if not Path(vmrun).is_file() or not os.access(vmrun, os.X_OK):
        raise ValueError("VMware owner cannot execute verified vmrun binary")
    from kingdoms import wslpe_vmware_recover as lifecycle
    arguments = {}
    if runner is not None:
        arguments["runner"] = runner
    if pause is not None:
        arguments["pause"] = pause
    if not authorized:
        executor = runner or lifecycle.subprocess.run
        running = lifecycle.parse_inventory(
            lifecycle.vmrun_list(vmrun, executor), vmx
        )
        if vmx.read_bytes() not in (plan.original, plan.candidate):
            raise ValueError("VMX has unexpected VMware rewrite; preview aborted")
        return "VERIFIED_RUNNING" if running else "VERIFIED_STOPPED"
    return lifecycle.owner_recover(
        plan, vmx, vmrun, execute=True, **arguments
    )
