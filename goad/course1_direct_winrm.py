"""Fail-closed NORTH fresh-Windows guest recovery over direct VMware NAT WinRM.

Only the exact registered VMware guest may be targeted. This is a fallback
when Vagrant's configured localhost port forward or guest adapter operation
fails after a fresh boot. It reuses the existing Vagrant provisioner scripts;
never changes VMX adapters, other machines, host networks, or lab scenarios.
"""
from __future__ import annotations

import base64
import hashlib
import uuid
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import time

from goad.kingdoms_topology import load_course1_topology

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "GOAD-DC01": "00:50:56:20:20:10",
    "GOAD-DC02": "00:50:56:20:10:11",
    "GOAD-SRV02": "00:50:56:20:10:22",
    "GOAD-WS01": "00:50:56:20:10:31",
}


class NorthGuestRecoveryBlocked(RuntimeError):
    pass


class NorthGuestIdentityMismatch(NorthGuestRecoveryBlocked):
    """Authenticated WinRM endpoint contradicts the exact owned guest."""
    pass


def _command(argv, *, timeout=20):
    try:
        return subprocess.run(
            argv, text=True, capture_output=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NorthGuestRecoveryBlocked("VMware inspection failed: " + argv[0]) from exc


def _vmx_properties(vmx):
    settings = {}
    for line in vmx.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.fullmatch(r'\s*(ethernet[01]\.[\w]+)\s*=\s*"([^"]+)"\s*', line, re.I)
        if m:
            key = m[1].lower()
            if key in settings:
                raise NorthGuestRecoveryBlocked("duplicate VMX setting: " + key)
            settings[key] = m[2].lower()
    return settings


def owned_guest(provider, machine):
    provider = Path(provider)
    if (machine not in EXPECTED or not provider.is_absolute() or
            provider.is_symlink() or not provider.is_dir() or
            provider.resolve() != provider or
            not re.fullmatch(r"[a-f0-9]{6}-north-vmware", provider.parent.name) or
            provider.name != "provider"):
        raise NorthGuestRecoveryBlocked("Exact installed NORTH instance required")

    ident = provider / ".vagrant" / "machines" / machine / "vmware_desktop" / "id"
    if not ident.is_file() or ident.is_symlink():
        raise NorthGuestRecoveryBlocked("Original Vagrant guest registration missing")
    vmx = Path(ident.read_text(encoding="utf-8").strip())
    root = ident.parent.resolve()
    if (not vmx.is_absolute() or not vmx.is_file() or vmx.is_symlink()
            or not vmx.resolve().is_relative_to(root)):
        raise NorthGuestRecoveryBlocked("Guest VMX does not belong to this instance")
    layout = load_course1_topology()
    guest = layout["windows"][machine]
    values = _vmx_properties(vmx)
    required = {
        "ethernet0.connectiontype": "nat",
        "ethernet0.present": "true",
        "ethernet1.connectiontype": "custom",
        "ethernet1.present": "true",
        "ethernet1.vnet": guest["vmnet"].lower(),
        "ethernet1.address": EXPECTED[machine].lower(),
    }
    for key, val in required.items():
        if values.get(key) != val:
            raise NorthGuestRecoveryBlocked("Guest VMX contract differs: " + key)
    if _command(["vmrun", "-T", "ws", "list"]).stdout.splitlines().count(str(vmx)) != 1:
        raise NorthGuestRecoveryBlocked("Original guest is not uniquely running")
    return vmx, guest, values


def _nat_network():
    result = _command(["ip", "-4", "-o", "addr", "show", "dev", "vmnet8"])
    if result.returncode:
        raise NorthGuestRecoveryBlocked("VMware vmnet8 host IP missing")
    interfaces = re.findall(r"\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)", result.stdout)
    if len(interfaces) != 1:
        raise NorthGuestRecoveryBlocked("Ambiguous VMware NAT interface")
    return ipaddress.IPv4Interface(interfaces[0]).network


def _vmx_nat_ip(vmx, network, *, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _command(["vmrun", "-T", "ws", "getGuestIPAddress", str(vmx)], timeout=12)
        if result.returncode == 0:
            try:
                address = ipaddress.IPv4Address(result.stdout.strip())
            except ipaddress.AddressValueError:
                pass
            else:
                if address in network and not (
                        address == network.network_address or
                        address == network.broadcast_address):
                    route = _command(["ip", "-4", "route", "get", str(address)])
                    if route.returncode == 0 and re.search(
                            r"\bdev\s+vmnet8\b", route.stdout):
                        return str(address)
        time.sleep(min(5, max(0, deadline-time.monotonic())))
    raise NorthGuestRecoveryBlocked("Exact guest NAT IP not proven by VMware")


def _run(session, script, marker=None):
    try:
        result = session.run_ps(script)
    except Exception as exc:
        raise NorthGuestRecoveryBlocked(
            "Authenticated direct WinRM operation unavailable: " + type(exc).__name__
        ) from exc
    stdout = result.std_out.decode("utf-8", errors="replace")
    stderr = result.std_err.decode("utf-8", errors="replace")
    if result.status_code or (marker is not None and marker not in stdout):
        raise NorthGuestRecoveryBlocked(
            "Direct guest operation failed: " + stderr[:500] + " " + stdout[-500:]
        )
    return stdout


def _identity_script():
    return r"""
$ErrorActionPreference = 'Stop'
$svc = Get-Service VMTools -ErrorAction Stop
$tools = @(Get-Process vmtoolsd -ErrorAction SilentlyContinue)
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
$adapters = @(Get-NetAdapter -ErrorAction Stop | ForEach-Object {
    [PSCustomObject]@{ Mac = (($_.MacAddress -replace '[:-]','').ToUpperInvariant());
                      Index = $_.ifIndex; Name = $_.Name;
                      IPv4 = @(Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                               Select-Object -ExpandProperty IPAddress) }
})
[PSCustomObject]@{
  Hostname = $env:COMPUTERNAME
  Windows = ($os.Caption -match 'Windows')
  Tools = ($svc.Status -eq 'Running' -and $tools.Count -gt 0)
  PowerShell = $PSVersionTable.PSVersion.Major
  Adapters = $adapters
} | ConvertTo-Json -Depth 5 -Compress
"""


def _authenticated_session(address, port=5985):
    import winrm
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise NorthGuestRecoveryBlocked("Invalid Windows WinRM port")
    return winrm.Session(
        "http://" + address + ":" + str(port) + "/wsman",
        auth=("vagrant", "vagrant"), transport="ntlm",
        operation_timeout_sec=25, read_timeout_sec=40
    )


def _verified_identity(session, values, machine):
    """Prove the *authenticated Windows endpoint* has both owned NIC MACs."""
    try:
        identity = json.loads(_run(session, _identity_script()))
    except (ValueError, TypeError) as exc:
        raise NorthGuestRecoveryBlocked("Authenticated Windows identity unreadable") from exc
    if not isinstance(identity, dict):
        raise NorthGuestRecoveryBlocked("Authenticated Windows identity invalid")
    adapters = identity.get("Adapters") or []
    if isinstance(adapters, dict):
        adapters = [adapters]
    if not isinstance(adapters, list):
        raise NorthGuestRecoveryBlocked("Authenticated Windows NIC list invalid")
    macs = []
    for item in adapters:
        if not isinstance(item, dict):
            raise NorthGuestRecoveryBlocked("Authenticated Windows NIC list malformed")
        mac = item.get("Mac")
        if not isinstance(mac, str):
            raise NorthGuestRecoveryBlocked("Authenticated Windows NIC MAC missing")
        macs.append(mac.upper())
    nat_mac = values.get("ethernet0.generatedaddress", "").replace(":", "").upper()
    lab_mac = EXPECTED[machine].replace(":", "").upper()
    if (not identity.get("Windows") or not identity.get("Hostname") or
            not isinstance(identity.get("PowerShell"), int) or
            identity["PowerShell"] < 5 or not identity.get("Tools") or
            not re.fullmatch(r"[0-9A-F]{12}", nat_mac) or
            macs.count(nat_mac) != 1 or macs.count(lab_mac) != 1 or
            nat_mac == lab_mac):
        raise NorthGuestIdentityMismatch(
            "Authenticated endpoint failed exact Windows/Tools/NAT-MAC/lab-MAC proof"
        )
    return next(item for item in adapters if item["Mac"].upper() == nat_mac)


def _validated_nat_address(value, network):
    try:
        ip = ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, TypeError) as exc:
        raise NorthGuestRecoveryBlocked("Invalid NAT guest IPv4 address") from exc
    if (ip not in network or ip in (
            network.network_address, network.broadcast_address)
            or ip.is_loopback or ip.is_link_local or ip.is_multicast):
        raise NorthGuestRecoveryBlocked("Guest NAT address is outside owned vmnet8")
    route = _command(["ip", "-4", "route", "get", str(ip)])
    if route.returncode != 0 or not re.search(r"\bdev\s+vmnet8\b", route.stdout):
        raise NorthGuestRecoveryBlocked("Guest NAT IPv4 is not routed via vmnet8")
    return str(ip)


def _forwarded_nat_ip(port, values, machine, network):
    """Seed NAT IP from an *authenticated* forwarded WinRM and exact guest MAC."""
    if not isinstance(port, int) or port <= 0 or port > 65535:
        raise NorthGuestRecoveryBlocked("Forwarded WinRM port unavailable")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=4):
            pass
    except OSError as exc:
        raise NorthGuestRecoveryBlocked("Forwarded WinRM port is not listening") from exc
    session = _authenticated_session("127.0.0.1", port=port)
    nat_adapter = _verified_identity(session, values, machine)
    ips = nat_adapter.get("IPv4") or []
    if isinstance(ips, str):
        ips = [ips]
    if not isinstance(ips, list) or len(ips) != 1:
        raise NorthGuestRecoveryBlocked("Guest NAT NIC does not have one IPv4 address")
    return _validated_nat_address(ips[0], network)


