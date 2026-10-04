#!/usr/bin/env bash
set -euo pipefail

IFACE="${IFACE:-vmnet10}"
WS01="${WS01:-10.4.10.31}"
PACDIR="${PACDIR:-/tmp/kingdoms-wpad}"

ip -br addr show "$IFACE"
ip route get "$WS01"
ip -6 addr show dev "$IFACE"

sudo ss -lntup | grep -E '(:80 |:80$|:53 |:53$|:547 |:547$|:5355 |:5355$|:137 |:137$)' || true
pgrep -af 'mitm6|Responder|ntlmrelayx|python3.*http|dnsmasq' || true

mkdir -p "$PACDIR"
cat > "$PACDIR/wpad.dat" <<'PAC'
function FindProxyForURL(url, host) {
    return "DIRECT";
}
PAC

chmod 644 "$PACDIR/wpad.dat"
sha256sum "$PACDIR/wpad.dat"

bash "${ROOT:-$HOME/Documents/GOAD_NOMAD}/scripts/phase03/diagnostics/ensure-wpad-rickon-session.sh"

echo "PASS: WPAD preflight completed; PAC and victim session ready with no WS01 network-state mutation"
