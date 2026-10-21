"""One 41-scenario installation transaction, not two deployment campaigns.

This is the source-tested execution engine. A separate, not-yet-implemented
native fresh-guest adapter must attest the *new* VMware instance and provide
real Ansible/guest-console stage evidence before execution is exposed.
Never use the previous master VM, its journal, TLS pin or snapshots as proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
from secrets import token_hex
from typing import Protocol

from kingdoms.wslpe41_fresh_contract import FreshScenario, fresh_scenario_manifest


class InstallBlocked(ValueError):
    """An installation invariant was not proven; stop without further writes."""


@dataclass(frozen=True)
class FreshGuestIdentity:
    instance_id: str
    workspace: str
    vmx: str
    subnet: str
    source_commit: str


@dataclass(frozen=True)
class FreshGuestAttestation:
    instance_id: str
    vmx: str
    source_commit: str
    created_by_this_install: bool
    standalone_workgroup: bool
    learner_ready: bool
    operator_recovery_ready: bool
    management_isolated: bool
    fresh_tls_identity: bool


@dataclass(frozen=True)
class StageProof:
    scenario_number: int
    stage: str
    transport: str
    evidence_id: str
    passed: bool


class FreshGuestRunner(Protocol):
    def preflight(self, identity: FreshGuestIdentity) -> FreshGuestAttestation:
        """Independently prove new native boot, foundation and management."""

    def run_stage(self, scenario: FreshScenario, stage: str) -> StageProof:
        """Execute and independently verify a single exact guest stage."""


def verify_attestation(identity: FreshGuestIdentity, proof: FreshGuestAttestation) -> None:
    if (not re.fullmatch(r"[a-zA-Z0-9_-]{4,100}", identity.instance_id)
            or not re.fullmatch(r"[0-9a-f]{40}", identity.source_commit)
            or not identity.workspace.startswith("/")
            or not identity.vmx.startswith("/")
            or not identity.vmx.endswith(".vmx")
            or not re.fullmatch(r"(?:[0-9]{1,3}\.){3}0/24", identity.subnet)):
        raise InstallBlocked("Invalid fresh native instance identity")
    if (proof.instance_id != identity.instance_id
            or proof.vmx != identity.vmx
            or proof.source_commit != identity.source_commit):
        raise InstallBlocked("Guest attestation does not match this installation")
    checks = (
        proof.created_by_this_install, proof.standalone_workgroup,
        proof.learner_ready, proof.operator_recovery_ready,
        proof.management_isolated, proof.fresh_tls_identity,
    )
    if not all(value is True for value in checks):
        raise InstallBlocked("New-guest foundation or independent recovery is not proven")


def verify_stage(scenario: FreshScenario, stage: str, proof: StageProof) -> None:
    expected_transport = (
        "guest_console" if scenario.execution_channel == "out_of_band_jea_activation"
        and stage == "activate" else "ansible"
    )
    expected_stage = "activate" if scenario.execution_channel == "out_of_band_jea_activation" else "apply"
    if stage not in (expected_stage, "validate"):
        raise InstallBlocked("Unexpected installation stage")
    if (type(proof.passed) is not bool or proof.passed is not True
            or proof.scenario_number != scenario.number
            or proof.stage != stage
            or proof.transport != expected_transport
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", proof.evidence_id)):
        raise InstallBlocked(f"Scenario #{scenario.number} {stage}: missing exact runtime proof")


def private_instance_directory(root: Path, instance_id: str) -> Path:
    if root.is_symlink():
        raise InstallBlocked("Private installation root must not be a symlink")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o077:
        raise InstallBlocked("Private installation root must be owner-only")
    target = root / instance_id
    if target.is_symlink():
        raise InstallBlocked("Refusing linked WSLPE instance state")
    target.mkdir(mode=0o700, exist_ok=True)
    if target.stat().st_uid != os.geteuid() or target.stat().st_mode & 0o077:
        raise InstallBlocked("WSLPE instance state must be owner-only")
    return target


def checkpoint(path: Path, report: dict) -> None:
    temporary = path.parent / (".install-" + token_hex(12))
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def install_41(identity: FreshGuestIdentity, runner: FreshGuestRunner, state_root: Path) -> Path:
    """Single ordered apply/validate pass for 41; fail closed, never auto-resume.

    The runner is intentionally injected: no production runner is authorized
    until fresh VMware/WinRM/guest-console lifecycle is implemented and tested.
    """
    scenarios = fresh_scenario_manifest()
    if len(scenarios) != 41 or len({s.number for s in scenarios}) != 41:
        raise InstallBlocked("Refusing an incomplete 41-scenario manifest")
    proof = runner.preflight(identity)
    verify_attestation(identity, proof)
    state = private_instance_directory(state_root, identity.instance_id)
    lockfd = os.open(state / ".install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InstallBlocked("Another WSLPE installation is active") from exc
        journal = state / "fresh-install.json"
        sentinel = state / ".incomplete"
        if journal.exists() or journal.is_symlink() or sentinel.exists() or sentinel.is_symlink():
            raise InstallBlocked("Existing installation evidence requires reviewed recovery; never replay")
        fd = os.open(sentinel, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(identity.instance_id + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        report = {
            "schema": "kingdoms.wslpe41.fresh-install.v1",
            "instance_id": identity.instance_id,
            "workspace": identity.workspace,
            "vmx": identity.vmx,
            "subnet": identity.subnet,
            "source_commit": identity.source_commit,
            "created_at": _now(),
            "status": "INSTALLING",
            "configuration_validated": 0,
            "learner_exploitation": "NOT_PROVEN",
            "course_release": "NOT_AUTHORIZED",
            "inflight": None,
            "failure": None,
            "scenarios": [
                {"number": s.number, "id": s.identifier,
                 "install": "PENDING", "validation": "PENDING", "proofs": []}
                for s in scenarios
            ],
        }
        checkpoint(journal, report)
        for scenario, record in zip(scenarios, report["scenarios"]):
            first = "activate" if scenario.execution_channel == "out_of_band_jea_activation" else "apply"
            for stage in (first, "validate"):
                report["inflight"] = {"number": scenario.number, "stage": stage}
                checkpoint(journal, report)  # durable intent BEFORE guest mutation
                try:
                    stage_proof = runner.run_stage(scenario, stage)
                    verify_stage(scenario, stage, stage_proof)
                except BaseException as exc:
                    report["status"] = "BLOCKED"
                    report["failure"] = {
                        "number": scenario.number, "stage": stage,
                        "reason": "Missing exact runtime proof or interrupted stage",
                        "exception": type(exc).__name__,
                    }
                    checkpoint(journal, report)
                    raise
                record["install" if stage != "validate" else "validation"] = "PASS"
                record["proofs"].append({
                    "stage": stage, "transport": stage_proof.transport,
                    "evidence_id": stage_proof.evidence_id,
                })
                if stage == "validate":
                    report["configuration_validated"] += 1
                report["inflight"] = None
                checkpoint(journal, report)
        if report["configuration_validated"] != 41 or any(
            record["install"] != "PASS" or record["validation"] != "PASS"
            for record in report["scenarios"]
        ):
            raise InstallBlocked("41/41 exact configuration proof is missing")
        report["status"] = "CONFIGURATION_VALIDATED"
        checkpoint(journal, report)
        sentinel.unlink()
        return journal
    finally:
        os.close(lockfd)
