"""WSLPE-only controlled IPv4 packet-path witness.

A temporary unprivileged TCP listener on the *existing* WSLPE host vmnet
and an exact local Windows socket test prove guest-to-host reachability.
No scans, no NORTH, no VM/network configuration changes and no persistence.
"""
from __future__ import annotations

import ipaddress
import socket
import threading

PORT = 47381
_TIMEOUT_MS = 2500


def validate_target(host: str, guest: str, subnet: str, port: int = PORT) -> None:
    network = ipaddress.IPv4Network(subnet, strict=True)
    h = ipaddress.IPv4Address(host)
    g = ipaddress.IPv4Address(guest)
    if (not network.is_private or network.prefixlen != 24
            or network.overlaps(ipaddress.IPv4Network("10.4.0.0/16"))
            or h not in network or g not in network or h == g
            or g != ipaddress.IPv4Address(int(network.network_address) + 31)
            or not isinstance(port, int) or not (1024 <= port <= 65535)):
        raise ValueError("Untrusted WSLPE-only control socket target")


def windows_tcp_probe(host: str, port: int = PORT) -> str:
    """Construct an exact-bound, read-only PowerShell socket probe."""
    ipaddress.IPv4Address(host)
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("Invalid controlled WSLPE TCP port")
    return rf"""
$ErrorActionPreference = 'Stop'
$machine = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if ($env:COMPUTERNAME -ine 'WSLPE-WS01' -or $machine.PartOfDomain) {{
  throw 'Target must be the domain-free WSLPE-WS01'
}}
$socket = New-Object System.Net.Sockets.TcpClient
$pending = $null
$connected = $false
try {{
  $pending = $socket.BeginConnect('{host}', {port}, $null, $null)
  if ($pending.AsyncWaitHandle.WaitOne({_TIMEOUT_MS}, $false)) {{
    try {{
      $socket.EndConnect($pending)
      $connected = [bool]$socket.Connected
    }} catch {{
      $connected = $false
    }}
  }}
}} catch {{
  $connected = $false
}} finally {{
  if ($null -ne $pending) {{ $pending.AsyncWaitHandle.Close() }}
  $socket.Dispose()
}}
Write-Output 'WSLPE_PACKET_MACHINE=WSLPE-WS01'
Write-Output 'WSLPE_PACKET_DOMAIN_FREE=TRUE'
if ($connected) {{
  Write-Output 'WSLPE_PACKET_TCP=OPEN'
}} else {{
  Write-Output 'WSLPE_PACKET_TCP=CLOSED'
}}
"""


def parse_windows_probe(status: int, output: bytes) -> bool:
    if status:
        raise ValueError("Authenticated WSLPE guest socket probe failed")
    if len(output) > 4096:
        raise ValueError("Unexpectedly large WSLPE guest response")
    lines = [line.strip() for line in output.decode("utf-8", "replace").splitlines()]
    counts = {line: lines.count(line) for line in set(lines)}
    for required in ("WSLPE_PACKET_MACHINE=WSLPE-WS01",
                     "WSLPE_PACKET_DOMAIN_FREE=TRUE"):
        if counts.get(required, 0) != 1:
            raise ValueError("Standalone WSLPE identity proof missing/ambiguous")
    states = (counts.get("WSLPE_PACKET_TCP=OPEN", 0),
              counts.get("WSLPE_PACKET_TCP=CLOSED", 0))
    if states not in ((1, 0), (0, 1)):
        raise ValueError("Guest TCP probe reported an ambiguous result")
    return states == (1, 0)


class ControlledHostListener:
    """Bound only to dedicated host-side WSLPE IPv4, never wildcard/NAT."""
    def __init__(self, host: str, guest: str, port: int = PORT):
        self.host = str(ipaddress.IPv4Address(host))
        self.guest = str(ipaddress.IPv4Address(guest))
        self.port = port
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._accepted = 0
        self._thread = None
        self._server = None

    def __enter__(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.settimeout(0.25)
            server.bind((self.host, self.port))
            server.listen(4)
        except Exception:
            server.close()
            raise
        self._server = server
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                if addr[0] == self.guest:
                    with self._lock:
                        self._accepted += 1

    def count(self):
        with self._lock:
            return self._accepted

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        if self._server:
            self._server.close()
        if self._thread:
            self._thread.join(timeout=2)
        return False
