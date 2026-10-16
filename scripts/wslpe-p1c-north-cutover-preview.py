#!/usr/bin/env python3
"""NORTH-derived WSLPE VMX/NAT transition and host nft candidates (READ ONLY).

Uses only WSLPE's exact registered VMware guest. Replicates NORTH's proven
ordering/identity checks *conceptually* while excluding its domain servers,
router nftables, provisioning routes, fixed vmnets and domain accounts.
NEVER changes, stops/starts, or saves a VMware VM or host nftables policy.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_nat_cutover_contract import (
    render_nat_offline, manifest, guarded_original_restore,
)
from kingdoms.wslpe_nat_readiness import vmx_snapshot
from kingdoms.wslpe_winrm_guard import firewall_batch, TABLE as GUARD_TABLE
from kingdoms.wslpe_isolation_policy import (
    render_host_filter, TABLE as FILTER_TABLE,
)

STAGE2 = ROOT / "scripts/wslpe-stage2-inspect.py"
PLAN = ROOT / "scripts/wslpe-p1c-isolation-plan.py"
NORTH_REFERENCE = ROOT / "scripts/lab-mode.sh"
NORTH_RUNTIME = ROOT / "scripts/validate-ws01-runtime.sh"


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Required WSLPE-only evidence module missing")
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


def north_source_contract() -> None:
    """Compare against exact existing NORTH source without executing it."""
    lifecycle = NORTH_REFERENCE.read_text(encoding="utf-8")
    runtime = NORTH_RUNTIME.read_text(encoding="utf-8")
    for required in (
        "vmx_for()", "is_running()", "wait_stopped()",
        "get_start_connected()", "set_start_connected()",
        "ensure_vm_nat_state()", "connectNamedDevice",
        "disconnectNamedDevice", "ethernet0.startConnected",
        'vmrun -T ws stop', 'vmrun -T ws start',
    ):
        if required not in lifecycle:
            raise ValueError("Proven NORTH lifecycle source drift detected")
    for required in (
        "ethernet0.startconnected", "ethernet1",
        "wait_for_tcp",
    ):
        if required not in runtime.lower():
            raise ValueError("NORTH post-transition validator changed")
    print("[PASS] Reused NORTH lifecycle sequence and runtime validation invariants")
    print("[EXCLUDED] NORTH router, DCs, domain rights and hardcoded NORTH VMnets")


def running_exact(vmx: Path) -> bool:
    # Observe exact registered VMX. Never stop or start from this preview.
    check = subprocess.run(["vmrun", "-T", "ws", "list"],
                           capture_output=True, text=True,
                           timeout=20, check=False)
    if check.returncode:
        raise ValueError("VMware inventory unavailable")
    lines = check.stdout.splitlines()
    if not lines or not lines[0].startswith("Total running VMs:"):
        raise ValueError("Unknown vmrun format")
    count = int(lines[0].partition(":")[2].strip())
    if count != len(lines[1:]) or len(set(lines[1:])) != count:
        raise ValueError("Ambiguous VMware running inventory")
    matches = [x for x in lines[1:] if Path(x).resolve() == vmx.resolve()]
    if len(matches) != 1:
        raise ValueError("Unique, running WSLPE VMX not confirmed")
    return True


def collect() -> dict:
    stage = module(STAGE2, "wslpe_cutover_stage2")
    existing = module(PLAN, "wslpe_cutover_network")
    root = stage.WORKSPACE.resolve()
    instance, data = stage.find_instance(stage.WORKSPACE)
    if data.get("lab") != "WSLPE":
        raise ValueError("WSLPE instance mismatch")
    vmx = stage.locate_registered_vm(instance)
    if vmx.is_symlink() or not vmx.resolve().is_relative_to(root):
        raise ValueError("Foreign or symlinked WSLPE VMX")
    vmnet, subnet, host, guest = existing.collect()
    running_exact(vmx)
    raw = vmx.read_bytes()
    if raw.decode("utf-8").encode("utf-8") != raw:
        raise ValueError("VMX has noncanonical text encoding")
    original = raw.decode("utf-8")
    # Proven NORTH semantics: snapshot NAT Ethernet0, preserve Ethernet1.
    nic = vmx_snapshot(original, vmnet)
    candidate = render_nat_offline(original, vmnet)
    proof = manifest(original, candidate, vmnet)
    if guarded_original_restore(candidate, original, proof, vmnet) != original:
        raise ValueError("Offline candidate rollback bytes do not match original")
    port = stage.forwarded_winrm_port(instance)
    guard = firewall_batch(port)
    filter_text = render_host_filter(vmnet, subnet, host, guest)
    return {"vmx": vmx, "vmnet": vmnet, "guest": guest, "host": host,
            "port": port, "vmx_proof": proof, "nic": nic,
            "guard": guard, "filter": filter_text}


def main() -> int:
    print("KINGDOMS WSLPE | NORTH-REUSED CUTOVER CANDIDATES (READ ONLY)")
    print("[NO CHANGES] NORTH, VMX, Windows, host nftables, VMware or NAT")
    try:
        north_source_contract()
        result = collect()
    except (OSError, ValueError, KeyError, TypeError, UnicodeError,
            subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {type(exc).__name__}; zero changes made")
        return 1
    proof = result["vmx_proof"]
    print(f"[PASS] Exact registered WSLPE VM: {result['vmx'].name}")
    print(f"[PASS] Provisioning NAT Ethernet0 verified; exercise Ethernet1={result['vmnet']}")
    print(f"[PASS] SHA256 original={proof.before_sha256}")
    print(f"[PASS] SHA256 offline candidate={proof.after_sha256}")
    print("[PASS] Candidate modifies only persistent ethernet0.startConnected")
    print("[PASS] Full-byte VMX restore renderer verified in memory")
    print("[INFO] NAT still connected; currently running WSLPE VM must not be edited")
    print(f"[PASS] Existing WSLPE WinRM forward port discovered: TCP/{result['port']}")
    print(f"[INFO] Existing NORTH-independent WinRM guard candidate: inet {GUARD_TABLE}")
    print(f"[INFO] Existing WSLPE INPUT/FORWARD filter candidate: inet {FILTER_TABLE}")
    print("[BLOCKED] No boot-persistence proof for BOTH dynamic WinRM guard and exercise filter")
    print("[BLOCKED] No independent VMware-owner restore execution has been proven")
    print("[BLOCKED] vmnet2 host-only ARP/Layer2 remains a learner isolation risk")
    print("[NEXT] Implement guarded VMware stop/offline-edit/start/restore + host boot guard")
    print("[RELEASE BLOCKED] No NAT cutover authorization, no learner access")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
