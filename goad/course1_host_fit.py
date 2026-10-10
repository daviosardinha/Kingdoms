"""Fail-closed comparison of a nondeployable Course 1 plan with VMware host observations.

No vmnet is allocated or proven free; dormant/suspended VM identities remain
outside a vmrun running snapshot. This is an observational gate only.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path

from goad.course1_host_survey import host_survey, compact_report
from goad.course1_network_plan import (
    ZONES, _mac, _network, require, validate_proposal,
)
from goad.course1_runtime_contract import ProfileNotReady

REQUIRED_COVERAGE = frozenset(
    ("ip_addresses", "ip_routes", "vmware_networking", "vmrun_running")
)


def _observed_ipv4_networks(snapshot: dict) -> set[ipaddress.IPv4Network]:
    """Handle host addresses, routes and VMware /24 subnet hints conservatively."""
    result: set[ipaddress.IPv4Network] = set()
    for interface in snapshot.get("host_interfaces", []):
        require(isinstance(interface, dict)
                and isinstance(interface.get("ipv4"), list),
                "malformed surveyed host interface")
        for item in interface["ipv4"]:
            try:
                parsed = ipaddress.ip_interface(item)
            except (ValueError, TypeError) as exc:
                raise ProfileNotReady("invalid observed host IPv4 interface") from exc
            require(isinstance(parsed, ipaddress.IPv4Interface),
                    "non-IPv4 observed interface in IPv4 field")
            result.add(parsed.network)

    for route in snapshot.get("ipv4_routes", []):
        require(isinstance(route, dict), "malformed surveyed route")
        dest = route.get("destination")
        require(isinstance(dest, str), "missing surveyed route destination")
        if dest == "default":
            continue
        try:
            net = ipaddress.ip_network(dest, strict=False)
        except ValueError as exc:
            raise ProfileNotReady("invalid observed host route") from exc
        if isinstance(net, ipaddress.IPv4Network):
            if net.prefixlen != 0:
                result.add(net)
        # IPv6 route entries are not IPv4 collision evidence.

    for item in snapshot.get("vmware_configured_subnet_hints", []):
        require(isinstance(item, dict)
                and isinstance(item.get("subnet_address"), str),
                "malformed VMware subnet hint")
        try:
            host_subnet = ipaddress.ip_network(
                item["subnet_address"] + "/24", strict=False
            )
        except ValueError as exc:
            raise ProfileNotReady("invalid VMware configured subnet hint") from exc
        require(isinstance(host_subnet, ipaddress.IPv4Network),
                "non-IPv4 VMware subnet hint")
        result.add(host_subnet)

    return result


def inspect_host_fit(proposal: object, snapshot: object) -> dict:
    """Reject observed collisions, never authorize new network allocation."""
    checked = validate_proposal(proposal)
    require(isinstance(snapshot, dict), "host survey must be a JSON object")
    require(snapshot.get("kind") == "KINGDOMS_COURSE1_VMWARE_HOST_READONLY"
            and snapshot.get("status") == "OBSERVED_SNAPSHOT",
            "host survey is not a complete verified observational snapshot")
    coverage = snapshot.get("coverage")
    require(isinstance(coverage, dict)
            and all(coverage.get(key) is True for key in REQUIRED_COVERAGE),
            "host survey lacks required read-only coverage")
    require(snapshot.get("no_changes_performed") is True
            and snapshot.get("candidate_allocation_authorized") is False
            and snapshot.get("deployment_authorized") is False,
            "host survey unexpectedly claims mutation or authorization")

    vmnets = snapshot.get("observed_vmnets")
    require(isinstance(vmnets, list) and all(isinstance(n, str) for n in vmnets),
            "invalid observed VMware network inventory")
    observed_vmnets = set(vmnets)
    proposed_vmnets = {proposal["zones"][zone]["vmnet"] for zone in ZONES}
    require(not (proposed_vmnets & observed_vmnets),
            "proposed VMware vmnet already observed in host or running guests")

    observed_nets = _observed_ipv4_networks(snapshot)
    proposed_nets = [_network(proposal["zones"][zone]["subnet"]) for zone in ZONES]
    require(not any(ours.overlaps(existing) for ours in proposed_nets
                    for existing in observed_nets),
            "proposed IPv4 subnet overlaps observed host networks or routes")

    running = snapshot.get("running_vms")
    require(isinstance(running, list)
            and isinstance(snapshot.get("running_vm_count"), int)
            and len(running) == snapshot["running_vm_count"],
            "running VMware VM inventory incomplete")
    known_macs: set[str] = set()
    for vm in running:
        require(isinstance(vm, dict) and vm.get("readable") is True
                and isinstance(vm.get("adapters"), list),
                "unreadable running VMX network identities")
        for adapter in vm["adapters"]:
            require(isinstance(adapter, dict), "invalid running VMX adapter")
            for field in ("address", "generatedAddress"):
                value = adapter.get(field)
                if value is not None:
                    known_macs.add(_mac(value))

    registered = snapshot.get("registered_inventory")
    library_status = "NOT_SURVEYED"
    registered_vm_count = 0
    registered_complete = False
    if registered is not None:
        require(isinstance(registered, dict), "VMware registered inventory is malformed")
        library_status = registered.get("library_status")
        require(library_status in ("INSPECTED", "NOT_FOUND", "INCOMPLETE", "UNREADABLE"),
                "VMware registered library status is unknown")
        registered_vm_count = registered.get("registered_vm_count")
        require(isinstance(registered_vm_count, int)
                and isinstance(registered.get("registered_vms"), list)
                and len(registered["registered_vms"]) == registered_vm_count,
                "VMware registered library VMX list is inconsistent")
        registered_complete = registered.get("complete") is True
        require(library_status not in ("INCOMPLETE", "UNREADABLE"),
                "VMware registered inventory incomplete; cannot exclude collisions")
        if library_status == "INSPECTED":
            require(registered_complete, "VMware registered inventory not complete")
        else:
            require(not registered_complete and registered_vm_count == 0,
                    "missing VMware registered inventory cannot claim guest coverage")
        for guest in registered["registered_vms"]:
            require(isinstance(guest, dict) and guest.get("readable") is True
                    and isinstance(guest.get("adapters"), list),
                    "unreadable registered VMX network identity")
            for adapter in guest["adapters"]:
                require(isinstance(adapter, dict), "malformed registered VMX adapter")
                candidate_vnet = adapter.get("vnet")
                require(candidate_vnet is None
                        or (isinstance(candidate_vnet, str)
                            and candidate_vnet not in proposed_vmnets),
                        "proposed vmnet collides with a registered VMware guest")
                for field in ("address", "generatedAddress"):
                    value = adapter.get(field)
                    if value is not None:
                        known_macs.add(_mac(value))

    desired_macs = {proposal["machines"][machine]["mac"].lower()
                    for machine in proposal["machines"]}
    desired_macs.update(mac.lower() for mac in proposal["router_macs"].values())
    require(not (desired_macs & known_macs),
            "proposed MAC collides with observed running VM adapter")

    return {
        **checked,
        "status": "NO_OBSERVED_CONFLICTS_NOT_PROVEN_AVAILABLE",
        "host_snapshot_complete": True,
        "host_observed_vmnets": len(observed_vmnets),
        "running_vms_examined": len(running),
        "registered_vm_count": registered_vm_count,
        "registered_inventory_status": library_status,
        "registered_vmx_complete": registered_complete,
        "unregistered_or_unscanned_vms_examined": False,
        "dormant_or_unregistered_vms_examined": False,
        "host_networks_surveyed": True,
        "candidate_allocation_authorized": False,
        "deployment_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-proposal", type=Path, required=True,
                        help="JSON with nondeployable three-segment Course 1 proposal")
    parser.add_argument("--snapshot", type=Path,
                        help="existing private JSON file from a single read-only survey")
    parser.add_argument("--inspect-host", action="store_true",
                        help="read actual host snapshot without changing VMware or Linux")
    args = parser.parse_args()
    try:
        proposal = json.loads(args.check_proposal.read_text(encoding="utf-8"))
        if args.snapshot is not None and args.inspect_host:
            parser.error("--inspect-host and --snapshot are mutually exclusive")
        if args.inspect_host or args.snapshot is not None:
            observed = (host_survey() if args.snapshot is None else
                        json.loads(args.snapshot.read_text(encoding="utf-8")))
            print("[PASS] Read-only host observations (single snapshot)")
            print(json.dumps(compact_report(observed), indent=2))
            answer = inspect_host_fit(proposal, observed)
            print(json.dumps(answer, indent=2))
            print("[BLOCKED] Host observations are NOT an allocation or installation grant")
        else:
            result = validate_proposal(proposal)
            print(json.dumps(result, indent=2))
            print("[BLOCKED] Static proposal; host not checked and deployment disabled")
    except (ProfileNotReady, OSError, ValueError, TypeError) as exc:
        parser.exit(1, "[FAIL] " + str(exc) + "\n")


if __name__ == "__main__":
    main()
