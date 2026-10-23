"""One-time reconciliation of an already installed JEA #30 on the exact WSLPE41 guest.

The local VMware-console witness records EXISTING_VERIFIED, never Apply.
Kali independently checks that record over pinned TLS and authenticates a fresh
nonadmin learner JEA Status session before migrating the private stage journal.
There is no guest registration/reset or prior-stage replay in this module.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from kingdoms import wslpe41_provided_install as provided
from kingdoms import wslpe41_operator_management as management
from kingdoms.wslpe41_fresh_contract import fresh_scenario_manifest
from kingdoms.wslpe41_install_flow import InstallBlocked, StageProof, checkpoint, private_instance_directory, verify_stage
from kingdoms.wslpe41_provided_runtime import INSTANCE, ROOT, existing_management

RECEIPT = r"C:\ProgramData\KingdomsWSLPE45\lib\WSLPE41-JEA30-existing-receipt.json"
NAMES = ("WslpeFixture.psm1", "WslpeJeaLocal.psm1", "WslpeJea.psm1")
SCHEMA = "kingdoms.wslpe41.jea30.existing-verified.v1"
MARKER = "WSLPE41_JEA30_EXISTING_ATTEST="


def source_hashes() -> dict[str, str]:
    root = ROOT / "ansible/files/wslpe45"
    hashes = {}
    for name in NAMES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 250_000:
            raise InstallBlocked("Exact committed JEA source module is missing or unsafe")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    return hashes


def _journal_preflight(context, state: dict) -> None:
    stages = provided._stages(context)
    if (state.get("schema") != provided.SCHEMA or state.get("instance") != INSTANCE
            or state.get("vmx") != context.identity.vmx
            or state.get("status") != "WAITING_CONSOLE_JEA"
            or state.get("next_stage") != 57
            or state.get("configuration_validated") != 28
            or state.get("inflight") is not None
            or not re.fullmatch(r"[0-9a-f]{32}", str(state.get("jea_nonce", "")))
            or not re.fullmatch(r"[0-9a-f]{40}", str(state.get("source_commit", "")))
            or len(stages) != 83
            or stages[57].number != 30 or stages[57].stage != "activate"
            or stages[57].transport != "guest_console"
            or stages[58].number != 30 or stages[58].stage != "validate"):
        raise InstallBlocked("Not the exact paused JEA #30 installation journal")
    proofs = state.get("proofs")
    if (not isinstance(proofs, list) or len(proofs) != 57
            or any(not isinstance(item, dict)
                   or item.get("number") != stages[i].number
                   or item.get("stage") != stages[i].stage
                   or item.get("transport") != "ansible"
                   or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", str(item.get("evidence_id", "")))
                   for i, item in enumerate(proofs))):
        raise InstallBlocked("Original 57 stage proofs do not match the canonical sequence")
    old = state["source_commit"]
    current = context.identity.source_commit
    if old != current:
        cmd = subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", old, current],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=15, check=False,
        )
        if cmd.returncode:
            raise InstallBlocked("Journal source commit is not an ancestor of the reviewed source")


def console_command(nonce: str, commit: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", nonce) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise InstallBlocked("Invalid console handoff nonce or source commit")
    return r"""$ErrorActionPreference = 'Stop'
