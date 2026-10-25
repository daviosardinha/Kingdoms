#!/usr/bin/env bash
# NORTH release qualification: 2 cold starts, snapshot, reset, exercise proof.
# Snapshot restoration discards guest changes made after its baseline.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
if [[ $# -ne 3 || ! "$1" =~ ^[a-f0-9]{6}-north-vmware$ ||
      ( "$2" != "--run" && "$2" != "--snapshot-only" ) ||
      "$3" != "--confirm-restore-data-loss" ]]; then
  echo "Usage: bash scripts/north-lifecycle-acceptance.sh <NORTH-ID> {--run|--snapshot-only} --confirm-restore-data-loss" >&2
  exit 2
fi
INSTANCE="$1"
SNAPSHOT_ONLY=false
if [[ "$2" == "--snapshot-only" ]]; then
  SNAPSHOT_ONLY=true
  [[ "$INSTANCE" == "8aafc9-north-vmware" ]] || {
    echo "[BLOCKED] Snapshot-only recovery qualification is scoped to the validated 8aafc9 NORTH instance" >&2; exit 2;
  }
fi
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
MODE="$PROVIDER/.goad-nomad-mode"
[[ -d "$PROVIDER" && ! -L "$PROVIDER" && -f "$MODE" && ! -L "$MODE" &&
   "$(cat "$MODE")" == exercise ]] || {
  echo "[BLOCKED] NORTH instance must be recorded in exercise mode" >&2; exit 2;
}
for tool in flock sudo vmrun git python3; do
  command -v "$tool" >/dev/null || { echo "[BLOCKED] Missing $tool" >&2; exit 2; }
done
exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo "[BLOCKED] Another NORTH acceptance is active" >&2; exit 2; }
[[ ! -L "$HOME/Kingdoms-evidence" ]] || {
  echo "[BLOCKED] Evidence directory symlink" >&2; exit 2;
}
mkdir -p -m 700 "$HOME/Kingdoms-evidence"
EVIDENCE="$(mktemp -d "$HOME/Kingdoms-evidence/north-lifecycle-XXXXXXXX")"
chmod 700 "$EVIDENCE"
SUMMARY="$EVIDENCE/summary.txt"
printf 'instance=%s\nsource_sha=%s\nmode=%s\n' "$INSTANCE" "$(git rev-parse HEAD)" "$2" > "$SUMMARY"
echo "[EVIDENCE] $EVIDENCE"

fail() {
  echo "FAIL | $*" | tee -a "$SUMMARY" >&2
  echo 'RESTART_RESTORE_RELIABILITY=NOT_CERTIFIED' | tee -a "$SUMMARY"
  echo "[BLOCKED] Do not retry reset or start before investigating the recorded VM state." >&2
  echo "[EVIDENCE] $EVIDENCE" >&2
  exit 1
}
stage() {
  local label="$1" started="$SECONDS" rc=0
  shift
  echo "[RUN] $label"
  "$@" > "$EVIDENCE/$label.log" 2>&1 || rc=$?
  if (( rc != 0 )); then
    tail -n 35 "$EVIDENCE/$label.log" >&2 || true
    fail "$label exited $rc: $EVIDENCE/$label.log"
  fi
  printf 'PASS | %s | seconds=%d\n' "$label" "$((SECONDS-started))" | tee -a "$SUMMARY"
}
native() {
  sudo -n -v >/dev/null 2>&1 || fail "sudo authorization expired before $2"
  # Do not wrap VMware/Vagrant lifecycle commands with GNU timeout.
  stage "$2" bash ./goad.sh -t "$1" -l NORTH -p vmware -i "$INSTANCE"
}
validate() {
  native validate "$1"
  grep -Fq '[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS' "$EVIDENCE/$1.log" ||
    fail "Authenticated NORTH acceptance marker missing after $1"
}
stopped() {
  local running
  running="$(vmrun -T ws list)" || fail "Cannot inspect VMware after stop"
  [[ "$running" == 'Total running VMs: 0' ]] ||
    fail "VMware guests remain after NORTH stop: $running"
  [[ "$(cat "$MODE")" == exercise ]] || fail "Recorded exercise mode changed"
}
snapshots() {
  "$HOME/.goad/.venv/bin/python" - "$PROVIDER" "$1" <<'PY'
import json, re, subprocess, sys
from pathlib import Path
provider, dest = Path(sys.argv[1]), Path(sys.argv[2])
machines = ("GOAD-ROUTER","GOAD-DC01","GOAD-DC02","GOAD-SRV02","GOAD-WS01")
out = {}
for machine in machines:
    vm_dir = provider / ".vagrant" / "machines" / machine / "vmware_desktop"
    ident = vm_dir / "id"
    if not ident.is_file() or ident.is_symlink():
        raise SystemExit("[BLOCKED] Registered VMX ID missing: " + machine)
    vmx = Path(ident.read_text().strip())
    if (not vmx.is_absolute() or not vmx.is_file() or vmx.is_symlink()
            or not vmx.resolve().is_relative_to(vm_dir.resolve())):
        raise SystemExit("[BLOCKED] Foreign VMX: " + machine)
    result = subprocess.run(["vmrun","-T","ws","listSnapshots",str(vmx)],
                            capture_output=True,text=True,timeout=30)
    if result.returncode:
        raise SystemExit("[BLOCKED] Snapshot list failed: " + machine)
    rows = [x.strip() for x in result.stdout.splitlines()]
    if not rows or not re.fullmatch(r"Total snapshots: \d+",rows[0]):
        raise SystemExit("[BLOCKED] Unexpected VMware snapshot output: " + machine)
    pushes = [x for x in rows[1:] if re.fullmatch(r"push_\d{10,}_\d+",x)]
    if len(pushes) != len(set(pushes)):
        raise SystemExit("[BLOCKED] Duplicate snapshot names: " + machine)
    out[machine] = pushes
dest.write_text(json.dumps(out, indent=2, sort_keys=True)+"\n")
print("[PASS] NORTH_SNAPSHOT_INVENTORY_CAPTURED")
PY
}

