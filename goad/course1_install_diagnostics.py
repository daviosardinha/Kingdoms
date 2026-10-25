"""Structured, private NORTH installation diagnostics and allowlisted recovery plans.

This records evidence; it NEVER executes an action. Caller controls recovery
only after original VMware guest identity, WinRM and exact phase are proven.
No credentials, raw PowerShell output, passwords or auth headers are persisted.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

GUESTS = frozenset(("GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"))
PHASES = frozenset(("post-ws01-eval", "pre-exercise-isolation",
                    "pre-vagrant-ws01-resume"))
SIGNATURES = frozenset((
    "VMTOOLS_HEALTHY",
    "VMTOOLS_MISSING",
    "VMTOOLS_PARTIAL",
    "VMTOOLS_READINESS_INCOMPLETE",
    "VMTOOLS_IDENTITY_OR_TRANSPORT_BLOCKED",
    "VMTOOLS_REPAIR_ATTEMPTED",
    "VMTOOLS_REPAIR_VERIFIED",
    "VMTOOLS_REPAIR_FAILED",
    "VMTOOLS_PARTIAL_PERSISTENT",
    "VMTOOLS_WS01_SIGNED_IDLE_ORPHAN",
))
ACTIONS = frozenset((
    "none",
    "read_only_wait",
    "one_shot_original_tools_install",
    "manual_review",
))
RESULTS = frozenset(("observed", "pass", "blocked", "failed"))
# No free-form error text or attacker-controllable strings in journal entries.
SAFE_ID = re.compile(r"^[0-9a-f]{6}-north-vmware$")


def recovery_policy(signature):
    """Document exactly which known signatures have approved automation."""
    return {
        "VMTOOLS_HEALTHY": "none",
        "VMTOOLS_MISSING": "one_shot_original_tools_install",
        "VMTOOLS_PARTIAL": "read_only_wait",
        "VMTOOLS_PARTIAL_PERSISTENT": "manual_review",
        "VMTOOLS_WS01_SIGNED_IDLE_ORPHAN": "one_shot_original_tools_install",
        "VMTOOLS_READINESS_INCOMPLETE": "manual_review",
        "VMTOOLS_IDENTITY_OR_TRANSPORT_BLOCKED": "manual_review",
        "VMTOOLS_REPAIR_ATTEMPTED": "none",
        "VMTOOLS_REPAIR_VERIFIED": "none",
        "VMTOOLS_REPAIR_FAILED": "manual_review",
    }[signature]


def emit(provider_dir, *, machine, phase, signature, result, attempts=0):
    """Append and fsync one newline-delimited JSON event to exact instance.

    Fail closed on unsafe paths or unexpected values; events never include
    external tool stdout or Windows secrets. Files are user-only mode 0600.
    """
    provider = Path(provider_dir)
    if (not provider.is_dir() or provider.is_symlink()
            or provider.name != "provider"
            or not SAFE_ID.fullmatch(provider.parent.name)
            or provider.parent.is_symlink()
            or provider.resolve(strict=True) != provider
            or provider.parent.resolve(strict=True) != provider.parent):
        raise ValueError("Unsafe NORTH provider event destination")
    if (machine not in GUESTS or phase not in PHASES
            or signature not in SIGNATURES or result not in RESULTS
            or type(attempts) is not int or attempts not in (0, 1)):
        raise ValueError("Unexpected NORTH event parameters")

    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "instance": provider.parent.name,
        "machine": machine,
        "phase": phase,
        "signature": signature,
        "policy": recovery_policy(signature),
        "outcome": result,
        "repair_attempts": attempts,
    }
    path = provider.parent / ".north-install-recovery.jsonl"
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        data = (json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n").encode()
        if os.write(fd, data) != len(data):
            raise OSError("Incomplete NORTH event write")
        os.fsync(fd)
    finally:
        os.close(fd)
    return path
