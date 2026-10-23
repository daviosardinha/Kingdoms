"""Fail-closed source/runtime result bridge for a single fresh WSLPE41 stage.

This module does not execute commands or authenticate a VMware guest.
The future native runner must independently bind the result to the actual
subprocess/guest-console channel, exact new VMX and fresh instance. It must
not accept a pasted log as an attestation. Raw output is never journaled.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from kingdoms.wslpe41_install_flow import StageProof
from kingdoms.wslpe41_stage_commands import StageInvocation


class RuntimeProofBlocked(ValueError):
    pass


MAX_TRANSCRIPT = 2_000_000
RECOVERY_MARKER = "WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS"


@dataclass(frozen=True)
class ObservedStageResult:
    instance_id: str
    vmx: str
    transport: str
    returncode: int
    stdout: str
    stderr: str


def verify_observed_stage(
    invocation: StageInvocation, observation: ObservedStageResult, *,
    expected_instance_id: str, expected_vmx: str,
) -> StageProof:
    """Verify one result; do not conflate a marker with fresh guest identity."""
    if (not re.fullmatch(r"[A-Za-z0-9_-]{4,100}", expected_instance_id)
            or not expected_vmx.startswith("/") or not expected_vmx.endswith(".vmx")
            or observation.instance_id != expected_instance_id
            or observation.vmx != expected_vmx):
        raise RuntimeProofBlocked("Stage result is not bound to the new native guest")
    if (observation.transport != invocation.transport
            or observation.transport not in ("ansible", "guest_console")):
        raise RuntimeProofBlocked("Stage transport differs from its approved execution channel")
    if (type(observation.returncode) is not int or observation.returncode != 0):
        raise RuntimeProofBlocked("Stage command failed")
    if (not isinstance(observation.stdout, str) or not isinstance(observation.stderr, str)
            or len(observation.stdout) > MAX_TRANSCRIPT
            or len(observation.stderr) > MAX_TRANSCRIPT):
        raise RuntimeProofBlocked("Stage transcript is missing or unbounded")
    marker = invocation.evidence_marker
    if not marker or observation.stdout.count(marker) != 1:
        raise RuntimeProofBlocked("Missing or duplicate exact Windows stage marker")
    # JEA can restart WinRM during registration. Local recovery must be
    # explicitly observed from the *guest-console* channel before accepting
    # the independent later learner/HTTPS validation stage.
    if invocation.stage == "activate":
        if (invocation.number != 30 or invocation.transport != "guest_console"
                or observation.stdout.count(RECOVERY_MARKER) != 1):
            raise RuntimeProofBlocked("JEA activation lacks independent local WinRM recovery")
    elif observation.transport == "guest_console":
        raise RuntimeProofBlocked("Unapproved guest-console stage")

    digest = hashlib.sha256(json.dumps(
        {"instance": expected_instance_id, "vmx": expected_vmx,
         "number": invocation.number, "stage": invocation.stage,
         "transport": invocation.transport, "marker": marker,
         "stdout_sha256": hashlib.sha256(observation.stdout.encode("utf-8")).hexdigest()},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()[:32]
    return StageProof(
        scenario_number=invocation.number,
        stage=invocation.stage,
        transport=invocation.transport,
        evidence_id=f"wslpe41.{invocation.number:02d}.{invocation.stage}.{digest}",
        passed=True,
    )
