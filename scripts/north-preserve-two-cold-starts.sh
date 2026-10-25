#!/usr/bin/env bash
# Preserve NORTH evidence and test two cold starts; no snapshot/reset.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$BASH_SOURCE")/.." && pwd -P)"
cd "$ROOT"
ID="8aafc9-north-vmware"
if [[ $# -ne 3 || "$1" != "$ID" || "$2" != "--run" || "$3" != "--confirm-two-cold-starts" ]]; then
  echo "Usage: bash scripts/north-preserve-two-cold-starts.sh $ID --run --confirm-two-cold-starts" >&2
  exit 2
fi
INST="$ROOT/workspace/$ID"
PROVIDER="$INST/provider"
MODE="$PROVIDER/.goad-nomad-mode"
[[ -d "$PROVIDER" && ! -L "$PROVIDER" && -f "$MODE" && ! -L "$MODE" &&
   "$(cat "$MODE")" == exercise && "$(git branch --show-current)" == main ]] || {
  echo "[BLOCKED] Expected installed NORTH on clean main and exercise mode" >&2
  exit 2
}
[[ ! -L "$HOME/Kingdoms-evidence" ]] || exit 2
mkdir -p -m 700 "$HOME/Kingdoms-evidence"
[[ ! -L "$PROVIDER/.course1-phase03-acceptance.lock" ]] || exit 2
exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo "[BLOCKED] Another NORTH acceptance is active" >&2; exit 2; }
EVIDENCE="$(mktemp -d "$HOME/Kingdoms-evidence/north-two-cold-starts-XXXXXXXX")"
chmod 700 "$EVIDENCE"
SUMMARY="$EVIDENCE/summary.txt"
printf 'id=%s\ncommit=%s\nNORTH_REPEATED_COLD_START=NOT_CERTIFIED\n' "$ID" "$(git rev-parse HEAD)" > "$SUMMARY"
echo "[EVIDENCE] $EVIDENCE"

capture() {
  local label="$1"
  {
    date -u
    cat "$MODE" || true
    vmrun -T ws list || true
    for machine in GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01; do
      local reg="$PROVIDER/.vagrant/machines/$machine/vmware_desktop/id"
      if [[ -f "$reg" && ! -L "$reg" ]]; then
        local vmx
        vmx="$(cat "$reg")"
        echo "$machine $vmx"
        grep -Ei '^ethernet0.startConnected' "$vmx" || true
      fi
    done
    ip route show 10.4.20.0/24 || true
  } > "$EVIDENCE/$label.txt" 2>&1
}
done_handler() {
  local rc=$?
  trap - EXIT INT TERM
  if (( rc != 0 )); then
    echo "FAIL | incomplete; do not automatically retry lifecycle" | tee -a "$SUMMARY" >&2
    capture failure-state || true
  fi
  echo "[EVIDENCE] $EVIDENCE"
  exit "$rc"
}
trap done_handler EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
fail() { echo "FAIL | $*" | tee -a "$SUMMARY" >&2; return 1; }
stage() {
  local label="$1" rc=0
  shift
  echo "[RUN] $label"
  "$@" > "$EVIDENCE/$label.log" 2>&1 || rc=$?
  if (( rc != 0 )); then
    tail -n 35 "$EVIDENCE/$label.log" >&2 || true
    fail "$label failed rc=$rc"
    return 1
  fi
  echo "PASS | $label" | tee -a "$SUMMARY"
}
native() {
  sudo -n -v || { fail "sudo expired"; return 1; }
  stage "$2" bash ./goad.sh -t "$1" -l NORTH -p vmware -i "$ID"
}
validate() {
  native validate "$1"
  grep -Fq '[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS' "$EVIDENCE/$1.log" ||
    { fail "runtime acceptance missing after $1"; return 1; }
  grep -Fq 'instance status is installed' "$EVIDENCE/$1.log" ||
    { fail "installed status missing after $1"; return 1; }
}
preserve() {
  python3 - "$INST" "$EVIDENCE" <<'PY'
from pathlib import Path
import json, shutil, sys
inst, dst = map(Path, sys.argv[1:])
meta = inst / "instance.json"
record = json.loads(meta.read_text())
assert (record.get("id"), record.get("lab"), record.get("provider"), record.get("status")) == (
    "8aafc9-north-vmware", "NORTH", "vmware", "installed"
)
shutil.copy2(meta, dst / "instance-before.json")
shutil.copy2(inst / "provider/.goad-nomad-mode", dst / "mode-before.txt")
for name in ("inventory",):
    p = inst / name
    if p.is_file() and not p.is_symlink():
        shutil.copy2(p, dst / name)
receipts = inst / "install-timings"
if receipts.is_dir() and not receipts.is_symlink():
    out = dst / "install-timings"
    out.mkdir(mode=0o700)
    for p in receipts.glob("*.json"):
        assert not p.is_symlink()
        shutil.copy2(p, out / p.name)
log = Path.home() / "north-recovered-validation-20261025-120457.log"
if log.is_file() and not log.is_symlink():
    shutil.copy2(log, dst / log.name)
print("[PASS] NORTH_EVIDENCE_PRESERVED")
PY
  echo 'PASS | evidence archived; no VMDK or snapshot copied' | tee -a "$SUMMARY"
}
all_stopped() {
  local running
  running="$(vmrun -T ws list)" || return 1
  for machine in GOAD-ROUTER GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01; do
    local reg="$PROVIDER/.vagrant/machines/$machine/vmware_desktop/id"
    [[ -f "$reg" && ! -L "$reg" ]] || return 1
    ! printf '%s\n' "$running" | grep -Fxq "$(cat "$reg")" || return 1
  done
  [[ "$(cat "$MODE")" == exercise ]]
}
stage 00-source bash scripts/verify-test-source.sh
sudo -v
stage 01-owner sudo -n bash scripts/setup-vmware-networks.sh --north verify --provider-dir "$PROVIDER"
validate 02-baseline-health
preserve
capture 03-before
for cycle in 1 2; do
  native stop "cold-$cycle-stop"
  all_stopped || { fail "cold-$cycle did not stop five owned VMs"; exit 1; }
  capture "cold-$cycle-stopped"
  native start "cold-$cycle-start"
  validate "cold-$cycle-health"
  capture "cold-$cycle-validated"
done
stage 04-owner-final sudo -n bash scripts/setup-vmware-networks.sh --north verify --provider-dir "$PROVIDER"
echo 'NORTH_REPEATED_COLD_START=PASS' | tee -a "$SUMMARY"
echo 'NORTH_SNAPSHOT_RESTORE=NOT_TESTED' | tee -a "$SUMMARY"
echo '[PASS] NORTH_TWO_COLD_STARTS=PASS'
