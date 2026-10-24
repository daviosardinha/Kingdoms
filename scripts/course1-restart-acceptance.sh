#!/usr/bin/env bash
# Explicitly destructive NORTH recovery acceptance; requires deliberate opt-in.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ $# != 3 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ ||
      "$2" != --run || "$3" != --confirm-restore-data-loss ]]; then
  echo 'Usage: bash scripts/course1-restart-acceptance.sh <instance> --run --confirm-restore-data-loss' >&2
  exit 2
fi
INSTANCE="$1"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
MODE="$PROVIDER/.goad-nomad-mode"
[[ -d "$PROVIDER" && -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] ||
  { echo '[BLOCKED] NORTH instance is not ready in exercise mode' >&2; exit 2; }
for cmd in timeout flock sudo vmrun realpath; do
  command -v "$cmd" >/dev/null || { echo "[BLOCKED] Missing $cmd" >&2; exit 2; }
done
exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Phase 03 acceptance lock busy' >&2; exit 2; }
[[ ! -L "$HOME/Kingdoms-evidence" ]] || { echo '[BLOCKED] Evidence symlink' >&2; exit 2; }
mkdir -p -m 700 "$HOME/Kingdoms-evidence"
EVIDENCE="$(mktemp -d "$HOME/Kingdoms-evidence/north-restart-acceptance-XXXXXXXX")"
chmod 700 "$EVIDENCE"
SUMMARY="$EVIDENCE/summary.txt"
echo "instance=$INSTANCE" > "$SUMMARY"
echo "Evidence: $EVIDENCE"
fail() {
  echo "FAIL | $*" | tee -a "$SUMMARY" >&2
  echo 'RESTART_RESTORE_RELIABILITY=NOT_CERTIFIED' | tee -a "$SUMMARY"
  echo '[BLOCKED] No automatic recovery/retry. Inspect logs before proceeding.' >&2
  exit 1
}
step() {
  local name="$1" limit="$2" start="$SECONDS" rc=0
  shift 2
  echo "[RUN] $name"
  timeout --signal=TERM --kill-after=30 "$limit" "$@" >"$EVIDENCE/$name.log" 2>&1 || rc=$?
  (( rc == 0 )) || fail "$name rc=$rc log=$EVIDENCE/$name.log"
  echo "PASS | $name | seconds=$((SECONDS-start))" | tee -a "$SUMMARY"
}
sudo -n -v >/dev/null 2>&1 || { echo '[BLOCKED] Run sudo -v first' >&2; exit 2; }
# Strict online Git/source validation is performed ONCE, before any power or
# snapshot operation. Rechecks later in this same run use this exact SHA plus
# the live owner, so a transient external DNS outage cannot hide AD readiness.
step 00-installed 650 bash scripts/course1-rollout.sh --installed "$PROVIDER"
PINNED_HEAD="$(git rev-parse --verify HEAD)"
[[ "$PINNED_HEAD" =~ ^[0-9a-f]{40}$ ]] || fail 'Could not pin initial verified checkout'
echo "source_pin=$PINNED_HEAD" | tee -a "$SUMMARY"

# Require a single, unambiguous snapshot per guest before any VM power change.
for machine in GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01 GOAD-ROUTER; do
  idfile="$PROVIDER/.vagrant/machines/$machine/vmware_desktop/id"
  [[ -f "$idfile" && ! -L "$idfile" ]] || fail "$machine has no VMX identity"
  vmx="$(cat "$idfile")"
  [[ "$vmx" == /* && -f "$vmx" ]] || fail "$machine VMX missing"
  timeout 30 vmrun -T ws listSnapshots "$(realpath "$vmx")" >"$EVIDENCE/snapshots-$machine.log" 2>&1 ||
    fail "$machine snapshot query failed"
  count="$(sed -nE 's/^[[:space:]]*[Tt]otal snapshots:[[:space:]]*([0-9]+).*$/\1/p' "$EVIDENCE/snapshots-$machine.log" | head -n1)"
  [[ "$count" == 1 ]] || fail "$machine expected one snapshot, got $count"
done

readiness() {
  local name="$1" machine
  [[ "$(tr -d '[:space:]' < "$MODE")" == exercise ]] || fail "$name mode not exercise"
  for machine in GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01; do
    vmx="$(cat "$PROVIDER/.vagrant/machines/$machine/vmware_desktop/id")"
    grep -Eqi '^[[:space:]]*ethernet0\.startConnected[[:space:]]*=[[:space:]]*"FALSE"[[:space:]]*$' "$vmx" ||
      fail "$name $machine NAT persists as connected"
  done
  step "$name-readiness" 900 bash scripts/course1-phase03-preflight.sh "$INSTANCE" --pinned-head "$PINNED_HEAD"
  grep -Fq 'PHASE03_READONLY_ACCEPTANCE=PASS' "$EVIDENCE/$name-readiness.log" ||
    fail "$name readiness failed"
}
# Do not wrap native start/stop/reset in GNU timeout. It sends signals to
# a process group and may kill vmware-vmx guests spawned by Vagrant. The native
# Kingdoms provider owns its bounded VMware/Vagrant calls and PID-safe cleanup.
native() {
  local task="$1" name="$2" started="$SECONDS" rc=0
  sudo -n -v >/dev/null 2>&1 || fail "$name sudo credentials expired"
  echo "[RUN] $name"
  bash ./goad.sh -t "$task" -l NORTH -p vmware -i "$INSTANCE" \
    >"$EVIDENCE/$name.log" 2>&1 || rc=$?
  if (( rc != 0 )); then
    fail "$name rc=$rc log=$EVIDENCE/$name.log"
  fi
  echo "PASS | $name | seconds=$((SECONDS-started))" | tee -a "$SUMMARY"
}
readiness initial
for cycle in 1 2; do
  native stop "cold-$cycle-stop"
  native start "cold-$cycle-start"
  readiness "cold-$cycle"
done
# do_reset ALREADY performs stop -> snapshot pop --no-delete -> start.
native reset snapshot-restore
readiness restored
echo 'NORTH_REPEATED_COLD_START=PASS' | tee -a "$SUMMARY"
echo 'NORTH_SNAPSHOT_RESTORE=PASS' | tee -a "$SUMMARY"
echo 'RESTART_RESTORE_RELIABILITY=PASS' | tee -a "$SUMMARY"
echo "Evidence: $EVIDENCE"
