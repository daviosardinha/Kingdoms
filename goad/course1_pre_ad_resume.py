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
            or data.get("status") != "ready for provisioning"):
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


# A single fourth clean-install instance stopped after WS01 rearm and before
# Ansible. Its first-boot Windows/WinRM work is complete after a manual verified
# VMware Tools repair. Recovery here must NOT become an unrestricted provider
# failure bypass for future installations.
REPAIRED_PROVIDER_INSTANCE = "8aafc9-north-vmware"
REPAIRED_PROVIDER_ATTEMPT = "20261024T231210Z-e678c23cc64a"
REPAIRED_PROVIDER_RESUME_MARKER = ".north-ws01-repaired-pre-ad-resume-used"


def assert_repaired_provider_north_resume(provider, manifest, start_playbook):
    """Read-only identity + receipt + live canonical guest proof for one instance.

    This authorizes ONLY Ansible.run_from('build.yml'), never Vagrant up,
    VMware networking reset, or fresh install. Controller must consume a
    one-shot marker before entering provider-managed provisioning.
    """
    from goad.course1_direct_winrm import (
        NorthGuestRecoveryBlocked, prove_canonical_guest,
    )

    if (getattr(provider, "lab_name", None) != "NORTH"
            or getattr(provider, "get_runtime_mode", lambda: None)() != "unknown"
            or not isinstance(manifest, list) or not manifest
            or manifest[0] != "build.yml" or start_playbook != "build.yml"):
        raise PreADResumeError("Repaired provider recovery requires NORTH unknown mode and build.yml")

    root = Path(str(getattr(provider, "path", "")))
    if (not root.is_absolute() or root.name != "provider"
            or root.is_symlink() or not root.is_dir()
            or root.parent.name != REPAIRED_PROVIDER_INSTANCE
            or root.parent.is_symlink() or root.resolve(strict=True) != root):
        raise PreADResumeError("Only the exact repaired NORTH provider is eligible")

    marker = root.parent / REPAIRED_PROVIDER_RESUME_MARKER
    if marker.exists() or marker.is_symlink():
        raise PreADResumeError("Repaired provider pre-AD resume was already attempted")

    metadata = root.parent / "instance.json"
    if not metadata.is_file() or metadata.is_symlink() or metadata.stat().st_size > 1048576:
        raise PreADResumeError("Original NORTH instance metadata missing or unsafe")
    try:
        state = json.loads(metadata.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise PreADResumeError("Original NORTH metadata unreadable") from exc
    if (not isinstance(state, dict)
            or (state.get("id"), state.get("lab"), state.get("provider"),
                state.get("status")) !=
            (REPAIRED_PROVIDER_INSTANCE, "NORTH", "vmware", "not provided")):
        raise PreADResumeError("Not the exact failed-before-Ansible instance")

    timing_dir = root.parent / "install-timings"
    if not timing_dir.is_dir() or timing_dir.is_symlink():
        raise PreADResumeError("Original failed-install receipt folder missing")
    receipts = sorted(timing_dir.glob("*.json"))
    if (len(receipts) != 1 or receipts[0].is_symlink()
            or receipts[0].stat().st_size > 1048576):
        raise PreADResumeError("Expected exactly one original install receipt")
    try:
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise PreADResumeError("Original receipt unreadable") from exc
    if (not isinstance(receipt, dict)
            or receipt.get("instance_id") != REPAIRED_PROVIDER_INSTANCE
            or receipt.get("attempt_id") != REPAIRED_PROVIDER_ATTEMPT
            or receipt.get("status") != "failed"
            or receipt.get("provider_success") is not False
            or receipt.get("ansible_phases") != []):
        raise PreADResumeError("Receipt does not prove the exact failed-before-Ansible attempt")
    phases = receipt.get("phases")
    if not isinstance(phases, list) or not all(isinstance(p, dict) for p in phases):
        raise PreADResumeError("Original provider phases missing or malformed")
    statuses = {
        p.get("label"): p.get("outcome")
        for p in phases if isinstance(p.get("label"), str)
    }
    if (len(statuses) != len(phases)
            or statuses.get("GOAD-ROUTER bring-up") != "succeeded"
            or statuses.get("Vagrant first creation GOAD-WS01") != "succeeded"
            or statuses.get("GOAD-WS01 VMware Tools / forwarded WinRM readiness") != "succeeded"):
        raise PreADResumeError("Receipt does not prove all original provider guests reached WS01 maintenance")

    if (set(getattr(provider, "goad_nomad_windows", ())) !=
            EXPECTED_GUESTS - {"GOAD-ROUTER"}):
        raise PreADResumeError("NORTH expected Windows roster differs")
    for machine in EXPECTED_GUESTS:
        vmx = provider._vmx_path(machine)
        ident = root / ".vagrant" / "machines" / machine / "vmware_desktop" / "id"
        directory = ident.parent
        if (not isinstance(vmx, str) or not vmx
                or not ident.is_file() or ident.is_symlink()
                or not Path(vmx).is_file() or Path(vmx).is_symlink()
                or not Path(vmx).resolve(strict=True).is_relative_to(
                    directory.resolve(strict=True))
                or ident.read_text(encoding="utf-8").strip() != vmx):
            raise PreADResumeError("Repaired provider guest VMX is missing or foreign: " + machine)

    running = provider._running_instance_vms()
    if running is None or len(running) != 5 or set(running) != EXPECTED_GUESTS:
        raise PreADResumeError("All five original NORTH VMX guests must be running")

    # Reconfirm current authenticated OS/service/IP/MAC/gateway state. A
    # previously captured terminal screenshot is NOT sufficient authorization.
    for machine in ("GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"):
        try:
            prove_canonical_guest(root, machine, timeout=45)
        except (NorthGuestRecoveryBlocked, OSError, ValueError) as exc:
            raise PreADResumeError(
                "Live canonical guest verification failed: " + machine
            ) from exc

    return (
        "NORTH one original failed-before-Ansible provider receipt verified",
        "All five original VMX guests running; four Windows endpoints strictly canonical",
        "No Vagrant replay or previous Ansible playbook execution authorized",
    )


def consume_repaired_provider_resume(provider):
    """Atomically consume the one authorized recovery attempt before Ansible.

    Do not remove the marker on failure: later attempts must be independently
    reviewed rather than replaying the first build.yml and AD promotion steps.
    """
    root = Path(str(getattr(provider, "path", "")))
    if (root.name != "provider" or root.parent.name != REPAIRED_PROVIDER_INSTANCE
            or not root.is_dir() or root.is_symlink() or
            root.resolve(strict=True) != root):
        raise PreADResumeError("Not the exact repaired NORTH provider")
    marker = root.parent / REPAIRED_PROVIDER_RESUME_MARKER
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(marker, flags, 0o600)
    except FileExistsError as exc:
        raise PreADResumeError("The repaired provider resume has already been consumed") from exc
    except OSError as exc:
        raise PreADResumeError("Cannot establish exclusive one-shot resume marker") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(
                "NORTH repaired provider resume for "
                + REPAIRED_PROVIDER_INSTANCE
                + "\nAttempt "
                + REPAIRED_PROVIDER_ATTEMPT
                + "\nAuthorized first playbook: build.yml\n"
            )
    except OSError as exc:
        # Preserve a partially written marker: fail-closed/no repeat.
        raise PreADResumeError("Resume marker write failed; do not replay") from exc
    return "NORTH repaired provider one-shot authorization consumed"
