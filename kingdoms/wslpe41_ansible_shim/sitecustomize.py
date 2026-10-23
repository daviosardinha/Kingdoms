"""Process-local DNS pin for the ONE existing fresh WSLPE WinRM endpoint.

Loaded via PYTHONPATH only by the exact instance's guarded Ansible subprocesses.
Preserves TLS hostname/SNI WSLPE-WS01; never modifies /etc/hosts, DNS, proxies,
VMware networks or other labs. It is NOT a substitute for pinned TLS validation.
"""
from __future__ import annotations

import os
import socket

_HOST = "wslpe-ws01"
_PORT = 5986
_IP = "172.28.233.31"
_original_getaddrinfo = socket.getaddrinfo

def _wslpe_getaddrinfo(host, port, *args, **kwargs):
    if isinstance(host, str) and host.casefold() == _HOST:
        if str(port) not in (str(_PORT), "https"):
            raise OSError("WSLPE process-scoped name used outside HTTPS/5986")
        return _original_getaddrinfo(_IP, _PORT, *args, **kwargs)
    return _original_getaddrinfo(host, port, *args, **kwargs)

# Apply only when the exact guarded instance owner explicitly enabled the shim.
if os.environ.get("KINGDOMS_WSLPE41_PINNED_OPERATOR") == "bf5369-wslpe-vmware":
    socket.getaddrinfo = _wslpe_getaddrinfo
