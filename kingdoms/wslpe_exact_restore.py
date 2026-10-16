"""WSLPE-only recovery transaction core. NORTH source is reference, never invoked.

A real VMX may be restored ONLY when the exact registered WSLPE VM is
already stopped and current bytes equal the prior approved NAT-off candidate.
An unexpected VMware rewrite is a manual-recovery condition: never force
overwrite. No hardcoded VMX path, username, NIC MAC, subnet or credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import stat
import tempfile

from kingdoms.wslpe_nat_cutover_contract import (
    guarded_original_restore, manifest as make_manifest, render_nat_offline,
)

@dataclass(frozen=True)
class RecoveryPlan:
    vmx: Path
    owner_uid: int
    vmnet: str
    original: bytes
    candidate: bytes
    original_sha256: str
    candidate_sha256: str


def prepare_plan(vmx: Path, expected_registered: Path, vmnet: str,
                 expected_uid: int) -> RecoveryPlan:
    """Read-only, exact-identity copy. Do not trust paths supplied in a bundle."""
    if expected_uid <= 0 or not isinstance(vmx, Path) or not isinstance(expected_registered, Path):
        raise ValueError("Invalid WSLPE restoration owner/VMX")
    if vmx.is_symlink() or expected_registered.is_symlink():
        raise ValueError("Symlinked VMX is not an eligible recovery target")
    current = vmx.resolve(strict=True)
    expected = expected_registered.resolve(strict=True)
    if current != expected or current.suffix.lower() != ".vmx":
        raise ValueError("VMX does not equal the unique registered WSLPE VMX")
    if vmx.stat().st_uid != expected_uid or not stat.S_ISREG(vmx.stat().st_mode):
        raise ValueError("Registered WSLPE VMX owner/type drift")
    raw = vmx.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    if text.encode("utf-8") != raw:
        raise ValueError("Noncanonical VMX source")
    after = render_nat_offline(text, vmnet).encode("utf-8")
    proof = make_manifest(text, after.decode("utf-8"), vmnet)
    return RecoveryPlan(current, expected_uid, vmnet, raw, after,
                        proof.before_sha256, proof.after_sha256)


def inspect_recovery_state(plan: RecoveryPlan, current: bytes, *,
                           running: bool) -> str:
    """Fail-closed tri-state. Restore requires confirmed power-off."""
    digest = sha256(current).hexdigest()
    if digest == plan.original_sha256 and current == plan.original:
        return "ALREADY_ORIGINAL"
    if digest != plan.candidate_sha256 or current != plan.candidate:
        raise ValueError("VMware VMX contains unexpected changes; manual intervention")
    if running:
        raise ValueError("VMX is still running; never write to live VMware metadata")
    original = guarded_original_restore(
        current.decode("utf-8", errors="strict"),
        plan.original.decode("utf-8", errors="strict"),
        make_manifest(plan.original.decode("utf-8"),
                      plan.candidate.decode("utf-8"), plan.vmnet),
        plan.vmnet,
    )
    if original.encode("utf-8") != plan.original:
        raise ValueError("Checksum-validated restoration mismatched original")
    return "RESTORE_OFFLINE_CANDIDATE"


def atomic_restore_offline(plan: RecoveryPlan, *,
                           registered: Path, still_running: bool) -> str:
    """Perform only exact offline rollback, never stop/start a VM itself.

    Caller must independently check VMware power state immediately prior
    to invoking. This does not authorize a NAT cutover or reboot.
    """
    if os.geteuid() != plan.owner_uid:
        raise ValueError("VMX restoration cannot run as other user/root")
    if plan.vmx.is_symlink() or registered.is_symlink():
        raise ValueError("Registered VMX path changed or became a symlink")
    if plan.vmx.resolve(strict=True) != registered.resolve(strict=True):
        raise ValueError("Registered WSLPE identity mismatch")
    if plan.vmx.stat().st_uid != plan.owner_uid:
        raise ValueError("VMX owner changed")
    result = inspect_recovery_state(plan, plan.vmx.read_bytes(), running=still_running)
    if result == "ALREADY_ORIGINAL":
        return result
    if still_running:
        raise ValueError("Power-off proof required for recovery")
    mode = stat.S_IMODE(plan.vmx.stat().st_mode)
    file_descriptor, scratch = tempfile.mkstemp(
        prefix=".wslpe-restore-", dir=str(plan.vmx.parent)
    )
    temporary = Path(scratch)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(plan.original)
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck the target after staging; never overwrite unknown changes.
        if plan.vmx.is_symlink() or plan.vmx.read_bytes() != plan.candidate:
            raise ValueError("VMX mutated before offline restoration")
        os.replace(temporary, plan.vmx)
        directory_fd = os.open(str(plan.vmx.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if plan.vmx.read_bytes() != plan.original:
            raise ValueError("VMX restore verification mismatch")
        return "RESTORED_ORIGINAL_OFFLINE"
    finally:
        temporary.unlink(missing_ok=True)
