#!/usr/bin/env bash
# NORTH Phase 03: read-only post-attack inspection when Stage 1 receipt is missing.
# Never generates a backdated ownership receipt or authorizes AD deletion.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

usage() {
  echo 'Usage: bash scripts/course1-phase03-rbcd-postattack-inspect.sh <NORTH-instance-id> <pre-attack-baseline.json> --inspect'
}
if [[ $# != 3 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ || "$3" != --inspect ]]; then
  usage >&2
  exit 2
fi
INSTANCE="$1"
BASELINE="$2"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
DATA_INVENTORY="$ROOT/ad/NORTH/data/inventory"
INSTANCE_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
MODE="$PROVIDER/.goad-nomad-mode"
EVIDENCE_DIR="$(dirname -- "$BASELINE")"
PROOF="$EVIDENCE_DIR/rbcd-baseline.sha256"

[[ "$BASELINE" == "$HOME"/Kingdoms-evidence/phase03-rbcd-baseline-*/rbcd-baseline.json ]] ||
  { echo '[BLOCKED] Explicit current NORTH pre-attack baseline required' >&2; exit 2; }
for p in "$PROVIDER" "$DATA_INVENTORY" "$INSTANCE_INVENTORY" "$BASELINE" "$PROOF"; do
  [[ -e "$p" && ! -L "$p" ]] || { echo "[BLOCKED] Missing or linked input: $p" >&2; exit 2; }
done
[[ -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] ||
  { echo '[BLOCKED] Exact NORTH exercise-mode instance required' >&2; exit 2; }
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] Ansible runtime unavailable' >&2; exit 2; }
command -v flock >/dev/null || { echo '[BLOCKED] flock unavailable' >&2; exit 2; }

exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Another Phase 03 acceptance owns the lock' >&2; exit 2; }

python3 - "$BASELINE" "$PROOF" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

base, proof = map(Path, sys.argv[1:])
for item, expected in ((base.parent, 0o700), (base, 0o600), (proof, 0o600)):
    info = item.lstat()
    kind = stat.S_ISDIR if item == base.parent else stat.S_ISREG
    if not kind(info.st_mode) or stat.S_IMODE(info.st_mode) != expected or info.st_uid != os.getuid():
        raise SystemExit(f"BLOCKED: unsafe pre-attack evidence: {item}")
data = json.loads(base.read_text(encoding="utf-8"))
if not (data.get("Target") == "WS01$"
        and data.get("CandidateName") == "PHASE03RBCD$"
        and data.get("CandidateExisted") is False
        and data.get("RBCDPresent") is False
        and data.get("CapturedAtUtc")
        and data.get("TargetDN", "").lower().endswith("dc=north,dc=sevenkingdoms,dc=local")):
    raise SystemExit("BLOCKED: selected file is not an intact clean NORTH baseline")
PY
sha256sum --check --status "$PROOF" ||
  { echo '[BLOCKED] Baseline checksum does not match' >&2; exit 2; }

echo '[RUN] Validate GitHub source and installed NORTH owner (read-only)'
bash scripts/course1-rollout.sh --installed "$PROVIDER" >/dev/null

[[ ! -L "$HOME/Kingdoms-evidence" ]] ||
  { echo '[BLOCKED] Evidence root is a symlink' >&2; exit 2; }
OUT="$(mktemp -d "$HOME/Kingdoms-evidence/phase03-rbcd-postattack-XXXXXXXX")"
chmod 700 "$OUT"
echo "Instance: $INSTANCE"
echo "Pre-attack baseline: $BASELINE"
echo "Evidence: $OUT"
echo '[RUN] Read exact computer SID/GUID/creation time and inspect WS01 RBCD ACE'

export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"
if ! "$ANSIBLE" -i "$DATA_INVENTORY" -i "$INSTANCE_INVENTORY" \
    ansible/phase03-rbcd-postattack-inspect-north.yml \
    >"$OUT/inspection.log" 2>&1; then
  echo "[FAIL] Inspection could not be completed. Review $OUT/inspection.log" >&2
  exit 1
fi
grep 'PHASE03_RBCD_POST_ATTACK_' "$OUT/inspection.log" || true
if ! grep -Fq 'PHASE03_RBCD_POST_ATTACK_READ_ONLY=True' "$OUT/inspection.log"; then
  echo '[FAIL] Missing read-only inspection marker; no changes permitted' >&2
  exit 1
fi
if ! grep -Fq 'PHASE03_RBCD_POST_ATTACK_CONSISTENT=True' "$OUT/inspection.log"; then
  echo 'PHASE03_RBCD_RECOVERY_REVIEW=INCONSISTENT'
  echo 'No directory writes were performed; STOP and inspect full evidence.'
  exit 3
fi
echo 'PHASE03_RBCD_RECOVERY_INSPECTION=PASS'
echo 'PHASE03_RBCD_RECOVERY_APPROVAL=REQUIRED'
echo 'PHASE03_RBCD_ROLLBACK_ACCEPTANCE=NOT_TESTED'
echo 'This is post-attack corroboration, NOT a Stage 1 ownership receipt.'
