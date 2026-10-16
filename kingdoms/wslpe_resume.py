"""Resume ONLY an existing, powered-off native Kingdoms WSLPE guest.

Reuse the standard Kingdoms VMware/Vagrant command executor, without creating a
new native instance, running Ansible, provisioning vulnerabilities, or changing
NORTH. A registered VMX is necessary but not sufficient: the same exact VM must
be absent from VMware's running inventory and Vagrant must explicitly report
'not running (vmware_desktop)' before a single authorized resume attempt.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import subprocess
import tempfile

from goad.goadpath import GoadPath
from goad.log import Log
from goad.utils import PROVIDED

GUEST = "WSLPE-WS01"


@contextmanager
def direct_winrm_resume_file(provider_dir: Path):
    """Use direct WinRM only for an existing registered WSLPE guest's resume.

    Fresh Stage-1 bootstrap retains the normal NAT communicator while Windows
    configures its private NIC. The original instance Vagrantfile is untouched.
    """
    source_file = provider_dir / "Vagrantfile"
    if source_file.is_symlink() or not source_file.is_file():
        raise ValueError("WSLPE Vagrantfile missing or symlinked")
    source = source_file.read_text(encoding="utf-8")
    needle = 'target.vm.communicator = "winrm"'
    if (source.count(needle) != 1
        or source.count(':name => "WSLPE-WS01"') != 1
        or source.count('target.vm.network :private_network, ip: box[:ip]') != 1
        or "target.winrm.host =" in source):
        raise ValueError("WSLPE WinRM resume configuration is ambiguous")
    # box[:ip] comes from this instance's validated private exercise prefix,
    # never a hardcoded operator-machine address or NORTH management network.
    replacement = (needle + '\n'
                   '        target.winrm.host = box[:ip]\n'
                   '        target.winrm.port = 5985')
    fd, temporary = tempfile.mkstemp(
        prefix="Vagrantfile.wslpe-resume-", dir=str(provider_dir)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(source.replace(needle, replacement, 1))
        yield Path(temporary).name
    finally:
        Path(temporary).unlink(missing_ok=True)



def inspect_powered_off(manager) -> tuple[object, Path] | None:
    instance = manager.get_current_instance()
    if instance is None or instance.lab_name != "WSLPE":
        Log.error("Load the existing WSLPE instance before resuming")
        return None
    if (instance.provider_name != "vmware"
        or instance.provisioner_name != "local"
        or instance.extensions
        or instance.get_status() != PROVIDED):
        Log.error("WSLPE native provider, provisioning or instance status differs")
        return None

    provider = manager.get_current_instance_provider()
    if provider is None or getattr(provider, "lab_name", None) != "WSLPE":
        Log.error("Current VMware provider is not the registered WSLPE provider")
        return None
    root = Path(GoadPath.get_project_path()).resolve()
    workspace = Path(GoadPath.get_workspace_path())
    instance_dir = Path(instance.instance_path)
    provider_dir = Path(instance.instance_provider_path)
    if (workspace.is_symlink() or instance_dir.is_symlink()
        or provider_dir.is_symlink()
        or workspace.resolve() != root / "workspace"
        or instance_dir.resolve().parent != workspace.resolve()
        or provider_dir.resolve().parent != instance_dir.resolve()
        or Path(str(provider.path)).resolve() != provider_dir.resolve()):
        Log.error("WSLPE instance/provider paths do not belong to this checkout")
        return None

    registration = (provider_dir / ".vagrant" / "machines"
                    / GUEST / "vmware_desktop" / "id")
    if not registration.is_file() or registration.is_symlink():
        Log.error("WSLPE's existing Vagrant registration is missing")
        return None
    try:
        raw_vmx = registration.read_text(encoding="utf-8").strip()
        if not Path(raw_vmx).is_absolute():
            raise ValueError("not absolute")
        vmx = Path(raw_vmx).resolve(strict=True)
        if (not vmx.is_file() or vmx.suffix.lower() != ".vmx"
            or "GOAD-" in str(vmx).upper()
            or "NORTH-VMWARE" in str(vmx).upper()):
            raise ValueError("not a dedicated WSLPE VMX")
        source = (provider_dir / "Vagrantfile").read_text(encoding="utf-8")
        if source.count(':name => "WSLPE-WS01"') != 1:
            raise ValueError("WSLPE Vagrant definition is ambiguous")
    except (OSError, ValueError):
        Log.error("Existing WSLPE VMX/Vagrant definition is unreadable or ambiguous")
        return None

    try:
        running = subprocess.run(
            ["vmrun", "-T", "ws", "list"],
            check=False, capture_output=True, text=True, timeout=30,
        )
        status = subprocess.run(
            ["vagrant", "status", GUEST],
            cwd=str(provider_dir), check=False,
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        Log.error("Cannot establish current VMware and Vagrant machine state")
        return None
    if running.returncode != 0 or status.returncode != 0:
        Log.error("VMware inventory or Vagrant status command failed")
        return None
    lines = running.stdout.splitlines()
    if not lines or not lines[0].startswith("Total running VMs:"):
        Log.error("VMware running-VM inventory is not authoritative")
        return None
    try:
        expected_count = int(lines[0].partition(":")[2].strip())
    except ValueError:
        Log.error("VMware running-VM count is invalid")
        return None
    paths = [Path(line.strip()).resolve() for line in lines[1:] if line.strip()]
    if len(paths) != expected_count or vmx in paths:
        Log.error("WSLPE is running or VMware inventory is inconsistent; no resume")
        return None
    # Require exact existing registered guest and powered-off VMware provider.
    # Vagrant's 'not created', 'saved', 'aborted' and unknown states are unsafe.
    if not re.search(
        rf"(?m)^\s*{re.escape(GUEST)}\s+not running\s+\(vmware_desktop\)\s*$",
        status.stdout,
    ):
        Log.error("Vagrant has not confirmed a safely powered-off WSLPE guest")
        return None
    Log.info(f"Existing registered WSLPE guest is stopped: {vmx.name}")
    Log.info("NORTH guests are excluded by exact VMX registration")
    return provider, vmx


def resume_existing_wslpe(manager, *, confirmed: bool) -> bool:
    """Single controlled provider resume, no instance creation or provisioning."""
    if not confirmed:
        Log.error("Exact confirmation RESUME WSLPE is required")
        return False
    inspected = inspect_powered_off(manager)
    if inspected is None:
        return False
    provider, vmx = inspected
    try:
        # The original Vagrantfile stays unchanged for fresh Stage-1 bootstrap.
        # Scope the proven direct WinRM communicator to this resume subprocess.
        # Keep the canonical command executor and --no-provision safeguard.
        with direct_winrm_resume_file(Path(str(provider.path))) as filename:
            previous = os.environ.get("VAGRANT_VAGRANTFILE")
            try:
                os.environ["VAGRANT_VAGRANTFILE"] = filename
                started = bool(provider.command.run_vagrant(
                    ["up", GUEST, "--no-provision"], provider.path
                ))
            finally:
                if previous is None:
                    os.environ.pop("VAGRANT_VAGRANTFILE", None)
                else:
                    os.environ["VAGRANT_VAGRANTFILE"] = previous
    except Exception as exc:
        Log.error(f"WSLPE resume failed: {type(exc).__name__}; no automatic retry")
        return False
    if not started:
        Log.error("WSLPE resume failed; inspect the registered instance, do not retry")
        return False
    try:
        listed = subprocess.run(
            ["vmrun", "-T", "ws", "list"], capture_output=True, text=True,
            check=False, timeout=30,
        )
        paths = [Path(line.strip()).resolve() for line in listed.stdout.splitlines()[1:]
                 if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        Log.error("Cannot verify WSLPE VMware runtime after resume")
        return False
    if (listed.returncode != 0
        or not listed.stdout.startswith("Total running VMs:")
        or paths.count(vmx) != 1):
        Log.error("Resumed WSLPE is not uniquely confirmed running; inspect manually")
        return False
    Log.success(f"Existing native Kingdoms WSLPE guest resumed: {vmx.name}")
    Log.warning(
        "Instance stays PROVIDED, NOT READY. Recheck forwarded WinRM firewall, "
        "Windows baseline and dedicated exercise NIC before further changes."
    )
    return True
