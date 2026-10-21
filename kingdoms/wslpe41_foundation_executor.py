"""Instance-bound Windows foundation stages for a future WSLPE41 fresh install.

Reuses existing WSLPE-only Ansible playbooks, never the NORTH lifecycle.
This is an internal adapter, NOT an authorized public install entry point.
The independent fresh VM, TLS trust and VMware-console recovery proofs must
be supplied by a future native orchestrator before any production use.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess

from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_stage_executor import (
    AnsibleStageContext, _environment, _guest, _inventory, _regular,
)


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "ansible/wslpe-foundation.yml"
OPERATOR = ROOT / "ansible/wslpe-operator-foundation.yml"
MARKERS = {
    "learner": (
        "WSLPE_WINDOWS_STANDALONE=PASS",
        "WSLPE_LICENSE_READY=PASS",
        "WSLPE_LOCAL_LEARNER=PASS",
        "WSLPE_LOCAL_ADMIN_MEMBERSHIP=DENIED",
        "WSLPE_LOCAL_LEARNER_RDP_GROUP=PASS",
    ),
    "operator": (
        "WSLPE_OPERATOR_TARGET=PASS",
        "WSLPE_OPERATOR_PRINCIPAL=CREATED_NOT_AUTHENTICATED",
    ),
}
MAX_OUTPUT = 2_000_000


@dataclass(frozen=True)
class FoundationStageProof:
    instance_id: str
    vmx: str
    stage: str
    evidence_id: str
    passed: bool
    operator_authenticated: bool = False


def run_foundation_stage(
    context: AnsibleStageContext, stage: str, *,
    operator_handoff_approved: bool = False,
    console_recovery_check=None,
) -> FoundationStageProof:
    """Run exactly one existing WSLPE-only playbook, with no retries.

    Operator stage requires a real out-of-band console recovery callback,
    invoked immediately before mutation. The callback must be implemented by
    the future native provider, NOT inferred from an Ansible/WinRM response.
    This step creates an account but does not authenticate it or disable vagrant.
    """
    if stage not in MARKERS:
        raise InstallBlocked("Unknown WSLPE41 foundation stage")
    if stage == "operator" and (
        operator_handoff_approved is not True
        or not callable(console_recovery_check)
    ):
        raise InstallBlocked("Operator creation requires explicit handoff and independent console recovery")
    if stage == "learner" and (
        operator_handoff_approved or console_recovery_check is not None
    ):
        raise InstallBlocked("Operator authorization cannot be used for learner foundation")
    if not 60 <= context.timeout_seconds <= 3600:
        raise InstallBlocked("WSLPE41 foundation timeout outside approved bounds")
    if (context.inventory.parent != context.instance_dir / "ansible"
            or context.private_vars.parent != context.instance_dir / "ansible"):
        raise InstallBlocked("WSLPE41 foundation inventory must belong to its native instance")
    for path in (context.ansible, context.inventory):
        _regular(path)
    _regular(context.private_vars, private=True)
    if not context.ansible.stat().st_mode & 0o111:
        raise InstallBlocked("Approved Ansible executable is unavailable")
    playbook = FOUNDATION if stage == "learner" else OPERATOR
    _regular(playbook)
    _guest(context)
    env = _environment(context)
    _inventory(context, env)
    if stage == "operator":
        # Fail closed if console callback fails, is absent or returns anything
        # except literal True. No remote WinRM result substitutes for this.
        if console_recovery_check(context.identity) is not True:
            raise InstallBlocked("Independent VMware-console recovery was not proven")
    command = [
        str(context.ansible), "-i", str(context.inventory),
        "-i", str(context.private_vars), "--limit", "ws01,localhost",
        str(playbook),
    ]
    if stage == "operator":
        command += ["-e", json.dumps(
            {"wslpe_operator_handoff_approved": True}, separators=(",", ":")
        )]
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=context.timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallBlocked("WSLPE41 foundation command failed or timed out") from exc
    _guest(context)
    if (result.returncode != 0 or not isinstance(result.stdout, str)
            or not isinstance(result.stderr, str)
            or len(result.stdout) > MAX_OUTPUT or len(result.stderr) > MAX_OUTPUT
            or any(result.stdout.count(marker) != 1 for marker in MARKERS[stage])):
        raise InstallBlocked(f"WSLPE41 {stage} foundation Windows proof missing")
    # Never persist raw Ansible output, private secrets or operator credentials.
    digest = hashlib.sha256(json.dumps({
        "instance": context.identity.instance_id,
        "vmx": context.identity.vmx,
        "stage": stage,
        "markers": MARKERS[stage],
        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:32]
    return FoundationStageProof(
        instance_id=context.identity.instance_id,
        vmx=context.identity.vmx,
        stage=stage,
        evidence_id=f"wslpe41.foundation.{stage}.{digest}",
        passed=True,
        # A created operator account is NOT an authenticated management path.
        operator_authenticated=False,
    )
