"""Immutable WSLPE-only VMX recovery bundle contract.

A restore timer cannot call prepare_plan on a NAT-disabled VMX: it must use
the EXACT previously approved original. This module stores a verified
original and hashes in a private snapshot and re-derives the NAT candidate.
No guest/VMware/systemd/network state changes are performed here.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import stat
import tempfile

from kingdoms.wslpe_exact_restore import RecoveryPlan
from kingdoms.wslpe_nat_cutover_contract import manifest, render_nat_offline

FORMAT = "kingdoms-wslpe-vmx-rollback/v1"
MAX_BYTES = 1_500_000


def encode_bundle(plan: RecoveryPlan) -> bytes:
    if plan.owner_uid <= 0 or not plan.vmx.is_absolute():
        raise ValueError("Invalid rollback source owner/identity")
    original = plan.original.decode("utf-8", errors="strict")
    candidate = render_nat_offline(original, plan.vmnet)
    proof = manifest(original, candidate, plan.vmnet)
    if (candidate.encode("utf-8") != plan.candidate
            or proof.before_sha256 != plan.original_sha256
            or proof.after_sha256 != plan.candidate_sha256):
        raise ValueError("Rollback plan does not match the exact Ethernet0 candidate")
    payload = {
        "format": FORMAT,
        "registered_vmx": str(plan.vmx),
        "owner_uid": plan.owner_uid,
        "exercise_vmnet": plan.vmnet,
        "original_sha256": plan.original_sha256,
        "candidate_sha256": plan.candidate_sha256,
        "original_b64": base64.b64encode(plan.original).decode("ascii"),
    }
    wire = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(wire) > MAX_BYTES:
        raise ValueError("Recovery bundle exceeds bounded size")
    return wire


def decode_bundle(wire: bytes, *, registered_vmx: Path, owner_uid: int) -> RecoveryPlan:
    """Never accept a path/owner merely because the JSON claims it."""
    if (not isinstance(wire, bytes) or len(wire) > MAX_BYTES
            or not registered_vmx.is_absolute() or registered_vmx.is_symlink()
            or owner_uid <= 0):
        raise ValueError("Untrusted WSLPE recovery bundle or registered VMX")
    try:
        data = json.loads(wire)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid WSLPE recovery manifest") from exc
    expected_keys = {
        "format", "registered_vmx", "owner_uid", "exercise_vmnet",
        "original_sha256", "candidate_sha256", "original_b64",
    }
    if not isinstance(data, dict) or set(data) != expected_keys or data["format"] != FORMAT:
        raise ValueError("Unknown WSLPE recovery manifest schema")
    if type(data["owner_uid"]) is not int or data["owner_uid"] != owner_uid:
        raise ValueError("Recovery account differs from VMware VMX owner")
    if type(data["registered_vmx"]) is not str or data["registered_vmx"] != str(registered_vmx):
        raise ValueError("Recovery VMX does not match current exact registration")
    if type(data["exercise_vmnet"]) is not str or not data["exercise_vmnet"].startswith("vmnet"):
        raise ValueError("Recovery exercise network is invalid")
    if type(data["original_b64"]) is not str:
        raise ValueError("Recovery original is invalid")
    try:
        original_bytes = base64.b64decode(data["original_b64"], validate=True)
        original = original_bytes.decode("utf-8", errors="strict")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Untrusted encoded original VMX") from exc
    candidate = render_nat_offline(original, data["exercise_vmnet"])
    proof = manifest(original, candidate, data["exercise_vmnet"])
    if (data["original_sha256"] != proof.before_sha256
            or data["candidate_sha256"] != proof.after_sha256):
        raise ValueError("Recovery original/candidate hash mismatch")
    return RecoveryPlan(
        registered_vmx, owner_uid, data["exercise_vmnet"],
        original_bytes, candidate.encode("utf-8"),
        proof.before_sha256, proof.after_sha256,
    )


def write_private_bundle(path: Path, plan: RecoveryPlan) -> None:
    """Stage ONE private file; refuse overwrite, links and weak parent modes.

    Call only before cutover with an exact verified native WSLPE RecoveryPlan.
    """
    directory = path.parent
    if (path.name != "recovery.json" or directory.is_symlink()
            or not directory.is_dir() or directory.stat().st_uid != plan.owner_uid
            or stat.S_IMODE(directory.stat().st_mode) != 0o700
            or path.exists() or path.is_symlink() or os.geteuid() != plan.owner_uid):
        raise ValueError("WSLPE recovery target must be new in private owner directory")
    content = encode_bundle(plan)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
    finally:
        if os.path.islink(path):
            raise ValueError("WSLPE recovery bundle changed to a symlink")


def read_private_bundle(path: Path, *, registered_vmx: Path, owner_uid: int) -> RecoveryPlan:
    directory = path.parent
    if (path.name != "recovery.json" or directory.is_symlink()
            or directory.stat().st_uid != owner_uid
            or stat.S_IMODE(directory.stat().st_mode) != 0o700
            or path.is_symlink() or path.stat().st_uid != owner_uid
            or stat.S_IMODE(path.stat().st_mode) != 0o600):
        raise ValueError("Untrusted WSLPE bundle storage permissions")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    return decode_bundle(content, registered_vmx=registered_vmx, owner_uid=owner_uid)
