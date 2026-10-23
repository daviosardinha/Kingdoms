"""One-time, read-only receipt gate for interrupted NORTH's first Ansible playbook.

This is deliberately *not* a general provisioning-mode bypass. A previous
fresh attempt must have created precisely the five native VMware guests and
failed at the initial pre-AD management preflight before running a playbook.
Existing/partially provisioned AD instances use normal AD-aware recovery.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class PreADResumeError(ValueError):
    pass


EXPECTED_GUESTS = frozenset({
    "GOAD-ROUTER", "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"
})


def assert_pre_ad_north_resume(provider, manifest, start_playbook):
    """Validate the exact native instance/receipt and live registered guests.

    This does not start, provision, change the network or create an authorization
    record. The controller must separately require its signed NORTH owner gate.
    """
    if (getattr(provider, "lab_name", None) != "NORTH"
            or getattr(provider, "get_runtime_mode", lambda: None)() != "unknown"
            or not isinstance(manifest, list) or not manifest
            or manifest[0] != "build.yml"
            or start_playbook != manifest[0]):
        raise PreADResumeError("Pre-AD recovery requires NORTH unknown mode and first manifest playbook")

    root = Path(str(getattr(provider, "path", "")))
    if (not root.is_absolute() or root.is_symlink() or not root.is_dir()
            or root.name != "provider" or root.parent.is_symlink()
            or not root.parent.name.endswith("-north-vmware")
            or root.resolve(strict=True) != root):
        raise PreADResumeError("Pre-AD recovery provider identity is not canonical")

    instance_path = root.parent / "instance.json"
    if not instance_path.is_file() or instance_path.is_symlink():
        raise PreADResumeError("Pre-AD NORTH instance metadata is absent")
    try:
        data = json.loads(instance_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise PreADResumeError("Pre-AD NORTH instance metadata is invalid") from exc
    if (not isinstance(data, dict) or data.get("id") != root.parent.name
            or data.get("lab") != "NORTH" or data.get("provider") != "vmware"
            or data.get("status") == "ready"):
        raise PreADResumeError("Pre-AD recovery instance identity/status differs")

    receipts = root.parent / "install-timings"
    if not receipts.is_dir() or receipts.is_symlink():
        raise PreADResumeError("Pre-AD recovery install receipts are missing")
    paths = sorted(receipts.glob("*.json"))
    if len(paths) != 1 or paths[0].is_symlink() or paths[0].stat().st_size > 1048576:
        raise PreADResumeError("Pre-AD recovery requires one unambiguous install attempt")
    try:
        receipt = json.loads(paths[0].read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise PreADResumeError("Pre-AD recovery receipt unreadable") from exc
    phases = receipt.get("ansible_phases") if isinstance(receipt, dict) else None
    if (not isinstance(receipt, dict) or receipt.get("provider_success") is not True
            or receipt.get("status") != "failed"
            or not isinstance(phases, list) or len(phases) != 1
            or not isinstance(phases[0], dict)
            or phases[0].get("label") != "Provisioning management-plane preparation"
            or phases[0].get("outcome") != "failed"):
        raise PreADResumeError("Pre-AD recovery lacks exact failed-before-first-playbook receipt")

    # The provider inventory only counts the five EXACT Vagrant-registered VMX
    # files; test their actual paths as well rather than trusting cached
    # Vagrant global-status entries or historical install receipts.
    if set(getattr(provider, "goad_nomad_windows", ())) != EXPECTED_GUESTS - {"GOAD-ROUTER"}:
        raise PreADResumeError("Pre-AD NORTH guest roster differs")
    for machine in EXPECTED_GUESTS:
        vmx = provider._vmx_path(machine)
        ident = root / ".vagrant" / "machines" / machine / "vmware_desktop" / "id"
        if (not isinstance(vmx, str) or not vmx
                or not ident.is_file() or ident.is_symlink()
                or not Path(vmx).is_file() or Path(vmx).is_symlink()
                or not Path(vmx).resolve(strict=True).is_relative_to(
                    (root / ".vagrant" / "machines" / machine / "vmware_desktop").resolve(strict=True)
                )
                or ident.read_text(encoding="utf-8").strip() != vmx):
            raise PreADResumeError("Pre-AD NORTH VMX registration missing or foreign: " + machine)

    running = provider._running_instance_vms()
    if running is None or len(running) != 5 or set(running) != EXPECTED_GUESTS:
        raise PreADResumeError("Pre-AD recovery requires all five original guests running")

    return ("NORTH signed instance receipt failed before first playbook",
            "All five exact registered NORTH VMX guests are running")
