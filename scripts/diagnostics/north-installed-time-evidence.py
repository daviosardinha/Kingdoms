#!/usr/bin/env python3
"""Read-only NORTH cold-start W32Time evidence; no VM or network modifications.

Use the KINGDOMS managed venv Python interpreter (pywinrm).
"""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "winterfell": ("GOAD-DC02", "10.4.10.11"),
    "castelblack": ("GOAD-SRV02", "10.4.10.22"),
}

POWERSHELL = r"""
$ErrorActionPreference='Continue'
Write-Output '==== CLOCK ===='
Get-Date -Format o
Write-Output '==== DOMAIN SECURE CHANNEL ===='
nltest.exe /sc_query:north.sevenkingdoms.local
Write-Output '==== WINDOWS TIME SERVICE ===='
Get-Service W32Time | Format-List Status,StartType
Write-Output '==== SOURCE ===='
w32tm.exe /query /source
Write-Output '==== PEERS ===='
w32tm.exe /query /peers /verbose
Write-Output '==== STATUS ===='
w32tm.exe /query /status /verbose
Write-Output '==== EFFECTIVE CONFIGURATION ===='
w32tm.exe /query /configuration
Write-Output '==== LOCAL UDP 123 ENDPOINTS ===='
Get-NetUDPEndpoint -LocalPort 123 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
Write-Output '==== SYSTEM TIME-SERVICE EVENTS (6H) ===='
Get-WinEvent -FilterHashtable @{
 LogName='System'
 ProviderName='Microsoft-Windows-Time-Service'
 StartTime=(Get-Date).AddHours(-6)
} -MaxEvents 25 -ErrorAction SilentlyContinue |
  Select-Object TimeCreated,Id,LevelDisplayName,Message | Format-List
Write-Output '==== OPERATIONAL TIME-SERVICE EVENTS (6H) ===='
Get-WinEvent -LogName 'Microsoft-Windows-Time-Service/Operational' -MaxEvents 40 -ErrorAction SilentlyContinue |
 Where-Object { $_.TimeCreated -ge (Get-Date).AddHours(-6) } |
 Select-Object TimeCreated,Id,LevelDisplayName,Message | Format-List
"""


def assert_instance(instance_id):
    if not re.fullmatch(r"[a-f0-9]{6}-north-vmware", instance_id):
        raise ValueError("Invalid exact NORTH instance ID")
    base = ROOT / "workspace" / instance_id
    provider = base / "provider"
    mode = provider / ".goad-nomad-mode"
    meta = base / "instance.json"
    if any(p.is_symlink() for p in (base, provider, meta, mode)):
        raise ValueError("Refusing symbolic link in provider identity")
    if not provider.is_dir() or not meta.is_file() or not mode.is_file():
        raise ValueError("NORTH instance or runtime mode absent")
    info = json.loads(meta.read_text(encoding="utf-8"))
    if tuple(info.get(k) for k in ("id", "lab", "provider", "status")) != (
        instance_id, "NORTH", "vmware", "installed"
    ) or mode.read_text(encoding="utf-8").strip() != "exercise":
        raise ValueError("Instance is not installed NORTH in recorded exercise mode")
    registrations = {}
    for label, (guest, _) in TARGETS.items():
        ident = provider / ".vagrant" / "machines" / guest / "vmware_desktop" / "id"
        if ident.is_symlink() or not ident.is_file():
            raise ValueError(f"Missing trusted VMware registration: {guest}")
        vmx = Path(ident.read_text(encoding="utf-8").strip())
        if (vmx.is_symlink() or not vmx.is_file()
                or not vmx.resolve().is_relative_to(ident.parent.resolve())):
            raise ValueError(f"Unsafe registered guest VMX: {guest}")
        registrations[label] = str(vmx.resolve())
    inventory = subprocess.run(
        ["vmrun", "-T", "ws", "list"], capture_output=True,
        text=True, check=False, timeout=20,
    )
    if inventory.returncode or not inventory.stdout.startswith("Total running VMs:"):
        raise ValueError("Cannot prove exact VMware running inventory")
    running = {str(Path(x).resolve()) for x in inventory.stdout.splitlines()[1:]}
    for name, vmx in registrations.items():
        if vmx not in running:
            raise ValueError(f"{name} is powered off; no auto-start attempted")


def capture(instance_id):
    assert_instance(instance_id)
    # Avoid a second Windows command-line length failure in diagnostics.
    encoded_length = len(base64.b64encode(POWERSHELL.encode("utf-16le")))
    if encoded_length > 6500:
        raise ValueError(f"Diagnostic encoded command too large: {encoded_length}")
    from goad.provider.vagrant.vmware_nomad import GoadNomadVmwareProvider

    parent = Path.home() / "Kingdoms-evidence"
    if parent.is_symlink():
        raise ValueError("Evidence directory is a symlink")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = parent / (
        f"north-w32time-{instance_id}-" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    dest.mkdir(mode=0o700, exist_ok=False)
    print(f"[EVIDENCE] {dest}", flush=True)
    failed = False
    for name, (_, ip) in TARGETS.items():
        target = dest / f"{name}.txt"
        try:
            session = GoadNomadVmwareProvider._lab_winrm_session(ip)
            result = session.run_ps(POWERSHELL)
            target.write_text(
                f"host={name} ip={ip} exit={result.status_code}\n" +
                result.std_out.decode(errors="replace") +
                "\nSTDERR:\n" + result.std_err.decode(errors="replace"),
                encoding="utf-8",
            )
            if result.status_code:
                failed = True
                print(f"[FAIL] {name} WinRM exit={result.status_code}: {target}")
            else:
                print(f"[PASS] {name} evidence: {target}")
        except Exception as exc:
            failed = True
            target.write_text(
                f"[UNAVAILABLE] {type(exc).__name__}: {exc}\n",
                encoding="utf-8",
            )
            print(f"[UNAVAILABLE] {name}: {type(exc).__name__}: {exc}")
    print(f"[EVIDENCE] {dest}")
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    args = parser.parse_args()
    try:
        return capture(args.instance)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
