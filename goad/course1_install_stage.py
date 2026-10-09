"""Verify an isolated Course 1 VMware bundle and plan its future instance layout.

This gate never creates workspace/instance.json, authorizes or invokes Vagrant,
powers on guests, modifies VMware networks, or writes to any existing instance.
A matching bundle is still a blocked preview, not an installer input token.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path

from goad.course1_instance_binding import parse_instance_vagrant_roster
from goad.course1_network_plan import require, validate_proposal
from goad.course1_runtime_contract import COURSE1, ROUTER, ProfileNotReady
from goad.course1_source_gate import PROJECT
from goad.course1_vmware_candidate import render_candidate

INSTANCE_ID = re.compile(r"kingdoms-c1-[a-z0-9]{8,24}\Z")
GUARD = "raise 'KINGDOMS_COURSE1_PREVIEW_NOT_INSTALLABLE: deployment blocked'\n"

# This is a destination planning map, not a copy/install instruction.
# It documents how the already-rendered private preview would relate to
# a future workspace WITHOUT writing one or registering an instance.
PLANNED_WORKSPACE_MAPPING = {
    "instance-preview/Vagrantfile": "provider/Vagrantfile",
    "providers/vmware/inventory": "inventory",
    "data/inventory_disable_vagrant": "inventory_disable_vagrant",
    "data/inventory": "data/inventory",
    "data/config.json": "data/config.json",
    "router/provision.sh": "router/provision.sh",
    "vagrant/fix_ip.ps1": "vagrant/fix_ip.ps1",
    "vagrant/ConfigureRemotingForAnsible.ps1": "vagrant/ConfigureRemotingForAnsible.ps1",
    "vagrant/Install-WMF3Hotfix.ps1": "vagrant/Install-WMF3Hotfix.ps1",
}


def _private_directory(path: Path, reason: str) -> None:
    require(path.is_dir() and not path.is_symlink(),
            "missing or symlinked private " + reason)
    require(stat.S_IMODE(path.stat().st_mode) == 0o700,
            "private " + reason + " directory must be mode 0700")


def inspect_bundle(bundle: str | Path, proposal: object, instance_id: str) -> dict:
    """Re-render from trusted source and prove *every* file byte-for-byte."""
    validate_proposal(proposal)
    require(isinstance(instance_id, str) and INSTANCE_ID.fullmatch(instance_id) is not None,
            "Course 1 staging ID must match kingdoms-c1-[a-z0-9]{8,24}")
    path = Path(bundle).expanduser()
    require(path.is_absolute(), "Course 1 staging directory must be absolute")
    require(not path.is_symlink(), "Course 1 staging directory must not be a symlink")

    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink(), "symlink in staging ancestry")
        require(ancestor.name != "workspace"
                and not (ancestor / "instance.json").exists()
                and not (ancestor / ".vagrant").exists(),
                "candidate cannot overlap installed workspace or Vagrant state")
    path = path.resolve(strict=True)
    require(not path.is_relative_to(PROJECT.resolve()),
            "candidate cannot be staged under Kingdoms source checkout")
    _private_directory(path, "staging root")

    expected = render_candidate(proposal)
    require(len(expected) == 11, "unexpected canonical VMware candidate file count")
    declared = json.loads(expected["manifest.json"])
    require(declared.get("state") == "PREVIEW_ONLY_NOT_INSTALLABLE"
            and declared.get("deployment_authorized") is False,
            "source manifest must prohibit deployment")
    require(set(declared.get("generated_files", []))
            == set(expected) - {"manifest.json"},
            "canonical manifest does not enumerate exact staging files")
    require(expected["instance-preview/Vagrantfile"].startswith(GUARD),
            "canonical staged Vagrantfile lacks execution guard")

    observed: set[str] = set()
    for item in path.rglob("*"):
        require(not item.is_symlink(), "symlink in Course 1 staging package")
        rel = item.relative_to(path).as_posix()
        if item.is_dir():
            _private_directory(item, rel)
            continue
        require(item.is_file() and rel in expected,
                "unexpected or invalid file inside Course 1 staging package")
        require(stat.S_IMODE(item.stat().st_mode) == 0o600,
                "Course 1 source artifact must be mode 0600")
        canonical = expected[rel].encode("utf-8")
        actual = item.read_bytes()
        require(hashlib.sha256(actual).digest() == hashlib.sha256(canonical).digest(),
                "staged Course 1 file differs from current canonical source: " + rel)
        observed.add(rel)
    require(observed == set(expected), "incomplete Course 1 staged artifact set")

    vagrant = (path / "instance-preview/Vagrantfile").read_text(encoding="utf-8")
    names = parse_instance_vagrant_roster(vagrant)
    require(set(names) == set(COURSE1.windows) | {ROUTER}
            and len(names) == 5,
            "staged Vagrantfile must have four Windows guests and one router")
    for file in PLANNED_WORKSPACE_MAPPING:
        require(file in expected, "planned workspace mapping references missing artifact")
    require(len(set(PLANNED_WORKSPACE_MAPPING.values()))
            == len(PLANNED_WORKSPACE_MAPPING),
            "workspace mapping contains conflicting destinations")

    return {
        "profile": COURSE1.name,
        "provider": "vmware",
        "instance_id": instance_id,
        "state": "STAGED_SOURCE_ONLY_NOT_INSTALLABLE",
        "verified_files": len(observed),
        "windows_guests": len(COURSE1.windows),
        "router": ROUTER,
        "three_zone_networks": True,
        "candidate_source_fingerprint": declared["source_proposal_sha256"],
        "planned_workspace_files": dict(sorted(PLANNED_WORKSPACE_MAPPING.items())),
        "instance_json_created": False,
        "vmware_networks_allocated": False,
        "guest_lifecycle_authorized": False,
        "deployment_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-candidate", type=Path, required=True,
                        help="private existing candidate directory; read-only")
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--instance-id", required=True,
                        help="future intended instance identity, not a registration")
    args = parser.parse_args()
    try:
        plan = json.loads(args.proposal.read_text(encoding="utf-8"))
        result = inspect_bundle(args.check_candidate, plan, args.instance_id)
        print(json.dumps(result, indent=2))
        print("[PASS] Canonical private Course 1 source bundle and import layout verified")
        print("[BLOCKED] No installed instance, network allocation, Vagrant or lifecycle authorization")
    except (ProfileNotReady, ValueError, TypeError, OSError, UnicodeError) as exc:
        parser.exit(1, "[FAIL] " + str(exc) + "\n")


if __name__ == "__main__":
    main()