def prove_guest(provider, machine, *, timeout=90, address_hint=None,
                forwarded_port=None):
    """Prove exact registered VMX, guest NICs and direct authenticated WinRM.

    Guest VIX IP reporting is advisory. A verified forwarded WinRM connection
    may seed the NAT IP when VIX reporting is stale or unavailable; the
    resulting direct endpoint must independently pass the same identity proof.
    """
    vmx, guest, values = owned_guest(provider, machine)
    network = _nat_network()
    if address_hint is not None:
        address = _validated_nat_address(address_hint, network)
    else:
        address = None
        forwarded_failure = None
        if forwarded_port is not None:
            try:
                address = _forwarded_nat_ip(forwarded_port, values, machine, network)
            except NorthGuestIdentityMismatch:
                # An authenticated *different* Windows guest is never a hint.
                raise
            except NorthGuestRecoveryBlocked as exc:
                forwarded_failure = exc
        if address is None:
            try:
                address = _vmx_nat_ip(vmx, network, timeout=timeout)
            except NorthGuestRecoveryBlocked as exc:
                if forwarded_failure is not None:
                    raise NorthGuestRecoveryBlocked(
                        f"VIX NAT IP unavailable ({exc}); authenticated "
                        f"forwarded bootstrap unavailable ({forwarded_failure})"
                    ) from exc
                raise
            address = _validated_nat_address(address, network)

    try:
        with socket.create_connection((address, 5985), timeout=5):
            pass
    except OSError as exc:
        raise NorthGuestRecoveryBlocked("Direct guest HTTP WinRM is not listening") from exc
    session = _authenticated_session(address)
    _verified_identity(session, values, machine)
    return session, address, guest


