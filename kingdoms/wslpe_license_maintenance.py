"""KINGDOMS native WSLPE-only automatic Windows evaluation maintenance.

Reuses the exact existing settings/eval_rearm role and the existing WSLPE
foundation licensing gate via an Ansible task tag. Never deploys a learner,
LPE scenario, guest, VMware network or NORTH resource. The temporary
Vagrant/WinRM management channel is bound to the registered VMX/NAT MAC
and retired only by the later independent operator handoff.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import subprocess

from goad.goadpath import GoadPath
from goad.log import Log
from goad.utils import CREATED, PROVIDED
from kingdoms.wslpe_stage1 import GUEST, inspect_vmware_guest, valid_prefix
from kingdoms.wslpe_stage1_repair import _guest_proof, _registered_guest_vmx


LICENSE_TAG = "wslpe_license"
TIMEOUT_SECONDS = 2100
# The only Windows mutation is in the pre-existing settings/eval_rearm role.
# This independent post-role query is read-only and never invokes slmgr.
READ_ONLY_LICENSE_PROOF = r"""
$ErrorActionPreference = 'Stop'
$c = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $c.PartOfDomain -or $os.ProductType -ne 1) {
    throw 'WSLPE_LICENSE_WRONG_WINDOWS_GUEST'
}
$products = @(Get-CimInstance SoftwareLicensingProduct -ErrorAction Stop |
    Where-Object { $_.Name -like 'Windows*' -and $_.PartialProductKey })
