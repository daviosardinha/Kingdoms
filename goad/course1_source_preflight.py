"""Read-only Kingdoms Course 1 source integrity preflight.

This is an early *static* gate. It cannot authorize VM creation or replace
runtime VMware ownership, DNS authority, NIC and AD health checks.
"""
from __future__ import annotations

import json
import re
import yaml
from pathlib import Path, PurePosixPath

from goad.kingdoms_topology import load_course1_topology

ROOT = Path(__file__).resolve().parents[1]
DOMAIN_HOSTS = frozenset({"dc01", "dc02", "srv02", "ws01"})
DC_HOSTS = frozenset({"dc01", "dc02"})
DOMAINS = frozenset({"sevenkingdoms.local", "north.sevenkingdoms.local"})


class Course1SourceError(ValueError):
    pass


def parse_inventory(path: Path) -> dict[str, tuple[str, ...]]:
    """Group only hostname entries, never echo inventory secrets."""
    groups: dict[str, list[str]] = {}
    section = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if not section or section in groups:
                raise Course1SourceError(f"Invalid/duplicate inventory section: {path.name}")
            groups[section] = []
            continue
        if section is None:
            raise Course1SourceError(f"Inventory content outside section: {path.name}")
        if section.endswith(":vars"):
            continue
        if "=" in line and not line.split()[0].isidentifier():
            raise Course1SourceError(f"Unexpected inventory entry: {path.name}")
        groups[section].append(line.split()[0])
    return {name: tuple(hosts) for name, hosts in groups.items()}


def inventory_addresses(path: Path) -> dict[str, str]:
    section = None
    addresses = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section != "default":
            continue
        parts = line.split()
        if not parts:
            continue
        match = next((x for x in parts[1:] if x.startswith("ansible_host=")), None)
        if not match or parts[0] in addresses:
            raise Course1SourceError(f"Missing/duplicate host address: {path.name}")
        addresses[parts[0]] = match.split("=", 1)[1]
    return addresses


