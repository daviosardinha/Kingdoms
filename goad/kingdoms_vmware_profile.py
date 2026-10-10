"""VMware configuration identities for native Kingdoms labs.

One patched Kingdoms provider implementation; per-course topology is data.
The active GOAD reference retains its exact 6-guest/4-zone contract.
NORTH uses 4 Windows guests/3 isolated zones but is NOT deployable until
the router, NAT, AD and provisioning lifecycle accepts this binding.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from goad.course1_network_plan import ZONES, validate_proposal
from goad.course1_runtime_contract import COURSE1, FULL, ROUTER, RuntimeRoster

ROOT = Path(__file__).resolve().parents[1]
NORTH_PLAN_PATH = ROOT / "docs/course1-network-candidate.example.json"


@dataclass(frozen=True)
class KingdomsVMwareBinding:
    lab: str
    roster: RuntimeRoster
    zones: tuple[tuple[str, str, str], ...]
    router: str
    router_management: str
    north_host: str
    management_host: str
    segmented_install_enabled: bool

    def __post_init__(self):
        if self.router != ROUTER:
            raise ValueError("unknown router identity")
        if not self.zones or len({zone[0] for zone in self.zones}) != len(self.zones):
            raise ValueError("invalid zone identity")
        if len({zone[1] for zone in self.zones}) != len(self.zones):
            raise ValueError("VMware network devices must be unique")
        if len(set(self.roster.management_hosts.values())) != len(self.roster.windows):
            raise ValueError("guest management addresses must be unique")
        if self.lab == "NORTH" and self.segmented_install_enabled:
            from goad.course_catalog import north_first_install_pilot_authorized
            if not north_first_install_pilot_authorized():
                raise ValueError("NORTH runtime is not authorized yet")


REFERENCE = KingdomsVMwareBinding(
    lab="GOAD",
    roster=FULL,
    zones=(
        ("NORTH", "vmnet10", "10.4.10.0/24"),
        ("SEVENKINGDOMS", "vmnet20", "10.4.20.0/24"),
        ("ESSOS", "vmnet30", "10.4.30.0/24"),
        ("MANAGEMENT", "vmnet99", "10.4.99.0/24"),
    ),
    router=ROUTER,
    router_management="10.4.99.1",
    north_host="10.4.10.254",
    management_host="10.4.99.254",
    segmented_install_enabled=True,
)


def _north_pilot_runtime_enabled() -> bool:
    from goad.course_catalog import north_first_install_pilot_authorized
    return north_first_install_pilot_authorized()


def north_binding() -> KingdomsVMwareBinding:
    """Re-read the exact reviewed and isolated NORTH address proposal."""
    if NORTH_PLAN_PATH.is_symlink() or not NORTH_PLAN_PATH.is_file():
        raise ValueError("missing or unsafe NORTH network proposal")
    proposal = json.loads(NORTH_PLAN_PATH.read_text(encoding="utf-8"))
    validate_proposal(proposal)
    hosts = {machine: proposal["machines"][machine]["ip"]
             for machine in COURSE1.windows}
    # The roster must come from the same native lab candidate, not from
    # the legacy 10.4.x management_hosts in the initial planning contract.
    roster = RuntimeRoster(
        name=COURSE1.name,
        windows=COURSE1.windows,
        start_order=COURSE1.start_order,
        dependencies=COURSE1.dependencies,
        management_hosts=hosts,
    )
    zones = tuple((zone, proposal["zones"][zone]["vmnet"],
                   proposal["zones"][zone]["subnet"]) for zone in ZONES)
    return KingdomsVMwareBinding(
        lab="NORTH",
        roster=roster,
        zones=zones,
        router=ROUTER,
        router_management=proposal["zones"]["MANAGEMENT"]["gateway"],
        north_host=proposal["host_addresses"]["NORTH"],
        management_host=proposal["host_addresses"]["MANAGEMENT"],
        segmented_install_enabled=_north_pilot_runtime_enabled(),
    )


def binding_for(lab_name: str) -> KingdomsVMwareBinding | None:
    if lab_name == "GOAD":
        return REFERENCE
    if lab_name == "NORTH":
        return north_binding()
    # Other existing GOAD lab profiles keep their provider behavior.
    return None
