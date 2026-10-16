"""WSLPE-only remote operator preflight and independent timer smoke test.

Host side only. Never changes firewall, NAT, VM, route, DNS or NORTH.
May create one short-lived, unique sentinel under /run using a scoped
systemd transient timer, then remove exactly that sentinel.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid


def command(args: list[str], timeout: int = 20):
    return subprocess.run(args, capture_output=True, text=True,
                          check=False, timeout=timeout)


def ssh_management_path(vmnet: str, subnet: str,
                        environ: dict[str, str] | None = None,
                        executor=command) -> str:
    env = environ if environ is not None else os.environ
    fields = env.get("SSH_CONNECTION", "").split()
    if len(fields) != 4:
        raise ValueError("SSH_CONNECTION with client/server IP and ports is required")
    client, client_port, server, server_port = fields
    try:
        remote = ipaddress.ip_address(client)
        local = ipaddress.ip_address(server)
        exercise = ipaddress.ip_network(subnet, strict=True)
        if remote.version != 4 or local.version != 4:
            raise ValueError("Only verified IPv4 SSH management is supported")
        if remote in exercise or local in exercise:
            raise ValueError("SSH traverses the WSLPE exercise subnet")
        if remote.is_loopback or local.is_loopback:
            raise ValueError("Loopback SSH cannot prove the remote network boundary")
        if not (1 <= int(client_port) <= 65535
                and 1 <= int(server_port) <= 65535):
            raise ValueError("Invalid SSH port")
    except ValueError as exc:
        raise ValueError("Untrusted remote SSH origin or destination") from exc

    result = executor(["ip", "-j", "-4", "route", "get", str(remote)])
    if result.returncode:
        raise ValueError("Could not prove host's route back to the SSH operator")
    try:
        routes = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Host SSH return-route evidence is not JSON") from exc
    if (not isinstance(routes, list) or len(routes) != 1
            or not isinstance(routes[0], dict)):
        raise ValueError("Host SSH return-route evidence is ambiguous")
    device = routes[0].get("dev")
    if (not isinstance(device, str) or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,32}", device)
            or device == vmnet or device.startswith("vmnet")):
        raise ValueError("SSH route may traverse the vulnerable WSLPE vmnet")
    source = routes[0].get("prefsrc") or routes[0].get("src")
    if not source:
        raise ValueError("SSH source route lacks a verifiable local address")
    try:
        if ipaddress.ip_address(source) in exercise:
            raise ValueError("SSH return path sources from WSLPE exercise subnet")
    except ValueError as exc:
        raise ValueError("SSH source route is untrusted") from exc
    return device


def host_timer_smoke_test(executor=command, sleeper=time.sleep) -> str:
    """Prove a real *host-side* timer fired without installing nftables rules.

    A 3-second systemd timer executes /usr/bin/touch on a uniquely named
    root-owned /run file. Success must be observed from a separate query.
    """
    identifier = uuid.uuid4().hex[:16]
    unit = f"kingdoms-wslpe-remote-check-{identifier}"
    sentinel = f"/run/{unit}.done"
    allowed_prefix = "/run/kingdoms-wslpe-remote-check-"
    if not (sentinel.startswith(allowed_prefix)
            and re.fullmatch(r"/run/kingdoms-wslpe-remote-check-[a-f0-9]{16}\.done",
                             sentinel)):
        raise ValueError("Untrusted WSLPE rollback test sentinel")
    try:
        arm = executor([
            "sudo", "-n", "systemd-run", "--quiet",
            "--unit", unit, "--on-active=3s", "--collect",
            "/usr/bin/touch", sentinel,
        ], timeout=20)
        if arm.returncode:
            raise ValueError("Cannot arm host-side systemd timer")
        timer = executor(["sudo", "-n", "systemctl", "is-active",
                          f"{unit}.timer"])
        if timer.returncode or timer.stdout.strip() != "active":
            raise ValueError("Host-side timer failed activation check")
        for _ in range(12):
            check = executor(["sudo", "-n", "/usr/bin/test", "-f", sentinel])
            if check.returncode == 0:
                return unit
            sleeper(1)
        raise ValueError("Host-side rollback smoke timer never executed")
    finally:
        # This is the only artifact this test ever deletes. No /etc,
        # nftables tables, VMX, host network or NORTH path is touched.
        clean = executor(["sudo", "-n", "/usr/bin/rm", "-f", "--", sentinel])
        if clean.returncode:
            raise ValueError("WSLPE host timer test sentinel cleanup failed")
