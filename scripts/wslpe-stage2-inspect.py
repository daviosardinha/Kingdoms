#!/usr/bin/env python3
"""Kingdoms WSLPE Stage 2: READ-ONLY native guest and network acceptance.

Operator-only. No provisioning, reconfiguration, Vagrant up, VM changes,
learner creation or status promotion. Reads the existing WSLPE instance,
registered VMware VMX, port forwarding and Windows security/network state.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workspace"
VMWARE_NET = Path("/etc/vmware/networking")
MACHINE = "WSLPE-WS01"
NORTH = ipaddress.ip_network("10.4.0.0/16")

# This is a query, not a configuration script. No registry writes, new users,
# firewall changes, network configuration or exploit simulation.
WINDOWS_READ_ONLY = r'''
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$machine = Get-CimInstance Win32_ComputerSystem
$uac = Get-ItemPropertyValue -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' -Name EnableLUA
$firewall = @(Get-NetFirewallProfile | Select-Object Name, Enabled)
$defender = Get-MpComputerStatus -ErrorAction Stop
$interfaces = @(Get-NetAdapter | Select-Object Name, InterfaceIndex, MacAddress, Status)
$ipv4 = @(Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' } |
    Select-Object IPAddress, InterfaceIndex, PrefixLength)
$routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' |
    Select-Object InterfaceIndex, NextHop, RouteMetric)
$learner = Get-LocalUser -Name 'lpe.trainee' -ErrorAction SilentlyContinue
$data = @{
    Name = $env:COMPUTERNAME
    ProductType = [int]$os.ProductType
    WindowsVersion = [string]$os.Version
    WindowsBuild = [string]$os.BuildNumber
    DomainJoined = [bool]$machine.PartOfDomain
    UAC = [int]$uac
    Firewall = $firewall
    DefenderService = [bool]$defender.AMServiceEnabled
    DefenderAntivirus = [bool]$defender.AntivirusEnabled
    Interfaces = $interfaces
    IPv4 = $ipv4
    DefaultRoutes = $routes
    LearnerExists = ($null -ne $learner)
}
Write-Output ('WSLPE_AUDIT_JSON=' + ($data | ConvertTo-Json -Compress -Depth 6))
'''


def read_command(command: list[str], *, cwd: Path | None = None, timeout=30) -> str:
    result = subprocess.run(
        command, cwd=str(cwd) if cwd is not None else None,
        capture_output=True, text=True, check=False, timeout=timeout,
    )
    if result.returncode != 0:
        raise ValueError(f"read-only command failed: {command[0]} {command[1:3]}")
    return result.stdout


def find_instance(workspace: Path) -> tuple[Path, dict]:
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("Native Kingdoms workspace missing or symlinked")
    matches = []
    for directory in workspace.iterdir():
        if not directory.is_dir() or directory.is_symlink():
            continue
        manifest = directory / "instance.json"
        if not manifest.is_file() or manifest.is_symlink():
            continue
        try:
            info = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError(f"Unreadable instance manifest: {directory.name}")
        if info.get("lab") == "WSLPE":
            matches.append((directory, info))
    if len(matches) != 1:
        raise ValueError(f"Exactly one native WSLPE instance required, found {len(matches)}")
    directory, info = matches[0]
    if (
        info.get("id") != directory.name
        or info.get("provider") != "vmware"
        or info.get("provisioner") != "local"
        or info.get("status") != "ready for provisioning"
        or info.get("extensions")
    ):
        raise ValueError("WSLPE instance identity, status or provider contract mismatch")
    prefix = info.get("ip_range")
    try:
        network = ipaddress.ip_network(f"{prefix}.0/24", strict=True)
    except (ValueError, TypeError):
        raise ValueError("Native WSLPE instance has invalid network metadata")
    if not network.is_private or network.overlaps(NORTH):
        raise ValueError("WSLPE instance network overlaps restricted ranges")
    return directory, info


def locate_registered_vm(instance_dir: Path) -> Path:
    provider = instance_dir / "provider"
    state = provider / ".vagrant" / "machines" / MACHINE / "vmware_desktop" / "id"
    if not state.is_file() or state.is_symlink():
        raise ValueError("Expected native WSLPE Vagrant registration missing")
    try:
        vmx = Path(state.read_text(encoding="utf-8").strip()).resolve(strict=True)
    except (OSError, ValueError):
        raise ValueError("Native WSLPE VMware VMX registration unreadable")
    if vmx.suffix.lower() != ".vmx" or not vmx.is_file():
        raise ValueError("Registered WSLPE VMware VMX is invalid")
    if "GOAD-" in str(vmx).upper() or "NORTH-VMWARE" in str(vmx).upper():
        raise ValueError("WSLPE points toward a NORTH VM")
    inventory = read_command(["vmrun", "-T", "ws", "list"])
    paths = [Path(line.strip()).resolve() for line in inventory.splitlines()[1:]
             if line.strip()]
    if not inventory.startswith("Total running VMs:") or paths.count(vmx) != 1:
        raise ValueError("Exact registered WSLPE VMX is not uniquely running")
    return vmx


def vmx_network_adapters(vmx_text: str) -> list[dict]:
    adapters: dict[int, dict] = {}
    expression = re.compile(
        r'^\s*ethernet(\d+)\.(present|connectionType|vnet|generatedAddress|address|startConnected)\s*=\s*"([^"]*)"',
        re.IGNORECASE,
    )
    for line in vmx_text.splitlines():
        found = expression.match(line)
        if found:
            number, key, value = found.groups()
            adapters.setdefault(int(number), {})[key.lower()] = value
    result = []
    for number, data in sorted(adapters.items()):
        if data.get("present", "TRUE").upper() == "FALSE":
            continue
        result.append({"index": number,
                       "type": data.get("connectiontype", "unknown").lower(),
                       "vnet": data.get("vnet", ""),
                       "mac": (data.get("generatedaddress") or data.get("address") or "").lower()})
    return result


def forwarded_winrm_port(instance_dir: Path) -> int:
    text = read_command(["vagrant", "port", MACHINE], cwd=instance_dir / "provider")
    match = re.search(r"5985\s+\(guest\)\s+=>\s+(\d+)\s+\(host\)", text)
    if match is None:
        raise ValueError("Loopback-forwarded WinRM 5985 port was not available")
    port = int(match.group(1))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid forwarded WinRM port")
    return port


def inspect_management_port_binding(port: int) -> str:
    """Require forwarded WinRM to listen on loopback, never a public interface."""
    output = read_command(["ss", "-H", "-ltn"])
    listeners = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0] != "LISTEN":
            continue
        endpoint = fields[3]
        try:
            bound_port = int(endpoint.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        if bound_port == port:
            listeners.append(endpoint.rsplit(":", 1)[0].strip("[]"))
    if not listeners:
        raise ValueError("Cannot establish WinRM forwarded port bind scope")
    if any(host not in ("127.0.0.1", "::1") for host in listeners):
        raise ValueError(
            "WSLPE bootstrap WinRM port appears exposed beyond host loopback"
        )
    return ", ".join(sorted(set(listeners)))


def windows_probe(port: int) -> dict:
    try:
        import winrm
    except ImportError:
        raise ValueError("pywinrm missing. Run with Kingdoms' established Python venv")
    user = os.environ.get("KINGDOMS_WSLPE_BOOTSTRAP_USER", "vagrant")
    password = os.environ.get("KINGDOMS_WSLPE_BOOTSTRAP_PASSWORD", "vagrant")
    session = winrm.Session(
        f"http://127.0.0.1:{port}/wsman",
        auth=(user, password), transport="ntlm",
        operation_timeout_sec=30, read_timeout_sec=45,
    )
    try:
        reply = session.run_ps(WINDOWS_READ_ONLY)
    except Exception as exc:
        raise ValueError(f"WinRM read-only query failed: {type(exc).__name__}") from exc
    if reply.status_code != 0:
        raise ValueError("Windows guest refused the read-only security query")
    data = reply.std_out.decode("utf-8", errors="replace")
    marker = "WSLPE_AUDIT_JSON="
    matched = next((line.partition(marker)[2].strip() for line in data.splitlines()
                    if marker in line), None)
    if not matched:
        raise ValueError("Windows guest did not return the expected audit record")
    try:
        return json.loads(matched)
    except ValueError:
        raise ValueError("Windows returned an invalid audit JSON record")


def evaluate_windows(data: dict, prefix: str) -> tuple[list[str], list[str]]:
    good, failed = [], []
    def verify(ok: bool, message: str):
        (good if ok else failed).append(message)
    verify(str(data.get("Name", "")).upper() == MACHINE, "Exact Windows machine identity")
    verify(data.get("ProductType") == 1 and str(data.get("WindowsVersion", "")).startswith("10."),
           "Windows client operating system")
    verify(data.get("DomainJoined") is False, "Not joined to Active Directory")
    verify(data.get("UAC") == 1, "UAC enabled")
    firewalls = data.get("Firewall")
    verify(isinstance(firewalls, list) and len(firewalls) >= 3
           and all(x.get("Enabled") is True for x in firewalls),
           "All Windows firewall profiles enabled")
    verify(data.get("DefenderService") is True and data.get("DefenderAntivirus") is True,
           "Microsoft Defender service and antivirus enabled")
    addresses = data.get("IPv4")
    expected = prefix + ".31"
    entries = [entry for entry in addresses if entry.get("IPAddress") == expected] \
        if isinstance(addresses, list) else []
    verify(len(entries) == 1 and entries[0].get("PrefixLength") == 24,
           f"Guest exercise IPv4 is {expected}/24")
    if entries:
        route = data.get("DefaultRoutes", [])
        if isinstance(route, list):
            verify(not any(x.get("InterfaceIndex") == entries[0].get("InterfaceIndex")
                           for x in route),
                   "No default outbound route over vulnerable exercise NIC")
        else:
            failed.append("Windows default-route evidence unavailable")
    return good, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show-adapters", action="store_true",
                        help="Print non-secret VMware and Windows interface metadata")
    args = parser.parse_args()

    print("KINGDOMS WSLPE | STAGE 2 NATIVE GUEST INSPECTION (READ ONLY)", flush=True)
    print("No Vagrant boot, instance mutation, WinRM configuration or guest provisioning")
    try:
        instance_dir, manifest = find_instance(WORKSPACE)
        prefix = manifest["ip_range"]
        vmx = locate_registered_vm(instance_dir)
        adapters = vmx_network_adapters(vmx.read_text(encoding="utf-8", errors="replace"))
        if len(adapters) < 2:
            raise ValueError("WSLPE VMX does not expose separate management and exercise NICs")
        port = forwarded_winrm_port(instance_dir)
        bind = inspect_management_port_binding(port)
        info = windows_probe(port)
        passed, failed = evaluate_windows(info, prefix)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {exc}")
        print("[NO CHANGES] Existing WSLPE and NORTH instances were not modified")
        return 1

    print(f"[PASS] Native instance: {manifest['id']} | state=PROVIDED (ready for provisioning)")
    print(f"[PASS] Registered VMware guest: {vmx.name}")
    print(f"[PASS] WinRM: read-only query through 127.0.0.1:{port}")
    print(f"[PASS] Bootstrap WinRM forwarded port bound only to loopback ({bind})")
    print(f"[INFO] VMware network adapters discovered: {len(adapters)}")
    if args.show_adapters:
        for a in adapters:
            print(f"  VMX ethernet{a['index']}: type={a['type']} vnet={a['vnet'] or '(implicit)'} MAC={a['mac'] or '(unavailable)'}")
        for a in info.get("Interfaces", []):
            print(f"  Windows interface: {a.get('Name')} index={a.get('InterfaceIndex')} "
                  f"MAC={a.get('MacAddress')} status={a.get('Status')}")
        for a in info.get("IPv4", []):
            print(f"  Windows IPv4: {a.get('IPAddress')}/{a.get('PrefixLength')} "
                  f"interface={a.get('InterfaceIndex')}")
    for name in passed:
        print(f"[PASS] {name}")
    for name in failed:
        print(f"[FAIL] {name}")
    print(f"WSLPE STAGE 2 WINDOWS BASELINE: {len(passed)} PASS / {len(failed)} FAIL")
    print("[NOT VERIFIED] Complete guest NIC-to-vmnet isolation, guest-to-host filtering,")
    print("               student connectivity, local learner and the 20 LPE scenarios")
    print("[NO CHANGES] No VM lifecycle, Windows settings or accounts modified")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
