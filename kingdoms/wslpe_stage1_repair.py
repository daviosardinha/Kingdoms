"""Explicit, one-attempt recovery of a partially created native WSLPE guest.

This is the existing LabManager/VMware provider, existing Vagrant provisioners
(including vagrant/fix_ip.ps1), and existing VMTools installer. No new VM,
VMnet, network manager, guest account, scenario runner, or GOAD/NORTH actions.
A failed attempt remains CREATED. Never automatically replay after failure.
"""
from __future__ import annotations

import ipaddress
from pathlib import Path

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
    if not inspect_vmware_guest(provider):
        Log.error("Existing native WSLPE guest is not running under its registered VMX")
        return None
    return instance, provider


def _guest_proof(provider, prefix: str, *, complete: bool) -> bool:
    """Proof over the registered provider's forwarded WinRM management path."""
    expected = str(ipaddress.IPv4Network(prefix + ".0/24").network_address + 31)
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