$Lib = 'C:\ProgramData\KingdomsWSLPE45\lib'
$Receipt = 'C:\ProgramData\KingdomsWSLPE45\lib\WSLPE41-JEA30-existing-receipt.json'
if (Test-Path -LiteralPath $Receipt) { throw 'Existing verification receipt present; do not overwrite' }
if (Test-Path -LiteralPath (Join-Path $Lib 'WSLPE41-JEA30-receipt.json')) {
    throw 'An original Apply receipt already exists; investigate rather than reconcile'
}
foreach ($Name in @('WslpeFixture.psm1','WslpeJeaLocal.psm1','WslpeJea.psm1')) {
    Import-Module (Join-Path $Lib $Name) -Global -Force -ErrorAction Stop
}
Assert-Wslpe45JeaConsole
$null = Assert-Wslpe45OwnedFixture -Number 30 -Id 'jea_role_capability_misconfig'
$Inspect = @(Invoke-Wslpe45JeaLocal -Action Inspect)
$Validate = @(Invoke-Wslpe45Jea -Action validate -Stage vulnerable)
if ($Inspect -cnotcontains 'WSLPE45_JEA_LOCAL_INSPECTION=PASS' -or
    $Validate -cnotcontains 'WSLPE45_BATCH_STAGE=jea_role_capability_misconfig:vulnerable:PASS') {
    throw 'Existing JEA inspection or configuration failed'
}
$Config = 'C:\ProgramData\KingdomsWSLPE45\fixtures\jea_role_capability_misconfig\Kingdoms45JEA.pssc'
if (-not (Test-PSSessionConfigurationFile -Path $Config) -or
    @(Get-PSSessionConfiguration -Name Kingdoms45JEA -ErrorAction Stop).Count -ne 1 -or
    (Get-Service WinRM -ErrorAction Stop).Status -ne 'Running' -or
    @(Get-NetTCPConnection -LocalPort 5986 -State Listen -ErrorAction SilentlyContinue).Count -eq 0) {
    throw 'Existing JEA session or management path is not healthy'
}
$Hashes = @{}
foreach ($Name in @('WslpeFixture.psm1','WslpeJeaLocal.psm1','WslpeJea.psm1')) {
    $Hashes[$Name] = (Get-FileHash -LiteralPath (Join-Path $Lib $Name) -Algorithm SHA256).Hash
}
$Record = @{
    schema = 'kingdoms.wslpe41.jea30.existing-verified.v1'
    nonce = '""" + nonce + r"""'
    source_commit = '""" + commit + r"""'
    machine = $env:COMPUTERNAME
    console_session = [Diagnostics.Process]::GetCurrentProcess().SessionId
    principal = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    mode = 'EXISTING_VERIFIED'
    inspection = 'WSLPE45_JEA_LOCAL_INSPECTION=PASS'
    validation = 'WSLPE45_BATCH_STAGE=jea_role_capability_misconfig:vulnerable:PASS'
    module_hashes = $Hashes
    observed_utc = [DateTime]::UtcNow.ToString('o')
}
$Record | ConvertTo-Json -Compress -Depth 4 |
    Set-Content -LiteralPath $Receipt -Encoding UTF8 -NoNewline -ErrorAction Stop
