#!/usr/bin/env python3
"""Read-only candidate VMware clone isolation audit for WSLPE41 learner proofs.

Requires an already created, POWERED-OFF test clone with all virtual NICs
disconnected. This never creates, starts, clones, connects, reverts or edits VMs.
A PASS does NOT prove clone ancestry or learner exploitability.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms import wslpe45_batch_operator as batch
from kingdoms import wslpe45_deploy21 as deployment

DISK_LINE = re.compile(
    r'^\s*(?:scsi|sata|ide|nvme)\d+:\d+\.fileName\s*=\s*"([^"]+\.vmdk)"\s*$',
    re.IGNORECASE)
ETHER_LINE = re.compile(
    r'^\s*ethernet(\d+)\.(present|startConnected)\s*=\s*"([^"]+)"\s*$',
    re.IGNORECASE)


def vmx_inventory(path: Path, master: Path) -> dict:
    if (not path.is_absolute() or path.is_symlink()
            or not path.is_file() or path.suffix.lower() != ".vmx"):
        raise batch.BatchBlocked("Candidate must be an existing absolute nonlinked VMX")
    actual = path.resolve(strict=True)
    original = master.resolve(strict=True)
    if (actual == original or actual.is_relative_to(original.parent)
            or original.is_relative_to(actual.parent)):
        raise batch.BatchBlocked("Candidate must be a separate clone, not the frozen master")
    if path.stat().st_uid != __import__("os").geteuid():
        raise batch.BatchBlocked("Candidate VMX is not owned by the operator")
    if any(p.is_symlink() for p in actual.parents if p != actual.anchor and p.exists()):
        raise batch.BatchBlocked("Candidate VMX ancestry contains a symlink")
    text = path.read_text(encoding="utf-8", errors="replace")
    adapters: dict[int,dict] = {}
    disks = []
    for line in text.splitlines():
        found=ETHER_LINE.match(line)
        if found:
            number,key,value=found.groups()
            item=adapters.setdefault(int(number),{})
            key=key.lower()
            if key in item:
                raise batch.BatchBlocked("Duplicate VMware network adapter property")
            item[key]=value.upper()
        disk=DISK_LINE.match(line)
        if disk:
            disks.append(disk.group(1))
    if not adapters:
        raise batch.BatchBlocked("Cannot prove disconnected clone NICs")
    present = [a for a in adapters.values() if a.get("present", "TRUE") != "FALSE"]
    if not present or any(a.get("startconnected") != "FALSE" for a in present):
        raise batch.BatchBlocked("All clone NICs must explicitly start disconnected")
    if not disks:
        raise batch.BatchBlocked("Clone has no independently addressable VMDK descriptor")
    for name in disks:
        if Path(name).is_absolute() or "\\" in name or ".." in Path(name).parts:
            raise batch.BatchBlocked("Clone disk references an external Windows/VMware path")
        disk=(actual.parent/name).resolve(strict=True)
        if not disk.is_file() or disk.is_symlink() or not disk.is_relative_to(actual.parent):
            raise batch.BatchBlocked("Clone disk is absent, linked or outside candidate directory")
        # VMware linked clones usually reference a parent VMDK descriptor.
        # Read only the header; never process/copy an entire virtual disk.
        with disk.open("rb") as stream:
            header=stream.read(8192)
        if b"parentFileNameHint" in header or b"parentCID=" in header:
            raise batch.BatchBlocked("Linked/differencing VMDK detected; use an independent full clone")
    return {"vmx":str(actual),"nics":len(present),"vmdks":len(disks)}


def powered_off(candidate: Path, master: Path, output: str) -> None:
    lines = output.splitlines()
    if not lines or not re.fullmatch(r"Total running VMs: \d+",lines[0].strip()):
        raise batch.BatchBlocked("Untrusted vmrun running VM inventory")
    active = [Path(line.strip()).resolve() for line in lines[1:] if line.strip()]
    if len(active) != len(set(active)) or len(active) != int(lines[0].split(":")[1]):
        raise batch.BatchBlocked("Ambiguous VMware running VM inventory")
    if candidate.resolve() in active:
        raise batch.BatchBlocked("Candidate is already running; isolate its NICs before boot")
    if master.resolve() not in active:
        raise batch.BatchBlocked("Frozen master VM not found under expected VMware registration")


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-receipt",required=True)
    parser.add_argument("--clone-vmx",required=True,
                        help="Absolute path to already-created, powered-off, NIC-disconnected full clone VMX")
    args=parser.parse_args(argv)
    deployment.provenance()  # clean, origin-synced, exact feature branch
    accept=deployment.helper("wslpe41-learner-acceptance.py")
    receipt=accept.verify_receipt(args.freeze_receipt)
    master=Path(receipt["vmx"])
    candidate=Path(args.clone_vmx).expanduser()
    detail=vmx_inventory(candidate,master)
    listing=subprocess.run(["vmrun","-T","ws","list"],cwd=ROOT,
                           capture_output=True,text=True,timeout=40,check=False)
    if listing.returncode:
        raise batch.BatchBlocked("VMware read-only running VM inventory unavailable")
    powered_off(candidate,master,listing.stdout)
    # Receipt alone does not guarantee snapshot still exists.
    freeze=deployment.helper("wslpe41-freeze.py")
    if freeze.snapshot_names(master).count(receipt["snapshot"]) != 1:
        raise batch.BatchBlocked("Frozen snapshot no longer exists uniquely on the original guest")
    print("[PASS] Frozen master receipt and source-bound snapshot remain valid")
    print(f"[PASS] Separate powered-off clone: {detail['nics']} disconnected NIC(s), {detail['vmdks']} local disk reference(s)")
    print("[PENDING] Confirm full-clone origin from the named snapshot in VMware UI; VMX cannot prove ancestry")
    print("[PENDING] Offline NIC review does not prove guest identity, VMware isolation or learner execution")
    print("[NO ACTION] No VM or guest mutation occurred")
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
        print("[BLOCKED] WSLPE41 test clone not approved: "+str(exc),file=sys.stderr)
        raise SystemExit(2)
