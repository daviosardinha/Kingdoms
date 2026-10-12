#!/usr/bin/env bash
# Read-only NORTH snapshot and lifecycle inventory. Never changes guest state.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ $# -ne 1 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ ]]; then
  echo 'Usage: bash scripts/course1-restart-preflight.sh <NORTH-instance-id>' >&2
  exit 2
fi
INSTANCE="$1"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
MODE="$PROVIDER/.goad-nomad-mode"
[[ -d "$PROVIDER" && -f "$MODE" ]] || {
  echo '[BLOCKED] Installed NORTH instance missing' >&2; exit 2
}
[[ "$(tr -d '[:space:]' < "$MODE")" == exercise ]] || {
  echo '[BLOCKED] NORTH is not in recorded exercise mode' >&2; exit 2
}
for tool in vmrun flock timeout sudo realpath; do
  command -v "$tool" >/dev/null || { echo "[BLOCKED] $tool unavailable" >&2; exit 2; }
done
exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Another Phase 03 acceptance is active' >&2; exit 2; }

[[ ! -L "$HOME/Kingdoms-evidence" ]] || {
  echo '[BLOCKED] Evidence directory is symlinked' >&2; exit 2
}
mkdir -p -m 700 "$HOME/Kingdoms-evidence"
EVIDENCE="$(mktemp -d "$HOME/Kingdoms-evidence/north-restart-preflight-XXXXXXXX")"
chmod 700 "$EVIDENCE"
SUMMARY="$EVIDENCE/summary.txt"
echo "instance=$INSTANCE" >"$SUMMARY"
echo "Evidence: $EVIDENCE"
fail() {
  echo "[FAIL] $*" | tee -a "$SUMMARY" >&2
  echo 'NORTH_RESTART_PREFLIGHT=FAIL' | tee -a "$SUMMARY"
  exit 1
}
sudo -n -v >/dev/null 2>&1 || {
  echo '[BLOCKED] Run sudo -v first. No guest action attempted.' >&2; exit 2
}
echo '[RUN] Installed NORTH source and ownership gate'
timeout 650 bash scripts/course1-rollout.sh --installed "$PROVIDER" \
  >"$EVIDENCE/installed.log" 2>&1 || fail 'Source/owner gate failed'
echo 'PASS | source + installed network owner' | tee -a "$SUMMARY"

for machine in GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01 GOAD-ROUTER; do
  idfile="$PROVIDER/.vagrant/machines/$machine/vmware_desktop/id"
  [[ -f "$idfile" && ! -L "$idfile" ]] || fail "$machine VMX id missing"
  vmx="$(cat "$idfile")"
  [[ "$vmx" == /* && -f "$vmx" ]] || fail "$machine VMX file missing"
  resolved="$(realpath "$vmx")"
  printf '%s: %s\n' "$machine" "$resolved" >>"$EVIDENCE/vmx-inventory.txt"

  timeout 30 vmrun -T ws listSnapshots "$resolved" \
    >"$EVIDENCE/snapshots-$machine.log" 2>&1 ||
      fail "$machine snapshot inventory failed"
  count="$(sed -nE 's/^[[:space:]]*[Tt]otal snapshots:[[:space:]]*([0-9]+).*$/\1/p' \
    "$EVIDENCE/snapshots-$machine.log" | head -n1)"
  [[ -n "$count" && "$count" =~ ^[0-9]+$ ]] || fail "$machine snapshot count unknown"
  (( count >= 1 )) || fail "$machine missing snapshot"
  echo "PASS | $machine | snapshots=$count" | tee -a "$SUMMARY"

  if [[ "$machine" != GOAD-ROUTER ]]; then
    grep -Eqi '^[[:space:]]*ethernet0\.startConnected[[:space:]]*=[[:space:]]*"FALSE"[[:space:]]*$' "$resolved" ||
      fail "$machine persistent exercise NAT is not disabled"
  fi
done

echo '[RUN] Recorded router and exercise routing status'
GOAD_LAB_PROFILE=NORTH GOAD_PROVIDER_DIR="$PROVIDER" \
  timeout 75 bash scripts/lab-mode.sh status >"$EVIDENCE/mode.log" 2>&1 ||
    fail 'Live exercise routing status unavailable'
echo 'NORTH_RESTART_PREFLIGHT=PASS' | tee -a "$SUMMARY"
echo 'NORTH_REPEATED_COLD_START=NOT_TESTED' | tee -a "$SUMMARY"
echo 'NORTH_SNAPSHOT_RESTORE=NOT_TESTED' | tee -a "$SUMMARY"
echo 'No power, snapshots, router or NIC state changed.'
echo "Evidence: $EVIDENCE"
