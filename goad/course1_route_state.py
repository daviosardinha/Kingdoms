"""Classify an existing NORTH parent provisioning route without changing it.

The textual output of iproute2 is not a stable identity format: protocol,
metric, source and spacing annotations differ across versions/restarts.
Use the structured ip -j output, retaining strict gateway/device/target checks.
"""
from __future__ import annotations

import argparse
import json
import sys

FORBIDDEN = frozenset(("nexthops", "nhid", "encap", "via", "multipath"))


def classify_route(payload: str, *, network: str, gateway: str,
                   device: str, host_source: str) -> str:
    """Return absent, owned, or foreign. Corrupt evidence is always foreign."""
    try:
        routes = json.loads(payload)
    except (TypeError, ValueError):
        return "foreign"
    if not isinstance(routes, list):
        return "foreign"
    if not routes:
        return "absent"
    if len(routes) != 1 or not isinstance(routes[0], dict):
        return "foreign"
    route = routes[0]
    if (route.get("dst") != network
            or route.get("gateway") != gateway
            or route.get("dev") != device
            or route.get("type", "unicast") != "unicast"
            or route.get("table", "main") not in ("main", 254)
            or route.get("scope", "global") not in ("global", "universe")
            or route.get("prefsrc", host_source) != host_source
            or route.get("flags", []) not in ([], None)
            or any(key in route for key in FORBIDDEN)):
        return "foreign"
    return "owned"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", required=True)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--host-source", required=True)
    args = parser.parse_args()
    try:
        data = sys.stdin.read(65537)
    except OSError:
        return 2
    if len(data) > 65536:
        print("foreign")
        return 0
    print(classify_route(
        data, network=args.network, gateway=args.gateway,
        device=args.device, host_source=args.host_source,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
