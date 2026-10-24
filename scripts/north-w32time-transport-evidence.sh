#!/usr/bin/env bash
# NORTH CASTELBLACK time failure: passive host-side NTP packet evidence.
# No resync, VMware power action, adapter change, route change, or AD write.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
if [[ $# -ne 1 || ! "$1" =~ ^[a-f0-9]{6}-north-vmware$ ]]; then
  echo "Usage: bash scripts/north-w32time-transport-evidence.sh <NORTH-instance-id>" >&2
  exit 2
fi
INSTANCE="$1"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
[[ -d "$PROVIDER" && ! -L "$PROVIDER" &&
   "$(cat "$PROVIDER/.goad-nomad-mode" 2>/dev/null)" == "exercise" ]] || {
  echo '[BLOCKED] Missing canonical NORTH exercise-mode provider' >&2
  exit 2
}
for tool in sudo tcpdump timeout vmrun ip date; do
  command -v "$tool" >/dev/null || {
    echo "[BLOCKED] Missing dependency: $tool" >&2; exit 2;
  }
done
[[ ! -L "$HOME/Kingdoms-evidence" ]] || {
  echo "[BLOCKED] Evidence base is a symlink" >&2; exit 2;
}
sudo -v
sudo -n bash "$ROOT/scripts/setup-vmware-networks.sh" --north verify \
  --provider-dir "$PROVIDER" >/dev/null || {
  echo '[BLOCKED] NORTH vmnet ownership verification failed' >&2; exit 2;
}
ip -4 -o addr show dev vmnet10 | grep -Fq '10.4.10.254/24' || {
  echo '[BLOCKED] vmnet10 host interface is not canonical' >&2; exit 2;
}
mkdir -p -m 700 "$HOME/Kingdoms-evidence"
EVIDENCE="$(mktemp -d "$HOME/Kingdoms-evidence/north-time-transport-XXXXXXXX")"
chmod 700 "$EVIDENCE"
echo "[EVIDENCE] $EVIDENCE"
printf 'Instance: %s\nCapture duration: 180s max\n' "$INSTANCE" > "$EVIDENCE/manifest.txt"

# Record the live state before observing; do not assert that all guests are up.
GOAD_LAB_PROFILE=NORTH GOAD_PROVIDER_DIR="$PROVIDER" \
  bash scripts/lab-mode.sh status > "$EVIDENCE/00-network.txt" 2>&1 || {
    echo '[BLOCKED] Could not capture current mode/routing state' >&2; exit 1;
  }
vmrun -T ws list > "$EVIDENCE/01-guests.txt" 2>&1 || {
  echo '[BLOCKED] Cannot record running VMware guests' >&2; exit 1;
}

# The BPF only includes CASTELBLACK <-> WINTERFELL UDP/123. Capture
# naturally-occurring NtpClient polls; do not trigger an artificial resync
# or run stripchart during this capture (it uses a different UDP source port).
BPF='udp port 123 and host 10.4.10.22 and host 10.4.10.11'
echo '[INFO] Passive capture of CASTELBLACK/WINTERFELL UDP/123 for up to 180 seconds.'
echo '[INFO] Please do not run w32tm, start/reset, or mode transitions during capture.'
rc=0
sudo -n timeout --signal=INT --kill-after=5 180 \
  tcpdump -i vmnet10 -n -s 0 -U -w - "$BPF" \
  > "$EVIDENCE/02-ntp.pcap" 2> "$EVIDENCE/02-capture-stderr.txt" || rc=$?
if (( rc != 0 && rc != 124 && rc != 130 )); then
  echo "[BLOCKED] tcpdump capture failure rc=$rc" >&2
  cat "$EVIDENCE/02-capture-stderr.txt" >&2
  exit 1
fi

tcpdump -nn -tttt -vvv -r "$EVIDENCE/02-ntp.pcap" \
  > "$EVIDENCE/03-ntp-decoded.txt" 2> "$EVIDENCE/03-decode-stderr.txt" || {
  echo '[BLOCKED] Failed to decode packet evidence' >&2
  exit 1
}
packets="$(grep -c ' IP ' "$EVIDENCE/03-ntp-decoded.txt" || true)"
printf 'CAPTURE_EXIT=%s\nDECODED_IP_LINES=%s\n' "$rc" "$packets" | tee -a "$EVIDENCE/manifest.txt"
echo '[PASS] NORTH_NTP_PASSIVE_CAPTURE_COMPLETED'
echo '[NOTE] Capture completion does not imply NTP synchronization success.'
echo "[EVIDENCE] $EVIDENCE"
