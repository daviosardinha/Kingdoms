"""Guarded TWO-PHASE installer for the already-running WSLPE41 native guest.

Uses only existing stage invocations and live operator/TLS foundation. One private
journal, 83 ordered stages, a mandatory interactive VMware-console pause for
JEA #30, and no automatic replay after failures. This is a distinct provided-
guest contract; do not falsify install_41's "created_by_this_install" claim.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

from kingdoms import wslpe41_operator_management as management
from kingdoms.wslpe41_fresh_contract import fresh_scenario_manifest
from kingdoms.wslpe41_install_flow import (
    InstallBlocked, checkpoint, private_instance_directory, verify_stage,
)
from kingdoms.wslpe41_operator_auth import authenticate_native_operator
from kingdoms.wslpe41_provided_runtime import INSTANCE, ROOT, load_existing
from kingdoms.wslpe41_runtime_proof import (
    ObservedStageResult, verify_observed_stage,
)
from kingdoms.wslpe41_stage_commands import (
    build_stage_invocation, one_install_invocations,
)
from kingdoms.wslpe41_stage_executor import _guest, run_ansible_stage

STATE_ROOT = Path.home() / ".local/state/kingdoms-wslpe41-provided-install"
SCHEMA = "kingdoms.wslpe41.provided-install.v1"
WITNESS = r"C:\ProgramData\KingdomsWSLPE45\lib\WSLPE41-JEA30-receipt.json"


@contextmanager
def private_environment(context, operator, learner):
    settings = {
        "KINGDOMS_WSLPE_INSTANCE_ID": context.identity.instance_id,
        "KINGDOMS_WSLPE_OPERATOR_PASSWORD": operator,
        "KINGDOMS_WSLPE_LEARNER_PASSWORD": learner,
        "KINGDOMS_WSLPE_FIXTURE_VARS_FILE": str(context.private_vars),
    }
    prior = {key: os.environ.get(key) for key in settings}
    try:
        os.environ.update(settings)
        yield
    finally:
        for key, previous in prior.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def _stages(context):
    plan = one_install_invocations(
        ansible=context.ansible, inventory=context.inventory,
        varsfile=context.private_vars,
        expected_address=context.expected_address,
        instance_id=context.identity.instance_id,
        management_address=context.management_address,
    )
    if (len(plan) != 83 or len({step.number for step in plan}) != 41
            or sum(step.transport == "guest_console" for step in plan) != 1):
        raise InstallBlocked("Exact provided 41/83 stage manifest drift")
    return plan


def _preflight(report=None):
    # Fixed gate labels never include private secrets or raw Ansible output.
    report = report or (lambda message: None)
    report("[CHECK] Existing private operator/fixture/TLS runtime")
    context, operator, learner = load_existing()
    report("[PASS] Existing private operator/fixture/TLS runtime")
    report("[CHECK] Exact registered native guest and source")
    if context.identity.instance_id != INSTANCE:
        raise InstallBlocked("Provided installer is not bound to exact native guest")
    if context.identity.vmx != str(management.exact_target().vmx):
        raise InstallBlocked("Native VMX changed after runtime preparation")
    if subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=normal"],
        text=True, timeout=15,
    ).strip():
        raise InstallBlocked("Installer source tree is dirty")
    _guest(context)
    report("[PASS] Exact registered native guest and clean source")
    report("[CHECK] Live pinned-certificate Ansible operator authentication")
    with private_environment(context, operator, learner):
        if authenticate_native_operator(context) is not True:
            raise InstallBlocked("Live certificate-validated Ansible operator auth missing")
    report("[PASS] Live pinned-certificate Ansible operator authentication")
    return context, operator, learner


def _base_state(context):
    return {
        "schema": SCHEMA, "instance": INSTANCE,
        "vmx": context.identity.vmx,
        "source_commit": context.identity.source_commit,
        "status": "RUNNING",
        "next_stage": 0,
        "inflight": None,
        "jea_nonce": secrets.token_hex(16),
        "proofs": [],
        "configuration_validated": 0,
        "course_release": "NOT_AUTHORIZED",
        "learner_exploitation": "NOT_PROVEN",
    }


def _check_state(context, record):
    if (record.get("schema") != SCHEMA or record.get("instance") != INSTANCE
            or record.get("vmx") != context.identity.vmx
            or record.get("source_commit") != context.identity.source_commit
            or not re.fullmatch(r"[a-f0-9]{32}", str(record.get("jea_nonce", "")))
            or type(record.get("next_stage")) is not int
            or not 0 <= record["next_stage"] <= 83
            or not isinstance(record.get("proofs"), list)
            or len(record["proofs"]) != record["next_stage"]):
        raise InstallBlocked("Existing provided journal or source revision mismatch")


def console_command(nonce: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise InstallBlocked("Invalid JEA console nonce")
    # The only intended source of this record is an elevated *active console*
    # after the already installed module validates that execution channel.
    return r"""$ErrorActionPreference = 'Stop'
Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeJeaLocal.psm1' -Force -ErrorAction Stop
Assert-Wslpe45JeaConsole
$Output = @(Invoke-Wslpe45JeaLocal -Action Apply)
foreach ($Marker in @('WSLPE45_JEA_LOCAL_APPLY=PASS','WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS')) {
    if (@($Output | Where-Object { $_ -ceq $Marker }).Count -ne 1) { throw ('Missing console marker: ' + $Marker) }
}
Assert-Wslpe45JeaConsole
$Destination = 'C:\ProgramData\KingdomsWSLPE45\lib\WSLPE41-JEA30-receipt.json'
if (Test-Path -LiteralPath $Destination) { throw 'Existing JEA30 receipt. Do not repeat activation.' }
$Record = @{
    schema = 'kingdoms.wslpe41.console-jea30.v1'
    nonce = '""" + nonce + r"""'
    machine = $env:COMPUTERNAME
    console_session = [Diagnostics.Process]::GetCurrentProcess().SessionId
    principal = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    applied = 'WSLPE45_JEA_LOCAL_APPLY=PASS'
    recovered = 'WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS'
}
$Record | ConvertTo-Json -Compress | Set-Content -LiteralPath $Destination -Encoding UTF8 -NoNewline -ErrorAction Stop
& icacls.exe $Destination /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'JEA console witness ACL hardening failed' }
Write-Output 'WSLPE41_JEA30_CONSOLE_RECEIPT=PASS'
"""


def _read_console_observation(context, nonce, certificate, operator):
    """Query a concrete Windows console-generated witness over verified TLS.

    Remote WinRM reads evidence only, never invokes local JEA activation.
    The witness is not accepted alone: the next canonical JEA status stage
    independently authenticates the nonadmin learner endpoint over WinRM.
    """
    auth = management.auth_helper()
    script = r"""
