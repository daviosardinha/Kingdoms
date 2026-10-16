#!/usr/bin/env python3
"""WSLPE P1-C: preview or bounded host firewall pilot; never changes NORTH.

DEFAULT is preview. Explicit --pilot confirmation can install only the
dedicated WSLPE nftables table for 120-300 seconds with a systemd timer
armed BEFORE applying. The independent timer always deletes only that table.
No NAT / VM / guest lifecycle operations, routing writes, or persistence.
"""
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import os
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_isolation_policy import (
    TABLE, INPUT_CHAIN, FORWARD_CHAIN, exact_rollback, render_host_filter,
)
from kingdoms.wslpe_remote_operator import ssh_management_path, host_timer_smoke_test

PLAN = ROOT / "scripts/wslpe-p1c-isolation-plan.py"
BATCH = ROOT / "scripts/wslpe-p1c-batch-review.py"
HTTPS = ROOT / "scripts/wslpe-https-auth-audit.py"
EXPECTED_CERT = "C773EC26D02940F559FE715B83628FEDAE2AA92D"
CONFIRM = "PILOT WSLPE HOST FILTER"
ROLLBACK_CONFIRM = "ROLLBACK WSLPE HOST FILTER"


def load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Required WSLPE source module missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd(args: list[str], *, payload: str | None = None, timeout: int = 30):
    return subprocess.run(
        args, input=payload, text=True, capture_output=True, check=False,
        timeout=timeout, cwd=str(ROOT),
    )


def sudo_nft(*args: str, payload: str | None = None) -> subprocess.CompletedProcess:
    # Exact caller-owned literal operations only, never a shell string.
    return cmd(["sudo", "-n", "nft", *args], payload=payload)


def nft_json(*args: str) -> list[dict]:
    r = sudo_nft("-j", "list", *args)
    if r.returncode:
        raise ValueError("Local privileged nftables inventory unavailable")
    data = json.loads(r.stdout)
    if not isinstance(data, dict) or not isinstance(data.get("nftables"), list):
        raise ValueError("Unexpected nftables JSON schema")
    return data["nftables"]


