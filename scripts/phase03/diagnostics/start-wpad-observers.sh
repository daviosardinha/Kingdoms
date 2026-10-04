#!/usr/bin/env bash
set -euo pipefail

IFACE="${IFACE:-vmnet10}"
PACDIR="${PACDIR:-/tmp/kingdoms-wpad}"
HTTP_LOG="${HTTP_LOG:-/tmp/kingdoms-wpad-http.log}"
PCAP="${PCAP:-/tmp/kingdoms-wpad.pcap}"

rm -f "$HTTP_LOG" /tmp/kingdoms-wpad-tcpdump.log
sudo rm -f "$PCAP"
[[ -f "$PACDIR/wpad.dat" ]] || {
  echo "FAIL: harmless PAC file missing: $PACDIR/wpad.dat" >&2
  echo 'Run scripts/phase03/diagnostics/wpad-preflight.sh first.' >&2
  exit 1
}

sudo python3 -m http.server 80 --bind :: --directory "$PACDIR" >"$HTTP_LOG" 2>&1 &
HTTP_PID=$!
sleep 2
sudo ss -lntp | grep ':80 ' || {
  echo "FAIL: HTTP server did not bind"
  exit 1
}

sudo tcpdump -i "$IFACE" -nn -U -s 0 -Z "$USER" -w "$PCAP" \
  '(udp port 53 or udp port 546 or udp port 547 or tcp port 80)' \
  >/tmp/kingdoms-wpad-tcpdump.log 2>&1 &
TCPDUMP_PID=$!
sleep 2
kill -0 "$TCPDUMP_PID"

echo "HTTP_PID=$HTTP_PID"
echo "TCPDUMP_PID=$TCPDUMP_PID"
echo "HTTP_LOG=$HTTP_LOG"
echo "PCAP=$PCAP"
echo "PASS: harmless WPAD observers running"