$Acl = New-Object System.Security.AccessControl.FileSecurity
$Acl.SetAccessRuleProtection($true, $false)
foreach ($SidText in @('S-1-5-18','S-1-5-32-544')) {
    $Sid = New-Object System.Security.Principal.SecurityIdentifier($SidText)
    $Rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $Sid,[System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $null = $Acl.AddAccessRule($Rule)
}
Set-Acl -LiteralPath $Receipt -AclObject $Acl -ErrorAction Stop
Assert-Wslpe45JeaConsole
Write-Output 'WSLPE41_JEA30_EXISTING_CONSOLE=PASS'
"""


def plan() -> str:
    """Inspect only the exact private journal and render a guest-console script."""
    folder = provided.STATE_ROOT / INSTANCE
    path = folder / "provided-install.json"
    if path.is_symlink() or not path.is_file():
        raise InstallBlocked("Existing JEA handoff journal absent or linked")
    state = json.loads(path.read_text(encoding="utf-8"))
    context, _, _ = provided._preflight()
    _journal_preflight(context, state)
    return console_command(state["jea_nonce"], context.identity.source_commit)


def _remote_script(nonce: str, commit: str, hashes: dict[str, str]) -> str:
    expected = "\n".join("  '" + name + "' = '" + hashes[name] + "'" for name in NAMES)
    return r"""$ErrorActionPreference = 'Stop'
$Path = 'C:\ProgramData\KingdomsWSLPE45\lib\WSLPE41-JEA30-existing-receipt.json'
$Item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
if ($Item.PSIsContainer -or ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
    $Item.Length -gt 5000) { throw 'Untrusted existing-console receipt path' }
$Acl = Get-Acl -LiteralPath $Path -ErrorAction Stop
if (-not $Acl.AreAccessRulesProtected) { throw 'Receipt ACL still inheriting' }
foreach ($Ace in $Acl.Access) {
    $Sid = $Ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
    if ($Ace.AccessControlType -eq 'Allow' -and
        $Sid -notin @('S-1-5-18','S-1-5-32-544')) { throw 'Untrusted receipt ACL' }
}
$Receipt = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$Expected = @{
""" + expected + r"""
}
if ($Receipt.schema -cne 'kingdoms.wslpe41.jea30.existing-verified.v1' -or
    $Receipt.nonce -cne '""" + nonce + r"""' -or
    $Receipt.source_commit -cne '""" + commit + r"""' -or
    $Receipt.machine -cne 'WSLPE-WS01' -or
    $Receipt.mode -cne 'EXISTING_VERIFIED' -or
    [int]$Receipt.console_session -lt 1 -or
    $Receipt.inspection -cne 'WSLPE45_JEA_LOCAL_INSPECTION=PASS' -or
    $Receipt.validation -cne 'WSLPE45_BATCH_STAGE=jea_role_capability_misconfig:vulnerable:PASS') {
    throw 'Existing-console receipt does not match installation'
}
foreach ($Name in @('WslpeFixture.psm1','WslpeJeaLocal.psm1','WslpeJea.psm1')) {
    $ModulePath = Join-Path 'C:\ProgramData\KingdomsWSLPE45\lib' $Name
    $File = Get-Item -LiteralPath $ModulePath -Force -ErrorAction Stop
    if ($File.PSIsContainer -or ($File.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Invalid privileged JEA module path'
    }
    $Hash = (Get-FileHash -LiteralPath $ModulePath -Algorithm SHA256 -ErrorAction Stop).Hash
    if ($Hash -cne $Expected[$Name] -or $Receipt.module_hashes.$Name -cne $Hash) {
        throw 'Existing-console module does not match source'
    }
}
$Fixture = 'C:\ProgramData\KingdomsWSLPE45\fixtures\jea_role_capability_misconfig'
$Owner = Get-Content -LiteralPath (Join-Path $Fixture '.kingdoms-owned.json') -Raw -ErrorAction Stop |
    ConvertFrom-Json -ErrorAction Stop
if ($Owner.schema -cne 'kingdoms.wslpe.fixture-owner.v1' -or
    $Owner.machine -cne 'WSLPE-WS01' -or
    [int]$Owner.number -ne 30 -or
    $Owner.id -cne 'jea_role_capability_misconfig') {
    throw 'JEA fixture does not have exact existing ownership'
}
$MarkerPath = Join-Path $env:ProgramFiles 'WindowsPowerShell\Modules\Kingdoms45JEA\.kingdoms45-owner.txt'
if ((Get-Content -LiteralPath $MarkerPath -Raw -ErrorAction Stop).Trim() -cne
    'WSLPE45:30:jea_role_capability_misconfig') { throw 'JEA module ownership differs' }
$Config = Join-Path $Fixture 'Kingdoms45JEA.pssc'
if (-not (Test-PSSessionConfigurationFile -Path $Config) -or
    @(Get-PSSessionConfiguration -Name Kingdoms45JEA -ErrorAction Stop).Count -ne 1 -or
    (Get-Service WinRM -ErrorAction Stop).Status -ne 'Running' -or
    @(Get-NetTCPConnection -LocalPort 5986 -State Listen -ErrorAction SilentlyContinue).Count -eq 0) {
    throw 'Existing JEA is not currently ready'
}
$Result = @{
    schema='kingdoms.wslpe41.jea30.remote-existing-attest.v1'
    receipt_sha256=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    machine=$env:COMPUTERNAME
    existing_verified=$true
}
Write-Output ('WSLPE41_JEA30_EXISTING_ATTEST=' + ($Result | ConvertTo-Json -Compress))
"""


def remote_attestation(context, nonce: str, commit: str, hashes: dict[str, str]) -> str:
    target, _, certificate, operator, _ = existing_management()
    if str(target.vmx) != context.identity.vmx:
        raise InstallBlocked("Pinned operator transport VMX changed")
    auth = management.auth_helper()
    with management.operator_session(auth, certificate, operator) as session:
        result = management.run_powershell(session, _remote_script(nonce, commit, hashes))
    if result.status_code != 0 or len(result.std_out) > 30000:
        raise InstallBlocked("Pinned HTTPS existing JEA attestation failed")
    output = result.std_out.decode("utf-8-sig", errors="replace")
    markers = [line[len(MARKER):] for line in output.splitlines() if line.startswith(MARKER)]
    if len(markers) != 1:
        raise InstallBlocked("Expected exactly one remote existing JEA attestation")
    record = json.loads(markers[0])
    digest = record.get("receipt_sha256")
    if (record.get("schema") != "kingdoms.wslpe41.jea30.remote-existing-attest.v1"
            or record.get("machine") != "WSLPE-WS01"
            or record.get("existing_verified") is not True
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9A-F]{64}", digest)):
        raise InstallBlocked("Existing JEA attestation identity or digest differs")
    return digest


def reconcile() -> str:
    context, operator, learner = provided._preflight()
    folder = private_instance_directory(provided.STATE_ROOT, INSTANCE)
    journal = folder / "provided-install.json"
    archive = folder / "provided-install.before-existing-jea30.json"
    intent = folder / "jea30-existing-reconciliation-intent.json"
    lock = os.open(folder / ".install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if archive.exists() or archive.is_symlink() or intent.exists() or intent.is_symlink():
            raise InstallBlocked("Prior JEA #30 existing-reconciliation attempt or interruption")
        if journal.is_symlink() or not journal.is_file():
            raise InstallBlocked("Exact installation journal missing or linked")
        info = journal.stat()
        if (info.st_uid != os.geteuid() or info.st_mode & 0o077 or
                info.st_nlink != 1 or info.st_size > 250_000):
            raise InstallBlocked("Private installation journal ownership unsafe")
        original = journal.read_bytes()
        state = json.loads(original)
        _journal_preflight(context, state)
        hashes = source_hashes()
        digest = remote_attestation(context, state["jea_nonce"], context.identity.source_commit, hashes)
        # Independent fresh learner Status, not a local administrator assertion.
        scenario = next(row for row in fresh_scenario_manifest() if row.number == 30)
        with provided.private_environment(context, operator, learner):
            learner_proof = provided.run_ansible_stage(context, scenario, "validate")
        verify_stage(scenario, "validate", learner_proof)
        evidence = hashlib.sha256(
            (context.identity.instance_id + "|" + context.identity.vmx + "|" +
             state["jea_nonce"] + "|" + digest + "|" +
             learner_proof.evidence_id).encode("utf-8")
        ).hexdigest()[:32]
        proof = StageProof(30, "activate", "guest_console",
                           "wslpe41.30.activate." + evidence, True)
        verify_stage(scenario, "activate", proof)
        new = dict(state)
        new["source_commit"] = context.identity.source_commit
        new["status"] = "JEA30_EXISTING_VERIFIED"
        new["next_stage"] = 58
        new["inflight"] = None
        new["proofs"] = [*state["proofs"], {
            "number": 30, "stage": "activate", "transport": "guest_console",
            "evidence_id": proof.evidence_id, "method": "EXISTING_VERIFIED",
        }]
        new["jea30_existing_reconciliation"] = {
            "kind": "EXISTING_VERIFIED_NOT_APPLY",
            "original_journal_sha256": hashlib.sha256(original).hexdigest(),
            "previous_source_commit": state["source_commit"],
            "current_source_commit": context.identity.source_commit,
            "console_receipt_sha256": digest,
            "module_sha256": hashes,
            "learner_status_evidence_id": learner_proof.evidence_id,
            "previous_stage_proofs": 57,
            "previous_configuration_validated": 28,
        }
        fd = os.open(intent, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(new["jea30_existing_reconciliation"], sort_keys=True).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(journal, archive)
        checkpoint(journal, new)
        print("[PASS] Existing JEA #30 console receipt, module hashes, owner and HTTPS verified")
        print("[PASS] Fresh lpe.trainee JEA Status checked independently")
        print("[ARCHIVED] All 57 original stage proofs preserved, source migration recorded")
        print("[READY] Stage 58/83 is reconciled as EXISTING_VERIFIED, not Apply")
        print("[NEXT] Run provided-install.py --resume only after reviewing this checkpoint")
        return "RECONCILED"
    finally:
        os.close(lock)


def reverify(context, state: dict) -> None:
    """Fail closed before resuming any new scenario after a reconciled JEA."""
    rec = state.get("jea30_existing_reconciliation")
    if (state.get("status") != "JEA30_EXISTING_VERIFIED"
            or state.get("next_stage") != 58 or state.get("inflight") is not None
            or not isinstance(rec, dict)
            or rec.get("kind") != "EXISTING_VERIFIED_NOT_APPLY"
            or rec.get("previous_stage_proofs") != 57
            or not re.fullmatch(r"[0-9A-F]{64}", str(rec.get("console_receipt_sha256", "")))
            or len(state.get("proofs", [])) != 58
            or state["proofs"][57].get("method") != "EXISTING_VERIFIED"):
        raise InstallBlocked("Reviewed JEA #30 existing reconciliation state missing")
    if source_hashes() != rec.get("module_sha256"):
        raise InstallBlocked("Privileged JEA module source changed after reconciliation")
    if remote_attestation(context, state["jea_nonce"], context.identity.source_commit,
                          source_hashes()) != rec["console_receipt_sha256"]:
        raise InstallBlocked("Existing JEA receipt changed after reconciliation")
