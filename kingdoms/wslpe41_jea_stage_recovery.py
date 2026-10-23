"""One-time proof recovery for exact blocked WSLPE41 JEA scenario #30 staging.

No repeated Ansible staging, JEA endpoint activation, host/VMware networking or
guest writes. Verifies three exact deployed module hashes and Windows safety
invariants over pinned TLS. Archives the failed journal with all 56 proofs,
adds one independently observed stage-57 proof, then pauses for guest console.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

from kingdoms import wslpe41_provided_install as provided
from kingdoms import wslpe41_operator_management as management
from kingdoms.wslpe41_install_flow import InstallBlocked, checkpoint, private_instance_directory, verify_stage
from kingdoms.wslpe41_fresh_contract import fresh_scenario_manifest
from kingdoms.wslpe41_provided_runtime import INSTANCE, ROOT, existing_management
from kingdoms.wslpe41_runtime_proof import ObservedStageResult, RuntimeProofBlocked, verify_observed_stage

NAMES = ("WslpeFixture.psm1", "WslpeJea.psm1", "WslpeJeaLocal.psm1")
MARKER = "WSLPE45_JEA_LOCAL_SOURCE=STAGED_NOT_EXECUTED"
AUDIT = "WSLPE41_JEA_STAGE_AUDIT="


def _source_digests() -> dict[str, str]:
    root = ROOT / "ansible" / "files" / "wslpe45"
    result = {}
    for name in NAMES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 250_000:
            raise InstallBlocked("Exact privileged JEA module source unavailable or unsafe")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _live_script(digests: dict[str, str]) -> str:
    if (set(digests) != set(NAMES)
            or any(not re.fullmatch(r"[a-f0-9]{64}", digest) for digest in digests.values())):
        raise InstallBlocked("Invalid source-hash attestation input")
    # Only public source filenames and SHA256 bytes; never private credentials.
    mapping = "\n".join("  '" + name + "' = '" + digests[name] + "'" for name in NAMES)
    return r"""$ErrorActionPreference='Stop'
