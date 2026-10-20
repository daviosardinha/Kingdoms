"""Read-only, root-attested WSLPE peer vmnet evidence for NORTH.

The root-owned peer record is an explicit operator-reviewed authorization of
one native WSLPE VMware registration, immutable VMX/Vagrant file bytes, one
non-overlapping host-only subnet and exact bootstrap forwarding ports.
It cannot be inferred from a guest filename or auto-created by this module.
No VMware, Vagrant, firewall or filesystem mutations occur here.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from goad.course1_vmnet_config import NetworkPlanError

PEER_RECORD = Path("/etc/vmware/kingdoms-wslpe-peer-owner.json")
SCHEMA = "kingdoms.north.wslpe-peer.v1"
REQUIRED_GUEST_PORTS = frozenset((22, 5985, 5986))


def _plain_file(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise NetworkPlanError("WSLPE peer source file missing or unsafe")
    return path.read_bytes()


def _unique_vmx_value(source: str, name: str) -> str:
    values = re.findall(
        r"(?im)^\s*" + re.escape(name) + r'\s*=\s*"([^"\r\n]+)"\s*$',
        source,
    )
    if len(values) != 1:
        raise NetworkPlanError("WSLPE VMX adapter definition missing or ambiguous")
    return values[0].lower()


def _host_interface(vmnet: str, subnet: ipaddress.IPv4Network, host: str):
    try:
        out = subprocess.run(
            ["ip", "-j", "-4", "addr", "show", "dev", vmnet],
            capture_output=True, text=True, timeout=8, check=False,
        )
        data = json.loads(out.stdout)
        expected = ipaddress.IPv4Address(host)
        if out.returncode or len(data) != 1 or data[0].get("ifname") != vmnet:
            raise ValueError("interface not uniquely available")
        addresses = [ipaddress.IPv4Interface(
            f'{addr["local"]}/{addr["prefixlen"]}'
        ) for addr in data[0].get("addr_info", []) if addr.get("family") == "inet"]
        if not any(x.ip == expected and x.network == subnet for x in addresses):
            raise ValueError("interface IPv4/subnet mismatch")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise NetworkPlanError("WSLPE vmnet interface does not match peer owner") from exc


def verified_wslpe_peer_additions(record_path=PEER_RECORD, owner_uid=0,
                                  inspect_host=True):
    """Authenticate exact peer additions or return None when no peer is approved.

    Never auto-discover/approve peer VMs. A root-owned, 0600 reviewed record
    is mandatory when the runtime network differs from NORTH's original owner.
    """
    path = Path(record_path)
    if not path.exists():
        return None
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise NetworkPlanError("WSLPE peer owner record is unsafe")
    meta = path.stat()
    if meta.st_uid != owner_uid or stat.S_IMODE(meta.st_mode) != 0o600:
        raise NetworkPlanError("WSLPE peer owner record must be root-owned mode 0600")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise NetworkPlanError("WSLPE peer owner record unreadable") from exc
    keys = {
        "schema", "vmx", "vmx_sha256", "vagrantfile", "vagrantfile_sha256",
        "vmnet", "subnet", "host_address", "guest_address", "host_ports",
    }
    if not isinstance(record, dict) or set(record) != keys or record["schema"] != SCHEMA:
        raise NetworkPlanError("WSLPE peer record schema or fields are not approved")
    try:
        vmnet = record["vmnet"]
        if not isinstance(vmnet, str) or not re.fullmatch(r"vmnet[0-9]+", vmnet):
            raise ValueError("invalid peer vmnet")
        netid = int(vmnet[5:])
        if netid in (1, 8, 10, 20, 30, 99) or netid == 0:
            raise ValueError("peer vmnet conflicts with existing Kingdoms networks")
        subnet = ipaddress.IPv4Network(record["subnet"], strict=True)
        if subnet.prefixlen != 24 or subnet.overlaps(ipaddress.IPv4Network("10.4.0.0/16")):
            raise ValueError("invalid peer /24")
        host = ipaddress.IPv4Address(record["host_address"])
        guest = ipaddress.IPv4Address(record["guest_address"])
        if host not in subnet.hosts() or guest not in subnet.hosts() or host == guest:
            raise ValueError("invalid host/guest pairing")
        ports = record["host_ports"]
        if not isinstance(ports, dict) or set(ports) != {"22", "5985", "5986"}:
            raise ValueError("WSLPE management port list is incomplete")
        if any(type(value) is not int or not (1025 <= value <= 65535)
               for value in ports.values()) or len(set(ports.values())) != len(ports):
            raise ValueError("invalid forwarded host ports")
        vmx = Path(record["vmx"])
        vagrant = Path(record["vagrantfile"])
        if vmx.parent.parent.name != "vmware_desktop" or (
            vmx.parent.parent.parent.name != "WSLPE-WS01"
        ):
            raise ValueError("not the native WSLPE-WS01 VMware instance")
        if vmx.parent.parent.parent.parent.name != "machines":
            raise ValueError("not inside the native Vagrant registration")
        if vmx.parent.parent.parent.parent.parent.name != ".vagrant":
            raise ValueError("not inside the native provider registration")
        provider = vmx.parent.parent.parent.parent.parent.parent
        if vagrant != provider / "Vagrantfile":
            raise ValueError("Vagrantfile does not belong to peer VMX provider")
        vmx_bytes = _plain_file(vmx)
        vagrant_bytes = _plain_file(vagrant)
        for key, raw in (("vmx_sha256", vmx_bytes), ("vagrantfile_sha256", vagrant_bytes)):
            checksum = record[key]
            if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise ValueError("bad peer SHA256")
            if hashlib.sha256(raw).hexdigest() != checksum:
                raise ValueError("peer VMX or Vagrantfile no longer matches approved bytes")
        vmx_content = vmx_bytes.decode("utf-8")
        if (_unique_vmx_value(vmx_content, "ethernet0.connectionType") != "nat"
                or _unique_vmx_value(vmx_content, "ethernet1.connectionType") != "custom"
                or _unique_vmx_value(vmx_content, "ethernet1.vnet") != vmnet):
            raise ValueError("peer VMware NIC role drift")
        vagrant_text = vagrant_bytes.decode("utf-8")
        ip_matches = re.findall(r""":ip\s*=>\s*['"](\d+\.\d+\.\d+\.\d+)['"]""",
                                vagrant_text)
        if ip_matches != [str(guest)]:
            raise ValueError("peer Vagrant guest address mismatch")
    except (TypeError, ValueError, KeyError, AttributeError, UnicodeError, OSError) as exc:
        raise NetworkPlanError("WSLPE peer record or native instance is not authenticated") from exc

    if inspect_host:
        _host_interface(vmnet, subnet, str(host))

    # Only these lines may be newly present relative to the immutable NORTH
    # baseline. Any other network directive stays blocked by NORTH's verifier.
    additions = {
        f"answer VNET_{netid}_DHCP no",
        f"answer VNET_{netid}_HOSTONLY_NETMASK 255.255.255.0",
        f"answer VNET_{netid}_HOSTONLY_SUBNET {subnet.network_address}",
        f"answer VNET_{netid}_NAT no",
        f"answer VNET_{netid}_VIRTUAL_ADAPTER yes",
    }
    additions.update(
        f"add_nat_portfwd 8 tcp {hostport} {guest} {guestport}"
        for guestport, hostport in ((int(k), v) for k, v in ports.items())
    )
    return frozenset(additions)
