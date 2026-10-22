"""Source-grounded per-scenario invocations for ONE fresh WSLPE41 transaction.

Plans are not executable authorization. The production runner must prove
exact guest identity, isolated inventory, credentials, transport and actual
Windows output *after* each command. This module never runs subprocesses.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import re

from kingdoms.wslpe41_fresh_contract import FreshScenario, fresh_scenario_manifest
from kingdoms.wslpe45_batch_operator import command as indexed_command, index_rows


class StagePlanBlocked(ValueError):
    pass


@dataclass(frozen=True)
class StageInvocation:
    number: int
    identifier: str
    stage: str
    transport: str
    argv: tuple[str, ...]
    evidence_marker: str | None
    evidence_kind: str


def build_stage_invocation(
    scenario: FreshScenario, stage: str, *,
    ansible: Path, inventory: Path, varsfile: Path, expected_address: str,
    instance_id: str, management_address: str | None = None,
) -> StageInvocation:
    """Construct one exact stage; never reuse golden-master runtime state."""
    if not isinstance(instance_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{4,100}", instance_id):
        raise StagePlanBlocked("Fresh native instance ID missing or invalid")
    allowed = {s.number: s for s in fresh_scenario_manifest()}
    if allowed.get(scenario.number) != scenario:
        raise StagePlanBlocked("Unrecognized or modified WSLPE41 scenario")
    try:
        address = ipaddress.IPv4Address(expected_address)
    except ipaddress.AddressValueError as exc:
        raise StagePlanBlocked("Invalid WSLPE target IP") from exc
    if (not address.is_private or address in ipaddress.IPv4Network("10.4.0.0/16")
            or address.is_loopback or address.is_link_local):
        raise StagePlanBlocked("Forbidden or non-private WSLPE target")
    if any(not isinstance(path, Path) or not path.is_absolute() or path.is_symlink()
           for path in (ansible, inventory, varsfile)):
        raise StagePlanBlocked("Ansible executable/inventory paths must be absolute and nonlinked")
    if management_address is not None:
        if expected_address != "172.28.232.31" or management_address != "172.28.233.31":
            raise StagePlanBlocked("Existing fresh WSLPE address pairing differs from pinned contract")
    transport_address = management_address or str(address)
    if stage not in (("stage", "activate", "validate") if scenario.number == 30
                     else ("apply", "validate")):
        raise StagePlanBlocked("Unexpected stage for exact scenario")

    if scenario.number == 30 and stage == "activate":
        # This is a *requirement*, not an executable PowerShell command.
        # JEA registration can disrupt WinRM; a future independent guest-console
        # transport must execute Invoke-Wslpe45JeaLocal -Action Apply and prove
        # both local recovery and a fresh remote learner Status check.
        return StageInvocation(
            scenario.number, scenario.identifier, stage, "guest_console", (),
            "WSLPE45_JEA_LOCAL_APPLY=PASS", "independent_console_and_winrm_recovery",
        )

    if scenario.number <= 20:
        extra = {
            "wslpe_action": stage,
            "wslpe_techniques": [scenario.identifier],
            "wslpe41_fresh_run": True,
            "wslpe41_expected_address": transport_address,
            "wslpe41_learner_address": str(address),
            "wslpe41_stage_label": "apply" if stage == "apply" else "vulnerable",
            # Runtime environment must independently bind this to the
            # private fixture vars and the freshly provisioned instance.
            "wslpe41_instance_id": instance_id,
        }
        playbook = scenario.playbook
        marker = f"WSLPE41_STAGE={scenario.identifier}:{extra['wslpe41_stage_label']}:PASS"
        proof_kind = "windows_post_role_and_exact_role_validation"
    elif scenario.number == 30:
        extra = {"wslpe_expected_address": transport_address,
                 "wslpe_learner_address": str(address)}
        if stage == "stage":
            extra.update(
                wslpe_45_action="stage",
                wslpe_45_technique=scenario.identifier,
                wslpe_jea_stage_approved=True,
            )
            playbook = scenario.playbook
            marker = "WSLPE45_JEA_LOCAL_SOURCE=STAGED_NOT_EXECUTED"
            proof_kind = "staged_source_presence"
        else:
            playbook = "ansible/wslpe45/deploy21-jea-status.yml"
            marker = "WSLPE21_JEA_ACTIVE=PASS"
            proof_kind = "fresh_learner_endpoint_status"
    else:
        rows = {r["number"]: r for r in index_rows()}
        row = rows.get(scenario.number)
        if not row or row["id"] != scenario.identifier or row["playbook"] != scenario.playbook:
            raise StagePlanBlocked("Unqualified standalone source row")
        action = "apply" if stage == "apply" else "validate"
        state = None if action == "apply" else "vulnerable"
        argv = indexed_command(
            ansible, inventory, varsfile, row, transport_address, action, state,
            "apply" if action == "apply" else "vulnerable",
        )
        extra = json.loads(argv[-1])
        # New guest: install shared standalone library; do not reuse the
        # previous golden-master preservation shortcut.
        extra["wslpe_learner_address"] = str(address)
        extra["wslpe_deploy21"] = True
        extra["wslpe_pilot_preserve_shared"] = False
        argv[-1] = json.dumps(extra, separators=(",", ":"))
        return StageInvocation(
            scenario.number, scenario.identifier, stage, "ansible", tuple(argv),
            f"WSLPE21_STAGE={scenario.identifier}:{'apply' if stage == 'apply' else 'vulnerable'}:PASS",
            "exact_windows_scenario_marker",
        )

    root = Path(__file__).resolve().parents[1]
    target = root / playbook
    if target.is_symlink() or not target.is_file():
        raise StagePlanBlocked("WSLPE stage playbook missing or linked")
    argv = (
        str(ansible), "-i", str(inventory), "-i", str(varsfile),
        "--limit", "ws01,localhost", str(target), "-e",
        json.dumps(extra, separators=(",", ":")),
    )
    return StageInvocation(
        scenario.number, scenario.identifier, stage, "ansible", argv,
        marker, proof_kind,
    )


def one_install_invocations(
    *, ansible: Path, inventory: Path, varsfile: Path, expected_address: str,
    instance_id: str, management_address: str | None = None,
) -> tuple[StageInvocation, ...]:
    """One ordered 41-scenario apply/validate transaction, 83 runtime stages."""
    result: list[StageInvocation] = []
    for scenario in fresh_scenario_manifest():
        stages = ("stage", "activate", "validate") if scenario.number == 30 else ("apply", "validate")
        for stage in stages:
            result.append(build_stage_invocation(
                scenario, stage, ansible=ansible, inventory=inventory,
                varsfile=varsfile, expected_address=expected_address,
                instance_id=instance_id, management_address=management_address,
            ))
    if len(result) != 83 or len({r.number for r in result}) != 41:
        raise StagePlanBlocked("Single WSLPE41 installation stage count drift")
    return tuple(result)
