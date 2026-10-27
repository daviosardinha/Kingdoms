#!/usr/bin/env bash
# PURPLE read-only host-only network check. No NORTH or VMware mutation.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m goad.purple_vmware_network verify
