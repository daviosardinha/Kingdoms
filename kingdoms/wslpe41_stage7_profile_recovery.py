"""One-time exact stage-7 Windows profile recovery for existing WSLPE41.

Preserves twelve successful stage proofs and every previous blocked journal.
Requires independent read-only Windows state, verifies original failed stage7,
creates ONLY the missing learner profile using Windows' CreateProfile API, then
resumes the canonical installer at stage 13. No generic resume or retries.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

from kingdoms import wslpe41_provided_install as provided
from kingdoms import wslpe41_stage7_readonly_audit as audit
from kingdoms import wslpe41_operator_management as management
from kingdoms.wslpe41_install_flow import InstallBlocked, checkpoint, private_instance_directory
from kingdoms.wslpe41_provided_runtime import INSTANCE, existing_management


CREATE_PROFILE_SCRIPT = r"""$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -cne 'WSLPE-WS01') { throw 'Unexpected profile-preparation machine' }
$who = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($who)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'An elevated administrator token is required'
}
$user = Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
if (-not $user.Enabled) { throw 'Learner account is disabled' }
$sid = $user.SID.Value
$profileKey = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$sid"
if (Test-Path -LiteralPath $profileKey) { throw 'Profile appeared since inspection; refuse recovery' }
$root = 'C:\Kingdom LPE\AlwaysInstallElevated'
if (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw 'Scenario 7 directory no longer exists'
}
if (Test-Path -LiteralPath (Join-Path $root 'state.json')) {
    throw 'Scenario7 state snapshot appeared; refuse profile recovery'
}
$machineKey = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Installer'
if ($null -ne (Get-ItemProperty -LiteralPath $machineKey -Name AlwaysInstallElevated -ErrorAction SilentlyContinue)) {
    throw 'Machine AlwaysInstallElevated policy changed'
}
if (Test-Path -LiteralPath "Registry::HKEY_USERS\$sid") { throw 'Learner hive already loaded' }
if (-not ([System.IO.Directory]::Exists("$env:SystemDrive\Users"))) {
    throw 'Standard users profile root unavailable'
}
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class KingdomsWslpe41CreateProfile {
    [DllImport("userenv.dll", EntryPoint="CreateProfile", CharSet=CharSet.Unicode, ExactSpelling=true)]
    public static extern int CreateProfile(string sid, string userName, StringBuilder profilePath, uint count);
}
'@ -ErrorAction Stop
$buffer = New-Object System.Text.StringBuilder 260
$hr = [KingdomsWslpe41CreateProfile]::CreateProfile($sid, 'lpe.trainee', $buffer, [uint32]$buffer.Capacity)
if ($hr -ne 0) { throw ('CreateProfile failed HRESULT=0x{0:X8}' -f ([uint32]$hr)) }
if (-not (Test-Path -LiteralPath $profileKey)) { throw 'CreateProfile returned success but no ProfileList entry' }
$realPath = [Environment]::ExpandEnvironmentVariables(
    [string](Get-ItemProperty -LiteralPath $profileKey -Name ProfileImagePath -ErrorAction Stop).ProfileImagePath)
