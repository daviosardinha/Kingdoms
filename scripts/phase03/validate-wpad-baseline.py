#!/usr/bin/env python3
import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path


def normalize_ipv6(value: str) -> str:
    value = re.sub(r"%\d+$", "", value.strip())
    return str(ipaddress.IPv6Address(value))


def mitm6_target_link_local(ipv4: str) -> str:
    octets = [str(int(part)) for part in ipv4.split(".")]
    if len(octets) != 4:
        raise ValueError(f"invalid IPv4 address: {ipv4}")
    return normalize_ipv6("fe80::" + ":".join(octets))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("--target-ip", default="10.4.10.31")
    parser.add_argument("--attacker-v6", required=True)
    args = parser.parse_args()

    path = Path(args.baseline)
    data = json.loads(path.read_text(encoding="utf-8"))

    if data.get("Target") != "WS01":
        raise SystemExit("invalid WPAD baseline target")
    if data.get("IPv4") != args.target_ip:
        raise SystemExit("invalid WPAD baseline IPv4 identity")

    forged = mitm6_target_link_local(args.target_ip)
    attacker = normalize_ipv6(args.attacker_v6)

    ipv6 = {
        normalize_ipv6(item["Address"])
        for item in data.get("IPv6Addresses", [])
        if item.get("Address")
    }
    dns6 = {
        normalize_ipv6(item)
        for item in data.get("IPv6DnsServers", [])
        if item
    }

    if forged in ipv6:
        raise SystemExit(
            f"unsafe WPAD baseline: contains mitm6-derived target IPv6 {forged}"
        )
    if attacker in dns6:
        raise SystemExit(
            f"unsafe WPAD baseline: contains attacker IPv6 DNS {attacker}"
        )

    print(f"PHASE03_WPAD_BASELINE_GUARD_TARGET=WS01")
    print(f"PHASE03_WPAD_BASELINE_GUARD_IPV4={args.target_ip}")
    print(f"PHASE03_WPAD_BASELINE_GUARD_FORGED_IPV6={forged}")
    print(f"PHASE03_WPAD_BASELINE_GUARD_ATTACKER_DNS={attacker}")
    print("PHASE03_WPAD_BASELINE_GUARD_VALID=True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
