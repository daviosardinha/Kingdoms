"""Read-only NORTH fifth-install DC02 guest-temp cleanup forensic probe.

Does not rerun repository provisioning scripts, remove guest files, reboot
Windows, modify host networks, or touch Active Directory state.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from goad.course1_direct_winrm import (
    NorthGuestRecoveryBlocked, _run, _strict_script, owned_guest, prove_guest,
)

INSTANCE = "bb3baf-north-vmware"
MACHINE = "GOAD-DC02"
ROOT = Path(__file__).resolve().parents[2]
PROVIDER = ROOT / "workspace" / INSTANCE / "provider"
PORT = re.compile(r"^\s*5985\s+\(guest\)\s*=>\s*(\d+)\s+\(host\)\s*$", re.M)

READONLY_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$rows = @(Get-ChildItem -LiteralPath $env:TEMP -Filter 'kingdoms-north-*.ps1' -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match '^kingdoms-north-[0-9a-f]{32}\.ps1$' } |
  ForEach-Object {
    [PSCustomObject]@{
       Name = $_.Name
       Length = $_.Length
       LastWriteTimeUtc = $_.LastWriteTimeUtc.ToString('o')
       Sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
    }
  })
$adapters = @(Get-NetAdapter -ErrorAction Stop | ForEach-Object {
   $adapter = $_
   [PSCustomObject]@{
      Name = $adapter.Name
      Mac = (($adapter.MacAddress -replace '[:-]', '').ToUpperInvariant())
      Status = [string]$adapter.Status
      IPv4 = @(Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty IPAddress)
   }
})
$svcs = @(Get-Service -Name VMTools,WinRM -ErrorAction SilentlyContinue | ForEach-Object {
  [PSCustomObject]@{ Name=$_.Name; Status=[string]$_.Status }
})
$https = @(Get-NetTCPConnection -LocalPort 5986 -State Listen -ErrorAction SilentlyContinue).Count
$routes = @(Get-NetRoute -DestinationPrefix '10.4.0.0/16' -ErrorAction SilentlyContinue |
  ForEach-Object { [PSCustomObject]@{ NextHop=$_.NextHop; InterfaceIndex=$_.InterfaceIndex } })
[PSCustomObject]@{
  Hostname = $env:COMPUTERNAME
  TempPath = $env:TEMP
  Utc = (Get-Date).ToUniversalTime().ToString('o')
  VMwareToolsAndWinRM = @($svcs)
  WinRMHttpsListeners = $https
  NICs = @($adapters)
  InternalRoutes = @($routes)
  KingdomsStageFiles = @($rows)
} | ConvertTo-Json -Depth 6 -Compress
"""


def forwarded_winrm_port(provider):
    """Read-only forwarding evidence; never authorize identity from a port."""
    result = subprocess.run(
        ["vagrant", "port", MACHINE], cwd=provider,
        check=False, capture_output=True, text=True, timeout=40,
    )
    if result.returncode:
        return None
    found = [int(value) for value in PORT.findall(result.stdout)]
    return found[0] if len(found) == 1 and 0 < found[0] < 65536 else None


def probe(provider=PROVIDER):
    provider = Path(provider)
    if provider.resolve() != PROVIDER or provider.is_symlink():
        raise NorthGuestRecoveryBlocked(
            "Unexpected provider: only the fifth NORTH DC02 is authorized"
        )
    vmx, topology, settings = owned_guest(provider, MACHINE)
    port = forwarded_winrm_port(provider)
    session, nat_ip, guest = prove_guest(
        provider, MACHINE, timeout=30, forwarded_port=port
    )
    if guest != topology:
        raise NorthGuestRecoveryBlocked("NORTH DC02 guest topology changed")
    raw = _run(session, READONLY_SCRIPT)
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("KingdomsStageFiles"), list):
        raise NorthGuestRecoveryBlocked("Read-only DC02 inventory malformed")
    stage = data["KingdomsStageFiles"]
    for item in stage:
        if (not isinstance(item, dict) or not isinstance(item.get("Name"), str)
                or not re.fullmatch(r"kingdoms-north-[0-9a-f]{32}\.ps1", item["Name"])
                or not re.fullmatch(r"[A-F0-9]{64}", str(item.get("Sha256", "")))):
            raise NorthGuestRecoveryBlocked("Unexpected DC02 staged-script evidence")
    try:
        _run(session, _strict_script(guest, MACHINE), "NORTH_DIRECT_FIRST_BOOT_READY")
        canonical = True
    except NorthGuestRecoveryBlocked:
        canonical = False
    known_hashes = {
        name: hashlib.sha256((ROOT / "vagrant" / name).read_bytes()).hexdigest().upper()
        for name in ("ConfigureRemotingForAnsible.ps1", "fix_ip.ps1")
    }
    for entry in stage:
        entry["MatchesOriginalSource"] = [
            name for name, digest in known_hashes.items()
            if digest == entry["Sha256"]
        ]
    return {
        "Instance": INSTANCE,
        "Machine": MACHINE,
        "VMX": str(vmx),
        "OriginalNatMac": settings.get("ethernet0.generatedaddress"),
        "AuthenticatedNatIp": nat_ip,
        "ForwardedWinRMPortAdvisory": port,
        "CanonicalFirstBootReady": canonical,
        "GuestReadOnlyInventory": data,
        "StateChangesAttempted": False,
        "SourceScriptsReplayed": False,
    }


def main():
    try:
        print("[INFO] NORTH_DC02_PROBE=READ_ONLY", flush=True)
        report = probe()
        print(json.dumps(report, sort_keys=True, indent=2))
        if report["CanonicalFirstBootReady"]:
            print("[PASS] NORTH_DC02_CANONICAL_FIRST_BOOT_READY")
        else:
            print("[INFO] NORTH_DC02_CANONICAL_FIRST_BOOT_INCOMPLETE")
        print("[PASS] NORTH_DC02_READONLY_DIAGNOSTIC_COMPLETED")
    except (NorthGuestRecoveryBlocked, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print("[BLOCKED] NORTH_DC02_READONLY_DIAGNOSTIC: " + str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
