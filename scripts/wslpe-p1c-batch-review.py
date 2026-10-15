#!/usr/bin/env python3
"""One-shot WSLPE P1-C READ-ONLY evidence collection.

Never applies nft/iptables, reboots, probes NORTH, changes VMware, or creates
Windows accounts. Reads existing WSLPE-only tests and live diagnostics;
captures bounded, sanitized findings so one operator run is enough to triage.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_isolation_policy import TABLE, render_host_filter

PLAN = ROOT / "scripts/wslpe-p1c-isolation-plan.py"
STATUS: list[tuple[str, str, str]] = []
READ_ONLY = {
    "vmrun", "ip", "ss", "nft", "iptables-save", "ip6tables-save",
    "systemctl", "bash", str(Path(sys.executable)),
}
MARKERS = ("[PASS]", "[FAIL]", "[BLOCKED]", "[WARN]", "[NOT VERIFIED]",
           "[RELEASE BLOCKED]", "[INFO]", "PLAY RECAP", "WSLPE STAGE 2 WINDOWS BASELINE")


def run(args: list[str], *, input_data: str | None = None, timeout: int = 60
        ) -> subprocess.CompletedProcess:
    """Allowlisted command runner: only existing read-only diagnostic paths."""
    if not args or args[0] not in READ_ONLY and args[:2] != ["sudo", "-n"]:
        raise ValueError("Non-read-only or unexpected command rejected")
    if args[:2] == ["sudo", "-n"]:
        if len(args) < 3 or args[2] not in ("nft", "ss", "iptables-save", "ip6tables-save"):
            raise ValueError("Privileged command not on WSLPE read-only allowlist")
        if args[2] == "nft" and (
            args[3:5] not in (["-j", "list"], ["-c", "-f"])
            or (args[3:5] == ["-c", "-f"] and args[5:] != ["-"])
        ):
            raise ValueError("Unsupported privileged nft operation")
    return subprocess.run(args, cwd=str(ROOT), input=input_data,
                          capture_output=True, text=True, check=False,
                          timeout=timeout)


def result(section: str, level: str, note: str) -> None:
    STATUS.append((section, level, note))
    print(f"[{level}] {section}: {note}", flush=True)


def load_plan():
    spec = importlib.util.spec_from_file_location("wslpe_batch_isolation_plan", PLAN)
    if spec is None or spec.loader is None:
        raise ValueError("WSLPE plan source unavailable")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_vm_membership(vmnet: str, target_vmx: Path) -> None:
    """Read *local VMX metadata only*, no contact with another VM."""
    output = run(["vmrun", "-T", "ws", "list"], timeout=25)
    if output.returncode:
        raise ValueError("VMware local running-VM inventory failed")
    header, *rows = output.stdout.splitlines()
    if not header.startswith("Total running VMs:"):
        raise ValueError("Unexpected vmrun inventory")
    count = int(header.partition(":")[2].strip())
    if len(rows) != count:
        raise ValueError("VMware running-VM count mismatch")
    target_vmx = target_vmx.resolve()
    found = 0
    shared = 0
    for item in rows:
        path = Path(item).resolve()
        if path == target_vmx:
            found += 1
            continue
        if not path.is_file():
            raise ValueError("Another running VMX is unreadable; vmnet membership unknown")
        source = path.read_text(encoding="utf-8", errors="replace")
        # Only look for exact VMware virtual network assignments; never
        # connect, execute guest commands, or print foreign VM identities.
        vn = re.findall(r'^\s*ethernet\d+\.vnet\s*=\s*"([^"]+)"\s*$',
                        source, re.I | re.M)
        if vmnet in vn:
            shared += 1
    if found != 1:
        raise ValueError("Unique running WSLPE VM registration not proven")
    if shared:
        raise ValueError(f"{shared} other running VMware guest(s) share {vmnet}")
    result("co-tenant VMnet", "PASS",
           f"no other running VMX explicitly assigned to {vmnet} ({count - 1} checked)")
    result("co-tenant VMnet", "NOT VERIFIED",
           "powered-off VMs, dynamic adapters and future VMware attachments")


def check_firewall(candidate: str, vmnet: str) -> None:
    """Read live host rules and do kernel syntax check WITHOUT committing rules."""
    check = run(["sudo", "-n", "nft", "-c", "-f", "-"],
                input_data=candidate, timeout=30)
    if check.returncode:
        result("nft candidate syntax", "BLOCKED",
               "nft --check failed (no changes made); review live rules and syntax")
    else:
        result("nft candidate syntax", "PASS", "nft --check accepted; NOT applied")
    snapshot = run(["sudo", "-n", "nft", "-j", "list", "ruleset"], timeout=30)
    if snapshot.returncode:
        raise ValueError("Privileged nftables read-only snapshot unavailable")
    parsed = json.loads(snapshot.stdout)
    entries = parsed.get("nftables", [])
    if not isinstance(entries, list):
        raise ValueError("Unexpected nftables JSON structure")
    chains = [x["chain"] for x in entries
              if isinstance(x, dict) and isinstance(x.get("chain"), dict)]
    rules = [x["rule"] for x in entries
             if isinstance(x, dict) and isinstance(x.get("rule"), dict)]
    matching = [r for r in rules if vmnet in json.dumps(r, sort_keys=True)]
    existing = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key in ("table", "chain", "rule"):
            payload = entry.get(key)
            if isinstance(payload, dict):
                name = payload.get("name") if key == "table" else payload.get("table")
                if name == TABLE:
                    existing.append(entry)
                    break
    if existing:
        result("existing candidate table", "BLOCKED",
               f"inet {TABLE} already exists; refuse duplicate installation")
    else:
        result("existing candidate table", "PASS", "proposed table does not yet exist")
    hooked = [c for c in chains if c.get("hook") in ("input", "forward")]
    result("host nft rules", "INFO",
           f"{len(chains)} chains; {len(rules)} rules; {len(hooked)} INPUT/FORWARD base chains")
    result("host nft vmnet rules", "INFO",
           f"{len(matching)} existing rules mention exact {vmnet}; effective rule precedence still unproven")
    for binary in ("iptables-save", "ip6tables-save"):
        check = run(["sudo", "-n", binary], timeout=20)
        if check.returncode:
            result(binary, "NOT VERIFIED", "read-only rules unavailable")
        else:
            lines = [l for l in check.stdout.splitlines() if l.startswith("-A ")]
            result(binary, "INFO", f"{len(lines)} existing IPv4/IPv6 legacy rules (not modified)")


def check_listeners(host_ip: str) -> None:
    completed = run(["sudo", "-n", "ss", "-H", "-lntup"], timeout=20)
    if completed.returncode:
        raise ValueError("Privileged host listen-socket inventory unavailable")
    ports = set()
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        local = fields[4]  # ss -H -lntup: Netid State Recv-Q Send-Q Local Peer
        address = local.rsplit(":", 1)[0].strip("[]")
        if address in (host_ip, "0.0.0.0", "::", "*"):
            port = local.rsplit(":", 1)[-1]
            if port.isdigit():
                ports.add(int(port))
    result("host sockets", "INFO",
           f"{len(ports)} TCP/UDP listening ports bound to {host_ip} or wildcard")
    result("host sockets", "NOT VERIFIED",
           "reachability/source ACLs require independent controlled packet tests")


def check_persistence() -> None:
    check = run(["systemctl", "is-enabled", "nftables"], timeout=15)
    status = check.stdout.strip() if check.returncode == 0 else "not enabled/unknown"
    result("nft persistence", "INFO", f"systemd nftables service: {status}")
    result("nft persistence", "NOT VERIFIED",
           "WSLPE-specific protection after actual host restart is not proven")


def existing_readonly(section: str, command: list[str], timeout: int = 180) -> None:
    try:
        finished = run(command, timeout=timeout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        result(section, "BLOCKED", f"{type(exc).__name__} during read-only audit")
        return
    markers = [line.strip() for line in finished.stdout.splitlines()
               if any(tag in line for tag in MARKERS)]
    for line in markers[-18:]:
        print("    " + line[:240])
    result(section, "PASS" if finished.returncode == 0 else "BLOCKED",
           f"command exit={finished.returncode}; read-only observation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-thumbprint", required=True,
                        help="Previously independently verified WSLPE WSMan cert SHA1")
    args = parser.parse_args()
    print("KINGDOMS WSLPE | ALL-IN-ONE P1-C READ-ONLY REVIEW", flush=True)
    print("[NO CHANGES] No NORTH probes, VM lifecycle, NAT, firewall, Windows writes")
    try:
        plan = load_plan()
        vmnet, subnet, host, guest = plan.collect()
        candidate = render_host_filter(vmnet, subnet, host, guest)
        instance, _ = plan.import_script(
            plan.STAGE2_PATH, "wslpe_batch_stage2"
        ).find_instance((ROOT / "workspace"))
        vmx = plan.import_script(plan.STAGE2_PATH, "wslpe_batch_vmx").locate_registered_vm(instance)
        result("VM identity and topology", "PASS",
               f"exact registered WSLPE VMX; {vmnet}; host {host}; guest {guest}; NAT attached")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        result("VM identity and topology", "BLOCKED",
               f"{type(exc).__name__}; no subsequent network inspection authorized")
        return 1
    stages = (
        ("co-tenant inventory", lambda: check_vm_membership(vmnet, vmx)),
        ("host firewall", lambda: check_firewall(candidate, vmnet)),
        ("host listeners", lambda: check_listeners(host)),
        ("systemd persistence", check_persistence),
    )
    for name, callback in stages:
        try:
            callback()
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
                subprocess.TimeoutExpired) as exc:
            result(name, "BLOCKED", f"{type(exc).__name__}: read-only evidence unavailable")

    existing_readonly("WSLPE Windows baseline and NAT guard",
        ["bash", str(ROOT / "scripts/wslpe-network-acceptance.sh")], timeout=210)
    existing_readonly("WSLPE HTTPS/RDP/NLA configuration",
        ["bash", str(ROOT / "scripts/wslpe-access-audit.sh")], timeout=150)
    existing_readonly("Authenticated pinned WinRM HTTPS",
        [sys.executable, str(ROOT / "scripts/wslpe-https-auth-audit.py"),
         "--expected-thumbprint", args.expected_thumbprint], timeout=90)
    print("\n===== CONSOLIDATED RESULTS =====")
    for section, level, note in STATUS:
        print(f"[{level}] {section}: {note}")
    blocked = sum(level == "BLOCKED" for _, level, _ in STATUS)
    print(f"\n[REPORT] blocked/unavailable checks={blocked}")
    print("[RELEASE BLOCKED] NAT cutover, out-of-band rollback, learner RDP,")
    print("                  host/L2 isolation, nft reboot persistence NOT VERIFIED")
    print("[NO CHANGES] No live firewall apply, VM/Windows modification or NORTH probe")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