$machine=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$os=Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain -or
    $os.Caption -notmatch 'Windows 10' -or [int]$os.ProductType -ne 1) {
    throw 'Unexpected WSLPE JEA staging target'
}
if ((Get-Service -Name WinRM -ErrorAction Stop).Status -ne 'Running') {
    throw 'WinRM is not running'
}
$learner=Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
if(-not $learner.Enabled) { throw 'Learner not enabled' }
$admins=Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
foreach($member in @(Get-LocalGroupMember -Group $admins.Name -ErrorAction Stop)) {
    if($member.SID.Value -eq $learner.SID.Value) { throw 'Learner unexpectedly administrator' }
}
if (@(Get-PSSessionConfiguration -Name Kingdoms45JEA -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'JEA endpoint already active; cannot attest source-only staging'
}
$expected=@{
""" + mapping + r"""
}
$root='C:\ProgramData\KingdomsWSLPE45'
$lib=Join-Path $root 'lib'
foreach($dir in @($root,$lib)) {
    $item=Get-Item -LiteralPath $dir -Force -ErrorAction Stop
    if(-not $item.PSIsContainer -or
       ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Invalid JEA privileged directory'
    }
    $acl=Get-Acl -LiteralPath $dir -ErrorAction Stop
    if(-not $acl.AreAccessRulesProtected) { throw 'JEA privileged directory ACL inheriting' }
    foreach($entry in $acl.Access) {
        $sid=$null
        try {
            $sid=$entry.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        } catch { throw 'Unresolvable JEA privileged ACL principal' }
        if($sid -in @('S-1-5-32-545','S-1-1-0','S-1-5-11') -and
           $entry.AccessControlType -eq 'Allow' -and
           (($entry.FileSystemRights -band [Security.AccessControl.FileSystemRights]::WriteData) -or
            ($entry.FileSystemRights -band [Security.AccessControl.FileSystemRights]::Delete) -or
            ($entry.FileSystemRights -band [Security.AccessControl.FileSystemRights]::ChangePermissions))) {
            throw 'Untrusted JEA library ACL is writable'
        }
    }
}
foreach($name in @('WslpeFixture.psm1','WslpeJea.psm1','WslpeJeaLocal.psm1')) {
    $path=Join-Path $lib $name
    $item=Get-Item -LiteralPath $path -Force -ErrorAction Stop
    if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'JEA staging module is missing or linked'
    }
    $hash=(Get-FileHash -LiteralPath $path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    if($hash -cne $expected[$name]) { throw 'JEA staged module hash differs from canonical source' }
}
$result=@{
    schema='kingdoms.wslpe41.jea30.source-audit.v1'
    machine=$env:COMPUTERNAME
    module_hashes=$expected
    endpoint_not_registered=$true
    winrm_ready=$true
}
Write-Output ('WSLPE41_JEA_STAGE_AUDIT=' + ($result | ConvertTo-Json -Compress -Depth 4))
Write-Output 'WSLPE45_JEA_LOCAL_SOURCE=STAGED_NOT_EXECUTED'
"""


def _blocked_state(context, journal: Path, stages) -> tuple[dict, bytes]:
    if journal.is_symlink() or not journal.is_file():
        raise InstallBlocked("Exact blocked JEA stage journal missing or linked")
    meta = journal.stat()
    if (meta.st_uid != os.geteuid() or meta.st_nlink != 1
            or meta.st_mode & 0o077 or meta.st_size > 250_000):
        raise InstallBlocked("Existing JEA journal not owner-private")
    raw = journal.read_bytes()
    state = json.loads(raw)
    if (state.get("schema") != provided.SCHEMA
            or state.get("instance") != INSTANCE
            or state.get("vmx") != context.identity.vmx
            or not re.fullmatch(r"[0-9a-f]{40}", str(state.get("source_commit", "")))
            or not re.fullmatch(r"[0-9a-f]{32}", str(state.get("jea_nonce", "")))
            or state.get("status") != "BLOCKED"
            or state.get("next_stage") != 56
            or state.get("configuration_validated") != 28
            or state.get("inflight") != {"number": 30, "stage": "stage"}
            or state.get("failure_gate") != "WSLPE41 scenario #30 stage: runtime proof missing"):
        raise InstallBlocked("Not the exact blocked JEA #30 staging proof journal")
    proofs = state.get("proofs")
    if (not isinstance(proofs, list) or len(proofs) != 56
            or any(not isinstance(proof, dict)
                   or proof.get("number") != stages[i].number
                   or proof.get("stage") != stages[i].stage
                   or proof.get("transport") != "ansible"
                   or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", str(proof.get("evidence_id","")))
                   for i, proof in enumerate(proofs))
            or stages[56].number != 30 or stages[56].stage != "stage"
            or stages[56].transport != "ansible"
            or stages[57].number != 30 or stages[57].stage != "activate"
            or stages[57].transport != "guest_console"):
        raise InstallBlocked("Original 56 runtime proofs or JEA guest-console boundary differ")
    return state, raw


def _verify_live_modules(context, operator: str, digests: dict[str, str], invocation):
    target, _, certificate, saved_operator, _ = existing_management()
    if str(target.vmx) != context.identity.vmx or saved_operator != operator:
        raise InstallBlocked("Existing pinned TLS operator/VMX identity changed")
    auth = management.auth_helper()
    with management.operator_session(auth, certificate, operator) as session:
        result = management.run_powershell(session, _live_script(digests))
    if result.status_code != 0 or len(result.std_out) > 30_000:
        raise InstallBlocked("Independent JEA source audit over pinned WinRM failed")
    output = result.std_out.decode("utf-8-sig", errors="replace")
    reports = [s[len(AUDIT):] for s in output.splitlines() if s.startswith(AUDIT)]
    if len(reports) != 1:
        raise InstallBlocked("Missing exact JSON attestation from guest JEA source audit")
    attested = json.loads(reports[0])
    if (attested.get("schema") != "kingdoms.wslpe41.jea30.source-audit.v1"
            or attested.get("machine") != "WSLPE-WS01"
            or attested.get("module_hashes") != digests
            or attested.get("endpoint_not_registered") is not True
            or attested.get("winrm_ready") is not True):
        raise InstallBlocked("Live JEA stage attestation does not match exact source and machine")
    if output.count(MARKER) != 1:
        raise InstallBlocked("Duplicate or missing independently observed staging marker")
    try:
        proof = verify_observed_stage(
            invocation, ObservedStageResult(
                instance_id=context.identity.instance_id, vmx=context.identity.vmx,
                transport="ansible", returncode=0,
                stdout=output, stderr="",
            ),
            expected_instance_id=context.identity.instance_id,
            expected_vmx=context.identity.vmx,
        )
        scenario = next(s for s in fresh_scenario_manifest() if s.number == 30)
        verify_stage(scenario, "stage", proof)
    except RuntimeProofBlocked as exc:
        raise InstallBlocked("Independent JEA source proof not accepted") from exc
    return proof


def recover() -> str:
    # All checks before journal archival are read only.
    context, operator, learner = provided._preflight()
    state_dir = private_instance_directory(provided.STATE_ROOT, INSTANCE)
    journal = state_dir / "provided-install.json"
    archive = state_dir / "provided-install.blocked-jea30-stage.json"
    intent = state_dir / "jea30-staging-proof-recovery-intent.json"
    lock = os.open(state_dir / ".install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if archive.exists() or archive.is_symlink() or intent.exists() or intent.is_symlink():
            raise InstallBlocked("JEA source-proof recovery already attempted or interrupted")
        stages = provided._stages(context)
        if len(stages) != 83:
            raise InstallBlocked("Canonical JEA stage manifest count changed")
        old, raw = _blocked_state(context, journal, stages)
        hashes = _source_digests()
        proof = _verify_live_modules(context, operator, hashes, stages[56])
        # Never repeat the already-executed JEA staging Ansible playbook.
        new = dict(old)
        new["source_commit"] = context.identity.source_commit
        new["status"] = "WAITING_CONSOLE_JEA"
        new["inflight"] = None
        new["next_stage"] = 57
        new["proofs"] = [*old["proofs"], {
            "number": 30, "stage": "stage",
            "transport": proof.transport, "evidence_id": proof.evidence_id,
        }]
        new["jea_staging_proof_recovery"] = {
            "kind": "independent-readonly-guest-source-attestation",
            "blocked_journal_sha256": hashlib.sha256(raw).hexdigest(),
            "previous_source_commit": old["source_commit"],
            "current_source_commit": context.identity.source_commit,
            "module_sha256": hashes,
            "prior_validated_scenarios": 28,
            "prior_stage_proofs": 56,
            "jea_remote_activation": "NOT_PERFORMED",
        }
        new.pop("failure_class", None)
        new.pop("failure_gate", None)
        fd = os.open(intent, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(json.dumps(new["jea_staging_proof_recovery"], sort_keys=True).encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(journal, archive)
        checkpoint(journal, new)
        print("[PASS] JEA #30 three source hashes, ACL and guest state verified over pinned TLS", flush=True)
        print("[ARCHIVED] Original BLOCKED journal retained; previous 56 runtime proofs unchanged", flush=True)
        print("[PASS] Scenario #30 stage (stage 57/83) independently proven", flush=True)
        print("[PAUSED] JEA #30 activation requires an elevated VMware guest console", flush=True)
        print("[RUN IN WINDOWS VMWARE CONSOLE ONLY]", flush=True)
        print(provided.console_command(new["jea_nonce"]), flush=True)
        print("[NEXT] After Windows console receipt, run provided-install.py --resume", flush=True)
        return "PAUSED"
    finally:
        os.close(lock)
