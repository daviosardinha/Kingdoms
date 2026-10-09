"""Read-only Kingdoms Course 1 VMware Workstation host survey.

This discovers *observed* interfaces, routes, VMware reservations and running
VMX network identities. It neither allocates vmnets nor authorizes deployment.
Use the result to plan host-specific isolation; lack of observation is not
proof that a network identifier is unallocated.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import shutil
import subprocess
from pathlib import Path

from goad.course1_network_plan import reference_contract

NETWORKING = Path("/etc/vmware/networking")
VMWARE_ROOT = Path("/etc/vmware")
DEVICE_ROOT = Path("/dev")
KNOWN_VMNET = re.compile(r"vmnet[0-9]+\Z", re.I)
MAC = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\Z", re.I)
VMX_SETTING = re.compile(
    r'(?im)^\s*ethernet(\d+)\.(vnet|connectionType|address|generatedAddress|'
    r'present|startConnected|connected)\s*=\s*"([^"\r\n]*)"\s*$'
)


def parse_vmware_networking(data: str) -> tuple[list[str], list[dict]]:
    """Expose only vmnet IDs and configured IPv4 network hints."""
    names: set[str] = set()
    hints: list[dict] = []
    for raw in data.splitlines():
        match = re.match(r"^\s*answer\s+VNET_(\d+)_([A-Z0-9_]+)\s+(\S+)", raw)
        if match is None:
            continue
        ident, key, value = match.groups()
        label = f"vmnet{ident}"
        names.add(label)
        if key == "HOSTONLY_SUBNET":
            try:
                address = ipaddress.IPv4Address(value)
            except ipaddress.AddressValueError:
                continue
            hints.append({"vmnet": label, "subnet_address": str(address)})
    return sorted(names, key=vmnet_order), hints


def vmnet_order(name: str) -> int:
    return int(name[5:])


def parse_ip_addresses(text: str) -> list[dict]:
    records = json.loads(text)
    if not isinstance(records, list):
        raise ValueError("unexpected ip address JSON")
    parsed = []
    for interface in records:
        if not isinstance(interface, dict):
            continue
        ifname = interface.get("ifname")
        if not isinstance(ifname, str):
            continue
        ipv4: set[str] = set()
        for item in interface.get("addr_info", []):
            if item.get("family") != "inet":
                continue
            try:
                network = ipaddress.ip_interface(
                    f'{item["local"]}/{item["prefixlen"]}'
                )
                ipv4.add(str(network))
            except (KeyError, ValueError):
                continue
        parsed.append({
            "interface": ifname,
            "ipv4": sorted(ipv4),
            "state": interface.get("operstate", "UNKNOWN"),
        })
    return sorted(parsed, key=lambda item: item["interface"])


def parse_ip_routes(text: str) -> list[dict]:
    rows = json.loads(text)
    if not isinstance(rows, list):
        raise ValueError("unexpected ip route JSON")
    result = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        dest = item.get("dst", "default")
        if not isinstance(dest, str):
            continue
        record = {"destination": dest}
        for src, dst in (("dev", "interface"), ("gateway", "gateway"),
                         ("prefsrc", "source"), ("table", "table")):
            value = item.get(src)
            if isinstance(value, (str, int)):
                record[dst] = value
        result.append(record)
    return sorted(result, key=lambda x: (str(x.get("table", "")),
                                         x["destination"],
                                         x.get("interface", "")))


def parse_vmrun_list(text: str) -> list[Path]:
    rows = text.splitlines()
    if not rows or not re.fullmatch(r"Total running VMs:\s*\d+", rows[0].strip()):
        raise ValueError("unrecognized vmrun list header")
    count = int(rows[0].split(":")[-1])
    paths = [Path(line.strip()) for line in rows[1:] if line.strip()]
    if len(paths) != count or any(not path.is_absolute() or path.suffix.lower() != ".vmx"
                                   for path in paths):
        raise ValueError("vmrun reported an inconsistent VMX list")
    return paths


def parse_vmx_adapters(text: str) -> list[dict]:
    adapters: dict[int, dict[str, str]] = {}
    for match in VMX_SETTING.finditer(text):
        number, key, value = match.groups()
        if key in ("address", "generatedAddress"):
            value = value.lower()
            if not MAC.fullmatch(value):
                continue
        if key == "vnet" and KNOWN_VMNET.fullmatch(value) is None:
            continue
        adapters.setdefault(int(number), {})[key] = value
    return [{"adapter": index, **values}
            for index, values in sorted(adapters.items())]


def running_guest_summary(path: Path, reference_macs: frozenset[str]) -> dict:
    """No full filesystem path or non-network VMX settings appear in report."""
    label = {
        "vmx_name": path.name,
        "vm_folder": path.parent.name,
        "vmx_identifier": hashlib.sha256(str(path).encode()).hexdigest()[:12],
    }
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("VMX unavailable or symlinked")
        adapters = parse_vmx_adapters(path.read_text(encoding="utf-8", errors="replace"))
        label["adapters"] = adapters
        label["reference_mac_match"] = any(
            item.get(field) in reference_macs
            for item in adapters for field in ("address", "generatedAddress")
        )
        label["readable"] = True
    except OSError:
        label["adapters"] = []
        label["reference_mac_match"] = None
        label["readable"] = False
    return label


def _query(command: list[str]) -> tuple[str | None, str | None]:
    binary = shutil.which(command[0])
    if binary is None:
        return None, f"{command[0]} is not installed"
    try:
        finished = subprocess.run(command, capture_output=True, text=True,
                                  check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None, f"{command[0]} inspection failed"
    if finished.returncode:
        # Never print unsanitized command output into shared test logs.
        return None, f"{command[0]} inspection returned nonzero"
    return finished.stdout, None


def host_survey() -> dict:
    reference, ref_subnets = reference_contract()
    warnings: list[str] = []
    coverage: dict[str, bool] = {}

    addresses, addr_error = _query(["ip", "-j", "address", "show"])
    coverage["ip_addresses"] = addr_error is None
    interfaces = []
    if addresses is not None:
        try:
            interfaces = parse_ip_addresses(addresses)
        except (ValueError, TypeError):
            coverage["ip_addresses"] = False
            warnings.append("ip address inspection returned unrecognized JSON")
    elif addr_error:
        warnings.append(addr_error)

    routes_text, route_error = _query(["ip", "-j", "route", "show", "table", "all"])
    coverage["ip_routes"] = route_error is None
    routes = []
    if routes_text is not None:
        try:
            routes = parse_ip_routes(routes_text)
        except (ValueError, TypeError):
            coverage["ip_routes"] = False
            warnings.append("ip route inspection returned unrecognized JSON")
    elif route_error:
        warnings.append(route_error)

    config_ids: list[str] = []
    config_hints: list[dict] = []
    try:
        if not NETWORKING.is_file() or NETWORKING.is_symlink():
            raise OSError("VMware network configuration not readable")
        config_ids, config_hints = parse_vmware_networking(
            NETWORKING.read_text(encoding="utf-8")
        )
        coverage["vmware_networking"] = True
    except (OSError, UnicodeError):
        coverage["vmware_networking"] = False
        warnings.append("VMware network configuration unavailable")

    filesystem_ids: set[str] = set()
    for directory in (VMWARE_ROOT, DEVICE_ROOT):
        try:
            filesystem_ids.update(
                p.name for p in directory.iterdir() if KNOWN_VMNET.fullmatch(p.name)
            )
        except OSError:
            warnings.append("could not enumerate one VMware network device directory")

    vmrun_text, vmrun_error = _query(["vmrun", "-T", "ws", "list"])
    coverage["vmrun_running"] = vmrun_error is None
    running = []
    if vmrun_text is not None:
        try:
            paths = parse_vmrun_list(vmrun_text)
            running = [running_guest_summary(path, reference.macs)
                       for path in paths]
            if any(not vm["readable"] for vm in running):
                warnings.append("some running VMX files are unreadable; identity coverage incomplete")
                coverage["vmrun_running"] = False
        except ValueError:
            coverage["vmrun_running"] = False
            warnings.append("vmrun list returned unrecognized guest list")
    elif vmrun_error:
        warnings.append(vmrun_error)

    names = set(config_ids) | filesystem_ids
    names |= {r["interface"] for r in interfaces if KNOWN_VMNET.fullmatch(r["interface"])}
    for vm in running:
        names |= {a["vnet"] for a in vm["adapters"] if "vnet" in a}

    # 100% of four key visibility sources must succeed before calling this a
    # complete *snapshot*. Even a complete snapshot is NOT host allocation
    # approval: dormant/suspended/unregistered VMX files may still exist.
    complete = all(coverage.values())
    return {
        "kind": "KINGDOMS_COURSE1_VMWARE_HOST_READONLY",
        "status": "OBSERVED_SNAPSHOT" if complete else "INCOMPLETE",
        "coverage": coverage,
        "reference_vmnets": sorted(reference.vmnets, key=vmnet_order),
        "reference_subnets": [str(n) for n in ref_subnets],
        "observed_vmnets": sorted(names, key=vmnet_order),
        "vmware_configured_subnet_hints": config_hints,
        "host_interfaces": interfaces,
        "ipv4_routes": routes,
        "running_vm_count": len(running),
        "running_vms": running,
        "warnings": warnings,
        "no_changes_performed": True,
        "candidate_allocation_authorized": False,
        "deployment_authorized": False,
    }


def compact_report(report: dict) -> dict:
    """Operational summary: full snapshot remains available without --summary."""
    return {
        "kind": report["kind"],
        "status": report["status"],
        "coverage": report["coverage"],
        "reference_vmnets": report["reference_vmnets"],
        "observed_vmnets": report["observed_vmnets"],
        "host_vmnet_interfaces": [
            {"interface": row["interface"], "ipv4": row["ipv4"]}
            for row in report["host_interfaces"]
            if row["interface"].startswith("vmnet")
        ],
        "ipv4_route_records": len(report["ipv4_routes"]),
        "running_vm_count": report["running_vm_count"],
        "running_vmx_readable": sum(vm["readable"] for vm in report["running_vms"]),
        "warnings": report["warnings"],
        "candidate_allocation_authorized": False,
        "deployment_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="perform host read-only survey; no guest or host mutation")
    parser.add_argument("--summary", action="store_true",
                        help="print compact status rather than full guest/routes inventory")
    args = parser.parse_args()
    if not args.check:
        parser.error("--check is mandatory")
    report = host_survey()
    print(json.dumps(compact_report(report) if args.summary else report, indent=2))
    if report["status"] != "OBSERVED_SNAPSHOT":
        parser.exit(2, "[INCOMPLETE] Host identity survey is partial; no allocation authorized\n")
    print("[PASS] Read-only host snapshot collected; no allocation authorized")
    print("[BLOCKED] Four-VM deployment remains disabled")


if __name__ == "__main__":
    main()
