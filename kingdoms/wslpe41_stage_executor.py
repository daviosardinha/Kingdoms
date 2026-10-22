"""Execute a single *Ansible* WSLPE41 stage against one registered native guest.

This is deliberately NOT a fresh-install runner. The caller must first create
and independently attest the new Windows guest, its credentials, TLS trust and
out-of-band JEA recovery. In particular, this module cannot activate #30.
It neither changes VMware networking nor interacts with NORTH lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess

from kingdoms.wslpe41_fresh_contract import FreshScenario
from kingdoms.wslpe41_host_preflight import HostEvidenceBlocked, read_only_command
from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked, StageProof
from kingdoms.wslpe41_native_identity import inspect_native_registration
from kingdoms.wslpe41_runtime_proof import (
    ObservedStageResult, RuntimeProofBlocked, verify_observed_stage,
)
from kingdoms.wslpe41_stage_commands import StagePlanBlocked, build_stage_invocation


@dataclass(frozen=True)
class AnsibleStageContext:
    identity: FreshGuestIdentity
    instance_dir: Path
    ansible: Path
    inventory: Path
    private_vars: Path
    expected_address: str  # learner/exercise target, not the WinRM transport
    timeout_seconds: int = 900
    management_address: str | None = None  # separately isolated HTTPS/5986 endpoint


def _regular(path: Path, *, private: bool = False) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise InstallBlocked("WSLPE41 stage input missing, linked or non-absolute")
    if private and (path.stat().st_uid != os.geteuid() or path.stat().st_mode & 0o077):
        raise InstallBlocked("WSLPE41 private stage input must be owner-only")


def _guest(context: AnsibleStageContext) -> None:
    """Read-only check against the *exact* registered, running native VMX."""
    identity = context.identity
    instance = context.instance_dir
    if (not instance.is_absolute() or instance.is_symlink()
            or instance.name != identity.instance_id
            or str(instance.parent) != identity.workspace):
        raise InstallBlocked("WSLPE41 stage is not bound to its native workspace")
    try:
        registration = inspect_native_registration(
            instance, read_only_command("vmrun", "-T", "ws", "list")
        )
    except HostEvidenceBlocked as exc:
        raise InstallBlocked("Exact WSLPE41 native guest is not running") from exc
    if (registration.instance_id != identity.instance_id
            or registration.vmx != identity.vmx
            or registration.subnet != identity.subnet
            or registration.guest_address != context.expected_address):
        raise InstallBlocked("WSLPE41 native guest identity changed")


def _environment(context: AnsibleStageContext) -> dict[str, str]:
    env = os.environ.copy()
    if (env.get("KINGDOMS_WSLPE_INSTANCE_ID") != context.identity.instance_id
            or len(env.get("KINGDOMS_WSLPE_LEARNER_PASSWORD", "")) < 12
            or len(env.get("KINGDOMS_WSLPE_OPERATOR_PASSWORD", "")) < 24
            or env.get("KINGDOMS_WSLPE_FIXTURE_VARS_FILE") != str(context.private_vars)):
        raise InstallBlocked("Fresh WSLPE41 instance-scoped private environment is missing")
    repo = Path(__file__).resolve().parents[1]
    env.update({
        "ANSIBLE_CONFIG": str(repo / "ansible" / "ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(repo / "ansible" / "roles"),
        "ANSIBLE_NOCOLOR": "1",
    })
    return env


def _inventory(context: AnsibleStageContext, env: dict[str, str]) -> None:
    """Resolve effective hostvars, not merely inventory file text."""
    tool = context.ansible.with_name("ansible-inventory")
    _regular(tool)
    if not os.access(tool, os.X_OK):
        raise InstallBlocked("Approved Ansible inventory executable is unavailable")
    try:
        result = subprocess.run(
            [str(tool), "-i", str(context.inventory), "-i",
             str(context.private_vars), "--list"],
            cwd=Path(__file__).resolve().parents[1], env=env,
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            timeout=45, check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 1_000_000:
            raise InstallBlocked("Fresh WSLPE41 inventory resolution failed")
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as exc:
        raise InstallBlocked("Fresh WSLPE41 inventory resolution failed") from exc
    if not isinstance(data, dict):
        raise InstallBlocked("Fresh WSLPE41 inventory is invalid")
    hostvars = data.get("_meta", {}).get("hostvars", {})
    guest = hostvars.get("ws01", {}) if isinstance(hostvars, dict) else {}
    def members(group: str) -> list:
        entry = data.get(group, {})
        return entry.get("hosts", []) if isinstance(entry, dict) else []
    management_target = context.management_address or context.expected_address
    # For the guarded existing-instance handoff, the HTTPS transport must
    # use vmnet4; scenario parameters must still refer to learner vmnet3.
    if context.management_address is not None and (
            context.management_address != "172.28.233.31"
            or context.expected_address != "172.28.232.31"):
        raise InstallBlocked("Fresh WSLPE management and learner IP roles are mismatched")
    if (members("wslpe") != ["ws01"]
            or members("windows_lpe_standalone") != ["ws01"]
            or members("dc") or members("domain")
            or not isinstance(guest, dict)
            or guest.get("ansible_host") != management_target
            or guest.get("ansible_connection") != "winrm"
            or guest.get("ansible_winrm_scheme") != "https"
            or str(guest.get("ansible_port")) != "5986"
            or guest.get("ansible_winrm_server_cert_validation") != "validate"
            or guest.get("domain_name") != "WSLPE"):
        raise InstallBlocked("Inventory is not the exact isolated HTTPS WSLPE guest")


def run_ansible_stage(
    context: AnsibleStageContext, scenario: FreshScenario, stage: str,
) -> StageProof:
    """Run and prove one stage; no retries, no raw transcript in the journal."""
    if not 60 <= context.timeout_seconds <= 3600:
        raise InstallBlocked("WSLPE41 stage timeout outside approved bounds")
    if (context.inventory.parent != context.instance_dir / "ansible"
            or context.private_vars.parent != context.instance_dir / "ansible"):
        raise InstallBlocked("WSLPE41 stage inventory must belong to this instance")
    _regular(context.ansible)
    _regular(context.inventory)
    _regular(context.private_vars, private=True)
    if not os.access(context.ansible, os.X_OK):
        raise InstallBlocked("Approved Ansible executable is unavailable")
    _guest(context)
    env = _environment(context)
    _inventory(context, env)
    try:
        invocation = build_stage_invocation(
            scenario, stage, ansible=context.ansible,
            inventory=context.inventory, varsfile=context.private_vars,
            expected_address=context.expected_address,
            instance_id=context.identity.instance_id,
        )
    except StagePlanBlocked as exc:
        raise InstallBlocked("Unapproved WSLPE41 stage invocation") from exc
    if invocation.transport != "ansible" or not invocation.argv:
        raise InstallBlocked("JEA #30 activation requires independent guest console")
    try:
        result = subprocess.run(
            list(invocation.argv), cwd=Path(__file__).resolve().parents[1],
            env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
            timeout=context.timeout_seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallBlocked("WSLPE41 Ansible stage failed or timed out") from exc
    # Recheck the exact running VMX after the guest mutation, before accepting proof.
    _guest(context)
    try:
        return verify_observed_stage(
            invocation,
            ObservedStageResult(
                instance_id=context.identity.instance_id,
                vmx=context.identity.vmx,
                transport="ansible", returncode=result.returncode,
                stdout=result.stdout, stderr=result.stderr,
            ),
            expected_instance_id=context.identity.instance_id,
            expected_vmx=context.identity.vmx,
        )
    except RuntimeProofBlocked as exc:
        raise InstallBlocked(
            f"WSLPE41 scenario #{scenario.number} {stage}: runtime proof missing"
        ) from exc
