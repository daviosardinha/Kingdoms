"""Source-only WSLPE operator management vmnet allocation plan.

NEVER modifies /etc/vmware/networking or runs vmware-networks.
An active VM or any VMX referencing the candidate vmnet blocks planning approval.
"""
from __future__ import annotations

import ipaddress
from pathlib import Path
import re

from kingdoms.wslpe_portless_management import _usable_subnet
from kingdoms.wslpe_nic_contract import FORBIDDEN, parse_vmx_networks, check_provisioning_layout

KEY = re.compile(r"^answer\s+VNET_(\d+)_(\w+)\s+(\S+)\s*$")
VMX_VNET = re.compile(r'(?im)^\s*ethernet\d+\.vnet\s*=\s*"([^"]+)"\s*$')
OWNED_BY_NORTH = {10, 20, 30, 99}
RESERVED = {0, 1, 8} | OWNED_BY_NORTH
REQUIRED_WSLPE = {
    "VNET_2_HOSTONLY_NETMASK": "255.255.255.0",
    "VNET_2_HOSTONLY_SUBNET": "172.28.231.0",
    "VNET_2_DHCP": "no",
    "VNET_2_NAT": "no",
}


def inventory(source: str) -> dict[int, dict[str, str]]:
    if not isinstance(source, str) or not source.strip():
        raise ValueError("VMware networking file is absent or empty")
    result: dict[int, dict[str, str]] = {}
    for line in source.splitlines():
        m = KEY.fullmatch(line)
        if not m:
            if re.match(r"^answer\s+VNET_\d+_", line):
                raise ValueError("Malformed VMware VNET metadata")
            continue
        n, key, value = m.groups()
        entry = result.setdefault(int(n), {})
        if key in entry:
            raise ValueError(f"Duplicate VMware vmnet{n} configuration key")
        entry[key] = value
    if not result:
        raise ValueError("No VMware VNET metadata")
    return result


