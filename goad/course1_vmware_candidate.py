"""Render an isolated, NONDEPLOYABLE VMware Course 1 Vagrant/router candidate.

The source-only generator deliberately does NOT alter the existing Kingdoms
six-Windows-VM instance, allocate host vmnets or permit guest power operations.
Ansible/AD/mode-controller translations are NOT part of this output yet.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
import re
from pathlib import Path

from goad.course1_inventory_candidate import render_candidate_inventories
from goad.kingdoms_foundation import FOUNDATION_ID
from goad.course1_network_plan import (
    REFERENCE_ROUTER, ZONES, require, validate_proposal,
)
from goad.course1_runtime_contract import COURSE1, ROUTER, ProfileNotReady
from goad.course1_source_gate import PROJECT, _generator_render

GENERATOR_PATH = PROJECT / "scripts/course1/generate-profile.py"
WINDOWS = COURSE1.windows
BOX_RX = re.compile(r"^  \{\n.*?^  \},?\n", re.M | re.S)
NAME_RX = re.compile(r':name\s*=>\s*"([^"]+)"')
FORBIDDEN = ("GOAD-DC03", "GOAD-SRV03", "vmnet30", "essos.local", "10.4.")


def _replace_one(text: str, pattern: str, replacement: str, field: str) -> str:
    output, matches = re.subn(pattern, lambda m: m.expand(replacement), text,
                              flags=re.M)
    require(matches == 1, f"expected one canonical {field}, found {matches}")
    return output


def _render_windows_box(machine: str, original: str, plan: dict) -> str:
    entry = plan["machines"][machine]
    zone = entry["zone"]
    gateway = plan["zones"][zone]["gateway"]
    vmnet = plan["zones"][zone]["vmnet"]
    ip, mac = entry["ip"], entry["mac"].lower()

    # Deliberately keep the original box, OS and provisioning properties.
    # Fail if its documented single-NIC contract changes.
    text = original
    for field, value in (
        ("ip", ip), ("lab_gateway", gateway), ("lab_mac", mac),
    ):
        text = _replace_one(
            text,
            rf'^(\s*:{field}\s*=>\s*)"[^"]+"',
            rf'\g<1>"{value}"',
            machine + " " + field,
        )
    text = _replace_one(
        text, r'^(\s*\{\s*:slot\s*=>\s*1,\s*:vnet\s*=>\s*)"[^"]+"',
        rf'\g<1>"{vmnet}"', machine + " vnet",
    )
    text = _replace_one(
        text, r'^(\s*\{\s*:slot\s*=>\s*1,\s*:vnet\s*=>\s*"[^"]+",\s*:mac\s*=>\s*)"[^"]+"',
        rf'\g<1>"{mac}"', machine + " adapter MAC",
    )
    require(len(re.findall(r':slot\s*=>', text)) == 1,
            "each Course 1 Windows VM requires exactly one exercise NIC")
    return text.rstrip().rstrip(",")


def _render_router_box(plan: dict) -> str:
    # These PCI slot values are a *proposed layout*. The new three-NIC router
    # still requires a disposable VMware runtime/udev discovery regression.
    lines = [
        "  {",
        '    :name => "GOAD-ROUTER",',
        '    :hostname => "kingdoms-course1-router",',
        '    :box => "bento/debian-12",',
        '    :os => "linux",',
        '    :cpus => 1,',
        '    :mem => 768,',
        '    :skip_private_network => true,',
        '    :vmware_vmx => {',
        '      "ethernet0.startConnected" => "TRUE",',
        '      "ethernet0.pcislotnumber" => "160",',
        '      "ethernet1.pcislotnumber" => "224",',
        '      "ethernet2.pcislotnumber" => "256",',
        '      "ethernet3.pcislotnumber" => "1184"',
        '    },',
        '    :vmware_network_adapters => [',
    ]
    for slot, zone in enumerate(ZONES, start=1):
        vmnet = plan["zones"][zone]["vmnet"]
        mac = plan["router_macs"][zone].lower()
        suffix = "," if slot < len(ZONES) else ""
        lines.append(
            f'      {{ :slot => {slot}, :vnet => "{vmnet}", :mac => "{mac}" }}{suffix}'
        )
    lines.extend([
        '    ],',
        '    :provision_scripts => [',
        '      "../router/provision.sh"',
        '    ]',
        '  }',
    ])
    return "\n".join(lines)


def _render_router_script(plan: dict) -> str:
    """Use the validated reference router bootstrap shape, minus ESSOS.

    Generated script deliberately starts with a deny-forward firewall policy
    until a dedicated Course 1 exercise/provisioning mode controller is proven.
    """
    reference = REFERENCE_ROUTER.read_text(encoding="utf-8")
    require(reference.count('configure_lab_interface "') == 4,
            "reference router interface function/calls changed")
    require(reference.count("table inet goad_nomad") == 1,
            "reference router nftables shape changed")
    require(reference.count("policy accept;") == 3,
            "reference router policy changed; manual review required")

    kept = []
    skipped = {"mac": 0, "config": 0, "print": 0}
    for line in reference.splitlines():
        if line.startswith("readonly ESSOS_MAC="):
            skipped["mac"] += 1
            continue
        if line.startswith('configure_lab_interface "ESSOS" '):
            skipped["config"] += 1
            continue
        if line.startswith('printf ') and '"    ESSOS ' in line:
            skipped["print"] += 1
            continue
        kept.append(line)
    require(skipped == {"mac": 1, "config": 1, "print": 1},
            "reference ESSOS router contract changed")
    script = "\n".join(kept).rstrip() + "\n"

    for zone, old_mac, old_gateway in (
        ("NORTH", "00:50:56:10:10:01", "10.4.10.1"),
        ("SEVENKINGDOMS", "00:50:56:10:20:01", "10.4.20.1"),
        ("MANAGEMENT", "00:50:56:10:99:01", "10.4.99.1"),
    ):
        # Old MAC appears exactly once as a quoted declaration.
        script = _replace_one(
            script,
            rf'^(readonly {zone}_MAC=)"{re.escape(old_mac)}"',
            rf'\g<1>"{plan["router_macs"][zone].lower()}"',
            zone + " router MAC",
        )
        require(script.count(f'"{old_gateway}"') == 1,
                "router gateway definition changed")
        script = script.replace(f'"{old_gateway}"',
                                f'"{plan["zones"][zone]["gateway"]}"')
        # Status printf lines pad NORTH, SEVENKINGDOMS and MANAGEMENT
        # differently. Match the zone label + old gateway without assuming
        # any fixed number of padding spaces, and fail if the line is missing.
        status_pattern = (
            rf'^(printf[^\n]*"[ \t]+{re.escape(zone)}[ \t]+)'
            rf'{re.escape(old_gateway)}(/24"[ \t]*)$'
        )
        script, status_count = re.subn(
            status_pattern,
            lambda match: (
                match.group(1) + plan["zones"][zone]["gateway"] + match.group(2)
            ),
            script,
            flags=re.M,
        )
        require(status_count == 1,
                "router status gateway definition changed")

    script = script.replace(
        "four custom adapters below",
        "three dedicated Course 1 lab adapters below",
    ).replace(
        "GOAD_NOMAD", "KINGDOMS_COURSE1"
    ).replace(
        "goad-router", "kingdoms-course1-router"
    )
    script = script.replace("table inet goad_nomad", "table inet kingdoms_north")
    require(script.count("table inet kingdoms_north") == 1,
            "Course 1 router nftables table identity not isolated")
    script = script.replace(
        "# Router bootstrap starts in provisioning mode.",
        "# NONDEPLOYABLE Course 1 preview: forwarding starts DENIED."
    )
    script = script.replace(
        "# Forwarding is intentionally permissive while Vagrant/Ansible configures the\n"
        "# lab. Before training begins, scripts/lab-mode.sh switches the range to the\n"
        "# validated deny-by-default exercise policy and isolates Windows NAT adapters.",
        "# This PREVIEW defaults to deny-forward. A future instance-bound Course 1\n"
        "# provisioning controller must explicitly manage temporary reachability,\n"
        "# failure rollback, exercise policy and Windows NAT isolation."
    )
    script = script.replace(
        "nftables active (provisioning allow-forward policy)",
        "nftables active (NONDEPLOYABLE preview deny-forward policy)"
    )
    script = script.replace(
        "type filter hook forward priority 0;\n        policy accept;",
        "type filter hook forward priority 0;\n        policy drop;",
    )
    require(script.count("policy drop;") == 1,
            "Course 1 default-deny forwarding not enforced")
    require("ESSOS" not in script.upper() and "10.4." not in script,
            "Course 1 router retained a legacy ESSOS or reference IP")
    require("configure_lab_interface " in script
            and script.count('configure_lab_interface "') == 3,
            "Course 1 router must have exactly three NIC binding calls")
    return script


WINDOWS_PROVISIONING_ASSETS = (
    "Install-WMF3Hotfix.ps1",
    "ConfigureRemotingForAnsible.ps1",
    "fix_ip.ps1",
)


def _render_vagrant_assets(plan: dict) -> dict[str, str]:
    # Copy the three exact provisioners into a private, self-contained source
    # bundle. NEVER rewrite the canonical Windows source in the live reference.
    win = {}
    for name in WINDOWS_PROVISIONING_ASSETS:
        content = (PROJECT / "vagrant" / name).read_text(encoding="utf-8")
        if name == "fix_ip.ps1":
            # The existing script installs a persistent cross-zone 10.4/16
            # route. Course 1's NORTH/SEVENKINGDOMS networks share 10.41/16.
            north = ipaddress.ip_network(plan["zones"]["NORTH"]["subnet"])
            parent = ipaddress.ip_network(plan["zones"]["SEVENKINGDOMS"]["subnet"])
            require(north.supernet(new_prefix=16) == parent.supernet(new_prefix=16),
                    "Windows provisioner cannot represent disjoint cross-zone routes")
            route = str(north.supernet(new_prefix=16))
            network_address = str(north.supernet(new_prefix=16).network_address)
            require(route == "10.41.0.0/16" and content.count("10.4.0.0") == 6,
                    "Windows provisioner contract changed; review routing before rendering")
            content = content.replace("10.4.0.0", network_address)
            content = content.replace("GOAD_NOMAD", "KINGDOMS_COURSE1")
            require(route in content and "10.4." not in content,
                    "legacy Windows static route escaped Course 1 translation")
        win["vagrant/" + name] = content
    return win


def _render_outer_template(recipe: str) -> str:
    spec = importlib.util.spec_from_file_location("course1_reference_generator",
                                                   GENERATOR_PATH)
    require(spec is not None and spec.loader is not None,
            "cannot load canonical Vagrant renderer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    outer = module.render_instance_vagrantfile(recipe)
    require("10.4.30.12" in outer,
            "reference template WinRM example moved; review before rendering")
    require(outer.count("../../../vagrant/") == 4,
            "canonical Windows provisioning relative paths changed")
    outer = outer.replace("../../../vagrant/", "../vagrant/")
    require("../../../vagrant/" not in outer
            and outer.count("../vagrant/") == 4,
            "Course 1 private Windows provisioner paths did not rebase")
    return outer.replace("10.4.30.12", "an isolated guest address")


def render_candidate(plan: dict) -> dict[str, str]:
    """Generate a self-contained Vagrant/router source candidate in memory."""
    validate_proposal(plan)
    reduced_source = _generator_render()
    reference = reduced_source["providers/vmware/Vagrantfile"]
    staged_inventories = render_candidate_inventories(reduced_source, plan)
    windows_assets = _render_vagrant_assets(plan)
    blocks = {}
    for match in BOX_RX.finditer(reference):
        original = match.group(0).rstrip()
        found = NAME_RX.search(original)
        require(found is not None, "unrecognized canonical Ruby box")
        machine = found.group(1)
        require(machine not in blocks, "duplicate canonical machine")
        blocks[machine] = original.rstrip(",")
    require(set(blocks) == set(WINDOWS) | {ROUTER},
            "reference reduced preview no longer has expected 4+1 machines")

    windows = [_render_windows_box(name, blocks[name], plan) for name in WINDOWS]
    router = _render_router_box(plan)
    recipe = (
        "# NONDEPLOYABLE KINGDOMS COURSE 1 VMWARE NETWORK CANDIDATE.\n"
        "boxes = [\n" + ",\n\n".join([*windows, router]) + "\n]\n"
    )
    require(recipe.count(":vmware_network_adapters") == 5,
            "expected four Windows NICs plus one router NIC bundle")
    # The preview's Ruby is syntactically valid, but a direct Vagrant load
    # must halt BEFORE any box or provisioning configuration is evaluated.
    # Instance creation can only enable a separate, approved copy later.
    vagrant = (
        "raise 'KINGDOMS_COURSE1_PREVIEW_NOT_INSTALLABLE: deployment blocked'\n"
        + _render_outer_template(recipe)
    )
    script = _render_router_script(plan)

    reference_sensitive = (recipe, vagrant, script)
    require(all(not any(s in text for s in FORBIDDEN) for text in reference_sensitive),
            "Course 1 candidate contains forbidden ESSOS/reference identifiers")
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    manifest = {
        "profile": COURSE1.name,
        "kingdoms_foundation": FOUNDATION_ID,
        "state": "PREVIEW_ONLY_NOT_INSTALLABLE",
        "provider": "vmware",
        "source_proposal_sha256": digest,
        "windows_machines": list(WINDOWS),
        "router": ROUTER,
        "zones": list(ZONES),
        "generated_files": ["providers/vmware/Vagrantfile",
                            "instance-preview/Vagrantfile", "router/provision.sh",
                            "data/config.json", "data/inventory",
                            "data/inventory_disable_vagrant",
                            "providers/vmware/inventory",
                            "vagrant/Install-WMF3Hotfix.ps1",
                            "vagrant/ConfigureRemotingForAnsible.ps1",
                            "vagrant/fix_ip.ps1"],
        "deployment_authorized": False,
        "incomplete": [
            "host vmnet allocation and VMware manual MAC compatibility unverified",
            "router three-NIC PCI/udev/SSH runtime unverified",
            "isolated Windows provisioner rebased but VMX/WinRM live execution unverified",
            "Ansible playbook and Phase 03 hardcoded address dependencies still require profile-aware migration",
            "instance binding/install/start/mode/reset not authorized",
            "SQL KINGDOMS2 and Phase 03 runtime regressions pending",
        ],
    }
    return {
        **staged_inventories,
        **windows_assets,
        "providers/vmware/Vagrantfile": recipe,
        "instance-preview/Vagrantfile": vagrant,
        "router/provision.sh": script,
        "manifest.json": json.dumps(manifest, indent=2) + "\n",
    }


def _output_dir(path: Path) -> Path:
    """Private out-of-repo path only; never touch a Kingdoms instance tree."""
    require(path.is_absolute(), "candidate output path must be absolute")
    require(not path.exists() and not path.is_symlink(),
            "candidate output exists, refuses overwrite")
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink(), "symlinked output ancestry")
        require(ancestor.name != "workspace",
                "candidate output cannot reside inside a Kingdoms workspace")
        require(not (ancestor / "instance.json").exists()
                and not (ancestor / ".vagrant").exists(),
                "candidate output may not overlap installed Vagrant state")
    target = path.resolve()
    require(not target.is_relative_to(PROJECT.resolve()),
            "candidate output must not be inside the Kingdoms source checkout")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True,
                        help="nondeployable three-zone JSON design")
    parser.add_argument("--output", type=Path,
                        help="write isolated candidate outside Git and workspaces")
    args = parser.parse_args()
    try:
        plan = json.loads(args.proposal.read_text(encoding="utf-8"))
        artifacts = render_candidate(plan)
        summary = json.loads(artifacts["manifest.json"])
        if args.output is not None:
            destination = _output_dir(args.output.expanduser())
            old = os.umask(0o077)
            try:
                destination.mkdir(mode=0o700, parents=True, exist_ok=False)
                for filename, content in artifacts.items():
                    output = destination / filename
                    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    output.write_text(content, encoding="utf-8")
                    output.chmod(0o600)
            finally:
                os.umask(old)
            print("[PASS] Private VMware/router source candidate rendered")
        else:
            print("[PASS] Course 1 VMware/router source candidate validated in memory")
        print(json.dumps({k: summary[k] for k in
                         ("profile", "state", "zones", "windows_machines",
                          "deployment_authorized", "incomplete")}, indent=2))
        print("[BLOCKED] This is not an installable Vagrant/Ansible instance")
    except (OSError, ValueError, TypeError, ProfileNotReady) as exc:
        parser.exit(1, "[FAIL] " + str(exc) + "\n")


if __name__ == "__main__":
    main()
