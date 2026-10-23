#!/usr/bin/env python3
"""Read-only Ansible localhost-only WSLPE41 private fixture guard check."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kingdoms.wslpe41_fixture_guard_probe import prove
from kingdoms.wslpe41_install_flow import InstallBlocked

if __name__ == "__main__":
    print("[MODE] READ ONLY | 0/41 preserved | controller-only credential guard", flush=True)
    try:
        prove()
        print("[PASS] WSLPE41_PRIVATE_FIXTURE_CONTROLLER_GUARD=PASS", flush=True)
    except (InstallBlocked, ValueError, OSError, RuntimeError) as exc:
        print("[BLOCKED] " + type(exc).__name__ + ": " + str(exc)[:240], flush=True)
        print("[NO REPLAY] Preserve both existing stage1 journals", flush=True)
        sys.exit(2)