def native_exercise_binding(vmx_text: str, instance_prefix: str,
                            source: str) -> tuple[str, str]:
    """Read exact provider NIC+VMware metadata; do not assume old vmnet2."""
    if not isinstance(instance_prefix, str) or not re.fullmatch(
            r"(?:[0-9]{1,3}\.){2}[0-9]{1,3}", instance_prefix):
        raise ValueError("Native WSLPE exercise prefix invalid")
    try:
        expected = ipaddress.IPv4Network(instance_prefix + ".0/24", strict=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Native WSLPE exercise prefix invalid") from exc
    _usable_subnet(str(expected))
    nic_errors = check_provisioning_layout(vmx_text)
    slots = parse_vmx_networks(vmx_text)
    if nic_errors or set(slots) != {0, 1}:
        raise ValueError("Native guest must have exact current NAT/exercise adapters")
    name = slots[1].get("vnet", "")
    if (not re.fullmatch(r"vmnet[0-9]+", name) or name in FORBIDDEN):
        raise ValueError("Native WSLPE exercise vmnet missing or reserved")
    entry = inventory(source).get(int(name[5:]), {})
    if (entry.get("HOSTONLY_SUBNET") != str(expected.network_address)
            or entry.get("HOSTONLY_NETMASK") != "255.255.255.0"
            or entry.get("NAT") != "no"
            or entry.get("DHCP") != "no"):
        raise ValueError("Native WSLPE exercise vmnet metadata does not match guest")
    return name, str(expected)


def candidate_plan(source: str, *, vmnet: str, subnet: str,
                   exercise_vmnet: str = "vmnet2",
                   exercise_subnet: str = "172.28.231.0/24") -> str:
    """Append an independent network proposal; defaults preserve legacy vmnet2."""
    if not isinstance(vmnet, str) or not re.fullmatch(r"vmnet(?:[2-9]|[1-9]\d{1,2})", vmnet):
        raise ValueError("Invalid management vmnet number")
    number = int(vmnet[5:])
    if number in RESERVED:
        raise ValueError("Management vmnet is reserved for VMware or NORTH")
    net = ipaddress.IPv4Network(subnet, strict=True)
    _usable_subnet(str(net))
    if net.network_address.packed[-1] != 0 or net.prefixlen != 24:
        raise ValueError("Management network must be an exact /24")
    netinfo = inventory(source)
    if number in netinfo:
        raise ValueError(f"{vmnet} already exists; never adopt or overwrite it")
    if not isinstance(exercise_vmnet, str) or not re.fullmatch(
            r"vmnet[0-9]+", exercise_vmnet) or exercise_vmnet in FORBIDDEN:
        raise ValueError("Exact WSLPE exercise vmnet is missing or reserved")
    try:
        exercise_net = ipaddress.IPv4Network(exercise_subnet, strict=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid existing WSLPE exercise subnet") from exc
    _usable_subnet(str(exercise_net))
    if vmnet == exercise_vmnet or net.overlaps(exercise_net):
        raise ValueError("Management vmnet and subnet must differ from learner exercise")
    exercise = netinfo.get(int(exercise_vmnet[5:]), {})
    for key, wanted in (
        ("HOSTONLY_NETMASK", "255.255.255.0"),
        ("HOSTONLY_SUBNET", str(exercise_net.network_address)),
        ("DHCP", "no"), ("NAT", "no"),
    ):
        if exercise.get(key) != wanted:
            raise ValueError(f"Existing WSLPE exercise network does not match: {key}")
    for number_existing, info in netinfo.items():
        if "HOSTONLY_SUBNET" not in info:
            continue
        if "HOSTONLY_NETMASK" not in info:
            raise ValueError(f"vmnet{number_existing} has incomplete IPv4 metadata")
        try:
            existing = ipaddress.IPv4Network(
                (info["HOSTONLY_SUBNET"], info["HOSTONLY_NETMASK"]), strict=False)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"vmnet{number_existing} invalid IPv4 metadata") from exc
        if net.overlaps(existing):
            raise ValueError(f"Management network overlaps existing vmnet{number_existing}")
    for value in netinfo.values():
        if value.get("VIRTUAL_ADAPTER", "").lower() not in ("", "yes", "no"):
            raise ValueError("Unexpected VMware adapter metadata")
    # Source proposal ONLY; host-only management requires a host-side adapter.
    # Workstation 26 may drop HOSTONLY_HOSTADDR at startup. Live host-address
    # persistence is a separate review and never silently applied here.
    lines = [
        "# KINGDOMS WSLPE disposable operator management candidate - NOT APPLIED",
        f"# {vmnet} is NOT a learner exercise network; do not route to NORTH",
        f"answer VNET_{number}_DHCP no",
        f"answer VNET_{number}_HOSTONLY_HOSTADDR {net.network_address + 254}",
        f"answer VNET_{number}_HOSTONLY_NETMASK 255.255.255.0",
        f"answer VNET_{number}_HOSTONLY_SUBNET {net.network_address}",
        f"answer VNET_{number}_NAT no",
        f"answer VNET_{number}_VIRTUAL_ADAPTER yes",
    ]
    return source.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"


def vmx_conflicts(paths: list[Path], vmnet: str) -> list[str]:
    """Reject registered machine VMXs that already attach the candidate vmnet."""
    if not paths:
        raise ValueError("Provide inspected, dedicated NORTH and WSLPE VMware workspace roots")
    hits = []
    scanned = 0
    for root in paths:
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"Workspace missing or unsafe: {root}")
        # Scan dedicated workspace roots, NOT the whole home filesystem.
        for vmx in root.rglob("*.vmx"):
            scanned += 1
            if scanned > 200:
                raise ValueError("Too many VMXs; cannot establish finite ownership")
            if vmx.is_symlink() or not vmx.is_file():
                raise ValueError("Unknown or symlinked VMware guest VMX")
            text = vmx.read_text(encoding="utf-8", errors="replace")
            if vmnet in VMX_VNET.findall(text):
                hits.append(str(vmx))
    if scanned == 0:
        raise ValueError("No registered guest VMX found in supplied roots")
    return hits