def _strict_script(guest, machine):
    return r"""
$ErrorActionPreference = 'Stop'
$mac = '""" + EXPECTED[machine].replace(":", "").upper() + r"""'
$ip = '""" + guest["address"] + r"""'
$gateway = '""" + guest["gateway"] + r"""'
$nic = @(Get-NetAdapter | Where-Object { ($_.MacAddress -replace '[:-]','').ToUpperInvariant() -eq $mac })
$address = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
    Where-Object { $nic.Count -eq 1 -and $_.InterfaceIndex -eq $nic[0].ifIndex -and $_.IPAddress -eq $ip -and $_.PrefixLength -eq 24 })
$route = @(Get-NetRoute -DestinationPrefix '10.4.0.0/16' -ErrorAction SilentlyContinue |
    Where-Object { $nic.Count -eq 1 -and $_.InterfaceIndex -eq $nic[0].ifIndex -and $_.NextHop -eq $gateway })
$https = @(Get-NetTCPConnection -LocalPort 5986 -State Listen -ErrorAction SilentlyContinue)
$tools = Get-Service VMTools -ErrorAction Stop
if ($nic.Count -ne 1 -or $address.Count -ne 1 -or $route.Count -lt 1 -or
    $https.Count -lt 1 -or $tools.Status -ne 'Running') {
    throw 'NORTH canonical IP / gateway / HTTPS / Tools contract incomplete'
}
Write-Output 'NORTH_DIRECT_FIRST_BOOT_READY'
"""


