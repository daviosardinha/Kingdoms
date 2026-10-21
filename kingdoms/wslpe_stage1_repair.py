"""Explicit, one-attempt recovery of a partially created native WSLPE guest.

This is the existing LabManager/VMware provider, existing Vagrant provisioners
(including vagrant/fix_ip.ps1), and existing VMTools installer. No new VM,
VMnet, network manager, guest account, scenario runner, or GOAD/NORTH actions.
A failed attempt remains CREATED. Never automatically replay after failure.
"""
from __future__ import annotations

import ipaddress
from pathlib import Path
import re
import subprocess

from kingdoms.wslpe_nic_contract import parse_vmx_networks

from goad.goadpath import GoadPath
from goad.log import Log
from goad.utils import CREATED, PROVIDED
from kingdoms.wslpe_stage1 import GUEST, inspect_vmware_guest, valid_prefix


def _native_repair_target(manager):
    instance = manager.get_current_instance()
    if (instance is None
            or instance.lab_name != "WSLPE"
            or instance.provider_name != "vmware"
            or instance.provisioner_name != "local"
            or instance.extensions
            or instance.get_status() != CREATED
            or not valid_prefix(instance.ip_range)):
        Log.error("Only a CREATED, standalone native WSLPE instance can be repaired")
        return None
    root = Path(GoadPath.get_project_path()).resolve()
    workspace = Path(GoadPath.get_workspace_path())
    instance_dir = Path(instance.instance_path)
    provider_dir = Path(instance.instance_provider_path)
    if (workspace.is_symlink() or instance_dir.is_symlink()
            or provider_dir.is_symlink()
            or workspace.resolve() != root / "workspace"
            or instance_dir.resolve().parent != workspace.resolve()
            or provider_dir.resolve().parent != instance_dir.resolve()):
        Log.error("Partial WSLPE instance paths do not belong to this checkout")
        return None
    provider = manager.get_current_instance_provider()
    if (provider is None or getattr(provider, "lab_name", None) != "WSLPE"
            or Path(str(provider.path)).resolve() != provider_dir.resolve()):
        Log.error("Current provider does not own the partially created WSLPE VM")
        return None
    try:
        vagrantfile = (provider_dir / "Vagrantfile")
        if vagrantfile.is_symlink() or not vagrantfile.is_file():
            return None
        source = vagrantfile.read_text(encoding="utf-8")
        if (source.count(':name => "WSLPE-WS01"') != 1
                or ':name => "GOAD-' in source
                or 'v.enable_vmrun_ip_lookup = false' not in source):
            Log.error("WSLPE generated Vagrantfile has drifted")
            return None
    except OSError:
        Log.error("Could not read native WSLPE Vagrantfile")
        return None
    return instance, provider


def _registered_guest_vmx(provider) -> Path | None:
    """Resolve only this instance's existing Vagrant registration, never a new VM."""
    provider_dir = Path(str(provider.path)).resolve()
    registration = (
        provider_dir / ".vagrant" / "machines" / GUEST / "vmware_desktop" / "id"
    )
    if not registration.is_file() or registration.is_symlink():
        Log.error("WSLPE partial instance has no safe Vagrant VM registration")
        return None
    try:
        raw = registration.read_text(encoding="utf-8").strip()
        original = Path(raw)
        if not original.is_absolute() or original.is_symlink():
            raise ValueError("invalid registered VMX")
        vmx = original.resolve(strict=True)
        machine_dir = registration.parent.resolve(strict=True)
        # Do not accept an unrelated GOAD, NORTH, or old standalone WSLPE VMX.
        vmx.relative_to(machine_dir)
        if (not vmx.is_file() or vmx.suffix.lower() != ".vmx"
                or any("GOAD-" in part.upper() or "NORTH" in part.upper()
                       for part in vmx.parts)):
            raise ValueError("VMX is not this native machine")
        if provider._vmx_path(GUEST) != raw:
            raise ValueError("native provider and registration disagree")
        return vmx
    except (OSError, ValueError, UnicodeError):
        Log.error("Native WSLPE VMX registration is missing or outside this instance")
        return None


