"""Dedicated WSLPE host-only guards for ALL native VMware management forwards.

Source/policy functions only. Existing WinRM 2210 legacy table is left alone.
All selected ports must be discovered from the existing WSLPE native Vagrant
registration, never assumed from a static port range.
"""
from __future__ import annotations

import json
import re

from kingdoms import wslpe_winrm_guard as legacy

TABLE = "kingdoms_wslpe_management"
CHAIN = "loopback_management_only"
COMMENT = "KINGDOMS_WSLPE_MANAGEMENT"
PRIORITY = -60
GUEST_PORTS = (22, 5985, 5986)


def parse_vagrant_ports(text: str) -> dict[int, int]:
    """Require exactly the three native SSH and WinRM guest forwards."""
    if not isinstance(text, str):
        raise ValueError("Vagrant port data must be text")
    mapping: dict[int, int] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(
            r"\s*(\d{1,5})\s+\(guest\)\s+=>\s+(\d{1,5})\s+\(host\)\s*",
            line,
        )
        if match is None:
            # Vagrant's standard informational header precedes port rows.
            # Never silently skip an unknown port or warning line.
            if line.strip().startswith((
                "The forwarded ports for the machine are listed below.",
                "these values may differ from values configured in the Vagrantfile",
                "provider supports automatic port collision detection and resolution.",
            )):
                continue
            raise ValueError("Unexpected or ambiguous native Vagrant forwarding")
        guest, host = (int(value) for value in match.groups())
        if guest not in GUEST_PORTS or guest in mapping:
            raise ValueError("Unexpected or duplicated WSLPE guest forwarding")
        if not (1025 <= host <= 65535):
            raise ValueError("Host forwarding port is outside approved range")
        mapping[guest] = host
    if set(mapping) != set(GUEST_PORTS) or len(set(mapping.values())) != 3:
        raise ValueError("Three unique WSLPE management forwards are required")
    return mapping


def firewall_batch(mapping: dict[int, int]) -> str:
    """One atomic nftables transaction, without flushing any existing table."""
    if not isinstance(mapping, dict) or set(mapping) != set(GUEST_PORTS):
        raise ValueError("Invalid WSLPE management forwarding selection")
    if any(type(v) is not int or not 1025 <= v <= 65535 for v in mapping.values()):
        raise ValueError("Invalid WSLPE host management port")
    if len(set(mapping.values())) != 3:
        raise ValueError("Overlapping WSLPE management forwarding ports")
    text = (
        f"add table inet {TABLE}\n"
        f"add chain inet {TABLE} {CHAIN} "
        f"{{ type filter hook input priority {PRIORITY}; policy accept; }}\n"
    )
    for guest in GUEST_PORTS:
        text += (
            f"add rule inet {TABLE} {CHAIN} "
            f'meta iifname != "lo" tcp dport {mapping[guest]} drop '
            f'comment "{COMMENT}"\n'
        )
    return text


def verify_firewall_json(raw: str, mapping: dict[int, int]) -> bool:
    """Verify one dedicated INPUT chain with three exact non-loopback drops.

    Reject all extra chains, rules, policy changes or unknown object types.
    """
    try:
        if not isinstance(mapping, dict) or set(mapping) != set(GUEST_PORTS):
            return False
        if any(type(p) is not int or not 1025 <= p <= 65535
               for p in mapping.values()) or len(set(mapping.values())) != 3:
            return False
        doc = json.loads(raw)
        entries = doc["nftables"]
        if not isinstance(entries, list):
            return False
        objects = [item for item in entries if isinstance(item, dict)
                   and "metainfo" not in item]
        if len(objects) != 5:
            return False
        tables = [x["table"] for x in objects if isinstance(x.get("table"), dict)]
        chains = [x["chain"] for x in objects if isinstance(x.get("chain"), dict)]
        rules = [x["rule"] for x in objects if isinstance(x.get("rule"), dict)]
        if len(tables) != 1 or len(chains) != 1 or len(rules) != 3:
            return False
        if tables[0].get("family") != "inet" or tables[0].get("name") != TABLE:
            return False
        chain = chains[0]
        if (chain.get("family"), chain.get("table"), chain.get("name"),
                chain.get("type"), chain.get("hook"), chain.get("prio"),
                chain.get("policy")) != (
                "inet", TABLE, CHAIN, "filter", "input", PRIORITY, "accept"):
            return False
        ports_found = []
        for rule in rules:
            if any(rule.get(k) != v for k, v in (
                    ("family", "inet"), ("table", TABLE), ("chain", CHAIN),
                    ("comment", COMMENT))):
                return False
            expr = rule.get("expr")
            if not isinstance(expr, list) or len(expr) != 3:
                return False
            if not any(isinstance(x, dict) and legacy._is_interface_match(x)
                       for x in expr):
                return False
            if not any(isinstance(x, dict) and set(x) == {"drop"} for x in expr):
                return False
            matches = [port for port in mapping.values() if
                       any(isinstance(x, dict) and legacy._is_port_match(x, port)
                           for x in expr)]
            if len(matches) != 1:
                return False
            ports_found.extend(matches)
        return set(ports_found) == set(mapping.values()) and len(set(ports_found)) == 3
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def verify_nat_listeners(ss_output: str, mapping: dict[int, int]) -> bool:
    """Reject missing, duplicated or non-vmnet-nat listeners for every port."""
    return (isinstance(mapping, dict)
            and set(mapping) == set(GUEST_PORTS)
            and len(set(mapping.values())) == 3
            and all(legacy.require_vmware_nat_owner(ss_output, port)
                    for port in mapping.values()))
