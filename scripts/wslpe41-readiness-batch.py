#!/usr/bin/env python3
"""One read-only WSLPE41 readiness batch for the CURRENT fresh native VM.

Runs existing tests and source/host/VMware library checks in one invocation.
NO --apply mode, sudo, vmware-networks, guest mutation, or VM shutdown.
Exit 0 means source/read-only checks passed; it NEVER authorizes deployment.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_management_vmnet_workstation import (
    BIN, IP, _trusted_binary,
)
from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked
from kingdoms.wslpe_management_vmnet_runtime import VMRUN, PGREP


TESTS = (
    "tests.test_wslpe_management_vmnet_plan",
    "tests.test_wslpe_management_vmnet_transaction",
    "tests.test_wslpe_management_vmnet_host_gate",
    "tests.test_wslpe_management_vmnet_registry",
    "tests.test_wslpe_management_vmnet_workstation",
    "tests.test_wslpe41_readiness_batch",
    "tests.test_wslpe_management_vmnet_isolation",
    "tests.test_wslpe_vmnet4_maintenance",
)
GUEST_ID = "bf5369-wslpe-vmware"
MANAGEMENT = "vmnet4"
MANAGEMENT_SUBNET = "172.28.233.0/24"
MAX_OUTPUT = 1_000_000


@dataclass(frozen=True)
class Check:
    title: str
    command: tuple[str, ...]
    required: tuple[str, ...]
    deferred: str = ""
    required_pattern: str = ""


def commands(*, root: Path, home: Path, python: str) -> tuple[Check, ...]:
    fresh = root / "workspace"
    roots = (
        fresh,
        home / "kingdoms-lpe-standalone" / "workspace",
        home / "kingdoms-rebuild" / "workspace",
        home / "vmware" / "KINGDOMS-WSLPE41-LEARNER-TEST",
    )
    flags = tuple(x for r in roots for x in ("--workspace-root", str(r)))
    base = str(root / "scripts")
    return (
        Check("Management source regressions",
              (python, "-m", "unittest", *TESTS),
              ("OK",), required_pattern=r"Ran [1-9]\d* tests"),
        Check("41-scenario installer manifest",
              (python, str(root / "scripts/wslpe41-install.py"), "--plan"),
              ("[PLAN ONLY] 41/41",)),
        Check("Existing native WSLPE instance",
              (python, str(root / "scripts/wslpe41-install.py"), "--native-status",
               "--instance-dir", str(fresh / GUEST_ID)),
              (f"[NATIVE PROVIDED] {GUEST_ID}", "[SUBNET] 172.28.232.0/24",
               "[GUEST ADDRESS] 172.28.232.31")),
        Check("Native vmnet4/subnet proposal",
              (python, f"{base}/wslpe-management-vmnet-plan.py",
               "--native-workspace", str(fresh),
               *flags[2:]),
              ("[NATIVE] Exact WSLPE exercise: vmnet3 172.28.232.0/24",
               f"[PROPOSAL] Operator-only: {MANAGEMENT} {MANAGEMENT_SUBNET}",
               "[PASS] Proposed management subnet has no visible network collision"),
              deferred="[DEFERRED]"),
        Check("Running VMware ownership",
              (python, f"{base}/wslpe-management-vmnet-host-audit.py",
               "--candidate-vmnet", MANAGEMENT, *flags),
              (f"[VMNET] {MANAGEMENT} unused in metadata and inspected workspaces",
               "[OWNERSHIP] All"),
              deferred="[DEFERRED]"),
        Check("Registered and offline VMX ownership",
              (python, f"{base}/wslpe-management-vmnet-registry-audit.py",
               "--candidate-vmnet", MANAGEMENT, *flags),
              (f"[CANDIDATE] No registered library VMX references {MANAGEMENT}",
               "[LIBRARY]"),
              deferred="[DEFERRED]"),
    )


def run_command(cmd: tuple[str, ...]) -> tuple[int, str]:
    try:
        process = subprocess.run(
            list(cmd), cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"Unable to execute read-only check: {type(exc).__name__}"
    output = process.stdout + "\n" + process.stderr
    if len(output) > MAX_OUTPUT:
        return 127, "[BLOCKED] Unbounded diagnostic output"
    return process.returncode, output


def classify(check: Check, rc: int, output: str) -> str:
    if "[BLOCKED]" in output or "[FAIL]" in output or "[OTHER OWNER]" in output or "[NOT IN LIBRARY]" in output:
        return "FAIL"
    if any(marker not in output for marker in check.required):
        return "FAIL"
    if check.required_pattern and not re.search(check.required_pattern, output):
        return "FAIL"
    if rc == 0:
        return "PASS"
    if rc == 2 and check.deferred and check.deferred in output:
        return "DEFERRED"
    return "FAIL"


def perform(checks: tuple[Check, ...], runner=run_command) -> tuple[int, tuple[str, ...]]:
    results = []
    failed = False
    has_deferred = False
    for check in checks:
        rc, output = runner(check.command)
        status = classify(check, rc, output)
        results.append(f"[{status}] {check.title}")
        if status == "DEFERRED":
            has_deferred = True
        elif status == "FAIL":
            failed = True
            results.append(f"  exit={rc}; diagnostic (trimmed):")
            results.extend("  " + line for line in output.strip().splitlines()[-55:])
    if failed:
        results.append("[BATCH BLOCKED] Review failures together; no host or guest changes")
        return 2, tuple(results)
    if has_deferred:
        results.append("[BATCH PASS] Read-only checks pass; VMware maintenance is DEFERRED")
    else:
        results.append("[BATCH PASS] Read-only checks pass; no deployment authorization")
    results.append("[NOT INSTALLED] vmnet4, operator handoff and 41 scenarios still require live acceptance")
    return 0, tuple(results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-only", action="store_true",
                        help="Run only source tests and installer manifest (CI-safe)")
    args = parser.parse_args(argv)
    print("[WSLPE41] Consolidated readiness batch | READ ONLY")
    print("[NO CHANGES] no sudo, VMware restart, VM stop, firewall or Windows mutation")
    selected = commands(root=ROOT, home=Path.home(), python=sys.executable)
    if not args.source_only:
        try:
            _trusted_binary(BIN)
            _trusted_binary(IP)
            _trusted_binary(VMRUN, allow_trusted_symlink=True)
            _trusted_binary(PGREP, allow_trusted_symlink=True)
        except NetworkTransactionBlocked as exc:
            print(f"[FAIL] Host executables: {exc}")
            return 2
        print("[PASS] VMware, iproute2, vmrun and pgrep launchers: trusted system paths")
        if any(not p.is_dir() or p.is_symlink() for p in (
                ROOT / "workspace", Path.home() / "kingdoms-lpe-standalone/workspace",
                Path.home() / "kingdoms-rebuild/workspace",
                Path.home() / "vmware/KINGDOMS-WSLPE41-LEARNER-TEST")):
            print("[BATCH BLOCKED] One of the four audited VMware workspace roots is missing or symlinked")
            return 2
    if args.source_only:
        selected = selected[:2]
    exit_code, lines = perform(selected)
    for line in lines:
        print(line)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
