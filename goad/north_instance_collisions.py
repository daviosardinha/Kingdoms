"""NORTH-only VMware guest identity collision gate; read-only by design.

Shares the same host survey as the operator's readiness command but treats
Vagrant VMX IDs under THIS concrete instance as owned. Reference Kingdoms
VMs are always foreign and may continue running on their own vmnets.
No inspected result grants permission to create or power on a VM.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from goad.course1_network_plan import require, validate_proposal, ZONES
from goad.course1_runtime_contract import COURSE1, ROUTER, ProfileNotReady

EXPECTED_GUESTS = COURSE1.windows + (ROUTER,)
COVERAGE = ("ip_addresses", "ip_routes", "vmware_networking", "vmrun_running")


def _identity(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]


def _owned_vmx_identifiers(provider_dir: Path, proposal: dict) -> dict[str, str]:
    """Trust only local regular Vagrant ID files pointing inside this provider."""
    root = provider_dir.resolve(strict=True)
    require(provider_dir.is_dir() and not provider_dir.is_symlink(),
            "NORTH provider path is missing or symlinked")
    allowed: dict[str, str] = {}
    for guest in EXPECTED_GUESTS:
        idfile = provider_dir / ".vagrant" / "machines" / guest / "vmware_desktop" / "id"
        if not idfile.exists():
            continue  # fresh Vagrant instance: guest has not been created
        require(idfile.is_file() and not idfile.is_symlink()
                and idfile.resolve(strict=True).is_relative_to(root),
                "NORTH Vagrant ID is unsafe")
        raw = idfile.read_text(encoding="utf-8").strip()
        require(bool(raw) and "\n" not in raw and "\r" not in raw,
                "NORTH Vagrant VMX identity malformed")
        vmx = Path(raw)
        require(vmx.is_absolute() and vmx.is_file() and not vmx.is_symlink(),
                "NORTH Vagrant VMX identity is unavailable")
        actual = vmx.resolve(strict=True)
        require(actual.is_relative_to(root),
                "NORTH Vagrant VMX points outside this instance provider")
        # Host survey hashes the literal VMX path from vmrun/VMware library.
        # Require canonical paths so no alias can create an ownership claim.
        require(str(actual) == str(vmx),
                "NORTH Vagrant VMX ID uses a noncanonical path")
        label = _identity(actual)
        require(label not in allowed,
                "NORTH Vagrant VMX ID is reused by multiple machines")
        allowed[label] = guest
    return allowed


def inspect_north_guest_collisions(
    provider_dir: str | Path, proposal: dict, snapshot: dict,
) -> dict:
    """Reject foreign guests on NORTH vmnets or using NORTH reserved MACs.

    This is a preflight to the existing Kingdoms VM lifecycle, not an alternate
    installer. Registered and running scopes must BOTH be readable.
    """
    validate_proposal(proposal)
    provider = Path(provider_dir)
    require(provider.name == "provider", "NORTH provider identity missing")
    ours = _owned_vmx_identifiers(provider, proposal)
    require(isinstance(snapshot, dict)
            and snapshot.get("kind") == "KINGDOMS_COURSE1_VMWARE_HOST_READONLY"
            and snapshot.get("status") == "OBSERVED_SNAPSHOT",
            "complete VMware host snapshot is required")
    coverage = snapshot.get("coverage", {})
    require(isinstance(coverage, dict)
            and all(coverage.get(key) is True for key in COVERAGE)
            and snapshot.get("no_changes_performed") is True,
            "VMware guest survey is incomplete or not read-only")
    registered = snapshot.get("registered_inventory", {})
    require(isinstance(registered, dict)
            and registered.get("library_status") == "INSPECTED"
            and registered.get("complete") is True
            and isinstance(registered.get("registered_vms"), list)
            and len(registered["registered_vms"]) == registered.get("registered_vm_count"),
            "complete registered VMware VMX evidence required")
    running = snapshot.get("running_vms")
    require(isinstance(running, list)
            and len(running) == snapshot.get("running_vm_count"),
            "complete running VMware VMX evidence required")

    reserved_macs = {proposal["machines"][vm]["mac"].lower()
                     for vm in COURSE1.windows}
    reserved_macs |= {mac.lower() for mac in proposal["router_macs"].values()}
    reserved_vmnets = {proposal["zones"][z]["vmnet"] for z in ZONES}
    expected_macs = {
        **{vm: {proposal["machines"][vm]["mac"].lower()}
           for vm in COURSE1.windows},
        ROUTER: {value.lower() for value in proposal["router_macs"].values()},
    }
    examined: set[str] = set()
    owned_seen: set[str] = set()
    for guest in [*running, *registered["registered_vms"]]:
        require(isinstance(guest, dict) and guest.get("readable") is True
                and isinstance(guest.get("adapters"), list)
                and isinstance(guest.get("vmx_identifier"), str)
                and len(guest["vmx_identifier"]) == 12,
                "VMware guest network identity is unreadable")
        vmx_id = guest["vmx_identifier"]
        require(all(isinstance(adapter, dict) for adapter in guest["adapters"]),
                "VMware guest adapter inventory is invalid")
        all_macs = {
            adapter[key].lower()
            for adapter in guest["adapters"]
            for key in ("address", "generatedAddress")
            if isinstance(adapter.get(key), str)
        }
        vnets = {adapter["vnet"] for adapter in guest["adapters"]
                 if isinstance(adapter.get("vnet"), str)}
        if vmx_id in ours:
            # An instance ID file alone cannot white-list a reference/foreign
            # VMX: prove the claimed guest has its own course MAC.
            require(all_macs & expected_macs[ours[vmx_id]],
                    "NORTH owned VMX does not match its expected guest MAC")
            require(not (all_macs & (reserved_macs - expected_macs[ours[vmx_id]])),
                    "NORTH owned guest claims another NORTH machine MAC")
            owned_seen.add(vmx_id)
            continue
        require(not (all_macs & reserved_macs),
                "foreign VMware guest uses a NORTH reserved MAC")
        require(not (vnets & reserved_vmnets),
                "foreign VMware guest is attached to an isolated NORTH vmnet")
        examined.add(vmx_id)
    return {
        "status": "NO_IDENTIFIED_NORTH_VM_COLLISIONS",
        "foreign_vmx_examined": len(examined),
        "owned_vmx_examined": len(owned_seen),
        "registered_inventory_complete": True,
        "reference_vmware_preserved": True,
        "runtime_authorized": False,
    }
