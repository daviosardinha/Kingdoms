"""NORTH-only offline VMware snapshot restoration with exact group selection.

Vagrant's snapshot pop can select the parent push_ snapshot when VMware's
nested snapshot tree contains parent/child names, and some VMware plugin builds
boot guests during pop even with --no-start. Neither behavior is safe while the
segmented NORTH exercise networking must remain offline until normalization.

This helper never calls Vagrant and never starts, provisions or changes a NIC.
The caller must have verified native NORTH ownership and stopped the range.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


NORTH_VMS = ("GOAD-ROUTER", "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01")
_PUSH = re.compile(r"^push_([0-9]{10,})_([0-9]+)$")


class NorthSnapshotRestoreError(RuntimeError):
    pass


def _run_vmrun(args, *, timeout=60, runner=subprocess.run):
    try:
        result = runner(["vmrun", "-T", "ws", *args], capture_output=True,
                        text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NorthSnapshotRestoreError(
            f"VMware snapshot command unavailable: {args[0]}: {exc}"
        ) from exc
    if result.returncode != 0:
        raise NorthSnapshotRestoreError(
            f"VMware snapshot {args[0]} failed: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout


def _exact_original_vmx(provider, machine, supplied):
    parent = provider / ".vagrant" / "machines" / machine / "vmware_desktop"
    identifier = parent / "id"
    if (not identifier.is_file() or identifier.is_symlink()
            or not parent.is_dir() or parent.is_symlink()):
        raise NorthSnapshotRestoreError(f"Missing original {machine} Vagrant VMX ID")
    try:
        raw = identifier.read_text(encoding="utf-8").strip()
        vmx = Path(raw)
        registered = Path(str(supplied or ""))
        correct_parent = parent.resolve(strict=True)
        # VMX is beneath its own VMware-desktop machine directory, in a
        # versioned subdirectory. Neither a reused VMX from a different lab
        # nor a symlink is accepted.
        if (not raw or not vmx.is_absolute() or registered != vmx
                or not vmx.is_file() or vmx.is_symlink()
                or not vmx.resolve(strict=True).is_relative_to(correct_parent)):
            raise NorthSnapshotRestoreError(f"Foreign or missing VMX: {machine}")
    except (OSError, ValueError) as exc:
        raise NorthSnapshotRestoreError(f"Unreadable VMX identity: {machine}") from exc
    return str(vmx)


def _running_vm_paths(*, runner):
    output = _run_vmrun(["list"], runner=runner)
    lines = output.splitlines()
    if not lines or not lines[0].startswith("Total running VMs:"):
        raise NorthSnapshotRestoreError("Unrecognized vmrun running-VM inventory")
    return set(lines[1:])


def select_north_snapshot_targets(provider_dir, vmx_lookup, *, runner=subprocess.run):
    """Read-only; returns five exact original VMX -> newest push_ snapshot pairs."""
    provider = Path(provider_dir)
    if (not provider.is_absolute() or provider.is_symlink() or not provider.is_dir()
            or provider.resolve(strict=True) != provider
            or provider.name != "provider" or not provider.parent.name.endswith("-north-vmware")):
        raise NorthSnapshotRestoreError("Expected canonical original NORTH VMware provider")

    running = _running_vm_paths(runner=runner)
    pairs = []
    timelines = []
    for machine in NORTH_VMS:
        vmx = _exact_original_vmx(provider, machine, vmx_lookup(machine))
        if vmx in running:
            raise NorthSnapshotRestoreError(f"{machine} is running; offline restore refused")
        output = _run_vmrun(["listSnapshots", vmx], runner=runner)
        lines = output.splitlines()
        if not lines or not lines[0].startswith("Total snapshots:"):
            raise NorthSnapshotRestoreError(f"{machine} snapshot inventory is invalid")
        names = []
        for name in lines[1:]:
            name = name.strip()
            match = _PUSH.fullmatch(name)
            if match:
                names.append((int(match.group(1)), name))
        if not names or len(set(name for _, name in names)) != len(names):
            raise NorthSnapshotRestoreError(f"Unambiguous push snapshots missing on {machine}")
        names.sort()
        timelines.append([timestamp for timestamp, _ in names])
        pairs.append((machine, vmx, names[-1][1]))

    # Every lab snapshot push must have reached ALL FIVE machines. Refuse
    # to mix e.g. the first snapshot for one VM and second for the others.
    count = len(timelines[0])
    if any(len(t) != count for t in timelines):
        raise NorthSnapshotRestoreError("NORTH snapshot generation counts disagree")
    for generation in range(count):
        stamps = [timeline[generation] for timeline in timelines]
        if max(stamps) - min(stamps) > 900:
            raise NorthSnapshotRestoreError("NORTH snapshot generations do not align")
    return pairs


def restore_north_offline_snapshots(provider_dir, vmx_lookup, *,
                                    runner=subprocess.run, log=None):
    """Revert only verified original NORTH VMX to their newest common generation.

    Stop and ownership checks are the caller's responsibility. On any failure
    the operation remains fail-closed; callers must NOT auto-start guests.
    """
    selected = select_north_snapshot_targets(
        provider_dir, vmx_lookup, runner=runner
    )
    if log is not None:
        for machine, _, name in selected:
            log(f"NORTH snapshot target: {machine} -> {name}")
    for machine, vmx, snapshot in selected:
        _run_vmrun(["revertToSnapshot", vmx, snapshot], runner=runner, timeout=900)
        if vmx in _running_vm_paths(runner=runner):
            raise NorthSnapshotRestoreError(
                f"{machine} unexpectedly started during offline restore; "
                "stop and inspect before any more restore actions"
            )
        if log is not None:
            log(f"NORTH offline snapshot restore verified: {machine} -> {snapshot}")
    return True