def prove_canonical_guest(provider, machine, *, timeout=90, address_hint=None):
    session, address, guest = prove_guest(
        provider, machine, timeout=timeout, address_hint=address_hint
    )
    _run(session, _strict_script(guest, machine), "NORTH_DIRECT_FIRST_BOOT_READY")
    return address


# Keep each PowerShell command small enough for Windows' process argument limit.
# pywinrm.run_ps encodes its entire command as UTF-16LE Base64 and passes it as
# a PowerShell process argument, so sending the entire script in one call fails.
_WINRM_CHUNK_BYTES = 1024
_MAX_SOURCE_BYTES = 262144
_ALLOWED_SOURCE_NAMES = frozenset({
    "ConfigureRemotingForAnsible.ps1", "fix_ip.ps1",
})


def _execute_source(session, path, args=()):
    """Transfer a pinned repository script in bounded WinRM calls and execute it.

    This is an internal source-transfer path, NOT an arbitrary command upload
    API. Never run a script that has not been byte-for-byte checked on Windows.
    It uses a unique guest TEMP file and cleans it in both success/failure
    cases; a failed source run is never automatically replayed.
    """
    source = Path(path)
    if (not source.is_file() or source.is_symlink()
            or source.parent != ROOT / "vagrant"
            or source.name not in _ALLOWED_SOURCE_NAMES):
        raise NorthGuestRecoveryBlocked("Unexpected Vagrant provisioning script")
    payload = source.read_bytes()
    if not payload or len(payload) > _MAX_SOURCE_BYTES:
        raise NorthGuestRecoveryBlocked("Invalid original Vagrant script size")
    if any(not re.fullmatch(r"[A-Za-z0-9.:-]{1,64}", str(a)) for a in args):
        raise NorthGuestRecoveryBlocked("Unexpected direct guest script argument")
    if (source.name == "ConfigureRemotingForAnsible.ps1" and args or
            source.name == "fix_ip.ps1" and len(args) != 3):
        raise NorthGuestRecoveryBlocked("Unexpected source script argument count")

    digest = hashlib.sha256(payload).hexdigest().upper()
    token = uuid.uuid4().hex
    name = "kingdoms-north-" + token + ".ps1"
    path_expr = "Join-Path $env:TEMP '" + name + "'"
    beginning = (
        "$ErrorActionPreference='Stop';$p=" + path_expr + ";"
        "$s=[IO.File]::Open($p,[IO.FileMode]::CreateNew,"
        "[IO.FileAccess]::Write,[IO.FileShare]::None);"
        "try{}finally{$s.Dispose()};"
        "Write-Output 'NORTH_STAGE_BEGIN'"
    )
    cleanup = (
        "$ErrorActionPreference='Stop';$p=" + path_expr + ";"
        "if(Test-Path -LiteralPath $p -PathType Leaf){"
        "Remove-Item -LiteralPath $p -Force -ErrorAction Stop};"
        "if(Test-Path -LiteralPath $p){throw 'NORTH temp script not removed'};"
        "Write-Output 'NORTH_STAGE_REMOVED'"
    )
    # Cleanup after any *confirmed* CreateNew, including a chunking or
    # checksum failure. If CreateNew itself fails, do not delete an unknown
    # file on the guest.
    _run(session, beginning, "NORTH_STAGE_BEGIN")
    error = None
    output = None
    try:
        for offset in range(0, len(payload), _WINRM_CHUNK_BYTES):
            chunk = base64.b64encode(
                payload[offset:offset + _WINRM_CHUNK_BYTES]
            ).decode("ascii")
            cmd = (
                "$ErrorActionPreference='Stop';$p=" + path_expr + ";"
                "$b=[Convert]::FromBase64String('" + chunk + "');"
                "$s=[IO.File]::Open($p,[IO.FileMode]::Append,"
                "[IO.FileAccess]::Write,[IO.FileShare]::None);"
                "try{$s.Write($b,0,$b.Length)}finally{$s.Dispose()};"
                "Write-Output 'NORTH_STAGE_CHUNK'"
            )
            _run(session, cmd, "NORTH_STAGE_CHUNK")

        quoted_args = " ".join(
            "'" + str(arg).replace("'", "''") + "'" for arg in args
        )
        execute = (
            "$ErrorActionPreference='Stop';$p=" + path_expr + ";"
            "$file=Get-Item -LiteralPath $p -ErrorAction Stop;"
            "if($file.Length -ne " + str(len(payload)) +
            "){throw 'NORTH staged script length mismatch'};"
            "$digest=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash;"
            "if($digest -ne '" + digest +
            "'){throw 'NORTH staged script hash mismatch'};"
            # Execute as a file, as the original Vagrant PowerShell provisioner
            # does, including its own MyInvocation context and exit behavior.
            "$exe=Join-Path $env:SystemRoot "
            "'System32\\WindowsPowerShell\\v1.0\\powershell.exe';"
            "& $exe -NoProfile -NonInteractive -ExecutionPolicy Bypass "
            "-File $p " + quoted_args + ";"
            "if($LASTEXITCODE -ne 0){throw "
            "('NORTH source script exited '+$LASTEXITCODE)};"
            "Write-Output 'NORTH_SOURCE_SCRIPT_COMPLETED'"
        )
        output = _run(session, execute, "NORTH_SOURCE_SCRIPT_COMPLETED")
    except Exception as exc:
        error = exc
    try:
        _run(session, cleanup, "NORTH_STAGE_REMOVED")
    except NorthGuestRecoveryBlocked as cleanup_error:
        raise NorthGuestRecoveryBlocked(
            "NORTH source script guest-temp cleanup not confirmed; "
            "do not repeat execution automatically"
        ) from (error or cleanup_error)
    if error is not None:
        raise error
    return output