def _vmware_running_inventory() -> set[Path] | None:
    """Validate VMware's full running list before touching a powered-off guest."""
    try:
        result = subprocess.run(
            ["vmrun", "-T", "ws", "list"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        Log.error("Cannot inspect current VMware running guests")
        return None
    if result.returncode != 0:
        Log.error("VMware running-VM query failed; no power action")
        return None
    lines = result.stdout.splitlines()
    if not lines or not re.fullmatch(r"Total running VMs:\s*\d+", lines[0]):
        Log.error("VMware running inventory format is unexpected")
        return None
    expected = int(lines[0].split(":", 1)[1].strip())
    guests = [Path(line.strip()).resolve() for line in lines[1:] if line.strip()]
    if len(guests) != expected or len(set(guests)) != expected:
        Log.error("VMware running inventory count or guest identity is inconsistent")
        return None
    return set(guests)


def _ensure_registered_guest_running(provider) -> bool:
    """Start the single existing powered-off VM once, after exact Vagrant proof."""
    vmx = _registered_guest_vmx(provider)
    if vmx is None:
        return False
    inventory = _vmware_running_inventory()
    if inventory is None:
        return False
    if vmx in inventory:
        Log.info("KINGDOMS WSLPE registered guest is already powered on")
        return inspect_vmware_guest(provider)

    # Vagrant must agree the exact already-created VM is powered off. Neither
    # 'not created', 'aborted', 'saved' nor an unknown state authorizes vmrun.
    try:
        status = subprocess.run(
            ["vagrant", "status", GUEST],
            cwd=str(provider.path), capture_output=True, text=True,
            check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        Log.error("Cannot confirm powered-off WSLPE state with Vagrant")
        return False
    if (status.returncode != 0
            or not re.search(
                rf"(?m)^\s*{re.escape(GUEST)}\s+not running\s+\(vmware_desktop\)\s*$",
                status.stdout,
            )):
        Log.error("Vagrant did not confirm this registered WSLPE VM is powered off")
        return False

    # Recheck after Vagrant's status query: someone could have started the VM
    # in the meantime. Never power a guest if host state has changed.
    latest = _vmware_running_inventory()
    if latest is None or latest != inventory:
        Log.error("VMware running inventory changed during preflight; no startup")
        return False

    Log.warning(f"Powering on existing, registered KINGDOMS WSLPE guest once: {vmx}")
    try:
        started = subprocess.run(
            ["vmrun", "-T", "ws", "start", str(vmx), "nogui"],
            capture_output=True, text=True, check=False, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        Log.error("Native WSLPE startup interrupted; inspect before any retry")
        return False
    if started.returncode != 0:
        Log.error("Existing WSLPE VM power-on failed; inspect before retry")
        return False
    # Do not equate vmrun command success with actual VMware guest state.
    if not inspect_vmware_guest(provider):
        Log.error("Existing WSLPE VMX was not independently confirmed running")
        return False
    return True


def _guest_proof(provider, prefix: str, *, complete: bool) -> bool:
    """Proof over the registered provider's forwarded WinRM management path."""
    expected = str(ipaddress.IPv4Network(prefix + ".0/24").network_address + 31)
    # A forwarded host port and the hostname WSLPE-WS01 are not enough:
    # two WSLPE instances intentionally share the same Windows hostname.
    # Bind authenticated WinRM to the NAT MAC of THIS Vagrant-registered VMX.
    vmx_name = provider._vmx_path(GUEST)
    if not vmx_name:
        Log.error("Native WSLPE VMX is not registered")
        return False
    vmx = Path(vmx_name)
    if vmx.is_symlink() or not vmx.is_file():
        Log.error("WSLPE VMX is missing or symlinked")
        return False
    try:
        nics = parse_vmx_networks(vmx.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        Log.error("Cannot inspect native WSLPE VMX NAT identity")
        return False
    nat = nics.get(0, {})
    if nat.get("connectiontype", "").lower() != "nat":
        Log.error("WSLPE registered VMware Ethernet0 must be provisioning NAT")
        return False
    nat_mac = nat.get("generatedaddress") or nat.get("address") or ""
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", nat_mac):
        Log.error("Native WSLPE Ethernet0 MAC is not proven")
        return False
    expected_mac = nat_mac.replace(":", "").upper()
    port = provider._winrm_forwarded_port(GUEST)
    if not port or not provider._wait_winrm_ready(port, 40):
        Log.error("Registered WSLPE forwarded WinRM is not authenticated")
        return False
    script = r"""
$ErrorActionPreference = 'Stop'
$c = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $c.PartOfDomain -or $os.ProductType -ne 1) {
    throw 'WSLPE_STAGE1_WRONG_WINDOWS_GUEST'
}
$routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop)
$ipv4 = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop)
$nat = @($ipv4 | Where-Object {
    $_.IPAddress -notmatch '^(127[.]|169[.]254[.])' -and
    $routes.InterfaceIndex -contains $_.InterfaceIndex
})
if ($nat.Count -ne 1) { throw 'WSLPE_STAGE1_NAT_NOT_READY' }
$adapter = @(Get-NetAdapter -ErrorAction Stop |
    Where-Object { $_.ifIndex -eq $nat[0].InterfaceIndex })
if ($adapter.Count -ne 1 -or
    (($adapter[0].MacAddress -replace '[:-]', '').ToUpperInvariant()) -cne '""" + expected_mac + r"""') {
    throw 'WSLPE_STAGE1_WRONG_NATIVE_NAT_ADAPTER'
}
Write-Output 'WSLPE_STAGE1_WINDOWS_NAT=PASS'
"""
    if complete:
        script += r"""
$svc = Get-Service -Name VMTools -ErrorAction Stop
$exe = Test-Path 'C:\Program Files\VMware\VMware Tools\vmtoolsd.exe'
$proc = Get-Process -Name vmtoolsd -ErrorAction SilentlyContinue
if ($svc.Status -ne 'Running' -or -not $exe -or -not $proc) {
    throw 'WSLPE_STAGE1_VMTOOLS_NOT_READY'
}
$exercise = @($ipv4 | Where-Object { $_.IPAddress -eq '""" + expected + r"""' -and $_.PrefixLength -eq 24 })
if ($exercise.Count -ne 1 -or $exercise[0].InterfaceIndex -eq $nat[0].InterfaceIndex) {
    throw 'WSLPE_STAGE1_EXERCISE_IP_NOT_READY'
}
Write-Output 'WSLPE_STAGE1_EXERCISE_NIC=PASS'
"""
    try:
        result = provider._winrm_session(port).run_ps(script)
    except Exception as exc:
        Log.error(f"Authenticated WSLPE guest readiness probe failed: {type(exc).__name__}")
        return False
    markers = ["WSLPE_STAGE1_WINDOWS_NAT=PASS"]
    if complete:
        markers.append("WSLPE_STAGE1_EXERCISE_NIC=PASS")
    return (result.status_code == 0
            and all(result.std_out.count(m.encode("ascii")) == 1 for m in markers))


def repair_native_wslpe_stage1(manager, *, confirmed: bool) -> bool:
    """One operator-approved repair of this exact partial guest, never creation.

    Reuse VMware Tools ISO/WinRM readiness and the *existing* Vagrantfile
    Windows network configuration including fix_ip.ps1; run at most one
    bounded native 'up --provision' after the Tools repair is independently
    confirmed. No hard shutdown, VM reset, or destructive rollback.
    """
    if confirmed is not True:
        Log.error("Exact REPAIR WSLPE STAGE1 confirmation required")
        return False
    target = _native_repair_target(manager)
    if target is None:
        return False
    instance, provider = target

    # The first failed Vagrant install can leave this guest powered off.
    # Recovery confirmation authorizes ONE exact registered-VM start, never
    # a new instance or an automatic repeated power attempt.
    if not _ensure_registered_guest_running(provider):
        Log.error("Existing WSLPE guest startup preflight/recovery failed")
        return False

    if not _guest_proof(provider, instance.ip_range, complete=False):
        Log.error("Refusing Tools repair on an unverified Windows management guest")
        return False
    Log.info("Recovering VMware Tools via existing KINGDOMS ISO/WinRM provider")
    if not provider._ensure_vmware_tools(GUEST):
        Log.error("VMware Tools repair failed; no Vagrant provisioning was replayed")
        return False
    # Do not let a successful installer exit alone authorize provisioning.
    if not _guest_proof(provider, instance.ip_range, complete=False):
        Log.error("Guest management path not ready after VMware Tools repair")
        return False
    if not provider._guest_tools_healthy(provider._winrm_forwarded_port(GUEST)):
        Log.error("VMware Tools core service still not running")
        return False
    Log.info("Completing interrupted native Vagrant provisioners once (includes fix_ip.ps1)")
    if not provider._run_vagrant_bounded(["up", GUEST, "--provision"], timeout=600):
        Log.error("WSLPE one-attempt Vagrant recovery failed; no automatic retry")
        return False
    if not inspect_vmware_guest(provider) or not _guest_proof(
        provider, instance.ip_range, complete=True
    ):
        Log.error("WSLPE exercise NIC/VMTools proof missing; instance remains CREATED")
        return False
    instance.set_status(PROVIDED)
    Log.success(
        "WSLPE native Stage 1 recovered on the original VM: Tools, NAT, and "
        "exercise IP verified; scenarios/learner NOT installed."
    )
    return True
