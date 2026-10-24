#!/usr/bin/env bash
# NORTH Phase 03 RBCD: capture a private baseline only; never start an attack.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# != 3 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ || "$2" != --capture || "$3" != --confirm ]]; then
  echo 'Usage: bash scripts/course1-phase03-rbcd-baseline.sh <NORTH-instance-id> --capture --confirm' >&2
  exit 2
fi
INSTANCE="$1"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
DATA_INVENTORY="$ROOT/ad/NORTH/data/inventory"
INSTANCE_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
MODE="$PROVIDER/.goad-nomad-mode"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"

for path in "$PROVIDER" "$DATA_INVENTORY" "$INSTANCE_INVENTORY" "$ROOT/ad/NORTH/data/config.json"; do
  [[ -e "$path" ]] || { echo "[BLOCKED] Missing NORTH input: $path" >&2; exit 2; }
done
[[ -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] || {
  echo '[BLOCKED] NORTH must be in recorded exercise mode' >&2; exit 2;
}
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] Ansible runtime unavailable' >&2; exit 2; }
command -v flock >/dev/null || { echo '[BLOCKED] flock unavailable' >&2; exit 2; }

# Serialize this checkpoint against the existing HTTP->LDAPS active runner.
exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Phase 03 acceptance already running' >&2; exit 2; }

EVIDENCE_ROOT="$HOME/Kingdoms-evidence"
[[ ! -L "$EVIDENCE_ROOT" ]] || { echo '[BLOCKED] Evidence root is a symlink' >&2; exit 2; }
mkdir -p -m 700 "$EVIDENCE_ROOT"
EVIDENCE="$(mktemp -d "$EVIDENCE_ROOT/phase03-rbcd-baseline-$(date +%Y%m%d-%H%M%S)-XXXXXXXX")"
chmod 700 "$EVIDENCE"
printf '[RUN] NORTH installed ownership and Phase 03 read-only prerequisites\n'
if ! timeout --signal=TERM 540 bash scripts/course1-phase03-preflight.sh "$INSTANCE" >"$EVIDENCE/preflight.log" 2>&1 ||
   ! grep -Fq 'PHASE03_READONLY_ACCEPTANCE=PASS' "$EVIDENCE/preflight.log"; then
  echo "[BLOCKED] Read-only prerequisite failure. Evidence: $EVIDENCE" >&2
  exit 1
fi

export ROOT
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export KINGDOMS_PHASE03_DATA_INVENTORY="$DATA_INVENTORY"
export KINGDOMS_PHASE03_PROVIDER_INVENTORY="$INSTANCE_INVENTORY"
export BASELINE="$EVIDENCE/rbcd-baseline.json"
export KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"

# Check the exact target state immediately before capturing the baseline.
if ! timeout --signal=TERM 150 "$ANSIBLE" -i "$DATA_INVENTORY" -i "$INSTANCE_INVENTORY" \
  ansible/phase03-rbcd-preflight.yml >"$EVIDENCE/rbcd-preflight.log" 2>&1; then
  echo "[BLOCKED] RBCD preflight failed. Evidence: $EVIDENCE" >&2
  exit 1
fi
for marker in 'PHASE03_RBCD_EXISTING=False' 'PHASE03_RBCD_CANDIDATE_EXISTS=False' 'PHASE03_RBCD_SELF_CAN_WRITE=True'; do
  grep -Fq "$marker" "$EVIDENCE/rbcd-preflight.log" || {
    echo "[BLOCKED] RBCD state is not clean ($marker). Evidence: $EVIDENCE" >&2
    exit 1
  }
done

[[ ! -e "$BASELINE" && ! -L "$BASELINE" ]] || {
  echo '[BLOCKED] Selected baseline already exists' >&2; exit 2;
}
if ! timeout --signal=TERM 150 bash scripts/phase03/capture-rbcd-baseline.sh >"$EVIDENCE/capture.log" 2>&1; then
  echo "[FAIL] Baseline capture failed. Evidence: $EVIDENCE" >&2
  exit 1
fi

python3 - "$BASELINE" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.is_symlink():
    raise SystemExit("FAIL: baseline is a symlink")
metadata = path.stat()
if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.getuid():
    raise SystemExit("FAIL: baseline file ownership, mode, or type invalid")
with path.open(encoding="utf-8") as stream:
    state = json.load(stream)
if state.get("Target") != "WS01$" or state.get("CandidateName") != "PHASE03RBCD$":
    raise SystemExit("FAIL: wrong RBCD identities")
if state.get("RBCDPresent") is not False or state.get("CandidateExisted") is not False:
    raise SystemExit("FAIL: non-neutral baseline")
if not state.get("TargetDN", "").lower().endswith("dc=north,dc=sevenkingdoms,dc=local"):
    raise SystemExit("FAIL: target outside NORTH domain")
print("PHASE03_RBCD_BASELINE_NEUTRAL=True")
PY

sha256sum "$BASELINE" >"$EVIDENCE/rbcd-baseline.sha256"
chmod 600 "$EVIDENCE/rbcd-baseline.sha256"
echo 'PHASE03_RBCD_BASELINE_CAPTURE=PASS'
echo 'PHASE03_RBCD_ACTIVE_ACCEPTANCE=NOT_TESTED'
echo "Baseline: $BASELINE"
echo "Evidence: $EVIDENCE"
