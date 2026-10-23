"""Read-only inspection of WSLPE41 blocked first-stage Windows effects.

The exact native VM, accepted pinned TLS and local operator account remain
authoritative. Do not delete, recreate, replay, or reset the blocked journal.
This only reports well-known service/fixture presence; no shell redirection,
VMware mutation, Windows configuration, or credential output.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from kingdoms import wslpe41_operator_management as management
from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_provided_runtime import INSTANCE, existing_management
from kingdoms.wslpe41_provided_install import STATE_ROOT, SCHEMA

SCRIPT = r"""$ErrorActionPreference = 'Stop'
$svc = Get-CimInstance Win32_Service -Filter "Name='KingdomUpdaterSvc'" -ErrorAction Stop
$dir = Test-Path -LiteralPath 'C:\Kingdom LPE\Unquoted Path' -PathType Container
$exe = Test-Path -LiteralPath 'C:\Kingdom LPE\Unquoted Path\Service\KingdomUpdater.exe' -PathType Leaf
$candidate = Test-Path -LiteralPath 'C:\Kingdom LPE\Unquoted.exe'
$valid = ($null -ne $svc -and
    $svc.PathName -ceq 'C:\Kingdom LPE\Unquoted Path\Service\KingdomUpdater.exe' -and
    $svc.StartName -eq 'LocalSystem' -and
    $svc.StartMode -eq 'Auto' -and $exe)
$result = @{
    schema = 'kingdoms.wslpe41.first-stage-readonly.v1'
    computer = $env:COMPUTERNAME
    service_exists = ($null -ne $svc)
    service_matches_expected = [bool]$valid
    scenario_directory_exists = [bool]$dir
    service_executable_exists = [bool]$exe
    candidate_exists = [bool]$candidate
}
Write-Output ('WSLPE41_STAGE1_AUDIT=' + ($result | ConvertTo-Json -Compress))
"""


def inspect(*, report=print, evidence_out=None) -> bool:
    path = STATE_ROOT / INSTANCE / "provided-install.json"
    if path.is_symlink() or not path.is_file():
        raise InstallBlocked("Exact first-stage install journal unavailable")
    st = path.stat()
    if (st.st_uid != os.geteuid() or st.st_nlink != 1
            or st.st_mode & 0o077 or st.st_size > 250_000):
        raise InstallBlocked("First-stage journal is not private and regular")
    state = json.loads(path.read_text(encoding="utf-8"))
    if (state.get("schema") != SCHEMA or state.get("instance") != INSTANCE
            or state.get("status") != "BLOCKED"
            or state.get("next_stage") != 0
            or state.get("configuration_validated") != 0
            or state.get("inflight") != {"number": 1, "stage": "apply"}
            or state.get("proofs") != []):
        raise InstallBlocked("Journal not an exact first-stage blocked apply; no inspection approved")
    report("[PASS] Existing private BLOCKED journal: scenario #1 apply, no validated stage")
    target, _, der, password, _ = existing_management()
    if state.get("vmx") != str(target.vmx):
        raise InstallBlocked("Blocked journal not bound to current exact native VMX")
    auth = management.auth_helper()
    with management.operator_session(auth, der, password) as session:
        result = management.run_powershell(session, SCRIPT)
    if result.status_code != 0:
        raise InstallBlocked("Remote first-stage read-only inspection failed")
    output = result.std_out.decode("utf-8-sig", errors="replace")
    markers = [x.split("=", 1)[1] for x in output.splitlines()
               if x.startswith("WSLPE41_STAGE1_AUDIT=")]
    if len(markers) != 1:
        raise InstallBlocked("Missing unique first-stage read-only evidence")
    obj = json.loads(markers[0])
    if (obj.get("schema") != "kingdoms.wslpe41.first-stage-readonly.v1"
            or obj.get("computer", "").upper() != "WSLPE-WS01"
            or any(type(obj.get(key)) is not bool for key in (
                "service_exists", "service_matches_expected",
                "scenario_directory_exists", "service_executable_exists",
                "candidate_exists"))):
        raise InstallBlocked("Unexpected first-stage evidence schema/host")
    for key in ("service_exists", "service_matches_expected",
                "scenario_directory_exists", "service_executable_exists",
                "candidate_exists"):
        report("[OBSERVED] " + key + "=" + str(obj[key]))
    present = any(obj[k] for k in ("service_exists", "scenario_directory_exists",
                                   "service_executable_exists", "candidate_exists"))
    report("[WINDOWS FIXTURE] " + (
        "PRESENT_NEEDS_VALIDATION" if obj["service_matches_expected"] else
        "PARTIALLY_PRESENT" if present else "ABSENT"))
    if evidence_out is not None:
        evidence_out.update(obj)  # Exact parsed Windows evidence, not a printed marker.
    report("[NO CHANGES] Journal and Windows remain unchanged; no automatic replay")
    return obj["service_matches_expected"]
