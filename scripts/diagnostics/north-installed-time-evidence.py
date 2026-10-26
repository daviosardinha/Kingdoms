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
import warnings

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
Write-Output '==== SYSTEM TIME-SERVICE EVENTS (24H) ===='
Get-WinEvent -FilterHashtable @{
 LogName='System'
 ProviderName='Microsoft-Windows-Time-Service'
 StartTime=(Get-Date).AddHours(-24)
} -MaxEvents 100 -ErrorAction SilentlyContinue |
  Select-Object TimeCreated,Id,LevelDisplayName,Message | Format-List
Write-Output '==== OPERATIONAL TIME-SERVICE EVENTS (24H) ===='
Get-WinEvent -LogName 'Microsoft-Windows-Time-Service/Operational' -MaxEvents 200 -ErrorAction SilentlyContinue |
 Where-Object { $_.TimeCreated -ge (Get-Date).AddHours(-24) } |
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


# A WinRM request may exit zero while individual non-terminating PowerShell
# errors remain in stderr or pywinrm's XML-decoding warnings. Such evidence is
# valuable but cannot be labeled a complete diagnostic.
REQUIRED_SECTIONS = (
    "==== CLOCK ====",
    "==== DOMAIN SECURE CHANNEL ====",
    "==== WINDOWS TIME SERVICE ====",
    "==== SOURCE ====",
    "==== PEERS ====",
    "==== STATUS ====",
    "==== EFFECTIVE CONFIGURATION ====",
    "==== SYSTEM TIME-SERVICE EVENTS (24H) ====",
    "==== OPERATIONAL TIME-SERVICE EVENTS (24H) ====",
)


def evidence_problems(status_code, stdout, stderr, warning_messages):
    problems = []
    if status_code != 0:
        problems.append(f"PowerShell exit={status_code}")
    if stderr.strip():
        problems.append("PowerShell stderr is nonempty")
    if warning_messages:
        problems.append("pywinrm emitted parsing/runtime warnings")
    for heading in REQUIRED_SECTIONS:
        if heading not in stdout:
            problems.append(f"Missing diagnostic section: {heading}")
    # The source, peers and status sections must contain actual observations,
    # not merely the section labels generated before a failing command.
    for heading, next_heading in (
        ("==== SOURCE ====", "==== PEERS ===="),
        ("==== PEERS ====", "==== STATUS ===="),
        ("==== STATUS ====", "==== EFFECTIVE CONFIGURATION ===="),
    ):
        if heading in stdout and next_heading in stdout:
            section = stdout.split(heading, 1)[1].split(next_heading, 1)[0]
            if not section.strip():
                problems.append(f"Empty diagnostic section: {heading}")
    return problems


def capture(instance_id):
    assert_instance(instance_id)
    # Avoid a second Windows command-line length failure in diagnostics.
    encoded_length = len(base64.b64encode(POWERSHELL.encode("utf-16le")))
    if encoded_length > 6500:
        raise ValueError(f"Diagnostic encoded command too large: {encoded_length}")
    # Scripts executed by path set sys.path[0] to scripts/diagnostics.
    # Resolve imports from this repository instead of assuming a shell PYTHONPATH.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
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
            with warnings.catch_warnings(record=True) as raised:
                warnings.simplefilter("always")
                result = session.run_ps(POWERSHELL)
            stdout = result.std_out.decode(errors="replace")
            stderr = result.std_err.decode(errors="replace")
            warning_messages = [str(item.message) for item in raised]
            problems = evidence_problems(
                result.status_code, stdout, stderr, warning_messages
            )
            target.write_text(
                f"host={name} ip={ip} exit={result.status_code}\n" +
                stdout + "\nSTDERR:\n" + stderr +
                "\nPYWINRM_WARNINGS:\n" + "\n".join(warning_messages) +
                "\nDIAGNOSTIC_LIMITATIONS:\n" + "\n".join(problems) + "\n",
                encoding="utf-8",
            )
            if problems:
                failed = True
                print(f"[PARTIAL] {name}: {', '.join(problems)}: {target}")
            else:
                print(f"[PASS] {name} complete read-only evidence: {target}")
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
