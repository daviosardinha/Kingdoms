#!/usr/bin/env python3
"""Preview the real Kingdoms WSLPE instance artifacts in a disposable directory.

Read-only toward the operator's Kingdoms instance state and VMware provider.
Invokes the existing LabInstance rendering methods, never create_instance_folder,
Vagrant, Ansible, or any instance mutation.
"""
from __future__ import annotations

import argparse
import ipaddress
import re
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from goad.instance import LabInstance
from goad.goadpath import GoadPath

EXPECTED_GUEST = "WSLPE-WS01"
EXPECTED_BOX = "mayfly/windows10"
EXPECTED_VERSION = "2024.01.06"
NORTH_SEGMENTS = ipaddress.ip_network("10.4.0.0/16")


def validate_prefix(value: str) -> ipaddress.IPv4Network:
    """Require an explicit private /24 outside the reserved NORTH range."""
    if not re.fullmatch(r"(?:\d{1,3}\.){2}\d{1,3}", value):
        raise ValueError("Specify an IPv4 three-octet prefix (example: 192.168.240)")
    try:
        network = ipaddress.ip_network(value + ".0/24", strict=True)
    except ValueError as exc:
        raise ValueError("Invalid WSLPE IPv4 prefix") from exc
    if not network.is_private or network.is_loopback or network.is_link_local:
        raise ValueError("WSLPE requires private non-loopback IPv4 addressing")
    if network.overlaps(NORTH_SEGMENTS):
        raise ValueError("WSLPE cannot overlap reserved NORTH 10.4.0.0/16")
    return network


def render_preview(prefix: str, destination: Path) -> dict[str, str]:
    """Use the actual LabInstance render functions and check their output."""
    network = validate_prefix(prefix)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    provider_dir = destination / "provider"
    provider_dir.mkdir()

    instance = LabInstance(
        "wslpe-source-preview", "WSLPE", None, "vmware", "local",
        prefix, extensions=[],
    )
    # The constructor calculates paths only. Override both before rendering.
    instance.instance_path = str(destination)
    instance.instance_provider_path = str(provider_dir)
    instance._create_vagrantfile()
    instance._create_provisioning_lab_inventory("inventory_disable_vagrant")
    instance._create_provisioning_provider_inventory()

    vm_text = (provider_dir / "Vagrantfile").read_text(encoding="utf-8")
    provider_inventory = (destination / "inventory").read_text(encoding="utf-8")
    disabled_inventory = (
        destination / "inventory_disable_vagrant"
    ).read_text(encoding="utf-8")

    # The initial Ansible stage reads the lab inventory from source directly,
    # not from the instance's post-Vagrant inventory. Match its Jinja inputs.
    lab_env = Environment(
        loader=FileSystemLoader(GoadPath.get_lab_data_path("WSLPE"))
    )
    lab_inventory = lab_env.get_template("inventory").render(
        lab_name="WSLPE", ip_range=prefix, provider_name="vmware"
    )

    guests = re.findall(r':name\s*=>\s*"([^"]+)"', vm_text)
    if guests != [EXPECTED_GUEST]:
        raise ValueError(f"Expected one WSLPE VM, rendered: {guests!r}")
    if f':box => "{EXPECTED_BOX}"' not in vm_text:
        raise ValueError("Windows box missing from native Vagrantfile")
    if f':box_version => "{EXPECTED_VERSION}"' not in vm_text:
        raise ValueError("Pinned box version missing")
    ip = f"{prefix}.31"
    if f':ip => "{ip}"' not in vm_text:
        raise ValueError("VM exercise IP was not rendered")
    if "target.vm.network :private_network, ip: box[:ip]" not in vm_text:
        raise ValueError("Existing Kingdoms private-network template not in use")
    if any(
        marker in vm_text for marker in (
            ':name => "GOAD-', "vmnet10", "vmnet20", "vmnet30", "vmnet99",
        )
    ):
        raise ValueError("NORTH-specific machine or VMware vmnet in WSLPE")
    if f"ws01 ansible_host={ip}" not in provider_inventory:
        raise ValueError("Provider inventory does not match guest IP")
    if f"ws01 ansible_host={ip}" not in disabled_inventory:
        # The post-Vagrant inventory currently uses groups without host IPs;
        # provider inventory still carries host addressing. Future overrides
        # must not bypass this source-only preview unexpectedly.
        if "ansible_connection=winrm" not in disabled_inventory:
            raise ValueError("Post-Vagrant inventory is not a Windows inventory")
    for name, source in (
        ("initial", lab_inventory),
        ("post-vagrant", disabled_inventory),
    ):
        if "[wslpe]" not in source or "[windows_lpe_standalone]" not in source:
            raise ValueError(f"{name} inventory lacks required WSLPE group")
        if "ansible_connection=winrm" not in source:
            raise ValueError(f"{name} inventory lacks WinRM transport")
        if "[dc]" in source or "north.sevenkingdoms.local" in source:
            raise ValueError(f"{name} inventory contains AD configuration")

    return {
        "guest": EXPECTED_GUEST,
        "box": EXPECTED_BOX,
        "version": EXPECTED_VERSION,
        "candidate_network": str(network),
        "guest_ip": ip,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ip-range", required=True,
        help="Candidate private three-octet /24 prefix (read-only simulation)",
    )
    args = parser.parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix="kingdoms-wslpe-render-") as tmp:
            report = render_preview(args.ip_range, Path(tmp))
            print("KINGDOMS WSLPE NATIVE INSTANCE RENDER: SOURCE PREVIEW PASS")
            for key, value in report.items():
                print(f"{key}={value}")
            print("Live host/VMware vmnet collision validation: NOT PERFORMED")
            print("Kingdoms workspace, VMware, Vagrant, WinRM, Ansible: NOT MODIFIED")
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"[BLOCKED] {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
