"""Read-only WSLPE /24 chooser for a *disposable* fresh-install pilot.

No vmnet creation, host networking restart, firewall edits, Vagrant invocation,
or installation is performed here. The existing host preflight remains the
authority for candidate subnet eligibility.
"""
from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/wslpe-check-host-network.py"
NETWORKING = Path("/etc/vmware/networking")
NORTH_OWNER = Path("/etc/vmware/kingdoms-course1-owner.json")

# Deliberately deterministic and narrow. The old operator's 172.28.231/24
# is NOT reserved globally; it is selected only when live inspection says free.
CANDIDATES = (
    tuple(f"172.28.{n}" for n in range(231, 255)) +
    tuple(f"172.29.{n}" for n in range(200, 255)) +
    tuple(f"172.30.{n}" for n in range(200, 255))
)


class NetworkSelectionError(ValueError):
    pass


def _checker():
    spec = importlib.util.spec_from_file_location("kingdoms_wslpe_network_check", CHECKER)
    if spec is None or spec.loader is None:
        raise NetworkSelectionError("The existing WSLPE host-network checker is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def choose_prefix(config: str, addresses: list, routes: list, *,
                  candidates=CANDIDATES) -> dict:
    """Choose a verified free /24 or fail rather than reusing any existing one."""
    from kingdoms.wslpe_management_vmnet_plan import inventory

    # Unlike the earlier lightweight read-only checker, this gate first
    # rejects duplicate and malformed VNET declarations before making a plan.
    try:
        vmnets = inventory(config)
        for identifier, settings in vmnets.items():
            if ("HOSTONLY_SUBNET" in settings) != ("HOSTONLY_NETMASK" in settings):
                raise ValueError(f"vmnet{identifier} has incomplete subnet metadata")
    except (ValueError, TypeError) as exc:
        raise NetworkSelectionError(f"Unsafe VMware network metadata: {exc}") from exc
    checker = _checker()
    inspected = []
    for value in candidates:
        try:
            candidate = checker.parse_prefix(value)
            _evidence, conflicts = checker.assess(candidate, addresses, routes, config)
        except (TypeError, ValueError, KeyError) as exc:
            raise NetworkSelectionError(f"Cannot reliably inspect host network: {exc}") from exc
        if not conflicts:
            return {
                "prefix": value,
                "cidr": str(candidate),
                "guest_ip": f"{value}.31",
                "networking_sha256": hashlib.sha256(config.encode("utf-8")).hexdigest(),
                "mode": "READ_ONLY_FRESH_PILOT",
                "scanned_candidates": len(inspected) + 1,
            }
        inspected.append(value)
    raise NetworkSelectionError("No collision-free private WSLPE /24 in approved candidate pool")


def require_no_installed_north_owner(owner: Path | None = None) -> None:
    """Fail closed before Vagrant can add another vmnet to a NORTH-owned host.

    A collision-free IP range alone does not prove that NORTH's immutable
    VMware ownership contract will accept the newly allocated vmnet. This
    pilot has no cross-instance attestation/rollback transaction yet.
    """
    path = NORTH_OWNER if owner is None else Path(owner)
    if path.exists() or path.is_symlink():
        raise NetworkSelectionError(
            "Installed NORTH VMware owner detected; fresh WSLPE boot on this "
            "host is deferred until verified multi-instance vmnet ownership "
            "is integrated. The read-only plan remains available."
        )


def require_no_running_guests():
    """Never initiate new VMware network allocation while peer guests run."""
    try:
        result = subprocess.run(
            ["vmrun", "-T", "ws", "list"], capture_output=True,
            text=True, check=False, timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NetworkSelectionError("Cannot establish VMware running guest inventory") from exc
    if result.returncode != 0 or result.stdout.strip() != "Total running VMs: 0":
        raise NetworkSelectionError(
            "Fresh-install pilot requires no running VMware guests; do not disturb NORTH"
        )
    try:
        vmx = subprocess.run(
            ["pgrep", "-x", "vmware-vmx"], capture_output=True,
            text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NetworkSelectionError("Cannot independently inspect VMware guest processes") from exc
    if vmx.returncode != 1:
        raise NetworkSelectionError("VMware guest process active or uninspectable")


def _network_config() -> str:
    if NETWORKING.is_symlink() or not NETWORKING.is_file():
        raise NetworkSelectionError("VMware networking metadata is missing or unsafe")
    try:
        data = NETWORKING.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise NetworkSelectionError("Cannot read VMware networking metadata") from exc
    if not data.strip():
        raise NetworkSelectionError("Empty VMware networking metadata")
    return data



def choose_live(*, fresh_boot: bool = True) -> dict:
    """Read host state; actual boot requires zero live peer VMware guests."""
    if fresh_boot:
        require_no_installed_north_owner()
        require_no_running_guests()
    checker = _checker()
    try:
        addresses = checker.run_ip("address", "show")
        routes = checker.run_ip("route", "show", "table", "all")
        config = _network_config()
        selected = choose_prefix(config, addresses, routes)
    except (ValueError, OSError) as exc:
        raise NetworkSelectionError(f"Live WSLPE network selection blocked: {exc}") from exc
    if fresh_boot:
        require_no_installed_north_owner()
        require_no_running_guests()
    return selected


def assert_plan_still_valid(plan: dict) -> None:
    """Refuse instance creation if evidence changed during preboot acceptance."""
    if not isinstance(plan, dict) or plan.get("mode") != "READ_ONLY_FRESH_PILOT":
        raise NetworkSelectionError("Missing fresh-pilot allocation provenance")
    current = choose_live()
    if (current["prefix"] != plan.get("prefix") or
            current["cidr"] != plan.get("cidr") or
            current["networking_sha256"] != plan.get("networking_sha256")):
        raise NetworkSelectionError("Host network changed after WSLPE selection; restart planning")
