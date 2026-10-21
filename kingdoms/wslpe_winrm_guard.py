"""WSLPE-only host management-port firewall contract.

NORTH already uses a provisioning-NAT to exercise-NIC transition. VMware's
vmnet-nat process can still own a host-wide forwarded TCP listener. This
module models ONE WSLPE WinRM host port and NEVER edits NORTH, VMware vmnets,
NAT daemon state, or any guest. Changes require an explicit operator action
in the separate CLI. An nftables drop on non-loopback INPUT traffic protects
a listening socket; it does not change where that socket is bound.
"""
from __future__ import annotations

import json
import re

TABLE = "kingdoms_wslpe_winrm"
CHAIN = "local_winrm_only"
COMMENT = "KINGDOMS_WSLPE_WINRM"
PRIORITY = -50


def firewall_batch(port: int) -> str:
    if type(port) is not int or port < 1 or port > 65535:
        raise ValueError("Invalid WSLPE forwarded port")
    return (
        f"add table inet {TABLE}\n"
        f"add chain inet {TABLE} {CHAIN} "
        f"{{ type filter hook input priority {PRIORITY}; policy accept; }}\n"
        f'add rule inet {TABLE} {CHAIN} '
        f'meta iifname != "lo" tcp dport {port} drop comment "{COMMENT}"\n'
    )


def _is_interface_match(part: dict) -> bool:
    value = part.get("match")
    return isinstance(value, dict) and (
        value.get("op") == "!="
        and value.get("left") == {"meta": {"key": "iifname"}}
        and value.get("right") == "lo"
    )


def _is_port_match(part: dict, port: int) -> bool:
    value = part.get("match")
    return isinstance(value, dict) and (
        value.get("op") == "=="
        and value.get("left") == {"payload": {"protocol": "tcp", "field": "dport"}}
        and value.get("right") == port
    )


def verify_firewall_json(raw: str, port: int) -> bool:
    """Accept only our exact dedicated input/drop chain and one-port rule.

    No grep for 'drop' or trusting a comment: inspect the nftables JSON AST.
    A different/multiple rule, a non-input chain, or a different port fails.
    """
    if type(port) is not int or not 1 <= port <= 65535:
        return False
    try:
        document = json.loads(raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(document, dict):
        return False
    entries = document.get("nftables", [])
    if not isinstance(entries, list):
        return False
    chains = [x["chain"] for x in entries
              if isinstance(x, dict) and isinstance(x.get("chain"), dict)]
    rules = [x["rule"] for x in entries
             if isinstance(x, dict) and isinstance(x.get("rule"), dict)]
    tables = [x["table"] for x in entries
              if isinstance(x, dict) and isinstance(x.get("table"), dict)]
    if len(chains) != 1 or len(rules) != 1 or len(tables) != 1:
        return False
    if tables[0].get("family") != "inet" or tables[0].get("name") != TABLE:
        return False
    chain = chains[0]
    if not all((
        chain.get("family") == "inet",
        chain.get("table") == TABLE,
        chain.get("name") == CHAIN,
        chain.get("type") == "filter",
        chain.get("hook") == "input",
        chain.get("prio") == PRIORITY,
        chain.get("policy") == "accept",
    )):
        return False
    rule = rules[0]
    if not all((
        rule.get("family") == "inet",
        rule.get("table") == TABLE,
        rule.get("chain") == CHAIN,
        rule.get("comment") == COMMENT,
    )):
        return False
    expressions = rule.get("expr")
    if not isinstance(expressions, list) or len(expressions) != 3:
        return False
    if not any(_is_interface_match(x) for x in expressions if isinstance(x, dict)):
        return False
    if not any(_is_port_match(x, port) for x in expressions if isinstance(x, dict)):
        return False
    if not any(isinstance(x, dict) and "drop" in x
               for x in expressions):
        return False
    return True



def migrated_firewall_batch(snapshot: str, old_port: int, new_port: int) -> str:
    """Replace only the uniquely verified WSLPE guard rule, by nft handle.

    nft applies a single replace-rule statement atomically: it never deletes
    the table or temporarily removes its input hook. The CLI independently
    validates native port ownership, requires both explicit port values, and
    checks the result before reporting success.
    """
    if (type(old_port) is not int or type(new_port) is not int
            or not 1 <= old_port <= 65535 or not 1 <= new_port <= 65535
            or old_port == new_port):
        raise ValueError("Two distinct valid WSLPE ports are required")
    if not verify_firewall_json(snapshot, old_port):
        raise ValueError("Existing WSLPE guard differs from exact old-port contract")
    document = json.loads(snapshot)
    rules = [item["rule"] for item in document["nftables"]
             if isinstance(item, dict) and isinstance(item.get("rule"), dict)]
    if len(rules) != 1:
        raise ValueError("Expected exactly one WSLPE input rule")
    handle = rules[0].get("handle")
    if type(handle) is not int or handle <= 0:
        raise ValueError("WSLPE rule handle is missing or invalid")
    return (
        f'replace rule inet {TABLE} {CHAIN} handle {handle} '
        f'meta iifname != "lo" tcp dport {new_port} '
        f'drop comment "{COMMENT}"\n'
    )

def listeners_for_port(ss_output: str, port: int) -> list[dict[str, str]]:
    """Extract locally bound addresses and process labels, no remote peers."""
    result = []
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid WinRM port")
    for line in ss_output.splitlines():
        columns = line.split()
        if len(columns) < 5 or columns[0] != "LISTEN":
            continue
        local = columns[3]
        try:
            p = int(local.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        if p != port:
            continue
        host = local.rsplit(":", 1)[0].strip("[]")
        result.append({
            "address": host,
            "owner_vmnet_nat": bool(re.search(r'users:\(\("vmnet-nat(?:d)?"', line)),
        })
    return result


def require_vmware_nat_owner(ss_output: str, port: int) -> bool:
    """Root ss -p must identify the unique IPv4 wildcard vmnet-nat listener."""
    listeners = listeners_for_port(ss_output, port)
    return (
        len(listeners) == 1
        and listeners[0]["address"] == "0.0.0.0"
        and listeners[0]["owner_vmnet_nat"]
    )
