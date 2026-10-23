"""Read-only scenario #7 AlwaysInstallElevated failure triage for exact WSLPE41 VM.

This routine only reads the existing blocked journal and WinRM guest state.
It does not create a profile, mount a user hive, modify registry policies,
restart services, change accounts, or resume the installation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from kingdoms import wslpe41_operator_management as management
from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_provided_runtime import INSTANCE, existing_management
from kingdoms.wslpe41_provided_install import STATE_ROOT, SCHEMA

SCRIPT = r"""$ErrorActionPreference = 'Stop'
$learner = Get-LocalUser -Name 'lpe.trainee' -ErrorAction SilentlyContinue
$sid = if ($null -ne $learner) { $learner.SID.Value } else { $null }
$profileKey = if ($sid) { "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$sid" } else { $null }
$profileExists = [bool]($profileKey -and (Test-Path -LiteralPath $profileKey))
$profilePath = $null
if ($profileExists) {
    $profilePath = [Environment]::ExpandEnvironmentVariables(
        [string](Get-ItemProperty -LiteralPath $profileKey -Name ProfileImagePath -ErrorAction Stop).ProfileImagePath
    )
}
$ntuser = [bool]($profilePath -and (Test-Path -LiteralPath (Join-Path $profilePath 'NTUSER.DAT') -PathType Leaf))
$root = 'C:\Kingdom LPE\AlwaysInstallElevated'
$stateFile = Join-Path $root 'state.json'
$machineKey = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Installer'
$hklm = Get-ItemProperty -LiteralPath $machineKey -Name AlwaysInstallElevated -ErrorAction SilentlyContinue
$machineValue = if ($null -ne $hklm) { [int]$hklm.AlwaysInstallElevated } else { $null }
$hiveLoaded = [bool]($sid -and (Test-Path -LiteralPath ("Registry::HKEY_USERS\" + $sid)))
$userValue = $null
if ($hiveLoaded) {
    $userKey = "Registry::HKEY_USERS\$sid\Software\Policies\Microsoft\Windows\Installer"
    $hkcu = Get-ItemProperty -LiteralPath $userKey -Name AlwaysInstallElevated -ErrorAction SilentlyContinue
    if ($null -ne $hkcu) { $userValue = [int]$hkcu.AlwaysInstallElevated }
}
$stateExists = Test-Path -LiteralPath $stateFile -PathType Leaf
$stateValid = $false
if ($stateExists) {
    try {
        $item = Get-Item -LiteralPath $stateFile -ErrorAction Stop
        if ($item.Length -le 8192 -and -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            $saved = Get-Content -LiteralPath $stateFile -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
            $stateValid = [bool]($saved.sid -eq $sid -and $saved.profile -eq $profilePath)
        }
    } catch { $stateValid = $false }
}
$result = @{
    schema = 'kingdoms.wslpe41.stage7-readonly.v1'
    computer = $env:COMPUTERNAME
    learner_exists = [bool]($null -ne $learner)
    learner_enabled = [bool]($null -ne $learner -and $learner.Enabled)
    profile_registry_exists = $profileExists
    profile_directory_exists = [bool]($profilePath -and (Test-Path -LiteralPath $profilePath -PathType Container))
    ntuser_dat_exists = $ntuser
    scenario_directory_exists = [bool](Test-Path -LiteralPath $root -PathType Container)
    state_file_exists = [bool]$stateExists
    state_snapshot_matches_learner = [bool]$stateValid
    machine_policy_value = $machineValue
    learner_hive_loaded = $hiveLoaded
    learner_policy_value = $userValue
}
Write-Output ('WSLPE41_STAGE7_AUDIT=' + ($result | ConvertTo-Json -Compress -Depth 3))
"""

BOOL_FIELDS = (
    "learner_exists", "learner_enabled", "profile_registry_exists",
    "profile_directory_exists", "ntuser_dat_exists",
    "scenario_directory_exists", "state_file_exists",
    "state_snapshot_matches_learner", "learner_hive_loaded",
)
POLICY_FIELDS = ("machine_policy_value", "learner_policy_value")


def _journal_state() -> dict:
    journal = STATE_ROOT / INSTANCE / "provided-install.json"
    if journal.is_symlink() or not journal.is_file():
        raise InstallBlocked("Exact blocked scenario7 journal missing or linked")
    st = journal.stat()
    if (st.st_uid != os.geteuid() or st.st_nlink != 1
            or st.st_mode & 0o077 or st.st_size > 250_000):
        raise InstallBlocked("Exact scenario7 journal is not owner-private")
    state = json.loads(journal.read_text(encoding="utf-8"))
    if (state.get("schema") != SCHEMA or state.get("instance") != INSTANCE
            or state.get("status") != "BLOCKED" or state.get("next_stage") != 12
            or state.get("configuration_validated") != 6
            or state.get("inflight") != {"number": 7, "stage": "apply"}):
        raise InstallBlocked("Not the exact blocked scenario7 apply after six validated scenarios")
    proofs = state.get("proofs")
    if (not isinstance(proofs, list) or len(proofs) != 12
            or any(not isinstance(p, dict)
                   or p.get("number") != index // 2 + 1
                   or p.get("stage") != ("apply" if index % 2 == 0 else "validate")
                   or p.get("transport") != "ansible"
                   for index, p in enumerate(proofs))):
        raise InstallBlocked("Expected exact twelve preceding approved runtime proofs")
    if not str(state.get("failure_gate", "")).startswith(
            "Scenario #7 apply: Ansible rc=2; last_task=windows_lpe : Apply AlwaysInstallElevated candidate"):
        raise InstallBlocked("Blocked stage7 failure reason differs from operator evidence")
    return state


def inspect(*, report=print, evidence_out=None) -> dict:
    state = _journal_state()
    report("[PASS] Six validated scenarios; exactly twelve preserved runtime proofs")
    target, _, der, password, _ = existing_management()
    if state.get("vmx") != str(target.vmx):
        raise InstallBlocked("Scenario7 journal VMX does not match exact registered guest")
    auth = management.auth_helper()
    with management.operator_session(auth, der, password) as session:
        result = management.run_powershell(session, SCRIPT)
    if result.status_code != 0:
        raise InstallBlocked("Read-only scenario7 guest inspection failed")
    lines = result.std_out.decode("utf-8-sig", errors="replace").splitlines()
    markers = [line.split("=", 1)[1] for line in lines
               if line.startswith("WSLPE41_STAGE7_AUDIT=")]
    if len(markers) != 1:
        raise InstallBlocked("Missing unique Windows scenario7 read-only evidence")
    evidence = json.loads(markers[0])
    if (evidence.get("schema") != "kingdoms.wslpe41.stage7-readonly.v1"
            or evidence.get("computer", "").upper() != "WSLPE-WS01"
            or any(type(evidence.get(key)) is not bool for key in BOOL_FIELDS)
            or any(evidence.get(key) is not None and (
                type(evidence.get(key)) is not int or evidence.get(key) not in (0, 1))
                for key in POLICY_FIELDS)):
        raise InstallBlocked("Invalid Windows scenario7 audit schema")
    for key in (*BOOL_FIELDS, *POLICY_FIELDS):
        report("[OBSERVED] " + key + "=" + str(evidence[key]))
    if (evidence["scenario_directory_exists"]
            or evidence["state_file_exists"]
            or evidence["machine_policy_value"] == 1
            or evidence["learner_policy_value"] == 1):
        report("[STATE] PARTIAL_OR_PRESENT; no stage replay permitted")
    else:
        report("[STATE] NO_SCENARIO7_POLICY_ARTIFACTS_VISIBLE; profile may still be pre-existing")
    report("[NO CHANGES] Windows, VMware, private credentials and installation journal untouched")
    if evidence_out is not None:
        evidence_out.update(evidence)
    return evidence