def recover_north_first_boot(provider, machine):
    """Replay only source-owned Windows Vagrant scripts through proved NAT WinRM.

    No implicit retry if a script failed or rebooted unexpectedly. A later
    fresh install must independently complete the normal AD/WinRM acceptance.
    """
    session, address, guest = prove_guest(provider, machine)
    try:
        _run(session, _strict_script(guest, machine), "NORTH_DIRECT_FIRST_BOOT_READY")
        return True  # Vagrant already completed the desired guest provisioning.
    except NorthGuestRecoveryBlocked:
        pass

    # WinRM HTTP can exist on the StefanScherer box before the Vagrant shell
    # provisioners have run. Powershell >=5 already makes WMF3 hotfix a no-op.
    _execute_source(session, ROOT / "vagrant" / "ConfigureRemotingForAnsible.ps1")
    session, address, verified_guest = prove_guest(
        provider, machine, timeout=90, address_hint=address
    )
    if guest != verified_guest:
        raise NorthGuestRecoveryBlocked("Guest topology changed during provision")
    _execute_source(session, ROOT / "vagrant" / "fix_ip.ps1", (
        guest["address"], guest["gateway"], EXPECTED[machine]
    ))
    prove_canonical_guest(provider, machine, timeout=90, address_hint=address)
    return True
