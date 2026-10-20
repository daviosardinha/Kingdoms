#!/usr/bin/env bash
# NORTH RBCD rollback only. Requires Stage 1 receipt and explicit operator approval.
# No listener startup, coercion, privilege escalation or snapshot restore.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  echo 'Usage: bash scripts/course1-phase03-rbcd-rollback.sh <NORTH-instance-id> <baseline.json> --plan'
  echo '       bash scripts/course1-phase03-rbcd-rollback.sh <NORTH-instance-id> <baseline.json> --apply --confirm'
}
if [[ $# -lt 3 || $# -gt 4 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ ]]; then
  usage >&2; exit 2
fi
INSTANCE="$1"
BASELINE="$2"
ACTION="$3"
case "$ACTION" in
  --plan) [[ $# == 3 ]] || { usage >&2; exit 2; } ;;
  --apply) [[ $# == 4 && "$4" == --confirm ]] || { usage >&2; exit 2; } ;;
  *) usage >&2; exit 2 ;;
esac

PROVIDER="$ROOT/workspace/$INSTANCE/provider"
LAB_INVENTORY="$ROOT/ad/NORTH/data/inventory"
INSTANCE_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
MODE="$PROVIDER/.goad-nomad-mode"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
EVIDENCE="$(dirname -- "$BASELINE")"
OWNERSHIP="$EVIDENCE/rbcd-ownership.json"

[[ "$BASELINE" == "$HOME"/Kingdoms-evidence/phase03-rbcd-baseline-*/rbcd-baseline.json ]] ||
  { echo '[BLOCKED] Require an explicit NORTH per-run baseline' >&2; exit 2; }
[[ -d "$PROVIDER" && -f "$INSTANCE_INVENTORY" && -f "$LAB_INVENTORY" ]] ||
  { echo '[BLOCKED] Selected NORTH provider or inventory missing' >&2; exit 2; }
[[ -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] ||
  { echo '[BLOCKED] NORTH instance not in exercise mode' >&2; exit 2; }
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] Expected Ansible runtime unavailable' >&2; exit 2; }
command -v flock >/dev/null || { echo '[BLOCKED] flock missing' >&2; exit 2; }

exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Another Phase 03 operation owns the lock' >&2; exit 2; }

python3 - "$BASELINE" "$OWNERSHIP" <<'PY'
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime
from pathlib import Path

baseline, receipt = map(Path, sys.argv[1:])
parent = baseline.parent
proofs = [baseline.with_name("rbcd-baseline.sha256"), receipt.with_name("rbcd-ownership.sha256")]
for item, mode in ((parent, 0o700), (baseline, 0o600), (receipt, 0o600),
                   (proofs[0], 0o600), (proofs[1], 0o600)):
    info = item.lstat()
    wanted = stat.S_ISDIR if item == parent else stat.S_ISREG
    if not wanted(info.st_mode) or stat.S_IMODE(info.st_mode) != mode or info.st_uid != os.getuid():
        raise SystemExit(f"[BLOCKED] Untrusted RBCD evidence owner/type/mode: {item}")
b = json.loads(baseline.read_text(encoding="utf-8"))
r = json.loads(receipt.read_text(encoding="utf-8"))
if not (b.get("Target") == "WS01$" and b.get("CandidateName") == "PHASE03RBCD$"
        and b.get("RBCDPresent") is False and b.get("CandidateExisted") is False):
    raise SystemExit("[BLOCKED] RBCD baseline is not the original clean NORTH state")
if (r.get("CandidateName") != "PHASE03RBCD$" or r.get("TargetDN") != b.get("TargetDN")
    or r.get("BaselineSHA256") != hashlib.sha256(baseline.read_bytes()).hexdigest()):
    raise SystemExit("[BLOCKED] Stage 1 receipt is not bound to baseline")
if not re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", r.get("CandidateSID", "")):
    raise SystemExit("[BLOCKED] Invalid candidate SID")
if not re.fullmatch(r"[0-9a-fA-F-]{36}", r.get("CandidateGUID", "")):
    raise SystemExit("[BLOCKED] Invalid candidate GUID")
if not r.get("CandidateDN", "").lower().endswith("dc=north,dc=sevenkingdoms,dc=local"):
    raise SystemExit("[BLOCKED] Candidate DN not in NORTH")
datetime.fromisoformat(b["CapturedAtUtc"].replace("Z", "+00:00"))
datetime.fromisoformat(r["CandidateCreatedAtUtc"].replace("Z", "+00:00"))
print("PHASE03_RBCD_ROLLBACK_EVIDENCE_VALID=True")
PY

sha256sum --check --status "$EVIDENCE/rbcd-baseline.sha256" ||
  { echo '[BLOCKED] Baseline checksum mismatch' >&2; exit 2; }
sha256sum --check --status "$EVIDENCE/rbcd-ownership.sha256" ||
  { echo '[BLOCKED] Ownership checksum mismatch' >&2; exit 2; }

echo "Instance: $INSTANCE"
echo "Baseline: $BASELINE"
echo "Stage 1 ownership: $OWNERSHIP"
if [[ "$ACTION" == --plan ]]; then
  echo 'PLAN_ONLY=True'
  echo 'PHASE03_RBCD_ROLLBACK_ACCEPTANCE=NOT_TESTED'
  exit 0
fi

# No automatic shutdown of someone else's listener/process.
if pgrep -af '(^|[ /])mitm6([ ]|$)|(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py)([ ]|$)' >/dev/null; then
  echo '[BLOCKED] Stop any NTLM relay or mitm6 listener before rollback' >&2
  exit 2
fi

# Require strict online source / installed network owner validation before AD changes.
bash scripts/course1-rollout.sh --installed "$PROVIDER" >/dev/null

export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"
export KINGDOMS_PHASE03_RBCD_OWNERSHIP="$OWNERSHIP"

OUT="$(mktemp -d "$HOME/Kingdoms-evidence/phase03-rbcd-rollback-XXXXXXXX")"
chmod 700 "$OUT"
echo "Evidence: $OUT"

if ! "$ANSIBLE" -i "$LAB_INVENTORY" -i "$INSTANCE_INVENTORY" \
  ansible/phase03-rbcd-rollback-north.yml >"$OUT/rollback.log" 2>&1 ||
  ! grep -Fq 'PHASE03_RBCD_ROLLBACK_COMPLETE=True' "$OUT/rollback.log"; then
  echo "[FAIL] Ownership-guarded rollback failed; inspect $OUT/rollback.log" >&2
  echo 'PHASE03_RBCD_ROLLBACK_ACCEPTANCE=FAIL'
  exit 1
fi

# Independent read-only verification. Do not trust the mutation task's own output.
if ! "$ANSIBLE" -i "$LAB_INVENTORY" -i "$INSTANCE_INVENTORY" \
  ansible/phase03-rbcd-verify-neutral.yml >"$OUT/independent-neutral.log" 2>&1 ||
  ! grep -Fq 'PHASE03_RBCD_NEUTRAL_VERIFIED=True' "$OUT/independent-neutral.log"; then
  echo "[FAIL] Independent AD rollback verification failed: $OUT/independent-neutral.log" >&2
  echo 'PHASE03_RBCD_ROLLBACK_ACCEPTANCE=FAIL'
  exit 1
fi

echo 'PHASE03_RBCD_ROLLBACK_ACCEPTANCE=PASS'
echo 'PHASE03_RBCD_NEUTRAL_ACCEPTANCE=PASS'
echo 'PHASE03_RBCD_ACTIVE_ACCEPTANCE=NOT_TESTED'
echo 'NOTE: No existing tickets are invalidated by reverting delegation. Clear owned ticket caches separately.'
echo "Evidence: $OUT"
