#!/usr/bin/env python3
"""Read-only NORTH WS01 identity and VMware Tools after evaluation reboot.

No VM power transitions, WinRM provisioning, licensing, firewall or network
mutations. Requires the original registered/running guest and independent
authenticated NAT/lab MAC proof before displaying diagnostics.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from goad.course1_direct_winrm import (  # noqa: E402
    EXPECTED, _authenticated_session, owned_guest,
)

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
$adapters = @(Get-NetAdapter -ErrorAction Stop | ForEach-Object {
    $nic = $_
    [PSCustomObject]@{
        Name = $nic.Name
        Mac = (($nic.MacAddress -replace '[:-]', '').ToUpperInvariant())
        Status = [string]$nic.Status
        IPv4 = @(Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty IPAddress)
    }
})
$service = @(Get-CimInstance Win32_Service -Filter "Name='VMTools'" -ErrorAction Stop)
$processes = @(Get-Process vmtoolsd -ErrorAction SilentlyContinue)
$installed = @()
foreach ($key in @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)) {
    $installed += @(Get-ItemProperty $key -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like 'VMware Tools*' } |
        Select-Object -ExpandProperty DisplayName)
}
$events = @(Get-WinEvent -FilterHashtable @{
    LogName = 'System'
    ProviderName = 'Service Control Manager'
    StartTime = (Get-Date).AddHours(-4)
} -MaxEvents 100 -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -match '(?i)VMTools|VMware Tools' } |
    Select-Object -First 8 TimeCreated,Id,Message |
    ForEach-Object {
        [PSCustomObject]@{
            Time = $_.TimeCreated.ToString('o')
            Id = $_.Id
            Message = ([string]$_.Message -replace '[\r\n]+', ' ').Trim()
        }
    })
[PSCustomObject]@{
    Hostname = $env:COMPUTERNAME
    OsCaption = $os.Caption
    LastBoot = $os.LastBootUpTime.ToString('o')
    Adapters = $adapters
    ToolsService = @($service | ForEach-Object {
        [PSCustomObject]@{
            Name = $_.Name
            State = $_.State
            StartMode = $_.StartMode
            PathName = $_.PathName
        }
    })
    ToolsExecutableExists = [bool](Test-Path 'C:\Program Files\VMware\VMware Tools\vmtoolsd.exe')
    ToolsProcessCount = $processes.Count
    InstalledVmwareTools = @($installed)
    RecentServiceEvents = $events
} | ConvertTo-Json -Depth 7 -Compress
"""


# Keep Windows PowerShell -EncodedCommand below the WinRM/CMD.exe length limit.
# pywinrm encodes UTF-16LE to base64, inflating even compact PowerShell by ~2.67x.
# The previously combined 4.4k-character SCRIPT failed before execution with
# "The command line is too long". Do not stage a guest script to work around this:
# all three authenticated calls are read-only and leave no artifacts.
TOOLS_METADATA_SCRIPT = r"""
$ErrorActionPreference='Stop'
$e='C:\Program Files\VMware\VMware Tools\vmtoolsd.exe'
$b=$null
if(Test-Path -LiteralPath $e -PathType Leaf){
$f=Get-Item -LiteralPath $e -ErrorAction Stop
$s=Get-AuthenticodeSignature -LiteralPath $e -ErrorAction SilentlyContinue
$b=[PSCustomObject]@{
Length=$f.Length
Version=$f.VersionInfo.FileVersion
Sha256=(Get-FileHash -LiteralPath $e -Algorithm SHA256 -ErrorAction Stop).Hash
SignatureStatus=if($null -ne $s){[string]$s.Status}else{'Unavailable'}
}
}
[PSCustomObject]@{
ToolsBinaryMetadata=$b
VMToolsServiceRegistryKeyPresent=[bool](Test-Path 'HKLM:\SYSTEM\CurrentControlSet\Services\VMTools')
VGAuthServiceRegistryKeyPresent=[bool](Test-Path 'HKLM:\SYSTEM\CurrentControlSet\Services\VGAuthService')
MsiInstallerInProgressRegistryKeyPresent=[bool](Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\InProgress')
MsiExecProcessCount=@(Get-Process msiexec -ErrorAction SilentlyContinue).Count
}|ConvertTo-Json -Depth 4 -Compress
"""

