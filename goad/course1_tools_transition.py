"""Authenticated, read-only VMTools inventory bound to an original NORTH VMX.

The first-boot WinRM identity helper requires Tools to exist. This inventory
deliberately does not: it can prove that the exact Windows guest is missing
Tools before a tightly scoped installer is allowed. No state is changed here.
"""
from __future__ import annotations

import json
import re

from goad.course1_direct_winrm import EXPECTED, owned_guest


class NorthToolsTransitionBlocked(RuntimeError):
    pass


SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
$adapters = @(Get-NetAdapter -ErrorAction Stop | ForEach-Object {
    $nic = $_
    [PSCustomObject]@{
        Mac = (($nic.MacAddress -replace '[:-]', '').ToUpperInvariant())
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
[PSCustomObject]@{
    Hostname = $env:COMPUTERNAME
    Windows = ($os.Caption -match 'Windows')
    Adapters = $adapters
    ToolsService = @($service | ForEach-Object {
        [PSCustomObject]@{ Name = $_.Name; State = $_.State }
    })
    ToolsExecutableExists = [bool](Test-Path 'C:\Program Files\VMware\VMware Tools\vmtoolsd.exe')
    ToolsProcessCount = $processes.Count
    InstalledVmwareTools = @($installed)
} | ConvertTo-Json -Depth 5 -Compress
"""


def inspect_owned_guest_tools(provider_path, machine, session):
    """Return (original_vmx, 'healthy'|'missing'|'partial') or refuse identity.

    Missing requires service, exe, process and registry product ALL absent.
    Healthy requires registered RUNNING VMTools, executable and process; the
    installed-product list may be empty on some otherwise healthy guests.
    A partial installation must never be reinstalled automatically.
    """
    if machine not in EXPECTED:
        raise NorthToolsTransitionBlocked("Not a NORTH Windows guest")
    vmx, guest, vmx_values = owned_guest(provider_path, machine)
    try:
        response = session.run_ps(SCRIPT)
        if response.status_code != 0:
            raise NorthToolsTransitionBlocked(
                "Windows Tools inventory failed: " +
                response.std_err.decode("utf-8", errors="replace")[-250:]
            )
        data = json.loads(response.std_out.decode("utf-8"))
    except (UnicodeError, ValueError, AttributeError, OSError) as exc:
        raise NorthToolsTransitionBlocked("Authenticated Tools inventory unreadable") from exc
    if not isinstance(data, dict):
        raise NorthToolsTransitionBlocked("Windows Tools inventory malformed")

    adapters = data.get("Adapters")
    if not isinstance(adapters, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("Mac"), str)
            or not isinstance(item.get("IPv4"), list) for item in adapters):
        raise NorthToolsTransitionBlocked("Authenticated Windows NIC inventory malformed")
    macs = [item["Mac"] for item in adapters]
    nat_mac = vmx_values.get("ethernet0.generatedaddress", "").replace(":", "").upper()
    lab_mac = EXPECTED[machine].replace(":", "").upper()
    matched_lab = [item for item in adapters if item["Mac"] == lab_mac]
    if (data.get("Windows") is not True or not data.get("Hostname")
            or not re.fullmatch(r"[0-9A-F]{12}", nat_mac)
            or nat_mac == lab_mac or macs.count(nat_mac) != 1
            or macs.count(lab_mac) != 1 or len(matched_lab) != 1
            or matched_lab[0]["IPv4"] != [guest["address"]]):
        raise NorthToolsTransitionBlocked(
            "Authenticated endpoint is not original running NORTH " + machine +
            " with both VMX-owned NIC MACs and canonical lab IPv4"
        )

    services = data.get("ToolsService")
    products = data.get("InstalledVmwareTools")
    process_count = data.get("ToolsProcessCount")
    binary = data.get("ToolsExecutableExists")
    if (not isinstance(services, list) or not isinstance(products, list)
            or type(process_count) is not int or type(binary) is not bool):
        raise NorthToolsTransitionBlocked("VMware Tools evidence incomplete")
    if (not services and not products and process_count == 0 and binary is False):
        return str(vmx), "missing"
    if (len(services) == 1 and isinstance(services[0], dict)
            and services[0].get("Name") == "VMTools"
            and services[0].get("State") == "Running"
            and binary and process_count > 0):
        return str(vmx), "healthy"
    return str(vmx), "partial"


# Exact binary from authenticated NORTH WS01 2026-10-25 forensic evidence.
# No broad "partial Tools" repair: new image versions require explicit review.
WS01_ORPHAN_SHA256 = "33F934D107F430452EED263EB8266C75C2DE68EA8AD310EBF09B245ACD1CEEE7"
WS01_ORPHAN_LENGTH = 110512
WS01_ORPHAN_VERSION = "13.1.0.0"

WS01_ORPHAN_PROOF = r"""
$ErrorActionPreference='Stop'
$e='C:\Program Files\VMware\VMware Tools\vmtoolsd.exe'
if(-not(Test-Path -LiteralPath $e -PathType Leaf)){throw 'No VMware binary'}
$f=Get-Item -LiteralPath $e -ErrorAction Stop
$s=Get-AuthenticodeSignature -LiteralPath $e -ErrorAction Stop
[PSCustomObject]@{
Length=$f.Length
Version=$f.VersionInfo.FileVersion
Sha256=(Get-FileHash -LiteralPath $e -Algorithm SHA256 -ErrorAction Stop).Hash
SignatureStatus=[string]$s.Status
VMToolsServiceRegistryKeyPresent=[bool](Test-Path 'HKLM:\SYSTEM\CurrentControlSet\Services\VMTools')
VGAuthServiceRegistryKeyPresent=[bool](Test-Path 'HKLM:\SYSTEM\CurrentControlSet\Services\VGAuthService')
MsiInstallerInProgressRegistryKeyPresent=[bool](Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\InProgress')
MsiExecProcessCount=@(Get-Process msiexec -ErrorAction SilentlyContinue).Count
}|ConvertTo-Json -Depth 4 -Compress
"""


def _is_known_idle_signed_ws01_orphan(record):
    """Strict, literal fingerprint. The return value does not mutate Windows."""
    return (
        isinstance(record, dict)
        and set(record) == {
            "Length", "Version", "Sha256", "SignatureStatus",
            "VMToolsServiceRegistryKeyPresent", "VGAuthServiceRegistryKeyPresent",
            "MsiInstallerInProgressRegistryKeyPresent", "MsiExecProcessCount",
        }
        and type(record["Length"]) is int and record["Length"] == WS01_ORPHAN_LENGTH
        and record["Version"] == WS01_ORPHAN_VERSION
        and record["Sha256"] == WS01_ORPHAN_SHA256
        and record["SignatureStatus"] == "Valid"
        and record["VMToolsServiceRegistryKeyPresent"] is False
        and record["VGAuthServiceRegistryKeyPresent"] is True
        and record["MsiInstallerInProgressRegistryKeyPresent"] is False
        and type(record["MsiExecProcessCount"]) is int
        and record["MsiExecProcessCount"] == 0
    )


def prove_idle_signed_original_ws01_orphan(provider_path, machine, original_vmx, session):
    """Prove exact WS01 is an idle, *known* interrupted Tools install.

    Caller must have separately proven canonical WinRM, both NIC MACs,
    empty Tools service/process/product registration, and rechecked partial
    convergence. This repeats original registered/running VMX verification
    before accepting any installer-recovery authorization.
    """
    if machine != "GOAD-WS01":
        raise NorthToolsTransitionBlocked("Orphaned Tools rule is WS01-only")
    vmx, topology, settings = owned_guest(provider_path, machine)
    if str(vmx) != original_vmx or topology.get("address") != "10.4.10.31":
        raise NorthToolsTransitionBlocked("Original WS01 VMX or topology changed")
    try:
        result = session.run_ps(WS01_ORPHAN_PROOF)
    except Exception as exc:
        raise NorthToolsTransitionBlocked("Orphan Tools WinRM proof unavailable") from exc
    if result.status_code != 0:
        raise NorthToolsTransitionBlocked(
            "Orphan Tools read-only proof failed: " +
            result.std_err.decode("utf-8", errors="replace")[-200:]
        )
    try:
        record = json.loads(result.std_out.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise NorthToolsTransitionBlocked("Orphan Tools evidence is not JSON") from exc
    return _is_known_idle_signed_ws01_orphan(record)
