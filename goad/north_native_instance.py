"""Read-only provenance gate for a freshly generated native NORTH instance.

This verifies the concrete files made by the SAME Kingdoms LabInstance builder
used for GOAD. It is NOT a runtime release token and NEVER touches VMware.
The existing reference instance and canonical repo fixtures are read-only.
"""
from __future__ import annotations

import json
from pathlib import Path

from goad.course1_instance_binding import parse_instance_vagrant_roster
from goad.course1_network_plan import surface_from_vagrant
from goad.course1_runtime_contract import COURSE1, ROUTER, ProfileNotReady
from goad.course1_vmware_candidate import render_candidate
from goad.kingdoms_vmware_profile import ROOT


def _regular_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ProfileNotReady(f"NORTH instance asset missing or unsafe: {path.name}")
    return path.read_text(encoding="utf-8")


def inspect_north_instance_assets(provider_dir: str | Path) -> dict:
    """Reject untrusted/mismatched NORTH workspaces before provider operations."""
    provider = Path(provider_dir)
    if (provider.name != "provider" or provider.is_symlink()
            or not provider.is_dir() or provider.parent.is_symlink()):
        raise ProfileNotReady("NORTH provider is not a safe instance directory")

    instance = provider.parent
    project = ROOT / "ad/NORTH"
    canonical = project / "providers/vmware"
    for relative in ("router", "vagrant"):
        path = instance / relative
        if path.is_symlink() or not path.is_dir():
            raise ProfileNotReady(f"NORTH instance folder missing or unsafe: {relative}")

    vagrantfile = _regular_file(provider / "Vagrantfile")
    canonical_vagrant = _regular_file(canonical / "Vagrantfile")
    names = parse_instance_vagrant_roster(vagrantfile)
    expected_names = COURSE1.windows + (ROUTER,)
    if names != expected_names:
        raise ProfileNotReady("NORTH VMware machine roster does not match four-guest course")
    if surface_from_vagrant(vagrantfile) != surface_from_vagrant(canonical_vagrant):
        raise ProfileNotReady("NORTH VMware vmnet, address or MAC identity differs from course")

    for essential in (
        'config.vm.box_check_update = false',
        'v.enable_vmrun_ip_lookup = false',
        '"../vagrant/fix_ip.ps1"',
        '"../vagrant/ConfigureRemotingForAnsible.ps1"',
        '"../vagrant/Install-WMF3Hotfix.ps1"',
        '"../router/provision.sh"',
    ):
        if essential not in vagrantfile:
            raise ProfileNotReady(f"NORTH Vagrantfile missing patched Kingdoms setting: {essential}")
    if "../../../vagrant/" in vagrantfile:
        raise ProfileNotReady("NORTH Vagrantfile points outside its own provisioning scripts")

    # Strict equality is intentional: no silent six-guest/GOAD inventory repair.
    for installed, expected in (
        (instance / "inventory", canonical / "inventory"),
        (instance / "inventory_disable_vagrant",
         project / "data/inventory_disable_vagrant"),
        (instance / "router/provision.sh", canonical / "router/provision.sh"),
    ):
        if _regular_file(installed) != _regular_file(expected):
            raise ProfileNotReady(f"NORTH instance asset differs from committed course: {installed.name}")

    plan_path = ROOT / "docs/course1-network-candidate.example.json"
    proposal = json.loads(_regular_file(plan_path))
    candidate = render_candidate(proposal)
    for script in (
        "fix_ip.ps1",
        "ConfigureRemotingForAnsible.ps1",
        "Install-WMF3Hotfix.ps1",
    ):
        actual = _regular_file(instance / "vagrant" / script)
        if actual != candidate["vagrant/" + script]:
            raise ProfileNotReady(f"NORTH Windows provisioning script drift: {script}")

    marker = provider / ".kingdoms-profile.json"
    if marker.is_symlink() or marker.exists():
        # The unreleased preview marker must never confer live authority.
        raise ProfileNotReady("NORTH runtime sidecar not approved for activation")

    return {
        "lab": "NORTH",
        "status": "NATIVE_INSTANCE_SOURCE_VERIFIED",
        "windows_machines": list(COURSE1.windows),
        "router": ROUTER,
        "runtime_authorized": False,
    }
