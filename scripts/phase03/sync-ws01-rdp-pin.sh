#!/usr/bin/env bash
# Refresh the local WS01 RDP SHA-256 pin only when management-side and
# network-side certificate observations agree.
set -euo pipefail
umask 077

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
EXPECTED_FQDN="${WS01_RDP_FQDN:-ws01.north.sevenkingdoms.local}"
EXPECTED_IP="${WS01_RDP_IP:-10.4.10.31}"
CERT_FILE="${KINGDOMS_WS01_RDP_CERT_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kingdoms/ws01-rdp.sha256}"
CERT_DIR="$(dirname "$CERT_FILE")"
TMP="$CERT_FILE.tmp.$$"

cd "$ROOT"

cleanup() {
  rm -f -- "$TMP"
}
trap cleanup EXIT INT TERM

echo '===== WS01 RDP CERTIFICATE CROSS-CHECK ====='

management_output="$(bash scripts/phase03/read-ws01-rdp-cert.sh)"
printf '%s\n' "$management_output"

management_sha="$(
  printf '%s\n' "$management_output" |
    sed -n 's/.*RDP_SHA256=\([0-9A-Fa-f]\{64\}\).*/\1/p' |
    tail -n1 |
    tr '[:upper:]' '[:lower:]'
)"

[[ "$management_sha" =~ ^[0-9a-f]{64}$ ]] || {
  echo 'FAIL: could not extract WS01 management-side RDP SHA-256 fingerprint' >&2
  exit 1
}

printf '%s\n' "$management_output" | grep -Eqi "SUBJECT=.*CN[ =]+${EXPECTED_FQDN//./\.}" || {
  echo "FAIL: WS01 RDP certificate subject does not contain expected name $EXPECTED_FQDN" >&2
  exit 1
}

network_output="$(python3 scripts/phase03/probe-ws01-rdp-cert.py --host "$EXPECTED_IP")"
printf '%s\n' "$network_output"

network_sha="$(
  printf '%s\n' "$network_output" |
    sed -n 's/^RDP_SHA256=\([0-9A-Fa-f]\{64\}\)$/\1/p' |
    tail -n1 |
    tr '[:upper:]' '[:lower:]'
)"

[[ "$network_sha" =~ ^[0-9a-f]{64}$ ]] || {
  echo 'FAIL: could not extract WS01 network-side RDP SHA-256 fingerprint' >&2
  exit 1
}

if [[ "$management_sha" != "$network_sha" ]]; then
  echo 'FAIL: WS01 RDP certificate differs between management and network observations' >&2
  echo "MANAGEMENT_SHA256=$management_sha" >&2
  echo "NETWORK_SHA256=$network_sha" >&2
  exit 1
fi

install -d -m 700 "$CERT_DIR"
printf '%s' "$management_sha" >"$TMP"
chmod 600 "$TMP"
mv -f -- "$TMP" "$CERT_FILE"
trap - EXIT INT TERM

echo "WS01_RDP_FQDN=$EXPECTED_FQDN"
echo "WS01_RDP_IP=$EXPECTED_IP"
echo "WS01_RDP_SHA256=$management_sha"
echo "WS01_RDP_PIN_FILE=$CERT_FILE"
echo 'PHASE03_WS01_RDP_PIN_SYNC_COMPLETE=True'