MSI_EVENTS_SCRIPT = r"""
$ErrorActionPreference='Stop'
$items=@(Get-WinEvent -FilterHashtable @{
LogName='Application'
ProviderName='MsiInstaller'
StartTime=(Get-Date).AddHours(-24)
} -MaxEvents 100 -ErrorAction SilentlyContinue |
Where-Object {$_.Message -match '(?i)vmware|vmtools|vm tools'} |
Select-Object -First 12 | ForEach-Object {
$m=([string]$_.Message -replace '[\r\n]+',' ').Trim()
[PSCustomObject]@{
Time=$_.TimeCreated.ToString('o')
Id=$_.Id
Message=$m.Substring(0,[Math]::Min(600,$m.Length))
}
})
[PSCustomObject]@{RecentVmwareInstallerEvents=@($items)} |
ConvertTo-Json -Depth 5 -Compress
"""


class DiagnosticBlocked(RuntimeError):
    pass


def _read_json_winrm(session, script: str, label: str) -> dict:
    """Read-only query: fail closed on WinRM transport errors or invalid JSON."""
    try:
        reply = session.run_ps(script)
    except Exception as exc:
        raise DiagnosticBlocked(
            label + " WinRM transport failed: " + type(exc).__name__
        ) from exc
    if reply.status_code:
        raise DiagnosticBlocked(
            label + " Windows diagnostics failed: " +
            reply.std_err.decode("utf-8", errors="replace")[:300]
        )
    try:
        result = json.loads(reply.std_out.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise DiagnosticBlocked(label + " diagnostics returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise DiagnosticBlocked(label + " diagnostics returned non-object JSON")
    return result


def parse_winrm_port(output: str) -> int:
    matches = re.findall(
        r"(?m)^\s*5985\s+\(guest\)\s*=>\s*(\d+)\s+\(host\)\s*$",
        output,
    )
    if len(matches) != 1:
        raise DiagnosticBlocked("Expected one original WS01 forwarded WinRM port")
    port = int(matches[0])
    if not 1024 <= port <= 65535:
        raise DiagnosticBlocked("Invalid WS01 forwarded WinRM port")
    return port


def verify_identity(payload: dict, vmx_values: dict) -> None:
    """Never trust a live forwarded Windows endpoint without both guest NIC MACs."""
    adapters = payload.get("Adapters") or []
    if isinstance(adapters, dict):
        adapters = [adapters]
    if not isinstance(adapters, list):
        raise DiagnosticBlocked("Guest adapter inventory is malformed")
    observed = [x.get("Mac") for x in adapters if isinstance(x, dict)]
    expected_nat = vmx_values.get("ethernet0.generatedaddress", "").replace(":", "").upper()
    expected_lab = EXPECTED["GOAD-WS01"].replace(":", "").upper()
    if not (payload.get("Hostname") and
            "Windows" in str(payload.get("OsCaption", "")) and
            re.fullmatch(r"[0-9A-F]{12}", expected_nat) and
            len(observed) == len(adapters) and
            observed.count(expected_nat) == 1 and
            observed.count(expected_lab) == 1 and
            expected_nat != expected_lab):
        raise DiagnosticBlocked(
            "Authenticated forwarded endpoint is not the exact original WS01 "
            "with both VMX-owned NAT and lab NIC MACs"
        )


def classify_tools_state(payload: dict) -> str:
    """Classification is evidence only, not approval to repair Windows."""
    service = payload.get("ToolsService")
    binary = payload.get("ToolsExecutableExists")
    process = payload.get("ToolsProcessCount")
    products = payload.get("InstalledVmwareTools")
    if (not isinstance(service, list) or type(binary) is not bool
            or type(process) is not int or not isinstance(products, list)):
        raise DiagnosticBlocked("Incomplete authenticated Tools inventory")
    if (not service and binary and process == 0 and not products):
        return "ORPHANED_TOOLS_EXECUTABLE"
    if (not service and not binary and process == 0 and not products):
        return "FULLY_MISSING_TOOLS"
    if (len(service) == 1 and isinstance(service[0], dict)
            and service[0].get("Name") == "VMTools"
            and service[0].get("State") == "Running" and binary and process > 0):
        return "HEALTHY"
    return "PARTIAL_OR_AMBIGUOUS_TOOLS"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True,
                        help="Exact pre-Ansible NORTH instance, e.g. 8aafc9-north-vmware")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{6}-north-vmware", args.instance):
        raise DiagnosticBlocked("Not an exact NORTH instance ID")
    provider = ROOT / "workspace" / args.instance / "provider"
    vmx, guest, values = owned_guest(provider, "GOAD-WS01")
    if guest["address"] != "10.4.10.31":
        raise DiagnosticBlocked("Unexpected NORTH WS01 topology")
    result = subprocess.run(
        ["vagrant", "port", "GOAD-WS01"], cwd=provider,
        text=True, capture_output=True, timeout=25, check=False,
    )
    if result.returncode:
        raise DiagnosticBlocked("Cannot read original WS01 Vagrant port mapping")
    port = parse_winrm_port(result.stdout)
    session = _authenticated_session("127.0.0.1", port=port)
    payload = _read_json_winrm(session, SCRIPT, "Original WS01 identity")
    verify_identity(payload, values)
    # Original VMX plus two authenticated guest MAC addresses are proven
    # before querying additional MSI state. No repair permissions are implied.
    metadata = _read_json_winrm(session, TOOLS_METADATA_SCRIPT, "Tools metadata")
    events = _read_json_winrm(session, MSI_EVENTS_SCRIPT, "Windows Installer events")
    if set(metadata) != {
        "ToolsBinaryMetadata", "VMToolsServiceRegistryKeyPresent",
        "VGAuthServiceRegistryKeyPresent",
        "MsiInstallerInProgressRegistryKeyPresent", "MsiExecProcessCount",
    } or set(events) != {"RecentVmwareInstallerEvents"}:
        raise DiagnosticBlocked("Forensic WinRM inventory is incomplete")
    if not isinstance(events["RecentVmwareInstallerEvents"], list):
        raise DiagnosticBlocked("Windows Installer event inventory is malformed")
    payload.update(metadata)
    payload.update(events)
    print("[PASS] NORTH_WS01_REGISTERED_RUNNING_VMX=" + str(vmx))
    print("[PASS] NORTH_WS01_BOTH_AUTHENTICATED_NIC_MACS_MATCH")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print("[INFO] NORTH_WS01_TOOLS_SIGNATURE=" + classify_tools_state(payload))
    service = payload.get("ToolsService") or []
    if not service:
        print("[FAIL] NORTH_WS01_VMTOOLS_SERVICE=ABSENT")
    else:
        print("[INFO] NORTH_WS01_VMTOOLS_SERVICE=" +
              str(service[0].get("State", "unknown")))
    observed_ips = []
    for adapter in payload.get("Adapters") or []:
        observed_ips.extend(adapter.get("IPv4") or [])
    print("[INFO] NORTH_WS01_CANONICAL_IP_PRESENT=" +
          str("10.4.10.31" in observed_ips))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (DiagnosticBlocked, OSError, subprocess.TimeoutExpired) as exc:
        print("[BLOCKED] NORTH WS01 diagnostic: " + str(exc), file=sys.stderr)
        sys.exit(1)
