#!/usr/bin/env python3
"""One-command, operator-only WSLPE PREBOOT acceptance gate.

Runs source and host checks in a single pass. No Kingdoms instance is created;
no Vagrant up, VMware network change, Ansible provisioning, or guest action.
A PASS is an offline preboot result, not learner readiness or permission to
run an unvalidated installer.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VMWARE_PLUGIN = "vagrant-vmware-desktop"
EXPECTED_WINDOWS_BOX = "mayfly/windows10"
EXPECTED_WINDOWS_VERSION = "2024.01.06"
EXISTING_LPE_REPLICA = re.compile(
    r"(?i)(WSLPE[-_]WS01|WSLPE41|kingdoms-lpe-ws01|[/\\]WSLPE[/\\])"
)


def selected_python() -> str:
    """Use the established Kingdoms Ansible Python when present."""
    candidate = Path.home() / ".goad/.venv/bin/python"
    return str(candidate) if candidate.is_file() else sys.executable


def selected_ansible() -> str:
    candidate = Path.home() / ".goad/.venv/bin/ansible-playbook"
    if candidate.is_file():
        return str(candidate)
    return shutil.which("ansible-playbook") or "ansible-playbook"


def commands(python: str, ansible: str, prefix: str) -> list[tuple[str, list[str], int]]:
    """Whitelist of *non-deployment* preboot commands."""
    return [
        (
            "WSLPE native source/instance/network tests",
            [python, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_wslpe_*.py", "-v"], 120,
        ),
        (
            "Course selection and NORTH isolation tests",
            [python, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_kingdoms_course_registry.py", "-v"], 120,
        ),
        (
            "Existing Windows LPE regression tests",
            [python, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_windows_lpe_*.py", "-v"], 120,
        ),
        (
            "Legacy install guard regression tests",
            [python, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_install_noninteractive.py", "-v"], 90,
        ),
        (
            "Legacy destroy guard regression tests",
            [python, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_destroy_noninteractive.py", "-v"], 90,
        ),
        (
            "Original 20-technique Windows LPE source contract",
            ["bash", "scripts/validate-windows-lpe-framework-source.sh"], 300,
        ),
        (
            "Native WSLPE Vagrantfile and inventory render + Ruby syntax",
            [python, "scripts/wslpe-preview-native-instance.py",
             "--ip-range", prefix, "--ruby-check"], 90,
        ),
        (
            "Live host/VPN/VMware candidate subnet collision inspection",
            [python, "scripts/wslpe-check-host-network.py",
             "--ip-range", prefix], 45,
        ),
        (
            "WSLPE Windows foundation Ansible syntax",
            [ansible, "-i", "ad/WSLPE/data/inventory",
             "ansible/wslpe-foundation.yml", "--syntax-check"], 90,
        ),
        (
            "Shared Windows LPE WSLPE-only test harness syntax",
            [ansible, "-i", "ad/WSLPE/data/inventory",
             "ansible/wslpe-lpe-test.yml", "--syntax-check"], 90,
        ),
        (
            "VMware Vagrant provider/plugin availability",
            ["vagrant", "plugin", "list"], 30,
        ),
        (
            "Pinned Windows 10 VMware box availability",
            ["vagrant", "box", "list"], 30,
        ),
        (
            "Existing VMware VM inventory (read-only)",
            ["vmrun", "-T", "ws", "list"], 30,
        ),
    ]


def verify_peer_wslpe_inventory(vmrun_output: str, candidate_prefix: str | None) -> str | None:
    """Permit ONLY separately registered native WSLPE VMs on other networks.

    A legitimate existing WSLPE course instance can coexist with a new fresh
    build. Unknown prototypes, stale Vagrant registration, same-subnet peers,
    and any guest registered inside the checkout being installed must block.
    The guest's Windows state and vmnet L2 isolation are not inferred here.
    """
    from kingdoms.wslpe41_host_preflight import HostEvidenceBlocked, running_vm_count
    from kingdoms.wslpe41_native_identity import inspect_native_registration

    try:
        count = running_vm_count(vmrun_output)
        paths = [line.strip() for line in vmrun_output.splitlines() if line.strip()][1:]
        if len(paths) != count:
            return "VMware running inventory is incomplete"
        if candidate_prefix is None:
            # Source-only callers have not supplied host/network evidence.
            if any(EXISTING_LPE_REPLICA.search(line) for line in paths):
                return "Existing WSLPE detected without explicit candidate subnet"
            return None
        candidate = ipaddress.IPv4Network(candidate_prefix + ".0/24", strict=True)
        if not candidate.is_private or candidate.prefixlen != 24:
            return "Invalid WSLPE coexistence candidate subnet"
        for raw in paths:
            vmx = Path(raw)
            if not vmx.is_absolute() or vmx.is_symlink():
                return "VMware running inventory contains an unsafe VMX path"
            if not EXISTING_LPE_REPLICA.search(raw):
                continue
            # Real native KINGDOMS provider layout, not a guessed VM name:
            # instance/provider/.vagrant/machines/WSLPE-WS01/vmware_desktop/ID/guest.vmx
            parents = vmx.parents
            if (len(parents) < 7
                    or parents[1].name != "vmware_desktop"
                    or parents[2].name != "WSLPE-WS01"
                    or parents[3].name != "machines"
                    or parents[4].name != ".vagrant"
                    or parents[5].name != "provider"):
                return "Unregistered WSLPE/prototype VM is running"
            instance = parents[6]
            if instance.parent.resolve() == (ROOT / "workspace").resolve():
                return "Existing WSLPE guest belongs to this installation workspace"
            registration = inspect_native_registration(instance, vmrun_output)
            if registration.vmx != str(vmx.resolve(strict=True)):
                return "Existing WSLPE registration does not match running VMX"
            if candidate.overlaps(ipaddress.IPv4Network(registration.subnet)):
                return "Existing WSLPE guest overlaps selected fresh subnet"
    except (HostEvidenceBlocked, OSError, ValueError, IndexError) as exc:
        return "Existing WSLPE VM registration or network cannot be verified"
    return None


def verify_output(name: str, stdout: str, *, candidate_prefix: str | None = None) -> str | None:
    """Fail closed when tools exit zero but don't prove the expected fact."""
    if name == "VMware Vagrant provider/plugin availability":
        if EXPECTED_VMWARE_PLUGIN not in stdout:
            return "VMware Vagrant plugin is not installed"
    elif name == "Pinned Windows 10 VMware box availability":
        if not any(
            EXPECTED_WINDOWS_BOX in line
            and "vmware_desktop" in line
            and EXPECTED_WINDOWS_VERSION in line
            for line in stdout.splitlines()
        ):
            return "Pinned mayfly/windows10 VMware box version is unavailable"
    elif name == "Existing VMware VM inventory (read-only)":
        return verify_peer_wslpe_inventory(stdout, candidate_prefix)
    elif name == "Native WSLPE Vagrantfile and inventory render + Ruby syntax":
        for phrase in (
            "KINGDOMS WSLPE NATIVE INSTANCE RENDER: SOURCE PREVIEW PASS",
            "[PASS] Rendered native Kingdoms Vagrantfile Ruby syntax",
        ):
            if phrase not in stdout:
                return f"Missing renderer evidence: {phrase}"
    elif name == "Live host/VPN/VMware candidate subnet collision inspection":
        if "[PASS] No candidate collision found" not in stdout:
            return "Host networking checker did not prove candidate clearance"
    return None


