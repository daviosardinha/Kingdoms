"""Stage-1 native WSLPE boot through the existing Kingdoms instance/provider.

Private operator control plane only. No direct or parallel Vagrant project,
no local learner provisioning, no LPE fixtures, no auto-reset or destroy.
This stage can at most mark the separate WSLPE instance PROVIDED, never READY.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

from goad.goadpath import GoadPath
from goad.log import Log
from goad.utils import CREATED, PROVIDED

GUEST = "WSLPE-WS01"
EXPECTED_LAB = "WSLPE"
EXPECTED_PROVIDER = "vmware"
EXPECTED_PROVISIONER = "local"
ACCEPTANCE = "KINGDOMS WSLPE OFFLINE ACCEPTANCE: 13 PASS / 0 FAIL"


def valid_prefix(raw: str) -> bool:
    """Use canonical network gate semantics without hardcoding the subnet."""
    import ipaddress
    if not re.fullmatch(r"(?:\d{1,3}\.){2}\d{1,3}", raw or ""):
        return False
    try:
        subnet = ipaddress.ip_network(raw + ".0/24", strict=True)
    except ValueError:
        return False
    return (
        subnet.is_private
        and not subnet.is_loopback
        and not subnet.is_link_local
        and not subnet.overlaps(ipaddress.ip_network("10.4.0.0/16"))
    )


def preboot_acceptance(prefix: str, root: Path) -> bool:
    """Run the same consolidated offline gate from the native operator path."""
    tool = root / "scripts/wslpe-acceptance.py"
    if not tool.is_file():
        Log.error("Missing committed WSLPE consolidated acceptance gate")
        return False
    command = [sys.executable, str(tool), "--ip-range", prefix]
    Log.info("Kingdoms: running consolidated WSLPE preboot acceptance")
    try:
        completed = subprocess.run(
            command, cwd=str(root), text=True, capture_output=True,
            check=False, timeout=480,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        Log.error(f"WSLPE offline acceptance unavailable: {type(exc).__name__}")
        return False

    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0 or ACCEPTANCE not in output:
        Log.error("WSLPE offline acceptance failed. No instance was created.")
        for line in output.splitlines()[-48:]:
            print(line)
        return False
    Log.success(ACCEPTANCE)
    return True


def inspect_vmware_guest(provider) -> bool:
    """Prove a unique registered WSLPE VMX is running; do not inspect NORTH."""
    if getattr(provider, "lab_name", None) != EXPECTED_LAB:
        Log.error("VMware provider unexpectedly targets another lab")
        return False
    project_dir = Path(str(provider.path)).resolve()
    machine_state = (
        project_dir / ".vagrant/machines" / GUEST / "vmware_desktop" / "id"
    )
    if not machine_state.is_file() or machine_state.is_symlink():
        Log.error("WSLPE Vagrant VM registration evidence missing")
        return False
    try:
        vmx_string = machine_state.read_text(encoding="utf-8").strip()
        vmx_path = Path(vmx_string).resolve(strict=True)
    except (OSError, ValueError):
        Log.error("WSLPE Vagrant VMX path is not readable")
        return False
    if vmx_path.suffix.lower() != ".vmx" or not vmx_path.is_file():
        Log.error("WSLPE registered machine does not point to a VMX file")
        return False
    if any(forbidden in str(vmx_path).upper() for forbidden in
           ("GOAD-WS01", "GOAD-DC", "GOAD-SRV", "GOAD-ROUTER")):
        Log.error("WSLPE resolved to an existing NORTH VMX; refusing")
        return False
    try:
        result = subprocess.run(
            ["vmrun", "-T", "ws", "list"], capture_output=True,
            text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        Log.error("Cannot verify independent VMware running-guest state")
        return False
    if result.returncode != 0 or not result.stdout.startswith("Total running VMs:"):
        Log.error("VMware running-guest inventory was not authoritative")
        return False
    running = {
        str(Path(line.strip()).resolve())
        for line in result.stdout.splitlines()[1:] if line.strip()
    }
    if str(vmx_path) not in running:
        Log.error("WSLPE is not independently confirmed running by VMware")
        return False
    Log.success(f"Native Kingdoms WSLPE guest running: {vmx_path.name}")
    Log.warning(
        "Actual VMware NIC isolation, Windows identity, local learner and "
        "Windows LPE scenario results have NOT been validated."
    )
    return True


def bootstrap_native_wslpe(manager, prefix: str, *, confirmed: bool) -> bool:
    """One-shot native Kingdoms instance creation, followed by provider-only boot.

    A failed/partial VMware boot remains in the WSLPE workspace for inspection.
    No automatic retry, deletion, NORTH operation, Ansible role or exploit fixture.
    """
    if not confirmed:
        Log.error("Exact operator confirmation CREATE WSLPE is required")
        return False
    if not valid_prefix(prefix):
        Log.error("Invalid WSLPE /24 prefix. NORTH ranges are forbidden.")
        return False
    settings = manager.current_settings
    if (
        manager.get_current_lab_name() != EXPECTED_LAB
        or manager.get_current_provider_name() != EXPECTED_PROVIDER
        or settings.provisioner_name != EXPECTED_PROVISIONER
        or settings.extensions_name
    ):
        Log.error("WSLPE requires a bare native VMware/local instance without extensions")
        return False
    if manager.get_current_instance() is not None:
        Log.error("An instance is already loaded; do not overwrite or retry a VM")
        return False
    root = Path(GoadPath.get_project_path()).resolve()
    workspace = Path(GoadPath.get_workspace_path())
    # Never follow a symlink to a different checkout (e.g. an active NORTH lab).
    if workspace.is_symlink() or workspace.parent.resolve() != root:
        Log.error("Kingdoms workspace is not local to this checkout")
        return False
    if not preboot_acceptance(prefix, root):
        return False
    try:
        workspace.mkdir(mode=0o755, exist_ok=True)
    except OSError as exc:
        Log.error(f"Cannot prepare local Kingdoms workspace: {exc}")
        return False

    # Reuse the native LabManager, LabInstance and VMware provider, preserving
    # the exact same instance.json / workspace / Vagrantfile scheme as NORTH.
    manager.set_ip_range(prefix)
    if manager.get_ip_range() != prefix:
        Log.error("Kingdoms refused the selected WSLPE subnet")
        return False
    if not manager.create_instance():
        Log.error("Kingdoms native WSLPE instance creation failed")
        return False

    instance = manager.get_current_instance()
    if instance is None or any((
        instance.lab_name != EXPECTED_LAB,
        instance.provider_name != EXPECTED_PROVIDER,
        instance.provisioner_name != EXPECTED_PROVISIONER,
        instance.ip_range != prefix,
        instance.get_status() != CREATED,
    )):
        Log.error("Generated instance identity/status mismatch. Do not retry automatically.")
        return False

    instance_dir = Path(instance.instance_path)
    provider_dir = Path(instance.instance_provider_path)
    try:
        if (instance_dir.is_symlink() or provider_dir.is_symlink()
            or instance_dir.resolve().parent != workspace.resolve()
            or provider_dir.resolve().parent != instance_dir.resolve()):
            Log.error("Native WSLPE instance paths did not stay in this workspace")
            return False
        source = (provider_dir / "Vagrantfile").read_text(encoding="utf-8")
    except OSError:
        Log.error("Native WSLPE generated provider Vagrantfile missing")
        return False
    if source.count(':name => "WSLPE-WS01"') != 1 or ':name => "GOAD-' in source:
        Log.error("Native WSLPE Vagrantfile machine inventory is not unique")
        return False
    provider = manager.get_current_instance_provider()
    if provider is None or getattr(provider, "lab_name", None) != EXPECTED_LAB:
        Log.error("Native VMware provider does not belong to WSLPE")
        return False
    if Path(str(provider.path)).resolve() != provider_dir.resolve():
        Log.error("Kingdoms VMware provider path is not the new instance")
        return False

    Log.info("Kingdoms native provider: first WSLPE guest-only boot")
    try:
        created = bool(provider.install())
    except Exception as exc:
        Log.error(f"WSLPE first boot interrupted: {type(exc).__name__}. Inspect state manually.")
        return False
    if not created:
        Log.error(
            "WSLPE Vagrant boot failed. Instance remains for evidence; "
            "never retry or destroy without reconciliation."
        )
        return False
    if not inspect_vmware_guest(provider):
        Log.error("WSLPE VM boot not independently proven. Do not provision.")
        return False

    instance.set_status(PROVIDED)
    Log.success(
        "WSLPE STAGE 1 COMPLETE: native guest running, instance status PROVIDED. "
        "The course is NOT READY and vulnerabilities have NOT been installed."
    )
    return True
