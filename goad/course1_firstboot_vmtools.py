"""Read-only, original-VMX-bound VMware Tools inventory for NORTH first boot.

A fresh Vagrant Windows guest may have an unconfigured lab IPv4 when its first
adapter provisioner fails. We therefore require both VMX-owned NIC MACs but do
NOT require the canonical lab IPv4 here. Canonical IP, routes and WinRM HTTPS
are still mandatory at the existing post-provision readiness gate.

This module never installs software, restarts services or changes guest state.
"""
from __future__ import annotations

import json
import re

from goad.course1_direct_winrm import EXPECTED, owned_guest


class NorthFirstbootToolsBlocked(RuntimeError):
    """Stop when guest identity or VMware Tools state cannot be proved."""


FIRSTBOOT_INVENTORY = r"""
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
$tools = @(Get-CimInstance Win32_Service -Filter "Name='VMTools'" -ErrorAction Stop)
$processes = @(Get-Process vmtoolsd -ErrorAction SilentlyContinue)
$products = @()
foreach ($key in @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)) {
  $products += @(Get-ItemProperty $key -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -like 'VMware Tools*' } |
    Select-Object -ExpandProperty DisplayName)
}
[PSCustomObject]@{
  Hostname = $env:COMPUTERNAME
  Windows = ($os.Caption -match 'Windows')
  Adapters = $adapters
  ToolsService = @($tools | ForEach-Object {
    [PSCustomObject]@{ Name = $_.Name; State = $_.State }
  })
  ToolsExecutableExists = [bool](Test-Path 'C:\Program Files\VMware\VMware Tools\vmtoolsd.exe')
  ToolsProcessCount = @($processes).Count
  InstalledVmwareTools = @($products)
  InstallerInProgress = [bool](Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\InProgress')
  MsiExecProcessCount = @(Get-Process msiexec -ErrorAction SilentlyContinue).Count
} | ConvertTo-Json -Depth 6 -Compress
"""


def classify_firstboot_inventory(record: dict) -> str:
    """Return healthy/missing/partial; uncertainty is NEVER treated as absent."""
    if not isinstance(record, dict):
        raise NorthFirstbootToolsBlocked("VMware Tools inventory is not an object")
    services = record.get("ToolsService")
    products = record.get("InstalledVmwareTools")
    process_count = record.get("ToolsProcessCount")
    binary = record.get("ToolsExecutableExists")
    installing = record.get("InstallerInProgress")
    msi_count = record.get("MsiExecProcessCount")
    if (not isinstance(services, list) or not isinstance(products, list)
            or type(process_count) is not int or process_count < 0
            or type(binary) is not bool or type(installing) is not bool
            or type(msi_count) is not int or msi_count < 0):
        raise NorthFirstbootToolsBlocked("VMware Tools evidence incomplete")
    if (len(services) == 1 and isinstance(services[0], dict)
            and services[0].get("Name") == "VMTools"
            and services[0].get("State") == "Running"
            and binary and process_count > 0):
        return "healthy"
    if (not services and not products and not binary and process_count == 0
            and not installing and msi_count == 0):
        return "missing"
    return "partial"


def inspect_firstboot_guest_tools(provider, machine, session):
    """Require the exact running VMX, matching NAT/lab MACs and authenticated WinRM.

    Unlike canonical readiness, first boot may not have the lab address yet.
    No software may be installed until this independent identity check succeeds.
    """
    if machine not in EXPECTED:
        raise NorthFirstbootToolsBlocked("Not an original NORTH Windows guest")
    try:
        vmx, _guest, values = owned_guest(provider, machine)
        response = session.run_ps(FIRSTBOOT_INVENTORY)
        if response.status_code != 0:
            raise NorthFirstbootToolsBlocked(
                "Read-only guest inventory failed: " +
                response.std_err.decode("utf-8", errors="replace")[-280:]
            )
        record = json.loads(response.std_out.decode("utf-8"))
    except (ValueError, UnicodeError, OSError, AttributeError) as exc:
        raise NorthFirstbootToolsBlocked(
            "Authenticated Windows VMware Tools inventory unavailable"
        ) from exc
    if not isinstance(record, dict) or record.get("Windows") is not True:
        raise NorthFirstbootToolsBlocked("Authenticated endpoint is not Windows")
    if not isinstance(record.get("Hostname"), str) or not record["Hostname"]:
        raise NorthFirstbootToolsBlocked("Authenticated Windows hostname missing")
    adapters = record.get("Adapters")
    if (not isinstance(adapters, list)
            or any(not isinstance(item, dict)
                   or not isinstance(item.get("Mac"), str)
                   or not isinstance(item.get("IPv4"), list)
                   for item in adapters)):
        raise NorthFirstbootToolsBlocked("Windows NIC inventory malformed")
    macs = [adapter["Mac"].upper() for adapter in adapters]
    nat_mac = values.get("ethernet0.generatedaddress", "").replace(":", "").upper()
    lab_mac = EXPECTED[machine].replace(":", "").upper()
    if (not re.fullmatch(r"[0-9A-F]{12}", nat_mac)
            or nat_mac == lab_mac or macs.count(nat_mac) != 1
            or macs.count(lab_mac) != 1):
        raise NorthFirstbootToolsBlocked(
            "Forwarded WinRM endpoint does not match both original VMX NIC MACs"
        )
    return str(vmx), classify_firstboot_inventory(record)
