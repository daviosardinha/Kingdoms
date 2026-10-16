"""WSLPE-only offline NAT cutover contract (pure functions, no file writes).

A valid candidate changes only ethernet0.startConnected on the exact
registered WSLPE VMX. It must be installed only while that VM is proven
powered off and a *separate*, actually tested rollback exists. VMware
Workstation may rewrite .vmx files; never alter a running guest.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from kingdoms.wslpe_nat_readiness import vmx_snapshot
from kingdoms.wslpe_nic_contract import parse_vmx_networks

CONFIG = re.compile(
    r'^(?P<pre>[ \t]*ethernet(?P<slot>\d+)\.(?P<key>[A-Za-z0-9]+)'
    r'[ \t]*=[ \t]*")(?P<value>[^"]*)(?P<post>"[ \t]*)$',
    re.IGNORECASE,
)
NEWLINE = re.compile(r"\r\n|\n|\r")


@dataclass(frozen=True)
class Candidate:
    before_sha256: str
    after_sha256: str
    change: str
    preview: str


def _lines_exact(source: str) -> tuple[list[str], dict[tuple[int, str], int]]:
    if not isinstance(source, str) or not source or "\x00" in source:
        raise ValueError("Unreadable VMX content")
    if len(source.encode("utf-8")) > 1024 * 1024:
        raise ValueError("VMX content too large for scoped update")
    lines = source.splitlines(keepends=True)
    found = {}
    for index, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        match = CONFIG.fullmatch(raw)
        if not match:
            if re.match(r"^[ \t]*ethernet\d+\.startConnected\b", raw, re.I):
                raise ValueError("Malformed VMX connection property")
            continue
        slot = int(match.group("slot"))
        key = match.group("key").lower()
        pair = (slot, key)
        if pair in found:
            raise ValueError("Duplicate VMX ethernet property: ambiguous")
        found[pair] = index
    return lines, found


def render_nat_offline(source: str, exercise_vmnet: str) -> str:
    """Produce the one-line persistent candidate; never write to the VMX."""
    lines, found = _lines_exact(source)
    vmx_snapshot(source, exercise_vmnet)
    slots = parse_vmx_networks(source)
    if set(slots) != {0, 1}:
        raise ValueError("VMX contains unexpected ethernet adapter slots")
    natkey = (0, "startconnected")
    if natkey in found:
        index = found[natkey]
        raw = lines[index]
        suffix = raw[len(raw.rstrip("\r\n")):]
        parsed = CONFIG.fullmatch(raw.rstrip("\r\n"))
        if parsed is None or parsed.group("value").upper() != "TRUE":
            raise ValueError("Existing NAT startConnected value is not TRUE")
        lines[index] = (
            parsed.group("pre") + "FALSE" + parsed.group("post") + suffix
        )
    else:
        anchor = (0, "connectiontype")
        if anchor not in found:
            raise ValueError("No exact provisioning ethernet0 anchor")
        suffix = "\r\n" if "\r\n" in source else "\n"
        at = found[anchor]
        # NORTH's audited offline transition appends one explicit
        # ethernet0 flag. WSLPE inserts immediately after the verified NAT
        # adapter anchor, retaining every unrelated VMware setting bytewise.
        if not lines[at].endswith(("\r", "\n")):
            lines[at] += suffix
        lines.insert(at + 1, f'ethernet0.startConnected = "FALSE"{suffix}')
    candidate = "".join(lines)
    updated = parse_vmx_networks(candidate)
    before = parse_vmx_networks(source)
    if updated[0].get("startconnected") != "FALSE":
        raise ValueError("NAT disconnection not represented exactly")
    if updated[1] != before[1]:
        raise ValueError("Exercise Ethernet1 was modified")
    if candidate == source:
        raise ValueError("No NAT candidate change")
    if candidate.count('startConnected = "FALSE"') > 2:
        raise ValueError("Unexpected VMX connection settings")
    return candidate


def manifest(source: str, candidate: str, vmnet: str) -> Candidate:
    if render_nat_offline(source, vmnet) != candidate:
        raise ValueError("Candidate differs from strict Ethernet0-only rendering")
    return Candidate(
        sha256(source.encode("utf-8")).hexdigest(),
        sha256(candidate.encode("utf-8")).hexdigest(),
        "WSLPE registered VMX, ethernet0.startConnected TRUE -> FALSE only",
        'ethernet0.startConnected = "FALSE"',
    )


def guarded_original_restore(current: str, original: str,
                             expected: Candidate, vmnet: str) -> str:
    """Render restore bytes only when current candidate is unchanged.

    NEVER apply this to a running VM; do not overwrite an unexpected VMware
    generated VMX or a file belonging to NORTH.
    """
    if sha256(original.encode("utf-8")).hexdigest() != expected.before_sha256:
        raise ValueError("Stored VMX original checksum does not match")
    if sha256(current.encode("utf-8")).hexdigest() != expected.after_sha256:
        raise ValueError("Current VMX differs; manual recovery is mandatory")
    if manifest(original, current, vmnet) != expected:
        raise ValueError("Candidate provenance does not match")
    return original
