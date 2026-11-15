#!/usr/bin/env bash
# Install network-capture diagnostics on a fresh PURPLE-C2 Debian guest.
# Sliver installation and operator activities remain manual course exercises.
# Vagrant runs this after Linux lab NIC setup with root privileges.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

if [[ "$(id -u)" -ne 0 ]]; then
    echo "[PURPLE-C2][ERROR] Diagnostic provisioner requires root" >&2
    exit 1
fi

if ! dpkg-query -W -f='${Status}' tcpdump 2>/dev/null | grep -qx 'install ok installed'; then
    apt-get update
    apt-get install -y --no-install-recommends tcpdump
fi

if ! command -v tcpdump >/dev/null 2>&1; then
    echo "[PURPLE-C2][ERROR] tcpdump is not available after provisioning" >&2
    exit 1
fi

echo "PURPLE_C2_TCPDUMP_READY=PASS"