if (-not [string]::Equals(
     [IO.Path]::GetFullPath($realPath).TrimEnd('\'),
     [IO.Path]::GetFullPath($buffer.ToString()).TrimEnd('\'),
     [StringComparison]::OrdinalIgnoreCase)) {
     throw 'Created profile path differs from registered profile path'
}
if (-not (Test-Path -LiteralPath $realPath -PathType Container)) {
    throw 'Profile directory missing after native creation'
}
$hive = Join-Path $realPath 'NTUSER.DAT'
if (-not (Test-Path -LiteralPath $hive -PathType Leaf)) {
    throw 'NTUSER.DAT missing after native creation'
}
Write-Output 'WSLPE41_STAGE7_LEARNER_PROFILE=CREATED_AND_VERIFIED'
"""


def _exact_empty_precondition(record: dict, context, evidence: dict) -> None:
    if (record.get("schema") != provided.SCHEMA or record.get("instance") != INSTANCE
            or record.get("vmx") != context.identity.vmx
            or not re.fullmatch(r"[a-f0-9]{40}", str(record.get("source_commit", "")))
            or not re.fullmatch(r"[a-f0-9]{32}", str(record.get("jea_nonce", "")))
            or record.get("status") != "BLOCKED"
            or record.get("next_stage") != 12
            or record.get("configuration_validated") != 6
            or record.get("inflight") != {"number": 7, "stage": "apply"}
            or len(record.get("proofs", [])) != 12
            or not str(record.get("failure_gate", "")).startswith(
                "Scenario #7 apply: Ansible rc=2; last_task=windows_lpe : Apply AlwaysInstallElevated candidate")):
        raise InstallBlocked("Not the exact stage7 blocked journal and source lineage")
    expected = {
        "learner_exists": True, "learner_enabled": True,
        "profile_registry_exists": False, "profile_directory_exists": False,
        "ntuser_dat_exists": False, "scenario_directory_exists": True,
        "state_file_exists": False, "state_snapshot_matches_learner": False,
        "machine_policy_value": None, "learner_hive_loaded": False,
        "learner_policy_value": None,
    }
    if any(type(evidence.get(k)) is not bool if type(v) is bool
           else evidence.get(k) is not None
           for k, v in expected.items()):
        # Do not broaden this guard if a profile or vulnerable policy exists.
        raise InstallBlocked("Unexpected scenario7 Windows state; preserve journal for review")
    if any(evidence[k] != v for k, v in expected.items()):
        raise InstallBlocked("Windows profile/policy state changed since blocked stage7 audit")


def _create_profile_verified(context, operator: str) -> None:
    target, _, cert, saved_password, _ = existing_management()
    if str(target.vmx) != context.identity.vmx or saved_password != operator:
        raise InstallBlocked("Operator or exact VMware identity differs during stage7 recovery")
    auth = management.auth_helper()
    with management.operator_session(auth, cert, operator) as session:
        response = management.run_powershell(session, CREATE_PROFILE_SCRIPT)
    if response.status_code != 0:
        raise InstallBlocked("Native CreateProfile stage7 preparation failed; state preserved for review")
    markers = [
        line for line in response.std_out.decode("utf-8-sig", errors="replace").splitlines()
        if line == "WSLPE41_STAGE7_LEARNER_PROFILE=CREATED_AND_VERIFIED"
    ]
    if len(markers) != 1:
        raise InstallBlocked("No unique native learner-profile proof after stage7 recovery")


def recover() -> str:
    context, operator, learner = provided._preflight()
    state_dir = private_instance_directory(provided.STATE_ROOT, INSTANCE)
    journal = state_dir / "provided-install.json"
    archived = state_dir / "provided-install.blocked-stage7.json"
    intent = state_dir / "stage7-profile-recovery-intent.json"
    lock = os.open(state_dir / ".install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if archived.exists() or archived.is_symlink() or intent.exists() or intent.is_symlink():
            raise InstallBlocked("Stage7 recovery already attempted or interrupted")
        record = audit._journal_state()  # exact 12 validated proofs, owner-private, blocked stage7
        if not journal.is_file() or journal.is_symlink():
            raise InstallBlocked("Active blocked scenario7 journal changed")
        raw = journal.read_bytes()
        if json.loads(raw) != record:
            raise InstallBlocked("Stage7 journal changed during recovery preflight")
        observed = audit.inspect()
        _exact_empty_precondition(record, context, observed)
        stages = provided._stages(context)
        if (len(stages) != 83 or stages[12].number != 7
                or stages[12].stage != "apply" or stages[12].transport != "ansible"):
            raise InstallBlocked("Canonical stage7 source/stage indexing changed")
        print("[PASS] Previous twelve stages and actual stage7 Windows state reviewed", flush=True)
        # The original failure is immutable. New journal carries forward
        # exactly the original 12 runtime proofs and JEA nonce.
        new_state = dict(record)
        new_state["source_commit"] = context.identity.source_commit
        new_state["status"] = "PROFILE_PREPARING"
        new_state["inflight"] = {"number": 7, "stage": "profile_prepare"}
        new_state.pop("failure_gate", None)
        new_state.pop("failure_class", None)
        new_state["stage7_profile_recovery"] = {
            "kind": "one-time-stage7-native-profile",
            "previous_journal_sha256": hashlib.sha256(raw).hexdigest(),
            "previous_source_commit": record["source_commit"],
            "current_source_commit": context.identity.source_commit,
            "completed_stages_retained": 12,
            "validated_scenarios_retained": 6,
        }
        fd = os.open(intent, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(new_state["stage7_profile_recovery"], sort_keys=True).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(journal, archived)
        checkpoint(journal, new_state)
        print("[ARCHIVED] Original scenario7 failure retained with all 12 proofs", flush=True)
        try:
            _create_profile_verified(context, operator)
        except BaseException as exc:
            new_state["status"] = "BLOCKED"
            new_state["failure_class"] = type(exc).__name__
            if isinstance(exc, InstallBlocked):
                new_state["failure_gate"] = str(exc)[:240]
            checkpoint(journal, new_state)
            raise
        print("[PASS] Created and verified missing native Windows learner profile", flush=True)
        new_state["status"] = "RUNNING"
        new_state["inflight"] = None
        checkpoint(journal, new_state)
        with provided.private_environment(context, operator, learner):
            return provided._install_steps(context, new_state, journal, stages)
    finally:
        os.close(lock)
