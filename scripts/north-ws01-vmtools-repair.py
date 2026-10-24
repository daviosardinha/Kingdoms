#!/usr/bin/env python3
"""One explicitly authorized VMware Tools repair for the original NORTH WS01.

The existing GOAD Kingdoms VMware Tools installer is reused without replaying
Vagrant, Windows evaluation maintenance, or AD provisioning. Refuse wrong
instance, guest identity, ownership, unexpected partial installations, and
concurrent repair. Never targets any other lab or machine.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from goad.course1_direct_winrm import _authenticated_session, owned_guest

INSTANCE_ID = "8aafc9-north-vmware"
MACHINE = "GOAD-WS01"
CONFIRMATION = "--confirm-vmtools-repair"
DIAGNOSTIC = ROOT / "scripts" / "diagnostics" / "diagnose-north-ws01-vmtools.py"


class RepairBlocked(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise RepairBlocked(message)


def run_checked(argv, **kwargs):
    result = subprocess.run(
        argv, cwd=kwargs.pop("cwd", ROOT),
        check=False, capture_output=True, text=True,
        timeout=kwargs.pop("timeout", 60), **kwargs
    )
    if result.returncode:
        raise RepairBlocked(
            "Preflight failed for " + argv[0] + ": " +
            (result.stderr.strip() or result.stdout.strip())[-600:]
        )
    return result.stdout


def load_diagnostic():
    """Load the exact checked-in MAC-bound diagnostic without modifying it."""
    require(DIAGNOSTIC.is_file() and not DIAGNOSTIC.is_symlink(),
            "The original read-only WS01 diagnostic is missing")
    spec = importlib.util.spec_from_file_location(
        "north_ws01_vmtools_identity_diagnostic", DIAGNOSTIC
    )
    require(spec is not None and spec.loader is not None,
            "Cannot import the original WS01 identity gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight_source():
    require(os.geteuid() != 0, "Run under the desktop user, not root")
    require(Path.cwd() == ROOT, "Run from the exact Kingdoms repo root")
    require(run_checked(["git", "branch", "--show-current"]).strip() == "main",
            "Only merged main is permitted")
    require(not run_checked(["git", "status", "--porcelain=v1", "--untracked-files=normal"]).strip(),
            "The worktree is not clean")
    run_checked(["bash", "scripts/verify-test-source.sh"], timeout=90)


def exact_failed_instance(instance):
    require(instance.is_dir() and not instance.is_symlink() and
            instance.resolve() == instance,
            "Exact failed instance is missing or unsafe")
    meta = instance / "instance.json"
    require(meta.is_file() and not meta.is_symlink(),
            "Original instance metadata missing")
    state = json.loads(meta.read_text(encoding="utf-8"))
    require((state.get("id"), state.get("lab"), state.get("provider"),
             state.get("status")) ==
            (INSTANCE_ID, "NORTH", "vmware", "not provided"),
            "Refusing a different, installed, or already-provisioned instance")
    receipts = sorted((instance / "install-timings").glob("*.json"))
    require(len(receipts) == 1 and not receipts[0].is_symlink(),
            "Expected exactly one original failed-install receipt")
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    require(receipt.get("instance_id") == INSTANCE_ID and
            receipt.get("status") == "failed" and
            receipt.get("provider_success") is False and
            receipt.get("ansible_phases") == [],
            "Original pre-Ansible failure receipt changed or is not proven")
    require(receipt.get("attempt_id") == "20261024T231210Z-e678c23cc64a",
            "The attempt ID is not the recorded fourth clean install")


def collect_verified_state(diag, provider, values, port):
    """Bind any proposed Tools change to one authenticated original WS01."""
    session = _authenticated_session("127.0.0.1", port=port)
    reply = session.run_ps(diag.SCRIPT)
    require(reply.status_code == 0,
            "Cannot collect Windows guest state: " +
            reply.std_err.decode("utf-8", errors="replace")[:300])
    try:
        payload = json.loads(reply.std_out.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise RepairBlocked("Windows diagnostics returned invalid JSON") from exc
    require(isinstance(payload, dict), "Windows identity is not a JSON object")
    # Independent WinRM identity verification does not require VMTools.
    diag.verify_identity(payload, values)
    adapters = payload.get("Adapters") or []
    if isinstance(adapters, dict):
        adapters = [adapters]
    lab_mac = "005056201031"
    lab_ips = [x.get("IPv4") or [] for x in adapters
               if isinstance(x, dict) and x.get("Mac") == lab_mac]
    require(len(lab_ips) == 1 and lab_ips[0] == ["10.4.10.31"],
            "Original WS01 lab NIC does not have exactly canonical 10.4.10.31")
    return payload


def require_uninstalled_tools(payload):
    """Do not run an installer on an ambiguous or partially installed guest."""
    services = payload.get("ToolsService")
    products = payload.get("InstalledVmwareTools")
    processes = payload.get("ToolsProcessCount")
    require(isinstance(services, list) and isinstance(products, list) and
            isinstance(processes, int) and
            isinstance(payload.get("ToolsExecutableExists"), bool),
            "VMware Tools inventory missing or malformed")
    require(not services and not products and processes == 0 and
            payload["ToolsExecutableExists"] is False,
            "VMware Tools state is not fully absent; do not replay the installer")


def new_runtime():
    # Import only after all exact-instance and authenticated guest checks.
    # The Windows/VMware dependencies are not needed for source-only tests.
    from goad.provider.vagrant.vmware_kingdoms import GoadKingdomsVmwareProvider
    return GoadKingdomsVmwareProvider("NORTH")


def repair_one_guest(diag, provider_path):
    vmx, guest, values = owned_guest(provider_path, MACHINE)
    require(guest["address"] == "10.4.10.31",
            "The registered WS01 has unexpected NORTH topology")
    result = run_checked(["vagrant", "port", MACHINE], cwd=provider_path)
    port = diag.parse_winrm_port(result)
    payload = collect_verified_state(diag, provider_path, values, port)
    require_uninstalled_tools(payload)
    print("[PASS] EXACT_WS01_IDENTITY_AND_MISSING_VMTOOLS_PROVEN", flush=True)
    print("[INFO] ORIGINAL_WS01_VMX=" + str(vmx), flush=True)
    print("[INFO] WINRM_FORWARD_PORT=" + str(port), flush=True)
    runtime = new_runtime()
    runtime.set_instance_path(str(provider_path))
    # Reuse the original Kingdoms installer, which mounts VMware Tools and
    # handles WinRM interruption/reboot. Invoke once only. Its vmrun IP
    # telemetry is advisory; strict final guest proof is authoritative.
    print("[INFO] Reusing the original Kingdoms VMware Tools installer once", flush=True)
    helper_result = runtime._install_vmware_tools(MACHINE, str(vmx), port)
    print("[INFO] ORIGINAL_VMTOOLS_HELPER_RESULT=" + str(bool(helper_result)), flush=True)
    # No second installation or forced power cycle on failure.
    ready = runtime._north_post_rearm_guest_ready(MACHINE, timeout=180)
    require(ready, "WS01 VMware Tools / WinRM / canonical IP not proven after repair")
    # Repeat original both-MAC identity verification after any reboot.
    post = collect_verified_state(diag, provider_path, values, port)
    services = post.get("ToolsService") or []
    require(isinstance(services, list) and len(services) == 1 and
            services[0].get("Name") == "VMTools" and
            services[0].get("State") == "Running" and
            post.get("ToolsExecutableExists") is True and
            isinstance(post.get("ToolsProcessCount"), int) and
            post["ToolsProcessCount"] > 0,
            "Strict final VMware Tools identity and service proof failed")
    print("[PASS] NORTH_WS01_VMTOOLS_REPAIR=PASS", flush=True)
    print("[PASS] NORTH_WS01_BOTH_NIC_MACS_AND_CANONICAL_IP=PASS", flush=True)
    print("[INFO] No Ansible provisioning or license maintenance was executed", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(CONFIRMATION, action="store_true",
                        help="Allow one tools installation and its required reboot on original WS01")
    args = parser.parse_args(argv)
    require(args.confirm_vmtools_repair,
            "Explicit --confirm-vmtools-repair required")
    preflight_source()
    instance = ROOT / "workspace" / INSTANCE_ID
    exact_failed_instance(instance)
    provider = instance / "provider"
    require(provider.is_dir() and not provider.is_symlink(),
            "Original NORTH provider directory is unsafe")
    run_checked([
        "sudo", "-n", "bash", "scripts/setup-vmware-networks.sh",
        "--north", "verify", "--provider-dir", str(provider)
    ], timeout=75)
    diag = load_diagnostic()
    # Only a single operator-controlled repair may mutate this Windows guest.
    lock_path = instance / ".north-ws01-vmtools-repair.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RepairBlocked("Another WS01 repair is already active") from exc
        # A fresh no-Tools identity proof occurs inside the lock.
        repair_one_guest(diag, provider)
    finally:
        os.close(fd)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RepairBlocked, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        print("[BLOCKED] NORTH WS01 VMware Tools repair: " + str(exc),
              file=sys.stderr)
        sys.exit(1)
