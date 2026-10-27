#!/usr/bin/env bash
# Convert the VMware-compatible Ubuntu 22.04 Bento box to a desktop endpoint
# with XRDP remote access and baseline net-tools. PURPLE-LX01 only.
# Called by Vagrant as root on fresh install; safe to repeat on provision.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

if [[ "$(id -u)" -ne 0 ]]; then
    echo "[PURPLE-LX01][ERROR] Desktop provisioner requires root" >&2
    exit 1
fi

apt-get update
apt-get install -y \
    ubuntu-desktop-minimal \
    open-vm-tools-desktop \
    xrdp \
    xorgxrdp \
    net-tools

# Ubuntu's graphical login remains available through the VMware console.
systemctl set-default graphical.target
systemctl enable --now gdm3

# XRDP uses an independent graphical Xorg session over TCP/3389.
# The ssl-cert group allows the xrdp daemon to use its generated TLS key.
usermod -aG ssl-cert xrdp
systemctl enable --now xrdp-sesman xrdp
# Reload service credentials so the ssl-cert group takes effect immediately.
systemctl restart xrdp

# Fail provisioning if the graphical remote-access stack is not operational.
systemctl is-active --quiet gdm3
systemctl is-active --quiet xrdp-sesman
systemctl is-active --quiet xrdp
command -v ifconfig >/dev/null

echo "PURPLE_UBUNTU_DESKTOP_PROVISIONED=1"
echo "PURPLE_LX01_XRDP_READY=1"
echo "PURPLE_LX01_NET_TOOLS_READY=1"
