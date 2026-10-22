"""VMware Workstation Linux service and vmnet4 host interface adapter.

Internal building block, NOT a CLI and NOT wired into WSLPE installation.
Caller MUST enforce zero guests + full ownership preflight + independent
firewall isolation proof before enabling the transaction.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Callable

from kingdoms.wslpe_management_vmnet_plan import inventory
from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked


BIN = Path("/usr/bin/vmware-networks")
IP = Path("/usr/bin/ip")
MAX_RESULT = 200_000


def _trusted_binary(path: Path, *, allow_trusted_symlink: bool = False) -> None:
    """Require trusted system binaries; allow vendor/OS links only when requested.

    vmware-networks and ip remain strict regular-file paths. vmrun and pgrep
    may be root-owned symlinks to other root-controlled /usr binaries.
    Refuse writable directory chains and symlinks into non-system locations.
    """
    if not path.is_absolute():
        raise NetworkTransactionBlocked(f"Unsafe nonabsolute host binary: {path}")
    try:
        entry = path.lstat()
        if stat.S_ISLNK(entry.st_mode):
            if not allow_trusted_symlink:
                raise NetworkTransactionBlocked(f"Symlinked binary not permitted: {path}")
            if entry.st_uid != 0:
                raise NetworkTransactionBlocked(f"Non-root-owned binary symlink: {path}")
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(Path("/usr")):
                raise NetworkTransactionBlocked(
                    f"Binary symlink leaves trusted /usr hierarchy: {path} -> {resolved}"
                )
            # Check both original and resolved directory chains, including
            # world/group writable parents and intermediate symlink paths.
            for directory in set(path.parents) | set(resolved.parents):
                metadata = directory.lstat()
                if (not stat.S_ISDIR(metadata.st_mode)
                        or metadata.st_uid != 0 or metadata.st_mode & 0o022):
                    raise NetworkTransactionBlocked(
                        f"Untrusted executable parent directory: {directory}"
                    )
            details = resolved.stat()
        else:
            details = entry
    except (OSError, RuntimeError) as exc:
        raise NetworkTransactionBlocked(f"Host binary path cannot be verified: {path}") from exc
    if (not stat.S_ISREG(details.st_mode) or details.st_uid != 0
            or details.st_mode & 0o022 or not details.st_mode & 0o111):
        raise NetworkTransactionBlocked(f"Host binary ownership/mode unsafe: {path}")


def _host_run(args: list[str], *, timeout: int = 90) -> str:
    try:
        result = subprocess.run(
            args, timeout=timeout, check=False, capture_output=True,
            text=True, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NetworkTransactionBlocked(f"Host command failed: {args[0]}") from exc
    if (result.returncode != 0 or len(result.stdout) > MAX_RESULT
            or len(result.stderr) > MAX_RESULT):
        raise NetworkTransactionBlocked(f"Host command failed: {args[0]} (rc={result.returncode})")
    return result.stdout


class WorkstationNetworkService:
    """Exact stop/start operations, only inside the protected transaction lock.

    This class must not be passed to the transaction until the caller proves
    exclusive maintenance, zero guests, and complete VMware consumer ownership.
    """

    def __init__(self, *, binary: Path = BIN,
                 run: Callable[..., str] = _host_run):
        self.binary = binary
        self.run = run

    def action(self, operation: str) -> None:
        if operation not in {"stop", "start"}:
            raise NetworkTransactionBlocked("Unexpected VMware service operation")
        if os.geteuid() != 0:
            raise NetworkTransactionBlocked("VMware host networking requires root")
        _trusted_binary(self.binary)
        # Never use the shell, scripts, service wildcards or vmrun power actions.
        self.run([str(self.binary), "--" + operation], timeout=90)


def _json_list(raw: str, command: str) -> list:
    if not raw or len(raw) > MAX_RESULT:
        raise NetworkTransactionBlocked(f"Empty or excessive host {command} output")
    try:
        rows = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise NetworkTransactionBlocked(f"Malformed host {command} JSON") from exc
    if not isinstance(rows, list):
        raise NetworkTransactionBlocked(f"Invalid host {command} JSON shape")
    return rows


def validate_vmnet4_host_state(*, vmnet: str, subnet: str,
                               networking_text: str,
                               address_rows: list, link_rows: list,
                               route_rows: list) -> str:
    """Validate the host adapter: NOT a Windows or firewall isolation proof."""
    if vmnet != "vmnet4" or subnet != "172.28.233.0/24":
        raise NetworkTransactionBlocked("Wrong fresh WSLPE operator network")
    expected = ipaddress.IPv4Network(subnet, strict=True)
    item = inventory(networking_text).get(4)
    required = {
        "HOSTONLY_SUBNET": "172.28.233.0",
        "HOSTONLY_NETMASK": "255.255.255.0",
        "HOSTONLY_HOSTADDR": "172.28.233.254",
        "DHCP": "no",
        "NAT": "no",
        "VIRTUAL_ADAPTER": "yes",
    }
    if item is None or any(item.get(key) != value for key, value in required.items()):
        raise NetworkTransactionBlocked("vmnet4 VMware metadata does not match host-only contract")

    if (len(address_rows) != 1 or len(link_rows) != 1
            or address_rows[0].get("ifname") != vmnet
            or link_rows[0].get("ifname") != vmnet):
        raise NetworkTransactionBlocked("vmnet4 host adapter is absent or ambiguous")
    link = link_rows[0]
    if ("UP" not in link.get("flags", []) or link.get("operstate") not in ("UP", "UNKNOWN")):
        raise NetworkTransactionBlocked("vmnet4 host adapter is down")
    ip_entries = [
        a for a in address_rows[0].get("addr_info", [])
        if a.get("family") == "inet"
    ]
    if len(ip_entries) != 1 or (
        ip_entries[0].get("local"), ip_entries[0].get("prefixlen")
    ) != ("172.28.233.254", 24):
        raise NetworkTransactionBlocked("vmnet4 must have only 172.28.233.254/24")
    if not route_rows or not all(isinstance(r, dict) for r in route_rows):
        raise NetworkTransactionBlocked("Missing IPv4 vmnet4 route evidence")
    if not any(r.get("dst") == str(expected) and r.get("dev") == vmnet
               for r in route_rows):
        raise NetworkTransactionBlocked("Expected connected vmnet4 route absent")
    if any(r.get("dst", "default") not in (str(expected),)
           or r.get("dev") != vmnet for r in route_rows):
        raise NetworkTransactionBlocked("Unexpected routing via operator vmnet4")
    return "HOST_VMNET4_ADDRESS_AND_METADATA=PASS"


class WorkstationHostAdapterVerifier:
    """Live bounded iproute2 read checks, not sufficient for full isolation.

    The transaction MUST still receive an independent firewall/network
    isolation capability. Do not wire this verifier as that final capability.
    """

    def __init__(self, *, ip_binary: Path = IP,
                 run: Callable[..., str] = _host_run):
        self.ip_binary = ip_binary
        self.run = run

    def verify_host_adapter(self, vmnet: str, subnet: str,
                            networking_text: str) -> str:
        _trusted_binary(self.ip_binary)
        binary = str(self.ip_binary)
        commands = (
            [binary, "-j", "-4", "address", "show", "dev", vmnet],
            [binary, "-j", "link", "show", "dev", vmnet],
            [binary, "-j", "-4", "route", "show", "dev", vmnet],
        )
        data = [_json_list(self.run(parts, timeout=15), kind)
                for parts, kind in zip(commands, ("address", "link", "route"))]
        return validate_vmnet4_host_state(
            vmnet=vmnet, subnet=subnet, networking_text=networking_text,
            address_rows=data[0], link_rows=data[1], route_rows=data[2],
        )
