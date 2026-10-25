#!/usr/bin/env python3
"""One-shot, identity-verified VMware Tools repair for original NORTH CASTELBLACK.

Scope: GOAD-SRV02 of 8aafc9-north-vmware only. This never runs Vagrant
provisioning, AD playbooks, lifecycle transitions or other guest commands.
"""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from goad.course1_direct_winrm import (
    EXPECTED, _authenticated_session, owned_guest, prove_canonical_guest,
)

IDENTITY = "8aafc9-north-vmware"
MACHINE = "GOAD-SRV02"
EXPECTED_IP = "10.4.10.22"


class RepairBlocked(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise RepairBlocked(message)


def command(argv, *, cwd=ROOT):
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True,
                            timeout=90, check=False)
    require(result.returncode == 0,
            "Command failed: " + argv[0] + " " +
            (result.stderr or result.stdout)[-400:])
    return result.stdout


def guest_evidence(provider, values, port, source_script):
    session = _authenticated_session("127.0.0.1", port=port)
    reply = session.run_ps(source_script)
    require(reply.status_code == 0, "Authenticated guest diagnostics failed: " +
            reply.std_err.decode(errors="replace")[-350:])
    try:
        record = json.loads(reply.std_out.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise RepairBlocked("Guest diagnostics returned invalid JSON") from exc
    require(isinstance(record, dict), "Guest diagnostic JSON malformed")
    adapters = record.get("Adapters")
    require(isinstance(adapters, list), "Guest NIC inventory is not a list")
    actual = [x.get("Mac") for x in adapters if isinstance(x, dict)]
    nat = values.get("ethernet0.generatedaddress", "").replace(":", "").upper()
    lab = EXPECTED[MACHINE].replace(":", "").upper()
    require(len(actual) == len(adapters) and
            re.fullmatch(r"[0-9A-F]{12}", nat) and
            actual.count(nat) == 1 and actual.count(lab) == 1 and nat != lab,
            "Authenticated endpoint is not the exact registered CASTELBLACK guest")
    nic = next(x for x in adapters if x["Mac"] == lab)
    require(nic.get("IPv4") == [EXPECTED_IP],
            "CASTELBLACK lab NIC is not exclusively at 10.4.10.22")
    return record


def absent_tools(record):
    service = record.get("ToolsService")
    products = record.get("InstalledVmwareTools")
    process = record.get("ToolsProcessCount")
    binary = record.get("ToolsExecutableExists")
    require(isinstance(service, list) and isinstance(products, list)
            and type(process) is int and type(binary) is bool,
            "VMware Tools inventory is malformed")
    return not service and not products and process == 0 and not binary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-srv02-repair", action="store_true",
                        help="Allow one VMware Tools installation and required SRV02 reboot")
    args = parser.parse_args(argv)
    require(args.confirm_srv02_repair, "Explicit repair confirmation required")
    require(os.geteuid() != 0 and Path.cwd() == ROOT,
            "Run from Kingdoms repository root as the VMware desktop user")
    require(command(["git", "branch", "--show-current"]).strip() == "main",
            "Only merged main may perform repair")
    require(not command(["git", "status", "--porcelain=v1"]).strip(),
            "Git tree must be clean")
    command(["bash", "scripts/verify-test-source.sh"])

    instance = ROOT / "workspace" / IDENTITY
    provider = instance / "provider"
    require(instance.is_dir() and not instance.is_symlink() and
            provider.is_dir() and not provider.is_symlink(),
            "Original NORTH provider is missing")
    record_file = instance / "instance.json"
    require(record_file.is_file() and not record_file.is_symlink(),
            "Original NORTH metadata missing")
    meta = json.loads(record_file.read_text())
    require((meta.get("id"), meta.get("lab"), meta.get("provider"),
             meta.get("status")) == (IDENTITY, "NORTH", "vmware", "not provided"),
            "Not the exact failed fourth NORTH install")
    mode = provider / ".goad-nomad-mode"
    require(not mode.exists() or mode.read_text().strip() == "unknown",
            "Instance mode changed; do not attempt this repair")
    resume = instance / ".north-ws01-repaired-pre-ad-resume-used"
    require(resume.is_file() and not resume.is_symlink(),
            "Expected recorded full Ansible resume is absent")
    command(["sudo", "-n", "bash", "scripts/setup-vmware-networks.sh",
             "--north", "verify", "--provider-dir", str(provider)])

    vmx, topology, values = owned_guest(provider, MACHINE)
    require(topology["address"] == EXPECTED_IP, "NORTH SRV02 topology changed")
    ports = re.findall(r"(?m)^\s*5985\s+\(guest\)\s*=>\s*(\d+)\s+\(host\)\s*$",
                       command(["vagrant", "port", MACHINE], cwd=provider))
    require(len(ports) == 1, "Ambiguous original SRV02 WinRM mapping")
    port = int(ports[0])

    diagnostics = ROOT / "scripts/diagnostics/diagnose-north-ws01-vmtools.py"
    require(diagnostics.is_file() and not diagnostics.is_symlink(),
            "Existing VMware Tools diagnostic missing")
    source_script = runpy.run_path(str(diagnostics))["SCRIPT"]
    before = guest_evidence(provider, values, port, source_script)
    require(absent_tools(before),
            "SRV02 Tools not completely absent; refuse unverified reinstall")

    # Marker is written BEFORE first mutation. Any partial attempt blocks replay.
    marker = instance / ".north-srv02-vmtools-repair-attempted"
    try:
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError as exc:
        raise RepairBlocked("SRV02 repair already attempted; do not repeat") from exc
    with os.fdopen(descriptor, "w") as stream:
        stream.write("One repair attempt for " + IDENTITY + "/GOAD-SRV02\n")

    print("[PASS] NORTH_SRV02_ORIGINAL_IDENTITY_AND_ABSENT_TOOLS_PROVEN", flush=True)
    from goad.provider.vagrant.vmware_kingdoms import GoadKingdomsVmwareProvider
    runtime = GoadKingdomsVmwareProvider("NORTH")
    runtime.set_instance_path(str(provider))
    result = runtime._install_vmware_tools(MACHINE, str(vmx), port)
    print("[INFO] ORIGINAL_VMTOOLS_HELPER_RESULT=" + str(bool(result)), flush=True)
    # VIX guest IP reporting can fail even when authenticated guest health passes.
    deadline = time.monotonic() + 180
    while True:
        try:
            prove_canonical_guest(provider, MACHINE, timeout=12)
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise RepairBlocked("SRV02 canonical guest health not proven after repair")
            time.sleep(5)
    after = guest_evidence(provider, values, port, source_script)
    svc = after.get("ToolsService")
    require(isinstance(svc, list) and len(svc) == 1 and
            svc[0].get("Name") == "VMTools" and svc[0].get("State") == "Running" and
            after.get("ToolsExecutableExists") is True and
            type(after.get("ToolsProcessCount")) is int and
            after["ToolsProcessCount"] > 0,
            "SRV02 VMware Tools not fully healthy after repair")
    print("[PASS] NORTH_SRV02_VMTOOLS_REPAIR=PASS", flush=True)
    print("[PASS] NORTH_SRV02_ORIGINAL_MACS_AND_CANONICAL_IP=PASS", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RepairBlocked, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print("[BLOCKED] NORTH SRV02 Tools repair: " + str(exc), file=sys.stderr)
        sys.exit(1)
