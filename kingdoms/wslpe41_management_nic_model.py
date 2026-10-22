"""Exact fresh WSLPE41 offline virtual NIC model correction.

The existing committed third NIC omitted ethernet2.virtualDev. VMware then
presented PCI 8086:100F (legacy E1000), while the two existing Windows adapters
use e1000e (PCI 8086:10D3). Correct ONLY that missing model declaration
after ALL VMware guests are off. Preserve the original NIC-attachment journal,
other NICs, MAC address, and a separate private recovery journal.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from kingdoms import wslpe41_management_nic as nic
from kingdoms.wslpe_nic_contract import parse_vmx_networks

APPROVAL = "PIN-FRESH-WSLPE-VMNET4-E1000E"
EXPECTED_MAC = "00:0c:29:2f:d7:6f"
HISTORY_NAME = ".local/state/kingdoms-wslpe41-mgmt-nic"
REPAIR_NAME = ".local/state/kingdoms-wslpe41-nic-model"
EXACT_LINE = b'ethernet2.virtualDev = "e1000e"\n'
OLD_NIC_LINES = tuple(x for x in nic.NIC_LINES if not x.startswith("ethernet2.virtualDev"))
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


def _committed_attachment(home: Path, vmx: Path) -> None:
    history = home / HISTORY_NAME / nic.INSTANCE / "journal.json"
    if history.is_symlink() or not history.is_file():
        raise nic.NicBlocked("Prior exact management NIC attachment journal absent")
    info = history.lstat()
    if (info.st_uid != os.getuid() or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 150_000):
        raise nic.NicBlocked("Prior NIC attachment journal is not privately owned")
    try:
        old = json.loads(history.read_text(encoding="utf-8"))
        if (old.get("schema") != "kingdoms.wslpe41.nic.v1"
                or old.get("status") != "committed"
                or old.get("instance") != nic.INSTANCE
                or old.get("vmx") != str(vmx)):
            raise nic.NicBlocked("Prior NIC journal does not match exact VMX/instance")
        raw = base64.b64decode(old["original_b64"], validate=True)
        if hashlib.sha256(raw).hexdigest() != old.get("original_sha256"):
            raise nic.NicBlocked("Prior NIC original-byte checksum invalid")
        expected = raw + ("\n".join(OLD_NIC_LINES) + "\n").encode("ascii")
        if hashlib.sha256(expected).hexdigest() != old.get("proposed_sha256"):
            raise nic.NicBlocked("Prior NIC attachment was not exact legacy model")
    except (KeyError, ValueError, UnicodeError, TypeError) as exc:
        raise nic.NicBlocked("Prior NIC journal malformed") from exc


def candidate(original: bytes) -> bytes:
    nic.verify_layout(original, allow_management=True, allow_legacy_model=True)
    text = original.decode("utf-8")
    slots = parse_vmx_networks(text)
    # The original source omitted virtualDev. Workstation may keep it
    # absent or persist the fallback e1000 after first power-on.
    old_model = slots[2].get("virtualdev")
    if old_model not in (None, "e1000"):
        raise nic.NicBlocked("Management virtual NIC model is not a legacy e1000 candidate")
    if (slots[0].get("virtualdev", "").lower() != "e1000e"
            or slots[1].get("virtualdev", "").lower() != "e1000e"):
        raise nic.NicBlocked("Existing working NIC models are not both e1000e")
    if slots[2].get("generatedaddress", "").lower() != EXPECTED_MAC:
        raise nic.NicBlocked("Management MAC differs from captured Windows/VMware evidence")
    if not original.endswith(b"\n") or EXACT_LINE in original:
        raise nic.NicBlocked("Cannot update exactly one model directive")
    if old_model == "e1000":
        lines = original.splitlines(keepends=True)
        found = [i for i, line in enumerate(lines)
                 if re.fullmatch(rb'ethernet2\.virtualDev = "e1000"\r?\n', line)]
        if len(found) != 1:
            raise nic.NicBlocked("Legacy management NIC model has ambiguous VMX definition")
        lines[found[0]] = EXACT_LINE
        result = b"".join(lines)
    else:
        result = original + EXACT_LINE
    nic.verify_layout(result, allow_management=True)
    return result


def plan(home: Path) -> tuple[nic.Target, bytes]:
    nic.host_operator_network_ready()
    # Probe only observed legacy 0771 mode; the ordinary NIC attachment gate
    # remains strict and can never apply new NICs to group-writable VMX files.
    target = nic.identify(home, existing_ok=True,
                          exact_legacy_0771_probe=True,
                          allow_legacy_management_model=True)
    _committed_attachment(home, target.vmx)
    return target, candidate(target.original)


def apply(home: Path, *, expected_sha256: str, approval: str) -> str:
    if approval != APPROVAL or not SHA256.fullmatch(expected_sha256):
        raise nic.NicBlocked("Exact legacy NIC-model approval and SHA256 required")
    nic.zero_vmware_guests()
    target, proposed = plan(home)
    if target.digest != expected_sha256:
        raise nic.NicBlocked("Fresh VMX changed after read-only model plan")
    state = home / REPAIR_NAME / nic.INSTANCE
    if state.is_symlink() or state.exists():
        raise nic.NicBlocked("Existing NIC-model recovery journal; no automatic retry")
    state.mkdir(parents=True, mode=0o700)
    info = state.lstat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise nic.NicBlocked("NIC-model journal directory not private")
    record = {
        "schema": "kingdoms.wslpe41.nic.model.v1", "status": "prepared",
        "instance": nic.INSTANCE, "vmx": str(target.vmx),
        "original_sha256": target.digest,
        "proposed_sha256": hashlib.sha256(proposed).hexdigest(),
        "original_mode": f"{stat.S_IMODE(target.vmx.lstat().st_mode):04o}",
        "original_b64": base64.b64encode(target.original).decode("ascii"),
    }
    journal = state / "journal.json"
    nic._write_atomic(journal, json.dumps(record, sort_keys=True).encode(), 0o600)
    try:
        nic.zero_vmware_guests()
        current = nic._read_vmx(target.vmx, exact_legacy_0771_probe=True)
        if current != target.original:
            raise nic.NicBlocked("Fresh VMX changed before model write")
        # Always normalize updated exact user-owned VMX to 0600, not 0771.
        nic._write_atomic(target.vmx, proposed, 0o600)
        stored = nic._read_vmx(target.vmx)
        if stored != proposed:
            raise nic.NicBlocked("VMX did not retain exact model-only change")
        nic.verify_layout(stored, allow_management=True)
        record["status"] = "committed"
        nic._write_atomic(journal, json.dumps(record, sort_keys=True).encode(), 0o600)
    except Exception:
        # A crash or ambiguous file state must preserve a prepared journal.
        try:
            current = nic._read_vmx(target.vmx, exact_legacy_0771_probe=True)
            if current == proposed:
                nic.zero_vmware_guests()
                nic._write_atomic(target.vmx, target.original, 0o600)
                record["status"] = "rolled_back"
                nic._write_atomic(journal, json.dumps(record, sort_keys=True).encode(), 0o600)
        except Exception:
            pass
        raise
    return str(journal)
