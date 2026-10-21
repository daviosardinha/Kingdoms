"""Read-only native WSLPE registration proof, never a freshness attestation.

A VM registered under a new instance may still be a copied or reused guest.
A future installer must separately prove a creation nonce, independent secrets,
management isolation and TLS pin before calling install_41.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import re

from kingdoms.wslpe41_host_preflight import HostEvidenceBlocked, running_vm_count


MACHINE = "WSLPE-WS01"
STATUS = "ready for provisioning"


@dataclass(frozen=True)
class NativeGuestRegistration:
    instance_id: str
    vmx: str
    subnet: str
    guest_address: str
    source: str = "read-only native registration (NOT fresh-build proof)"


def inspect_native_registration(instance: Path, vmrun_output: str) -> NativeGuestRegistration:
    """Validate one exact WSLPE provider registration, without guest mutation."""
    if instance.is_symlink() or not instance.is_dir() or not instance.is_absolute():
        raise HostEvidenceBlocked("Native instance path must be absolute, real and existing")
    manifest = instance / "instance.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 200_000:
        raise HostEvidenceBlocked("Native instance manifest is unsafe")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise HostEvidenceBlocked("Native instance manifest unreadable") from exc
    if not isinstance(data, dict):
        raise HostEvidenceBlocked("Native instance manifest invalid")
    identity = data.get("id")
    if (not isinstance(identity, str) or identity != instance.name
            or not re.fullmatch(r"[A-Za-z0-9_-]{4,100}", identity)
            or data.get("lab") != "WSLPE"
            or data.get("provider") != "vmware"
            or data.get("provisioner") != "local"
            or data.get("status") != STATUS
            or data.get("extensions")):
        raise HostEvidenceBlocked("Native instance is not an exact provided WSLPE guest")
    prefix = data.get("ip_range")
    if not isinstance(prefix, str) or not re.fullmatch(r"(?:\d{1,3}\.){2}\d{1,3}", prefix):
        raise HostEvidenceBlocked("Native WSLPE prefix invalid")
    try:
        subnet = ipaddress.IPv4Network(prefix + ".0/24", strict=True)
    except ValueError as exc:
        raise HostEvidenceBlocked("Native WSLPE prefix invalid") from exc
    if (not subnet.is_private or subnet.is_loopback or subnet.is_link_local
            or subnet.overlaps(ipaddress.IPv4Network("10.4.0.0/16"))):
        raise HostEvidenceBlocked("Native WSLPE overlaps a reserved network")
    provider = instance / "provider"
    if provider.is_symlink() or not provider.is_dir():
        raise HostEvidenceBlocked("Native provider directory unsafe")
    machine = provider / ".vagrant" / "machines" / MACHINE / "vmware_desktop"
    vmid = machine / "id"
    if vmid.is_symlink() or not vmid.is_file() or vmid.stat().st_size > 10_000:
        raise HostEvidenceBlocked("Native Vagrant registration missing or unsafe")
    try:
        raw = vmid.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise HostEvidenceBlocked("Native VMware registration unreadable") from exc
    vmx = Path(raw)
    if not vmx.is_absolute() or vmx.is_symlink():
        raise HostEvidenceBlocked("VMware VMX path must be absolute and nonlinked")
    try:
        vmx = vmx.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise HostEvidenceBlocked("Native VMware registration unreadable") from exc
    if not vmx.is_file() or vmx.suffix.lower() != ".vmx":
        raise HostEvidenceBlocked("Native VMware registration is not a VMX")
    if not vmx.is_relative_to(provider.resolve()):
        raise HostEvidenceBlocked("Native VMware VMX escapes its independent provider")
    if any(word in str(vmx).upper() for word in ("GOAD-DC", "GOAD-SRV", "GOAD-WS", "GOAD-ROUTER")):
        raise HostEvidenceBlocked("Native VMware registration references a domain guest")
    count = running_vm_count(vmrun_output)
    lines = [line.strip() for line in vmrun_output.splitlines() if line.strip()]
    registered = [Path(line).resolve() for line in lines[1:]]
    if count < 1 or registered.count(vmx) != 1:
        raise HostEvidenceBlocked("Exact native WSLPE VMX not uniquely running")
    return NativeGuestRegistration(
        instance_id=identity,
        vmx=str(vmx),
        subnet=str(subnet),
        guest_address=str(subnet.network_address + 31),
    )
