"""Read-only WSLPE /24 chooser for a *disposable* fresh-install pilot.

No vmnet creation, host networking restart, firewall edits, Vagrant invocation,
or installation is performed here. The existing host preflight remains the
authority for candidate subnet eligibility.
"""
from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import json
import re
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/wslpe-check-host-network.py"
NETWORKING = Path("/etc/vmware/networking")

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
        inventory(config)
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



VMWARE_LIBRARY = Path.home() / ".vmware/inventory.vmls"
VAGRANT_INDEX = Path.home() / ".vagrant.d/data/machine-index/index"
REGISTERED = re.compile(r'(?m)^vmlist\d+\.config\s*=\s*"([^"]+)"\s*$')
WSLPE_NAME = re.compile(r'(?i)(wslpe[-_]?ws01|kingdoms[-_]lpe[-_]ws01|[/\\]wslpe[/\\]|kingdoms-lpe-standalone)')


def require_no_existing_wslpe_registration(
    library: Path = VMWARE_LIBRARY, vagrant_index: Path = VAGRANT_INDEX,
) -> None:
    """Refuse a second master alongside an offline registered machine."""
    library = Path(library)
    vagrant_index = Path(vagrant_index)
    for path in (library, vagrant_index):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise NetworkSelectionError("Unsafe VMware/Vagrant registered-machine index")
    if library.is_file():
        try:
            text = library.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise NetworkSelectionError("Unreadable VMware inventory") from exc
        for item in REGISTERED.findall(text):
            if WSLPE_NAME.search(item):
                raise NetworkSelectionError("Existing registered WSLPE VMX; use a clean host")
            vmx = Path(item)
            if vmx.is_file() and not vmx.is_symlink():
                try:
                    contents = vmx.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    raise NetworkSelectionError("Cannot inspect registered guest identity") from exc
                if any(WSLPE_NAME.search(line) for line in contents.splitlines()
                       if line.strip().lower().startswith("displayname")):
                    raise NetworkSelectionError("Registered WSLPE master found in VMware inventory")
            elif vmx.is_symlink():
                raise NetworkSelectionError("Unsafe registered VMware VMX link")
    if vagrant_index.is_file():
        try:
            data = json.loads(vagrant_index.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise NetworkSelectionError("Cannot inspect Vagrant machine index") from exc
        machines = data.get("machines") if isinstance(data, dict) else None
        if not isinstance(machines, dict):
            raise NetworkSelectionError("Unsupported Vagrant machine index structure")
        for entry in machines.values():
            if not isinstance(entry, dict):
                raise NetworkSelectionError("Malformed registered Vagrant machine")
            if (WSLPE_NAME.search(str(entry.get("name", ""))) or
                    WSLPE_NAME.search(str(entry.get("vagrantfile_path", "")))):
                raise NetworkSelectionError("Existing WSLPE Vagrant registration; use a clean host")


def choose_live(*, fresh_boot: bool = True) -> dict:
    """Read host state; only an actual boot demands zero live/registered peers."""
    if fresh_boot:
        require_no_running_guests()
        require_no_existing_wslpe_registration()
    checker = _checker()
    try:
        addresses = checker.run_ip("address", "show")
        routes = checker.run_ip("route", "show", "table", "all")
        config = _network_config()
        selected = choose_prefix(config, addresses, routes)
    except (ValueError, OSError) as exc:
        raise NetworkSelectionError(f"Live WSLPE network selection blocked: {exc}") from exc
    if fresh_boot:
        require_no_running_guests()
        require_no_existing_wslpe_registration()
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