echo "===== SOURCE AND INSTALLED OWNER ====="
stage 00-source bash scripts/verify-test-source.sh
sudo -v || fail "sudo authentication failed"
stage 01-owner sudo -n bash scripts/setup-vmware-networks.sh --north verify --provider-dir "$PROVIDER"
validate 02-initial-health

if [[ "$SNAPSHOT_ONLY" != true ]]; then
  echo "===== TWO COLD-START CYCLES ====="
  for cycle in 1 2; do
  native stop "cold-$cycle-stop"
  stopped
  echo "PASS | cold-$cycle-offline" | tee -a "$SUMMARY"
  native start "cold-$cycle-start"
  validate "cold-$cycle-health"
  done
  echo 'NORTH_REPEATED_COLD_START=PASS' | tee -a "$SUMMARY"
else
  echo "===== SNAPSHOT-ONLY: PREVIOUS TWO COLD-STARTS ALREADY CERTIFIED ====="
  echo 'NORTH_REPEATED_COLD_START=NOT_RERUN' | tee -a "$SUMMARY"
fi

echo "===== CREATE EXERCISE-MODE SNAPSHOT ====="
snapshots "$EVIDENCE/snapshots-before.json" || fail "Cannot inventory original snapshots"
native snapshot 03-snapshot-create
validate 04-post-snapshot-health
snapshots "$EVIDENCE/snapshots-after.json" || fail "Cannot inventory new snapshots"
"$HOME/.goad/.venv/bin/python" - "$EVIDENCE/snapshots-before.json" "$EVIDENCE/snapshots-after.json" <<'PY' ||
  fail "Not all five VMs received exactly one new snapshot generation"
import json,sys
from pathlib import Path
before=json.loads(Path(sys.argv[1]).read_text())
after=json.loads(Path(sys.argv[2]).read_text())
if before.keys()!=after.keys() or len(after)!=5:
    raise SystemExit("[BLOCKED] Snapshot roster changed")
for name in after:
    old,new=before[name],after[name]
    if len(new)!=len(old)+1 or not set(old).issubset(set(new)):
        raise SystemExit("[BLOCKED] Snapshot generation missing/ambiguous: "+name)
    print("[PASS] SNAPSHOT_GENERATION="+name)
PY
echo 'NORTH_SNAPSHOT_CREATE=PASS' | tee -a "$SUMMARY"

echo "===== RESTORE SNAPSHOT AND VERIFY ====="
native reset 05-snapshot-restore
validate 06-post-restore-health
echo 'NORTH_SNAPSHOT_RESTORE=PASS' | tee -a "$SUMMARY"

[[ "$(cat "$MODE")" == exercise ]] || fail "Exercise mode not preserved"
stage 07-owner-final sudo -n bash scripts/setup-vmware-networks.sh --north verify --provider-dir "$PROVIDER"
if [[ "$SNAPSHOT_ONLY" == true ]]; then
  echo 'NORTH_SNAPSHOT_ACCEPTANCE=PASS' | tee -a "$SUMMARY"
  echo '[PASS] NORTH_SNAPSHOT_ONLY_ACCEPTANCE=PASS'
else
  echo 'RESTART_RESTORE_RELIABILITY=PASS' | tee -a "$SUMMARY"
  echo '[PASS] NORTH_LIFECYCLE_RELIABILITY=PASS'
fi
echo "[EVIDENCE] $EVIDENCE"
