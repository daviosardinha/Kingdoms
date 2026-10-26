"""PURPLE VMware network gate. PURPLE NEVER edits /etc/vmware or NORTH.

The laptop pilot uses an already present host-only vmnet4. This module is
read-only on both 'plan' and 'ensure', so an existing NORTH owner record and
its immutable VMware network baseline remain untouched.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import pwd
import re
import subprocess
from pathlib import Path

NETWORKING = Path("/etc/vmware/networking")
VMNET = "vmnet4"
CIDR = ipaddress.ip_network("172.28.233.0/24")
PROPOSED_HOSTS = (30, 31, 32, 51)
MACS = frozenset(
    f"00:50:56:10:04:{suffix:02x}" for suffix in (0x30, 0x31, 0x32, 0x51)
)
VMX_REGISTRY = re.compile(r'(?m)^vmlist\d+\.config\s*=\s*"([^"]+)"')
VMX_NET = re.compile(r'(?im)^\s*ethernet\d+\.vnet\s*=\s*"([^"]+)"')
VMX_MAC = re.compile(
    r'(?im)^\s*ethernet\d+\.(?:address|generatedaddress)\s*=\s*"([^"]+)"'
)


class PurpleNetworkError(RuntimeError):
    pass


def _exec(*argv: str):
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PurpleNetworkError("Cannot inspect " + argv[0]) from exc
    if p.returncode != 0:
        raise PurpleNetworkError(
            f"{argv[0]} failed: " + (p.stderr or p.stdout)[:220]
        )
    return p.stdout


def validate_config(content: str):
    """Validate *only* existing vmnet4 declarations; never synthesize one."""
    prefix = "VNET_4_"
    values: dict[str, str] = {}
    for raw in content.splitlines():
        if raw.lstrip().startswith("#"):
            continue
        terms = raw.split()
        if len(terms) >= 2 and terms[0] == "answer" and terms[1].startswith(prefix):
            if len(terms) != 3:
                raise PurpleNetworkError("Malformed vmnet4 setting")
            key = terms[1][len(prefix):]
            if key in values:
                raise PurpleNetworkError("Duplicate vmnet4 setting: " + key)
            values[key] = terms[2]
    for key, expected in {
        "HOSTONLY_SUBNET": str(CIDR.network_address),
        "HOSTONLY_NETMASK": "255.255.255.0",
        "DHCP": "no",
        "NAT": "no",
        "VIRTUAL_ADAPTER": "yes",
    }.items():
        if values.get(key) != expected:
            raise PurpleNetworkError(
                f"Existing {VMNET} {key}: expected {expected}, "
                f"got {values.get(key, 'missing')}"
            )


def validate_vmx(vmware_inventory: str, contents: dict[str, str]):
    """Block if *any other* registered VMware guest owns vmnet4 or Purple MAC."""
    for path in VMX_REGISTRY.findall(vmware_inventory):
        if path not in contents:
            raise PurpleNetworkError("Cannot inspect registered VMware guest: " + path)
        source = contents[path]
        nets = {s.lower() for s in VMX_NET.findall(source)}
        macs = {s.lower() for s in VMX_MAC.findall(source)}
        if VMNET in nets or MACS & macs:
            raise PurpleNetworkError(
                "A registered VM already uses Purple network/MAC: " + path
            )


def check_host(provider_dir: str | None = None):
    if NETWORKING.is_symlink() or not NETWORKING.is_file():
        raise PurpleNetworkError("VMware networking configuration is missing/unsafe")
    validate_config(NETWORKING.read_text(encoding="utf-8"))

    # Hosts must have an existing host-only interface and route. Read only.
    address = _exec("ip", "-o", "-4", "addr", "show", "dev", VMNET)
    host_cidrs = re.findall(r"\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)", address)
    if len(host_cidrs) != 1 or ipaddress.ip_interface(host_cidrs[0]).network != CIDR:
        raise PurpleNetworkError("vmnet4 host adapter is missing its expected /24")
    host_addr = ipaddress.ip_interface(host_cidrs[0]).ip
    if host_addr in {CIDR.network_address + n for n in PROPOSED_HOSTS}:
        raise PurpleNetworkError("VMware host IP would conflict with a Purple guest")

    if not Path("/dev/vmnet4").exists():
        raise PurpleNetworkError("vmnet4 device is absent")
    routes = _exec("ip", "-4", "route", "show", "table", "all")
    if not any(re.match(r"^172[.]28[.]233[.]0/24\s+.*\bdev vmnet4\b", line)
               for line in routes.splitlines()):
        raise PurpleNetworkError("Expected local route via vmnet4 is missing")
    for line in routes.splitlines():
        if re.match(r"^172[.]28[.]233[.]0/24\s+", line) and "dev vmnet4" not in line:
            raise PurpleNetworkError("Conflicting host route to Purple subnet")

    # Resolve the actual VMware desktop inventory, including under sudo.
    user = os.environ.get("SUDO_USER")
    home = Path(pwd.getpwnam(user).pw_dir) if user else Path.home()
    registry = home / ".vmware/inventory.vmls"
    if registry.is_symlink():
        raise PurpleNetworkError("Unsafe VMware inventory symlink")
    if registry.exists():
        source = registry.read_text(encoding="utf-8")
        registered = {}
        for raw in VMX_REGISTRY.findall(source):
            p = Path(raw)
            if p.is_symlink() or not p.is_file():
                raise PurpleNetworkError("Registered VMware VMX missing: " + raw)
            registered[raw] = p.read_text(encoding="utf-8", errors="replace")
        validate_vmx(source, registered)

    # If a generated provider folder is supplied, do not accept an unknown
    # or symlinked target. No modifications are performed.
    if provider_dir is not None:
        path = Path(provider_dir)
        if path.is_symlink() or not path.is_absolute() or not path.is_dir():
            raise PurpleNetworkError("Purple instance provider path not ready")
    print(f"[PASS] {VMNET} exists, host-only, static {CIDR}, no DHCP/NAT")
    print("[PASS] No registered VMware guest owns PURPLE network/MACs")
    print("[PASS] NORTH network settings and ownership unchanged")
    print("[NOTE] Vagrant management NAT may still change on VM deployment")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "ensure", "verify"))
    parser.add_argument("--provider-dir")
    args = parser.parse_args()
    try:
        check_host(args.provider_dir)
    except (OSError, ValueError, PurpleNetworkError) as exc:
        parser.exit(1, f"[BLOCKED] PURPLE network preflight: {exc}\n")


if __name__ == "__main__":
    main()