def scoped_objects(entries: list[dict]) -> list[tuple[str, dict]]:
    found: list[tuple[str, dict]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for kind in ("table", "chain", "rule"):
            obj = entry.get(kind)
            if not isinstance(obj, dict):
                continue
            table = obj.get("name") if kind == "table" else obj.get("table")
            if obj.get("family") == "inet" and table == TABLE:
                found.append((kind, obj))
    return found


def absent_before_pilot() -> None:
    if scoped_objects(nft_json("ruleset")):
        raise ValueError("Proposed WSLPE nft table already exists: no overwrite allowed")


def installed_exact_policy(vmnet: str | None = None) -> bool:
    # A failed privileged query is NOT proof that the table is absent.
    if not scoped_objects(nft_json("ruleset")):
        return False
    entries = nft_json("table", "inet", TABLE)
    found = scoped_objects(entries)
    tables = [obj for kind, obj in found if kind == "table"]
    chains = [obj for kind, obj in found if kind == "chain"]
    rules = [obj for kind, obj in found if kind == "rule"]
    if len(tables) != 1 or len(chains) != 2 or len(rules) != 4:
        raise ValueError("WSLPE table has unexpected extra/missing objects")
    hooks = {(str(c.get("name")), str(c.get("hook")),
              int(c.get("prio", 999))) for c in chains}
    if hooks != {(INPUT_CHAIN, "input", -75), (FORWARD_CHAIN, "forward", -75)}:
        raise ValueError("Unexpected WSLPE nft chain hooks or priorities")
    expected = {
        (INPUT_CHAIN, "WSLPE operator reply only", "accept"),
        (INPUT_CHAIN, "WSLPE guest to Kali blocked", "drop"),
        (FORWARD_CHAIN, "WSLPE guest forwarding blocked", "drop"),
        (FORWARD_CHAIN, "WSLPE cross-network ingress blocked", "drop"),
    }
    actual = []
    for item in rules:
        operations = {key for expression in item.get("expr", ())
                      if isinstance(expression, dict) for key in expression}
        action = "accept" if "accept" in operations else "drop" if "drop" in operations else ""
        actual.append((str(item.get("chain")), str(item.get("comment")), action))
        if vmnet and vmnet not in json.dumps(item.get("expr", ())):
            raise ValueError("WSLPE nft rule lacks the expected dedicated vmnet")
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("WSLPE nft rule actions/comments differ from reviewed candidate")
    return True


def local_preflight():
    plan = load_script(PLAN, "wslpe_pilot_plan")
    vmnet, subnet, host, guest = plan.collect()
    policy = render_host_filter(vmnet, subnet, host, guest)

    # The co-tenant check reads VMX metadata from local files only and
    # does not run any command inside another VM.
    batch = load_script(BATCH, "wslpe_pilot_cotenants")
    stage2 = plan.import_script(plan.STAGE2_PATH, "wslpe_pilot_identity")
    instance, info = stage2.find_instance(stage2.WORKSPACE)
    vmx = stage2.locate_registered_vm(instance)
    batch.check_vm_membership(vmnet, vmx)

    absent_before_pilot()
    checked = sudo_nft("-c", "-f", "-", payload=policy)
    if checked.returncode:
        raise ValueError("Kernel rejected WSLPE host filter in CHECK mode")
    return policy, vmnet, host, guest


def rollback_now() -> None:
    r = sudo_nft("-f", "-", payload=exact_rollback())
    if r.returncode:
        raise ValueError("WSLPE-owned table could not be removed")
    if scoped_objects(nft_json("ruleset")):
        raise ValueError("WSLPE-owned table remains present after rollback")


def arm_rollback(seconds: int, timer_id: str) -> str:
    nft_bin = shutil.which("nft")
    if not nft_bin:
        raise ValueError("nft binary unavailable for independent rollback")
    nft_bin = str(Path(nft_bin).resolve())
    unit = f"kingdoms-wslpe-fw-rollback-{timer_id}"
    r = cmd([
        "sudo", "-n", "systemd-run", "--quiet",
        "--unit", unit, f"--on-active={seconds}s", "--collect",
        nft_bin, "delete", "table", "inet", TABLE,
    ], timeout=20)
    if r.returncode:
        raise ValueError("Could not arm independent WSLPE automatic rollback")
    state = cmd(["sudo", "-n", "systemctl", "is-active", f"{unit}.timer"])
    if state.returncode or state.stdout.strip() != "active":
        raise ValueError("WSLPE automatic rollback timer was not verified active")
    return f"{unit}.timer"


def check_https() -> bool:
    # Existing validated HTTPS read-only identity proof, no credential args
    # or insecure TLS fallback; do not echo stdout or stderr on failure.
    r = cmd([sys.executable, str(HTTPS),
             "--expected-thumbprint", EXPECTED_CERT], timeout=90)
    return r.returncode == 0 and (
        "[PASS] WSLPE_AUTHENTICATED_HTTPS=TRUE" in r.stdout
        and "[PASS] WSLPE_DOMAIN_FREE=TRUE" in r.stdout
    )


def remote_preflight(vmnet: str, host: str) -> None:
    # The caller's SSH route must be disjoint from the guest exercise vmnet.
    subnet = str(ipaddress.ip_interface(f"{host}/24").network)
    dev = ssh_management_path(vmnet, subnet)
    print(f"[PASS] Operator SSH return route uses {dev}, not {vmnet}", flush=True)
    unit = host_timer_smoke_test()
    print(f"[PASS] Independent host rollback timer smoke test fired: {unit}", flush=True)


def pilot(seconds: int, remote: bool = False) -> None:
    policy, vmnet, host, guest = local_preflight()
    if remote:
        remote_preflight(vmnet, host)
    if not check_https():
        raise ValueError("Pre-pilot HTTPS management is not healthy")
    timer = arm_rollback(seconds, uuid.uuid4().hex[:12])
    print(f"[PASS] Independent rollback timer armed: {timer}", flush=True)
    r = sudo_nft("-f", "-", payload=policy)
    if r.returncode:
        raise ValueError("nftables rejected WSLPE-only candidate; rollback timer remains armed")
    try:
        if not installed_exact_policy(vmnet):
            raise ValueError("Post-installation WSLPE table proof failed")
        if not check_https():
            raise ValueError("Operator certificate-verified HTTPS broke after policy")
    except Exception:
        # Immediate rollback on any post-apply failure; independent timer
        # remains in place even if the calling Python process disappears.
        rollback_now()
        raise
    print(f"[PASS] Temporary WSLPE-only filter active on {vmnet}, host={host}, guest={guest}")
    print("[PASS] Certificate-verified WSLPE HTTPS survived temporary filter")
    print(f"[AUTOMATIC ROLLBACK] Timer {timer} removes ONLY inet {TABLE}")
    print("[RELEASE BLOCKED] Provisioning NAT still attached; host/L2 isolation unproven")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--pilot", action="store_true")
    modes.add_argument("--rollback", action="store_true")
    modes.add_argument("--remote-preflight", action="store_true")
    modes.add_argument("--verify-rollback", action="store_true")
    parser.add_argument("--remote", action="store_true",
                        help="explicitly authorize bounded remote SSH pilot after host timer smoke proof")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()

    print("KINGDOMS WSLPE | BOUNDED HOST FILTER PILOT")
    print("[SCOPE] Exact native WSLPE only; NEVER NAT, NORTH or other nftables tables")
    try:
        if args.rollback:
            if args.remote or args.confirm != ROLLBACK_CONFIRM:
                raise ValueError("Exact WSLPE-only rollback confirmation required")
            if installed_exact_policy():
                rollback_now()
                print("[PASS] Scoped WSLPE table rolled back")
            else:
                print("[PASS] WSLPE table already absent; no modification")
        elif args.verify_rollback:
            if args.confirm or args.remote:
                raise ValueError("Read-only rollback verification takes no confirmation")
            if scoped_objects(nft_json("ruleset")):
                raise ValueError("WSLPE host firewall pilot table still present")
            print("[PASS] WSLPE_PILOT_TABLE_ABSENT=TRUE")
            print("[INFO] Table absence after the timer window is verified;")
            print("       prior timer smoke-test supports, but does not prove, timer causation")
            if not check_https():
                raise ValueError("Post-rollback authenticated HTTPS failed")
            print("[PASS] WSLPE_POST_ROLLBACK_HTTPS=TRUE")
        elif args.remote_preflight:
            if args.confirm or args.remote:
                raise ValueError("Remote smoke-test does not accept pilot confirmation")
            _, vmnet, host, guest = local_preflight()
            remote_preflight(vmnet, host)
            print("[PASS] REMOTE_WSLPE_ROLLBACK_PREFLIGHT=TRUE")
            print("[NO FIREWALL CHANGES] Standalone timer proof completed")
        elif args.pilot:
            if args.confirm != CONFIRM or not 120 <= args.seconds <= 300:
                raise ValueError("Exact PILOT confirmation and 120–300s window required")
            is_ssh = bool(os.environ.get("SSH_CONNECTION")
                          or __import__("os").environ.get("SSH_TTY"))
            if is_ssh and not args.remote:
                raise ValueError("Remote SSH pilot requires --remote and independent rollback proof")
            if args.remote and not is_ssh:
                raise ValueError("Remote pilot requires an authenticated SSH session")
            pilot(args.seconds, remote=args.remote)
        else:
            if args.confirm or args.remote:
                raise ValueError("Confirmation supplied without an operation")
            policy, vmnet, host, guest = local_preflight()
            print(f"[PASS] Exact WSLPE-only policy plan: {vmnet} {host} -> {guest}")
            print("[PASS] Host nftables syntax check accepted (NOT APPLIED)")
            print("[PREVIEW] Scoped table and independent rollback are prepared")
            print("[RELEASE BLOCKED] No host firewall write, no NAT cutover, no learner access")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {type(exc).__name__}; no action against NORTH")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