def validate_course1_source(root: Path = ROOT) -> tuple[str, ...]:
    """Return safe PASS evidence, fail on first actual source inconsistency."""
    base = Path(root) / "ad" / "NORTH"
    lab = json.loads((base / "data/config.json").read_text(encoding="utf-8"))["lab"]
    topo = load_course1_topology(manifest_path=base / "topology.json")
    messages = []
    if set(lab["hosts"]) != DOMAIN_HOSTS or set(lab["domains"]) != DOMAINS:
        raise Course1SourceError("Unexpected Course 1 Windows or domain roster")

    groups = parse_inventory(base / "data/inventory")
    if set(groups.get("domain", ())) != DOMAIN_HOSTS:
        raise Course1SourceError("Wrong domain group: missing or unexpected Windows host")
    if set(groups.get("dc", ())) != DC_HOSTS:
        raise Course1SourceError("Wrong domain-controller group")
    if set(groups.get("parent_dc", ())) != {"dc01"}:
        raise Course1SourceError("Wrong parent DC identity")
    if set(groups.get("child_dc", ())) != {"dc02"}:
        raise Course1SourceError("Wrong child DC identity")
    for group, members in groups.items():
        if group in ("domain", "dc", "server", "workstation", "parent_dc", "child_dc") or (
            group not in ("default", "all:vars", "extensions") and
            not group.endswith((":vars", ":children"))
        ):
            if set(members) - DOMAIN_HOSTS:
                raise Course1SourceError(f"Unknown machine in inventory group [{group}]")
    if any(domain.get("trust") for domain in lab["domains"].values()):
        raise Course1SourceError("Course 1 unexpectedly retained external forest trust")
    if groups.get("trust"):
        raise Course1SourceError("External trust group is populated without a forest trust")
    messages.append("Domain/AD and Ansible group membership are self-consistent")

    for host_key, host in lab["hosts"].items():
        if host["domain"] not in DOMAINS:
            raise Course1SourceError(f"Unknown host domain for {host_key}")
        for script in host.get("scripts", []):
            if not (root / "ad/GOAD/scripts" / script).is_file():
                raise Course1SourceError(f"Missing retained Kingdoms script for {host_key}")
    # NORTH preserves original Kingdoms file fixtures, including the full
    # CASTELBLACK IIS binary/site tree. The source mapping must be explicit:
    # silently looking for ad/NORTH/files will fail after ~20 minutes of AD
    # provisioning, despite the same fixture existing under ad/GOAD/files.
    role = root / "ansible/roles/vulns/files/tasks/main.yml"
    role_text = role.read_text(encoding="utf-8")
    if not ("domain_name == 'NORTH'" in role_text
            and "'../ad/GOAD/files'" in role_text
            and "item.value.src" in role_text):
        raise Course1SourceError("NORTH file-copy role must reuse existing Kingdoms fixtures")
    assets = root / "ad/GOAD/files"
    for host_key, host in lab["hosts"].items():
        refs = host.get("vulns_vars", {}).get("files", {})
        if "files" in host.get("vulns", []) and not refs:
            raise Course1SourceError(f"Missing file fixture declarations for {host_key}")
        if not isinstance(refs, dict):
            raise Course1SourceError(f"Invalid file fixture declarations for {host_key}")
        for fixture_name, fixture in refs.items():
            src = fixture.get("src") if isinstance(fixture, dict) else None
            if not isinstance(src, str):
                raise Course1SourceError(f"Invalid retained file reference for {host_key}/{fixture_name}")
            relative = PurePosixPath(src)
            if (relative.is_absolute() or not relative.parts
                    or any(part in (".", "..") for part in relative.parts)
                    or "\\" in src):
                raise Course1SourceError(f"Unsafe retained file reference for {host_key}/{fixture_name}")
            target = assets.joinpath(*relative.parts)
            if not target.exists() or target.is_symlink() or not (
                target.is_file() or (target.is_dir() and
                                     any(child.is_file() for child in target.rglob("*")))
            ):
                raise Course1SourceError(
                    f"Missing retained Kingdoms file fixture for {host_key}/{fixture_name}"
                )
    messages.append("Retained Kingdoms scenario scripts and vulnerability file assets are valid")

    expected = {spec["inventory"]: spec["address"] for spec in topo["windows"].values()}
    for filename in ("providers/vmware/inventory", "data/inventory_disable_vagrant"):
        resolved = inventory_addresses(base / filename)
        if resolved != expected:
            missing = sorted(set(expected) - set(resolved))
            extra = sorted(set(resolved) - set(expected))
            wrong = sorted(k for k in expected.keys() & resolved.keys()
                           if expected[k] != resolved[k])
            raise Course1SourceError(
                f"{filename}: unresolved host addresses "
                f"(missing={missing}, extra={extra}, wrong={wrong})"
            )
    post = parse_inventory(base / "data/inventory_disable_vagrant")
    if set(post.get("domain", ())) != DOMAIN_HOSTS:
        raise Course1SourceError("Post-Vagrant inventory does not list all Windows members")
    messages.append("Pre/Post-Vagrant inventory addresses resolve for all four Windows guests")

    vagrant = (base / "providers/vmware/Vagrantfile").read_text(encoding="utf-8")
    router = (base / "providers/vmware/router/provision.sh").read_text(encoding="utf-8")
    policy = (base / "providers/vmware/router/nftables/exercise.nft").read_text(encoding="utf-8")
    for name, spec in topo["windows"].items():
        if f':name => "{name}"' not in vagrant or (
            f':ip => "{spec["address"]}"' not in vagrant or
            f':vnet => "{spec["vmnet"]}"' not in vagrant
        ):
            raise Course1SourceError(f"VMware guest definition differs from topology: {name}")
    if len(re.findall(r':name\s*=>\s*"GOAD-[^"]+"', vagrant)) != 5:
        raise Course1SourceError("Expected exactly four Windows guests and one router")
    for name, spec in topo["segments"].items():
        if f'"{spec["gateway"]}"' not in router or spec["vmnet"] not in vagrant:
            raise Course1SourceError(f"Router segment differs from topology: {name}")
    dc_child = topo["windows"]["GOAD-DC02"]["address"]
    dc_parent = topo["windows"]["GOAD-DC01"]["address"]
    if f"ip saddr {dc_child} ip daddr {dc_parent}" not in policy or (
        f"ip saddr {dc_parent} ip daddr {dc_child}" not in policy
    ):
        raise Course1SourceError("Parent/child AD forwarding absent in router policy")
    for document in (vagrant, router, policy):
        if re.search(r"GOAD-DC03|GOAD-SRV03|vmnet30|essos", document, re.I):
            raise Course1SourceError("Deleted Essos machine/network persists in Course 1")
    messages.append("Vagrant/router/AD policy matches default Course 1 topology")

    # The generic Ansible provisioner silently falls back to "default"
    # for unknown lab IDs. Refuse a missing or incomplete Course 1 manifest
    # here, before the first VM/workspace or 20-minute Windows startup.
    plan = yaml.safe_load((root / "playbooks.yml").read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or not isinstance(plan.get("GOAD"), list) or (
        not isinstance(plan.get("NORTH"), list)
    ):
        raise Course1SourceError("Missing explicit Kingdoms Course 1 NORTH playbook manifest")
    full = plan["GOAD"]
    north = plan["NORTH"]
    expected = [entry for entry in full if entry != "ad-trusts.yml"]
    if full.count("ad-trusts.yml") != 1 or north != expected:
        raise Course1SourceError(
            "NORTH playbook order differs from validated Kingdoms sequence minus Essos trust"
        )
    for playbook in north:
        if not isinstance(playbook, str) or "/" in playbook or (
            not (root / "ansible" / playbook).is_file()
        ):
            raise Course1SourceError("NORTH references missing or invalid Ansible playbook")
    phase01 = (root / "ansible/phase01.yml").read_text(encoding="utf-8")
    if not ("domain_name in ['GOAD', 'NORTH']" in phase01
            and 'file: "../ad/{{ domain_name }}/data/config.json"' in phase01):
        raise Course1SourceError("Phase 01 is not bound to the selected Kingdoms scenario")
    messages.append("NORTH Ansible manifest reproduces Kingdoms sequence minus Essos trust")
    messages.append("SOURCE PRECHECK PASS; NORTH lifecycle remains blocked pending runtime wiring")
    return tuple(messages)


def main() -> None:
    try:
        messages = validate_course1_source()
    except (Course1SourceError, OSError, KeyError, ValueError) as exc:
        raise SystemExit(f"[BLOCKED] Course 1 source preflight: {exc}") from None
    for message in messages:
        print("[PASS] " + message)


if __name__ == "__main__":
    main()
