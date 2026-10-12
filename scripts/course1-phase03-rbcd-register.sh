#!/usr/bin/env bash
# NORTH RBCD Stage 1: evidence registration only, NO AD mutation.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# != 4 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ || "$3" != --register || "$4" != --confirm ]]; then
  echo 'Usage: bash scripts/course1-phase03-rbcd-register.sh <NORTH-instance-id> <baseline.json> --register --confirm' >&2
  exit 2
fi
INSTANCE="$1"
BASELINE="$2"
EVIDENCE="$(dirname -- "$BASELINE")"
RECEIPT="$EVIDENCE/rbcd-ownership.json"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
MODE="$PROVIDER/.goad-nomad-mode"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"

[[ "$BASELINE" == "$HOME"/Kingdoms-evidence/phase03-rbcd-baseline-*/rbcd-baseline.json ]] ||
  { echo '[BLOCKED] Exact NORTH baseline path required' >&2; exit 2; }
[[ -d "$PROVIDER" && -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] ||
  { echo '[BLOCKED] Exact NORTH instance must be in exercise mode' >&2; exit 2; }
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] Ansible unavailable' >&2; exit 2; }
[[ ! -e "$RECEIPT" && ! -L "$RECEIPT" ]] ||
  { echo '[BLOCKED] Ownership receipt already exists; no overwrite' >&2; exit 2; }

exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Another Phase 03 action is running' >&2; exit 2; }

python3 - "$BASELINE" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
proof = path.with_name("rbcd-baseline.sha256")
for item, mode in ((path.parent, 0o700), (path, 0o600), (proof, 0o600)):
    info = item.lstat()
    correct = stat.S_ISDIR if item == path.parent else stat.S_ISREG
    if not correct(info.st_mode) or stat.S_IMODE(info.st_mode) != mode or info.st_uid != os.getuid():
        raise SystemExit("BLOCKED: invalid evidence mode, owner, or type")
data = json.loads(path.read_text(encoding="utf-8"))
if (data.get("Target"), data.get("CandidateName"), data.get("RBCDPresent"), data.get("CandidateExisted")) != (
    "WS01$", "PHASE03RBCD$", False, False
):
    raise SystemExit("BLOCKED: baseline must be clean for NORTH RBCD")
if not data.get("CapturedAtUtc"):
    raise SystemExit("BLOCKED: baseline predates the Stage 1 provenance contract; capture a fresh one")
PY
sha256sum -c --status "$EVIDENCE/rbcd-baseline.sha256" ||
  { echo '[BLOCKED] Baseline hash mismatch' >&2; exit 2; }

# Required source/VMnet owner preflight. Do not reuse stale service state.
bash scripts/course1-rollout.sh --installed "$PROVIDER" >/dev/null

export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"
export KINGDOMS_PHASE03_RBCD_OWNERSHIP="$RECEIPT"

"$ANSIBLE" -i "$ROOT/ad/NORTH/data/inventory" \
  -i "$ROOT/workspace/$INSTANCE/inventory" \
  ansible/phase03-rbcd-record-ownership-north.yml

[[ -f "$RECEIPT" && ! -L "$RECEIPT" ]] ||
  { echo '[FAIL] Missing Stage 1 ownership receipt' >&2; exit 1; }
sha256sum "$RECEIPT" >"$EVIDENCE/rbcd-ownership.sha256"
chmod 600 "$EVIDENCE/rbcd-ownership.sha256"
echo 'PHASE03_RBCD_STAGE1_OWNERSHIP_CAPTURE=PASS'
echo 'PHASE03_RBCD_ACTIVE_ACCEPTANCE=NOT_TESTED'
echo "Receipt: $RECEIPT"