def run_check(
    name: str, command: list[str], timeout: int,
    *,
    cwd: Path = ROOT,
    environment: dict[str, str] | None = None,
    candidate_prefix: str | None = None,
) -> tuple[bool, str]:
    """Capture output; never rerun failed steps or launch provider mutations."""
    try:
        result = subprocess.run(
            command, cwd=str(cwd), env=environment,
            capture_output=True, text=True, check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if result.returncode != 0:
        return False, f"Exit code {result.returncode}\n{output}"
    problem = verify_output(name, output, candidate_prefix=candidate_prefix)
    return (False, problem + "\n" + output) if problem else (True, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ip-range", required=True,
        help="Explicit private three-octet /24 candidate, e.g. 172.28.231",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print detailed output even for passing checks",
    )
    args = parser.parse_args()
    # Import the existing canonical prefix guard rather than duplicating it.
    import importlib.util
    checker_path = ROOT / "scripts/wslpe-check-host-network.py"
    spec = importlib.util.spec_from_file_location("wslpe_host_checker", checker_path)
    if spec is None or spec.loader is None:
        parser.error("WSLPE host-network checker unavailable")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    try:
        candidate = checker.parse_prefix(args.ip_range)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"KINGDOMS WSLPE | CONSOLIDATED OFFLINE ACCEPTANCE | {candidate}", flush=True)
    print("Scope: source, native VM definition, host network, VMware prerequisites")
    print("Safety: no guest creation, network changes, or Ansible deployment\n")
    python = selected_python()
    ansible = selected_ansible()
    environment = os.environ.copy()
    environment["ANSIBLE_CONFIG"] = str(ROOT / "ansible" / "ansible.cfg")

    passed, failed = 0, 0
    for name, command, timeout in commands(python, ansible, args.ip_range):
        print(f"[CHECK] {name}", flush=True)
        good, detail = run_check(
            name, command, timeout, environment=environment,
            candidate_prefix=args.ip_range,
        )
        print(("  [PASS] " if good else "  [FAIL] ") + name, flush=True)
        if good:
            passed += 1
        else:
            failed += 1
        if args.verbose or not good:
            lines = detail.splitlines()
            if len(lines) > 45:
                print(f"    [... {len(lines) - 45} earlier lines omitted ...]")
                lines = lines[-45:]
            for line in lines:
                print("    " + line)

    print(f"\nKINGDOMS WSLPE OFFLINE ACCEPTANCE: {passed} PASS / {failed} FAIL")
    if failed:
        print("[BLOCKED] Resolve all failed preboot gates before any instance/VM creation")
    else:
        print("[PASS] Source and visible host prerequisites passed for this candidate")
    print("[NOT VERIFIED] Actual VMware guest NIC mapping, guest domain status,")
    print("               WinRM, learner identity, LPE exploit paths and isolation")
    print("[LOCKED] WSLPE installation remains disabled until runtime gates are accepted")
    print("[NO CHANGES] No VM creation, VMware network mutation or learner provisioning")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
