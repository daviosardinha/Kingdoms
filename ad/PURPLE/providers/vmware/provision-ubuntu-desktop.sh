#!/usr/bin/env bash
# Convert the VMware-compatible Ubuntu 22.04 Bento base box to Ubuntu Desktop.
# Invoked once by Vagrant as the guest's root user. Repeat-safe apt operations.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ubuntu-desktop-minimal open-vm-tools-desktop
systemctl set-default graphical.target
systemctl enable gdm3
echo "PURPLE_UBUNTU_DESKTOP_PROVISIONED=1"