$eval = @($products | Where-Object {
    $_.Description -match 'TIMEBASED_EVAL'
} | Select-Object -First 1)
if ($eval.Count -gt 0) {
    if ([int64]$eval[0].GracePeriodRemaining -lt 1440) {
        throw 'WSLPE_LICENSE_EVALUATION_EXPIRED'
    }
} elseif (@($products | Where-Object { [int]$_.LicenseStatus -eq 1 }).Count -eq 0) {
    throw 'WSLPE_LICENSE_NOT_ACTIVATED'
}
Write-Output 'WSLPE_LICENSE_READY=PASS'
"""


def _exact_instance(manager):
    instance = manager.get_current_instance()
    if (instance is None or instance.lab_name != "WSLPE"
            or instance.provider_name != "vmware"
            or instance.provisioner_name != "local"
            or instance.extensions
            or instance.get_status() not in (CREATED, PROVIDED)
            or not valid_prefix(instance.ip_range)
            or manager.get_current_lab_name() != "WSLPE"):
        raise ValueError("Only the loaded native WSLPE guest may receive evaluation maintenance")
    root = Path(GoadPath.get_project_path()).resolve()
    workspace = Path(GoadPath.get_workspace_path())
    directory = Path(instance.instance_path)
    provider_dir = Path(instance.instance_provider_path)
    if (workspace.is_symlink() or directory.is_symlink() or provider_dir.is_symlink()
            or workspace.resolve() != root / "workspace"
            or directory.resolve() != workspace.resolve() / instance.instance_id
            or provider_dir.resolve() != directory.resolve() / "provider"):
        raise ValueError("WSLPE native instance or VMware provider belongs to another checkout")
    provider = manager.get_current_instance_provider()
    if (provider is None or getattr(provider, "lab_name", None) != "WSLPE"
            or Path(str(provider.path)).resolve() != provider_dir.resolve()
            or _registered_guest_vmx(provider) is None):
        raise ValueError("WSLPE guest does not match native Vagrant VMX registration")
    return instance, provider, root, directory


def _approved_inventory(root: Path, instance_dir: Path, address: str) -> tuple[Path, Path]:
    """Check source inventory resolves to exactly one standalone guest, BEFORE overrides."""
    native = instance_dir / "inventory"
    defaults = root / "ad/WSLPE/data/inventory"
    tool = Path.home() / ".goad/.venv/bin/ansible-inventory"
    for item in (native, defaults, tool):
        if not item.is_file() or item.is_symlink():
            raise ValueError("Native WSLPE inventory or Ansible binary unavailable")
    if not os.access(tool, os.X_OK):
        raise ValueError("Approved Ansible inventory executable unavailable")
    try:
        result = subprocess.run(
            [str(tool), "-i", str(native), "-i", str(defaults), "--list"],
            cwd=root, capture_output=True, text=True, check=False,
            timeout=45, stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0 or len(result.stdout) > 1_000_000:
            raise ValueError("Native WSLPE inventory failed resolution")
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ValueError("Cannot resolve exact native WSLPE inventory") from exc
    if not isinstance(data, dict):
        raise ValueError("Unexpected WSLPE inventory format")
    groups = data.get("_meta", {}).get("hostvars", {})
    host = groups.get("ws01", {}) if isinstance(groups, dict) else {}
    def members(name):
        group = data.get(name, {})
        return group.get("hosts", []) if isinstance(group, dict) else []
    if (members("wslpe") != ["ws01"]
            or members("windows_lpe_standalone") != ["ws01"]
            or members("dc") or members("domain")
            or not isinstance(host, dict)
            or host.get("ansible_host") != address
            or host.get("domain_name") != "WSLPE"
            or host.get("ansible_connection") != "winrm"
            or str(host.get("ansible_port")) != "5985"
            or host.get("ansible_winrm_scheme") != "http"
            or host.get("ansible_winrm_transport") != "ntlm"
            or host.get("ansible_user") != "vagrant"
            or host.get("ansible_password") != "vagrant"):
        raise ValueError("Source inventory is not the original WSLPE-only bootstrap channel")
    return native, defaults


def maintain_native_wslpe_license(manager, *, confirmed: bool = False) -> bool:
    """Run existing license role once and verify guest grace; no blind retries.

    Intended both as the final native Stage-1 readiness gate for future guests
    and as an explicitly confirmed recovery operation for an existing PROVIDED
    or completed CREATED Windows guest. Never creates or powers on a VM.
    """
    if confirmed is not True:
        Log.error("Exact WSLPE license-maintenance approval is required")
        return False
    try:
        instance, provider, root, directory = _exact_instance(manager)
        expected = str(ipaddress.IPv4Network(instance.ip_range + ".0/24").network_address + 31)
        port = provider._winrm_forwarded_port(GUEST)
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValueError("Native Vagrant forwarded management port unavailable")
        playbook = root / "ansible/wslpe-foundation.yml"
        ansible = Path.home() / ".goad/.venv/bin/ansible-playbook"
        if (not playbook.is_file() or playbook.is_symlink()
                or not ansible.is_file() or ansible.is_symlink()
                or not os.access(ansible, os.X_OK)):
            raise ValueError("Existing approved WSLPE foundation or Ansible unavailable")
        if not inspect_vmware_guest(provider):
            raise ValueError("The exact registered WSLPE guest is not running")
        if not _guest_proof(provider, instance.ip_range, complete=True):
            raise ValueError("Windows/NAT MAC/VMware Tools/exercise NIC attestation failed")
        native, defaults = _approved_inventory(root, directory, expected)
    except (OSError, ValueError) as exc:
        Log.error(f"WSLPE license preflight blocked: {exc}")
        return False

    # Only these two tagged tasks run: settings/eval_rearm and the existing
    # licensing gate. Learner creation, hostname and all scenarios are skipped.
    # No password is included in the command or log; the original WSLPE
    # bootstrap credentials are resolved from the existing operator inventory.
    env = os.environ.copy()
    env.update({
        "ANSIBLE_CONFIG": str(root / "ansible/ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(root / "ansible/roles"),
        "ANSIBLE_NOCOLOR": "1",
    })
    override = json.dumps({
        "ansible_host": "127.0.0.1",
        "ansible_port": port,
        "ansible_connection": "winrm",
        "ansible_winrm_scheme": "http",
        "ansible_winrm_transport": "ntlm",
    }, separators=(",", ":"))
    Log.info("WSLPE-only licensing: applying existing settings/eval_rearm role once")
    try:
        result = subprocess.run(
            [str(ansible), "-i", str(native), "-i", str(defaults),
             "--limit", "ws01", "--tags", LICENSE_TAG,
             str(playbook), "-e", override],
            cwd=root, env=env, capture_output=True, text=True, check=False,
            timeout=TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        Log.error(f"WSLPE licensing role interrupted: {type(exc).__name__}; no automatic retry")
        return False
    if result.returncode != 0:
        # Ansible diagnostics may contain credentials; never emit them.
        Log.error(f"Existing WSLPE evaluation role failed (exit {result.returncode}); no retry")
        return False
    if not inspect_vmware_guest(provider) or not _guest_proof(
        provider, instance.ip_range, complete=True
    ):
        Log.error("WSLPE identity or management path changed after license maintenance")
        return False
    try:
        result = provider._winrm_session(port).run_ps(READ_ONLY_LICENSE_PROOF)
    except Exception as exc:
        Log.error(f"WSLPE post-reboot license verification unavailable: {type(exc).__name__}")
        return False
    if (result.status_code != 0
            or result.std_out.count(b"WSLPE_LICENSE_READY=PASS") != 1):
        Log.error("Windows license still expired/unverified; no scenario installation authorized")
        return False
    Log.success(
        "WSLPE_LICENSE_READY=PASS on exact registered guest; "
        "no learner or scenarios installed"
    )
    return True
