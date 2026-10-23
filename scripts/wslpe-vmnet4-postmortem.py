#!/usr/bin/env python3
"""Read-only WSLPE vmnet4 failed-maintenance postmortem.

Prints ONLY journal metadata, VMware config fingerprints, link/route snapshots,
kernel forwarding flags and two independent running-guest counts.
No original_b64, VMX secrets or host file content is printed.
This command NEVER writes journal, restarts VMware or changes guests.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_management_vmnet_transaction import (
    MAX_JOURNAL_BYTES, MAX_NETWORKING_BYTES, NetworkTransactionBlocked,
    _digest, _read_regular,
)
from kingdoms.wslpe_management_vmnet_plan import inventory

JOURNAL = Path("/var/lib/kingdoms/wslpe-vmnet4/journal.json")
NETWORKING = Path("/etc/vmware/networking")
VMNET = "vmnet4"


def journal_summary(path: Path, actual_sha: str) -> dict[str, object]:
    """Validate protected journal and return a whitelist of nonsecret fields."""
    if not path.exists() and not path.is_symlink():
        return {"exists": False}
    raw, info = _read_regular(path, MAX_JOURNAL_BYTES)
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise NetworkTransactionBlocked("Journal ownership or permissions unsafe")
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Unexpected journal format")
        original = data["original_sha256"]
        proposed = data["proposed_sha256"]
        if any(not isinstance(h, str) or len(h) != 64 for h in (original, proposed)):
            raise ValueError("Malformed journal hashes")
        status = data["status"]
        if status not in {"prepared", "stopped", "installed", "committed", "rolled_back"}:
            raise ValueError("Unknown journal status")
    except (ValueError, KeyError, TypeError) as exc:
        raise NetworkTransactionBlocked("Unreadable/invalid transaction journal") from exc
    return {
        "exists": True, "status": status,
        "source_sha256": original, "candidate_sha256": proposed,
        "current_matches_original": actual_sha == original,
        "current_matches_candidate": actual_sha == proposed,
        "original_failure_captured": bool(data.get("failure_reason")),
        "failure_stage": str(data.get("failure_stage", "unrecorded"))[:80],
        "failure_class": str(data.get("failure_class", "unrecorded"))[:80],
        "failure_reason": str(data.get("failure_reason", "unrecorded"))[:200],
        "vmnet4_failure_network_evidence": data.get("failure_network_evidence", "not captured"),
    }


def _command(args: list[str], *, allowed_failure: bool = False) -> tuple[int, str]:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=12,
            stdin=subprocess.DEVNULL, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NetworkTransactionBlocked(f"Read-only host query failed: {args[0]}") from exc
    if len(result.stdout) > 150_000 or len(result.stderr) > 150_000:
        raise NetworkTransactionBlocked("Oversized host query response")
    if result.returncode != 0 and not allowed_failure:
        raise NetworkTransactionBlocked(
            f"Read-only host query exited {result.returncode}: {args[0]}"
        )
    return result.returncode, result.stdout


def snapshot_network() -> list[str]:
    details = []
    for action, args in (
        ("LINK", ["/usr/bin/ip", "-j", "link", "show", "dev", VMNET]),
        ("ADDRESS", ["/usr/bin/ip", "-j", "-4", "address", "show", "dev", VMNET]),
        ("ROUTES", ["/usr/bin/ip", "-j", "-4", "route", "show", "dev", VMNET]),
    ):
        code, output = _command(args, allowed_failure=True)
        if code:
            details.append(f"[{action}] absent/unavailable (exit={code})")
            continue
        try:
            records = json.loads(output)
        except ValueError:
            details.append(f"[{action}] malformed iproute2 output")
            continue
        if not isinstance(records, list) or len(records) > 8:
            details.append(f"[{action}] unexpected iproute2 shape")
            continue
        if action == "LINK":
            details.append(f"[{action}] " + json.dumps([
                {k: row.get(k) for k in ("ifname", "operstate", "master", "flags")}
                for row in records if isinstance(row, dict)
            ], sort_keys=True))
        elif action == "ADDRESS":
            details.append(f"[{action}] " + json.dumps([
                {"ifname": row.get("ifname"),
                 "inet": [(a.get("local"), a.get("prefixlen"))
                          for a in row.get("addr_info", [])
                          if isinstance(a, dict) and a.get("family") == "inet"]}
                for row in records if isinstance(row, dict)
            ], sort_keys=True))
        else:
            details.append(f"[{action}] " + json.dumps([
                {k: row.get(k) for k in ("dst", "dev", "gateway", "scope")}
                for row in records if isinstance(row, dict)
            ], sort_keys=True))
    return details


def forward_flags() -> list[str]:
    paths = (
        Path("/proc/sys/net/ipv4/conf/vmnet4/forwarding"),
        Path("/proc/sys/net/ipv6/conf/vmnet4/forwarding"),
        Path("/proc/sys/net/ipv6/conf/all/forwarding"),
    )
    out = []
    for path in paths:
        try:
            data = path.read_bytes()
            value = data.strip().decode("ascii") if len(data) <= 16 else "oversized"
        except (OSError, UnicodeError):
            value = "UNAVAILABLE"
        out.append(f"[FORWARD] {path}: {value}")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="stark",
                        help="Original Workstation owner for descriptive context")
    args = parser.parse_args(argv)
    print("[READ ONLY] WSLPE vmnet4 failed-allocation postmortem")
    print("[NO CHANGES] No VMware restart, journal recovery, guest boot or host writes")
    if os.geteuid() != 0:
        print("[BLOCKED] Read-only journal inspection requires root")
        return 2
    try:
        raw, info = _read_regular(NETWORKING, MAX_NETWORKING_BYTES)
        if info.st_uid != 0:
            raise NetworkTransactionBlocked("Untrusted VMware network configuration owner")
        source = raw.decode("utf-8")
        current = _digest(raw)
        summary = journal_summary(JOURNAL, current)
        print(f"[NETWORK SHA256] {current}")
        print(f"[VMNET4 IN CONFIG] {4 in inventory(source)}")
        print("[JOURNAL] " + json.dumps(summary, sort_keys=True))
        print(f"[WORKSTATION OWNER] {args.owner} (not a guest state attestation)")
        for line in snapshot_network() + forward_flags():
            print(line)
        pgrep_rc, pgrep_out = _command(
            ["/usr/bin/pgrep", "-c", "-x", "vmware-vmx"], allowed_failure=True)
        if pgrep_rc == 1 and pgrep_out.strip() in ("", "0"):
            print("[VMWARE-VMM PROCESS COUNT] 0")
        elif pgrep_rc == 0 and pgrep_out.strip().isdigit():
            print("[VMWARE-VMM PROCESS COUNT] " + pgrep_out.strip())
        else:
            print(f"[VMWARE-VMM PROCESS COUNT] UNKNOWN (exit={pgrep_rc})")
        print("[NOTE] Earlier journal schema does not record the original failure cause")
        print("[NO AUTHORIZATION] This report does not permit retry or journal deletion")
        return 0
    except (OSError, UnicodeError, ValueError, NetworkTransactionBlocked) as exc:
        print(f"[BLOCKED] Incomplete failure evidence: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
