#!/usr/bin/env bash
# Foreground HTTP observer for the WS01 WebDAV shortcut proof.
# It records HTTP requests only and does not request or capture authentication.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

WORK="${WORK:-$HOME/.config/kingdoms/phase03-webdav}"
BIND="${BIND:-10.4.10.254}"
PORT="${PORT:-80}"
ROOTDIR="$WORK/http-root"
HTTP_LOG="$WORK/http.log"
PCAP="$WORK/webdav-shortcut.pcap"
TCPDUMP_PID=""

cleanup() {
  if [[ -n "${TCPDUMP_PID:-}" ]]; then
    sudo kill "$TCPDUMP_PID" 2>/dev/null || true
    wait "$TCPDUMP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

sudo -v

if sudo -n ss -H -lnt 2>/dev/null | grep -Eq ":$PORT[[:space:]]"; then
  echo "FAIL: TCP/$PORT already has a listener" >&2
  exit 1
fi

install -d -m 700 "$WORK" "$ROOTDIR"
: >"$HTTP_LOG"
rm -f -- "$PCAP"
printf 'KINGDOMS\n' >"$ROOTDIR/kingdoms.ico"

echo '===== WEBDAV SHORTCUT OBSERVER ====='
echo "BIND=$BIND"
echo "PORT=$PORT"
echo "HTTP_LOG=$HTTP_LOG"
echo "PCAP=$PCAP"
echo 'MODE=anonymous HTTP observation only'
echo

sudo -n tcpdump -ni vmnet10 host 10.4.10.31 and tcp port "$PORT" -w "$PCAP" >/dev/null 2>&1 &
TCPDUMP_PID=$!

sleep 1

echo 'Leave this terminal running until verification is complete.'
echo 'Stop with Ctrl+C after the request has been proven.'
echo

cd "$ROOTDIR"
sudo -n python3 -u -m http.server "$PORT" --bind "$BIND" 2>&1 | tee "$HTTP_LOG"