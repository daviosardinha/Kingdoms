"""Read-only pre/post VMware host checks for one Kingdoms NORTH deployment.

The pre-allocation collision gate intentionally rejects allocated vmnets.
After successful explicit maintenance, this checker recognizes ONLY the
expected owned segments, reuses the collision gate for unrelated identities,
and reports separately whether .254 host-address persistence is ready.
"""
from __future__ import annotations

import copy
import ipaddress
import json
import argparse
from pathlib import Path

from goad.course1_host_fit import inspect_host_fit
from goad.north_native_instance import inspect_north_instance_assets
from goad.north_instance_collisions import (
    _owned_vmx_identifiers, inspect_north_guest_collisions,
)
from goad.course1_network_plan import ZONES, require, validate_proposal
from goad.course1_runtime_contract import ProfileNotReady
from goad.course1_host_survey import compact_report

HOST_ZONES = ("NORTH", "MANAGEMENT")
REF_HOST_IPS = {"vmnet10": "10.4.10.254/24", "vmnet99": "10.4.99.254/24"}


def inspect_network_phase(proposal: dict, snapshot: dict,
                          instance_provider: str | Path | None = None) -> dict:
    validate_proposal(proposal)
    require(isinstance(snapshot, dict)
            and snapshot.get("status") == "OBSERVED_SNAPSHOT",
            "complete current VMware host snapshot required")
    vmnets = {proposal["zones"][z]["vmnet"] for z in ZONES}
    observed = set(snapshot.get("observed_vmnets", []))
    seen = vmnets & observed
    if not seen:
        before = inspect_host_fit(proposal, snapshot)
        return {**before, "network_phase": "UNALLOCATED",
                "host_addresses_ready": False,
                "deployment_authorized": False}
    require(seen == vmnets,
            "incomplete NORTH VMware network allocation; manual recovery required")

    hints = snapshot.get("vmware_configured_subnet_hints")
    require(isinstance(hints, list), "VMware configured subnet inventory incomplete")
    for zone in ZONES:
        vmnet, subnet = (proposal["zones"][zone][k] for k in ("vmnet", "subnet"))
        network = ipaddress.ip_network(subnet)
        entries = [x for x in hints if x.get("vmnet") == vmnet]
        require(len(entries) == 1
                and entries[0].get("subnet_address") == str(network.network_address),
                f"NORTH {zone} VMware subnet missing or mismatched")

    interfaces = snapshot.get("host_interfaces")
    require(isinstance(interfaces, list), "VMware host adapter evidence missing")
    by_name = {x["interface"]: x for x in interfaces}
    require(not any(x["interface"] == proposal["zones"]["SEVENKINGDOMS"]["vmnet"]
                    for x in interfaces),
            "NORTH SEVENKINGDOMS must have no host-side adapter")
    for iface, cidr in REF_HOST_IPS.items():
        require(cidr in by_name.get(iface, {}).get("ipv4", []),
                f"protected reference host address {cidr} is missing")

    addresses_ready = True
    for zone in HOST_ZONES:
        vmnet = proposal["zones"][zone]["vmnet"]
        subnet = ipaddress.ip_network(proposal["zones"][zone]["subnet"])
        desired = proposal["host_addresses"][zone] + "/24"
        vmware_auto = str(subnet.network_address + 1) + "/24"
        addresses = by_name.get(vmnet, {}).get("ipv4")
        require(isinstance(addresses, list) and len(addresses) == 1
                and addresses[0] in (desired, vmware_auto),
                f"{zone} host interface must have only VMware .1 or Kingdoms .254")
        addresses_ready = addresses_ready and addresses[0] == desired

    # Remove only the verified intended owned evidence for reuse of the
    # pre-allocation collision/MAC/registered-VM checks. Any foreign address,
    # subnet or route overlap remains in the copy and is rejected.
    normalized = copy.deepcopy(snapshot)
    normalized["observed_vmnets"] = sorted(observed - vmnets)
    normalized["vmware_configured_subnet_hints"] = [
        x for x in hints if x["vmnet"] not in vmnets
    ]
    normalized["host_interfaces"] = [
        x for x in interfaces if x["interface"] not in vmnets
    ]
    owned_nets = {
        proposal["zones"][zone]["vmnet"]: ipaddress.ip_network(
            proposal["zones"][zone]["subnet"]
        ) for zone in HOST_ZONES
    }
    scoped_provider = Path(instance_provider) if instance_provider is not None else None
    owned_ids: set[str] = set()
    owned_count = 0
    if scoped_provider is not None:
        # Deployed NORTH's own VMX identities legitimately occupy its
        # reserved vmnets/MACs. Verify the canonical instance source and
        # Vagrant ownership before subtracting precisely those identities.
        inspect_north_instance_assets(scoped_provider)
        owned_report = inspect_north_guest_collisions(
            scoped_provider, proposal, snapshot,
        )
        require(owned_report["owned_vmx_examined"] > 0,
                "scoped NORTH survey found no verified instance-owned VMX")
        owned_ids = set(_owned_vmx_identifiers(scoped_provider, proposal))
        observed_ids = {
            vm["vmx_identifier"]
            for vm in [*snapshot["running_vms"],
                       *snapshot["registered_inventory"]["registered_vms"]]
        }
        owned_count = len(owned_ids & observed_ids)
        require(owned_count == owned_report["owned_vmx_examined"],
                "scoped NORTH VMX survey changed during inspection")
        normalized["running_vms"] = [
            vm for vm in snapshot["running_vms"]
            if vm["vmx_identifier"] not in owned_ids
        ]
        normalized["running_vm_count"] = len(normalized["running_vms"])
        normalized["registered_inventory"]["registered_vms"] = [
            vm for vm in snapshot["registered_inventory"]["registered_vms"]
            if vm["vmx_identifier"] not in owned_ids
        ]
        normalized["registered_inventory"]["registered_vm_count"] = len(
            normalized["registered_inventory"]["registered_vms"]
        )

    filtered = []
    for route in snapshot.get("ipv4_routes", []):
        dev = route.get("interface")
        target = route.get("destination")
        net = None
        if isinstance(target, str) and target != "default":
            try:
                net = ipaddress.ip_network(target, strict=False)
            except ValueError:
                pass
        if (dev in owned_nets and isinstance(net, ipaddress.IPv4Network)
                and net.subnet_of(owned_nets[dev])):
            continue
        if (scoped_provider is not None
                and dev == proposal["zones"]["NORTH"]["vmnet"]
                and target == proposal["zones"]["SEVENKINGDOMS"]["subnet"]
                and route.get("gateway") == proposal["zones"]["NORTH"]["gateway"]):
            # Only the expected temporary parent route may be normalized;
            # foreign routes, vmnets and VMX remain collision evidence.
            continue
        filtered.append(route)
    normalized["ipv4_routes"] = filtered
    conflict = inspect_host_fit(proposal, normalized)
    require(conflict["registered_vmx_complete"],
            "complete registered VMX evidence required after allocation")

    return {
        "profile": conflict["profile"],
        "network_phase": "ALLOCATED",
        "status": ("NORTH_HOST_ADDRESSES_READY" if addresses_ready
                   else "NORTH_HOST_ADDRESSES_PENDING"),
        "vmnets": {zone: proposal["zones"][zone]["vmnet"] for zone in ZONES},
        "host_addresses": {
            zone: by_name[proposal["zones"][zone]["vmnet"]]["ipv4"][0]
            for zone in HOST_ZONES
        },
        "host_addresses_ready": addresses_ready,
        "reference_host_addresses_preserved": True,
        "registered_vm_count": conflict["registered_vm_count"],
        "running_vm_count": snapshot["running_vm_count"],
        "north_owned_vmx_verified": owned_count,
        "host_networks_modified": False,
        "guest_lifecycle_authorized": False,
        "deployment_authorized": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--proposal", type=Path, required=True)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--instance-provider", type=Path,
                   help="explicit deployed NORTH provider for scoped survey")
    args = p.parse_args()
    try:
        proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        print(json.dumps(compact_report(snapshot), indent=2))
        result = inspect_network_phase(
            proposal, snapshot, instance_provider=args.instance_provider,
        )
        print(json.dumps(result, indent=2))
        print("[BLOCKED] Host/VM network status does not authorize course installation")
    except (ProfileNotReady, KeyError, OSError, ValueError, TypeError) as exc:
        p.exit(1, "[FAIL] " + str(exc) + "\n")


if __name__ == "__main__":
    main()