$ErrorActionPreference='Stop'
$p='C:\ProgramData\KingdomsWSLPE45\lib\WSLPE41-JEA30-receipt.json'
$i=Get-Item -LiteralPath $p -ErrorAction Stop
if($i.PSIsContainer -or ($i.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Bad witness path' }
if($i.Length -gt 5000) { throw 'Witness too large' }
$r=Get-Content -LiteralPath $p -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
if($r.schema -cne 'kingdoms.wslpe41.console-jea30.v1' -or
   $r.nonce -cne '""" + nonce + r"""' -or
   $r.machine -cne 'WSLPE-WS01' -or
   [int]$r.console_session -lt 1 -or
   $r.applied -cne 'WSLPE45_JEA_LOCAL_APPLY=PASS' -or
   $r.recovered -cne 'WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS') {
    throw 'Console witness does not match bounded JEA stage'
}
if((Get-Service WinRM -ErrorAction Stop).Status -ne 'Running' -or
   -not @(Get-PSSessionConfiguration -Name Kingdoms45JEA -ErrorAction Stop)) {
    throw 'JEA or WinRM is not active'
}
Write-Output 'WSLPE45_JEA_LOCAL_APPLY=PASS'
Write-Output 'WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS'
"""
    with management.operator_session(auth, certificate, operator) as session:
        result = management.run_powershell(session, script)
    if result.status_code != 0:
        raise InstallBlocked("Independent console witness could not be verified over TLS")
    output = result.std_out.decode("utf-8-sig", errors="replace")
    # A remote witness is never a substitute for running the guest-console
    # script. This is a bounded, machine-side record of that separate event.
    if (output.count("WSLPE45_JEA_LOCAL_APPLY=PASS") != 1
            or output.count("WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS") != 1):
        raise InstallBlocked("Exact console witness markers missing or duplicated")
    return ObservedStageResult(
        instance_id=context.identity.instance_id, vmx=context.identity.vmx,
        transport="guest_console", returncode=0, stdout=output, stderr="",
    )


def _install_steps(context, state, journal, stages):
    scenarios = {s.number: s for s in fresh_scenario_manifest()}
    while state["next_stage"] < len(stages):
        ix = state["next_stage"]
        step = stages[ix]
        if step.transport == "guest_console":
            state["status"] = "WAITING_CONSOLE_JEA"
            state["inflight"] = None
            checkpoint(journal, state)
            print("[PAUSED] JEA #30 must be applied from elevated VMware guest console")
            print("[RUN IN WINDOWS VMWARE CONSOLE ONLY]")
            print(console_command(state["jea_nonce"]))
            print("[NEXT] After console receipt, run --resume (do not repeat --start)")
            return "PAUSED"
        state["inflight"] = {"number": step.number, "stage": step.stage}
        checkpoint(journal, state)  # durable intent BEFORE Windows mutation
        try:
            proof = run_ansible_stage(context, scenarios[step.number], step.stage)
            verify_stage(scenarios[step.number], step.stage, proof)
        except BaseException as exc:
            state["status"] = "BLOCKED"
            # Keep only source-authored, bounded error classification, not
            # Ansible output, Windows private data or credential material.
            state["failure_class"] = type(exc).__name__
            if isinstance(exc, InstallBlocked):
                state["failure_gate"] = str(exc)[:240]
            checkpoint(journal, state)
            raise
        state["proofs"].append({
            "number": step.number, "stage": step.stage,
            "transport": proof.transport, "evidence_id": proof.evidence_id,
        })
        state["next_stage"] += 1
        state["inflight"] = None
        if step.stage == "validate":
            state["configuration_validated"] += 1
        checkpoint(journal, state)
        print(f"[PASS] Scenario #{step.number:02d} {step.stage} (stage {state['next_stage']}/83)", flush=True)
    if state["configuration_validated"] != 41 or state["next_stage"] != 83:
        raise InstallBlocked("Missing full 41/83 provided-install configuration proof")
    state["status"] = "CONFIGURATION_VALIDATED"
    checkpoint(journal, state)
    print("[PASS] WSLPE41_PROVIDED_CONFIGURATION_VALIDATED=41/41")
    print("[NOT PROVEN] Learner exploitation and course release remain separate")
    return "DONE"


def diagnose(report=print) -> bool:
    """Read-only preflight and installation-journal presence inspection.

    Never creates a journal, lock, or private state directory. No scenario
    may execute here; an existing install journal requires separate review.
    """
    root = STATE_ROOT / INSTANCE
    journal = root / "provided-install.json"
    report("[READ ONLY] Exact WSLPE41 preflight and journal audit")
    if journal.is_symlink():
        raise InstallBlocked("Installation journal is a symlink; manual review required")
    if journal.exists():
        if not journal.is_file():
            raise InstallBlocked("Existing install journal is not a regular file")
        if journal.stat().st_size > 250_000:
            raise InstallBlocked("Existing installation journal is oversized")
        data = json.loads(journal.read_text(encoding="utf-8"))
        report("[JOURNAL] status=" + str(data.get("status", "UNKNOWN")) +
               " next_stage=" + str(data.get("next_stage", "UNKNOWN")) +
               " validated=" + str(data.get("configuration_validated", "UNKNOWN")) +
               " inflight=" + str(bool(data.get("inflight"))))
        report("[STOP] Existing installation journal; do not rerun --start")
        return False
    if root.is_symlink():
        raise InstallBlocked("Install state directory is a symlink")
    if root.exists() and not root.is_dir():
        raise InstallBlocked("Install state directory is not a directory")
    report("[JOURNAL] No provided-install.json found")
    context, _, _ = _preflight(report=report)
    report("[CHECK] Exact 41 scenarios / 83 stage plan")
    plan = _stages(context)
    if not plan or plan[0].number != 1:
        raise InstallBlocked("Canonical stage plan first entry unexpected")
    report("[PASS] Exact 41 scenarios / 83 stage plan")
    report("[READY] WSLPE41_PROVIDED_START_PREFLIGHT=PASS")
    report("[NO CHANGES] No VM, guest, journal, credentials or scenario writes")
    return True


def install(mode: str) -> str:
    if mode not in ("start", "resume", "status"):
        raise InstallBlocked("Invalid provided installation mode")
    context, operator, learner = _preflight()
    state_dir = private_instance_directory(STATE_ROOT, INSTANCE)
    journal = state_dir / "provided-install.json"
    lock = os.open(state_dir / ".install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stages = _stages(context)
        if mode == "start":
            if journal.exists() or journal.is_symlink():
                raise InstallBlocked("Existing provided installation journal; never replay")
            state = _base_state(context)
            checkpoint(journal, state)
        else:
            if not journal.is_file() or journal.is_symlink():
                raise InstallBlocked("Existing provided installation journal missing or unsafe")
            state = json.loads(journal.read_text())
            _check_state(context, state)
            if mode == "status":
                print(f"[STATE] {state['status']} | completed={state['next_stage']}/83 | scenarios={state['configuration_validated']}/41")
                if state["status"] == "WAITING_CONSOLE_JEA":
                    print("[RUN IN WINDOWS VMWARE CONSOLE ONLY]")
                    print(console_command(state["jea_nonce"]))
                return state["status"]
            if (state["status"] != "WAITING_CONSOLE_JEA"
                    or state["inflight"] is not None
                    or stages[state["next_stage"]].number != 30
                    or stages[state["next_stage"]].stage != "activate"):
                raise InstallBlocked("No reviewed JEA console handoff pending; refusing resume")
            from kingdoms.wslpe41_provided_runtime import existing_management
            _, _, certificate, _, _ = existing_management()
            with private_environment(context, operator, learner):
                observation = _read_console_observation(
                    context, state["jea_nonce"], certificate, operator)
            step = stages[state["next_stage"]]
            from kingdoms.wslpe41_runtime_proof import verify_observed_stage
            proof = verify_observed_stage(
                step, observation,
                expected_instance_id=context.identity.instance_id,
                expected_vmx=context.identity.vmx,
            )
            verify_stage(next(s for s in fresh_scenario_manifest() if s.number == 30),
                         "activate", proof)
            state["proofs"].append({
                "number": 30, "stage": "activate", "transport": "guest_console",
                "evidence_id": proof.evidence_id,
            })
            state["next_stage"] += 1
            state["status"] = "RUNNING"
            checkpoint(journal, state)
        with private_environment(context, operator, learner):
            return _install_steps(context, state, journal, stages)
    finally:
        os.close(lock)
