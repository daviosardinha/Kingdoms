"""Read-only proposal for retiring a preserved NORTH VMware network owner.

There is deliberately NO apply, vmrun, systemctl, file write or ownership
deletion path in this module. The output is a review artifact for a separately
tested transactional release. In particular, Vagrant-created NAT forwarding
rules are not silently assumed to belong to the five NORTH VMs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from goad.course1_offline_handoff import HandoffPlanError, plan, regular_file
from goad.course1_host_network_apply import (
    NETWORKING, NorthSetupError, operator_inventory, require_explicit_root,
)
from goad.kingdoms_topology import load_course1_topology

ANSWER = re.compile(rb"^[ \t]*answer[ \t]+VNET_(\d+)_([A-Z0-9_]+)[ \t]+\S+[ \t]*(?:\r?\n)?$")
NAT_FORWARD = re.compile(rb"^[ \t]*add_nat_portfwd[ \t]+.*")
HEADER = b"# Kingdoms Course 1 managed networks (additive; source-only plan)"
ZONE_COMMENT = re.compile(rb"^#[ \t]+vmnet(\d+):[ \t]+(?:NORTH|SEVENKINGDOMS|MANAGEMENT)[ \t]*$")


def propose_removed_north_vmnets(current: bytes, selected: frozenset[int]):
    """Remove ONLY owned vmnet declarations, leaving all other bytes intact.

    This is a candidate for human review, never a safe-to-apply authorization.
    Require all three vmnet declarations, and refuse any unknown VNET directive
    for an owned ID rather than pretending its deletion would be harmless.
    """
    if not current:
        raise HandoffPlanError("VMware networking configuration is empty")
    lines = current.splitlines(keepends=True)
    kept = []
    removed = []
    seen = set()
    for line in lines:
        raw = line.rstrip(b"\r\n")
        m = ANSWER.match(line)
        if m and int(m.group(1)) in selected:
            seen.add(int(m.group(1)))
            removed.append(line)
            continue
        if raw == HEADER:
            removed.append(line)
            continue
        comment = ZONE_COMMENT.match(raw)
        if comment and int(comment.group(1)) in selected:
            removed.append(line)
            continue
        # Reject malformed or non-answer directives with owned vmnet IDs.
        for number in selected:
            if re.search(rb"\bVNET_" + str(number).encode() + rb"_", raw):
                raise HandoffPlanError("Unrecognized owned vmnet directive; manual review required")
        kept.append(line)
    if seen != selected:
        raise HandoffPlanError(
            "Owned vmnet declarations are missing: " + repr(sorted(selected - seen))
        )
    candidate = b"".join(kept)
    # Even comments or unknown syntax cannot leave ownership references.
    if any(re.search(rb"\bVNET_" + str(n).encode() + rb"_", candidate)
           for n in selected):
        raise HandoffPlanError("A candidate contains leftover NORTH vmnet declarations")
    return candidate, tuple(removed)


def preview(provider: Path, inventory: Path, networking: Path) -> dict:
    provider, inventory, networking = map(Path, (provider, inventory, networking))
    proof = plan(provider, inventory, "registered")
    regular_file(networking)
    current = networking.read_bytes()
    layout = load_course1_topology()
    selected = frozenset(int(zone["vmnet"][5:]) for zone in layout["segments"].values())
    if len(selected) != 3:
        raise HandoffPlanError("NORTH layout must define three distinct vmnets")
    candidate, removed = propose_removed_north_vmnets(current, selected)
    nat = [
        line.decode("utf-8", errors="replace").strip()
        for line in current.splitlines()
        if NAT_FORWARD.match(line)
    ]
    return {
        "mode": "READ_ONLY_RELEASE_REVIEW_NO_HOST_CHANGES",
        "provider": proof["provider"],
        "vm_count": proof["vm_count"],
        "inventory_reference_count": proof["inventory_reference_count"],
        "network_ownership": proof["network_ownership"],
        "vmnets_proposed_for_removal": sorted(selected),
        "vmnet_declarations_proposed": len(removed),
        "networking_before_sha256": hashlib.sha256(current).hexdigest(),
        "networking_candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "nat_forward_count": len(nat),
        "nat_forwards_requiring_independent_owner_review": nat,
        "fresh_install_blocked_by_forward_rules": bool(nat),
        "release_authorized": False,
        "instructions": (
            "Keep running NORTH unchanged. After controlled shutdown and "
            "Remove from Library (not Delete from Disk), a SEPARATELY APPROVED "
            "transaction must check zero VMs, no VMware processes, correct "
            "owner/journal/asset identity and reviewed forwarding ownership. "
            "This command does NOT release the network."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-dir", required=True)
    args = parser.parse_args()
    try:
        require_explicit_root()
        outcome = preview(Path(args.provider_dir), operator_inventory(), NETWORKING)
    except (OSError, UnicodeError, NorthSetupError, HandoffPlanError, ValueError) as exc:
        parser.exit(1, "[BLOCKED] NORTH release review: " + str(exc) + "\n")
    print(json.dumps(outcome, sort_keys=True, indent=2))
    print("[NOT AUTHORIZED] No VMware state, network or Vagrant files were modified")


if __name__ == "__main__":
    main()
