#!/usr/bin/env bash
# Course 1 NORTH: plan/verify or exact-fingerprint authorized Shadow rollback.
# Never touches the legacy September 2026 GOAD Shadow baseline.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
usage() {
  echo 'Usage: bash scripts/course1-phase03-shadow-rollback.sh <NORTH-instance> <shadow-baseline.json> --plan'
  echo '       bash scripts/course1-phase03-shadow-rollback.sh <NORTH-instance> <shadow-baseline.json> --verify'
  echo '       bash scripts/course1-phase03-shadow-rollback.sh <NORTH-instance> <shadow-baseline.json> --apply --confirm <64-char-KCL-SHA256>'
}
if [[ $# -lt 3 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ ]]; then
  usage >&2; exit 2
fi
INSTANCE="$1"
BASELINE="$2"
ACTION="$3"
FINGERPRINT=""
case "$ACTION" in
  --plan|--verify) [[ $# == 3 ]] || { usage >&2; exit 2; } ;;
  --apply)
    [[ $# == 5 && "$4" == --confirm && "$5" =~ ^[0-9a-f]{64}$ ]] ||
      { usage >&2; exit 2; }
    FINGERPRINT="$5"
    ;;
  *) usage >&2; exit 2 ;;
esac

PROVIDER="$ROOT/workspace/$INSTANCE/provider"
MODE="$PROVIDER/.goad-nomad-mode"
DATA="$ROOT/ad/NORTH/data/inventory"
INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
EVIDENCE_ROOT="$HOME/Kingdoms-evidence"
BASELINE_DIR="$(dirname -- "$BASELINE")"
PROOF="$BASELINE_DIR/shadow-baseline.sha256"
[[ "$BASELINE" == "$EVIDENCE_ROOT"/phase03-shadow-baseline-*/shadow-baseline.json ]] ||
  { echo '[BLOCKED] Explicit private NORTH Shadow baseline required' >&2; exit 2; }
for item in "$PROVIDER" "$DATA" "$INVENTORY" "$BASELINE" "$PROOF"; do
  [[ -e "$item" && ! -L "$item" ]] || { echo "[BLOCKED] Input missing or linked: $item" >&2; exit 2; }
done
[[ -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] ||
  { echo '[BLOCKED] NORTH is not in exercise mode' >&2; exit 2; }
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] Ansible unavailable' >&2; exit 2; }
command -v flock >/dev/null || { echo '[BLOCKED] flock unavailable' >&2; exit 2; }

exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Another Phase 03 acceptance is running' >&2; exit 2; }
python3 - "$BASELINE" "$PROOF" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

b, p = map(Path, sys.argv[1:])
for item, mode in ((b.parent, 0o700), (b, 0o600), (p, 0o600)):
    info = item.lstat()
    predicate = stat.S_ISDIR if item == b.parent else stat.S_ISREG
    if not predicate(info.st_mode) or stat.S_IMODE(info.st_mode) != mode or info.st_uid != os.getuid():
        raise SystemExit(f'[BLOCKED] Shadow baseline evidence unsafe: {item}')
v = json.loads(b.read_text(encoding='utf-8'))
if (v.get('Version') != 1 or v.get('Target') != 'WS01$'
        or v.get('KCLPresent') is not False or v.get('KCLCount') != 0
        or v.get('KCLValues') != [] or not v.get('TargetSID')
        or not v.get('TargetDN', '').lower().endswith('dc=north,dc=sevenkingdoms,dc=local')):
    raise SystemExit('[BLOCKED] Exact NORTH neutral WS01 baseline required')
PY
sha256sum --check --status "$PROOF" ||
  { echo '[BLOCKED] Shadow baseline SHA256 mismatch' >&2; exit 2; }

# Nothing mutating is permitted while any active relay or poisoning listener remains.
if [[ "$ACTION" == --apply ]] &&
   pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' >/dev/null; then
  echo '[BLOCKED] Stop relay, Responder and mitm6 before rollback' >&2
  exit 2
fi

echo '[RUN] Current NORTH source and installed network ownership'
bash scripts/course1-rollout.sh --installed "$PROVIDER" >/dev/null || {
  echo '[BLOCKED] NORTH installed ownership/source gate failed' >&2
  exit 1
}

[[ ! -L "$EVIDENCE_ROOT" ]] || { echo '[BLOCKED] Evidence root is symlinked' >&2; exit 2; }
OUT="$(mktemp -d "$EVIDENCE_ROOT/phase03-shadow-rollback-XXXXXXXX")"
chmod 700 "$OUT"
echo "Instance: $INSTANCE"
echo "Baseline: $BASELINE"
echo "Evidence: $OUT"

export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export KINGDOMS_PHASE03_SHADOW_BASELINE="$BASELINE"
export KINGDOMS_PHASE03_SHADOW_KCL_FINGERPRINT="$FINGERPRINT"
if [[ "$ACTION" == --verify ]]; then
  echo '[RUN] Independent read-only neutral verification'
  if ! "$ANSIBLE" -i "$DATA" -i "$INVENTORY" \
      ansible/phase03-shadow-verify-neutral-north.yml >"$OUT/independent-neutral.log" 2>&1 ||
      ! grep -Fq 'PHASE03_SHADOW_NEUTRAL_VERIFIED=True' "$OUT/independent-neutral.log"; then
    echo "[FAIL] Exact WS01 baseline mismatch: $OUT/independent-neutral.log" >&2
    exit 1
  fi
  echo 'PHASE03_SHADOW_NEUTRAL_ACCEPTANCE=PASS'
  echo 'PHASE03_SHADOW_ACTIVE_ACCEPTANCE=NOT_TESTED'
  exit 0
fi

export KINGDOMS_PHASE03_SHADOW_ROLLBACK_ACTION=plan
if [[ "$ACTION" == --apply ]]; then
  export KINGDOMS_PHASE03_SHADOW_ROLLBACK_ACTION=apply
fi
echo '[RUN] Check exact WS01 SID/DN and sole KCL value against baseline'
if ! "$ANSIBLE" -i "$DATA" -i "$INVENTORY" \
    ansible/phase03-shadow-rollback-north.yml >"$OUT/rollback.log" 2>&1; then
  echo "[FAIL] Shadow $ACTION failed; inspect $OUT/rollback.log" >&2
  echo 'PHASE03_SHADOW_ROLLBACK_ACCEPTANCE=FAIL'
  exit 1
fi
grep -E 'PHASE03_SHADOW_ROLLBACK_(PLAN|KCL_SHA256|TARGET_IDENTITY|APPLIED|DIRECTORY_CHANGED)=' "$OUT/rollback.log" || true
if [[ "$ACTION" == --plan ]]; then
  grep -Fq 'PHASE03_SHADOW_ROLLBACK_PLAN=' "$OUT/rollback.log" ||
    { echo '[FAIL] No valid plan marker' >&2; exit 1; }
  echo 'PHASE03_SHADOW_ROLLBACK_PLAN_ACCEPTANCE=PASS'
  echo 'PHASE03_SHADOW_ROLLBACK_ACCEPTANCE=NOT_TESTED'
  exit 0
fi

grep -Fq 'PHASE03_SHADOW_ROLLBACK_APPLIED=True' "$OUT/rollback.log" ||
  { echo '[FAIL] No Shadow rollback apply marker' >&2; exit 1; }
echo '[RUN] Independently verify restored baseline using a separate read-only playbook'
if ! "$ANSIBLE" -i "$DATA" -i "$INVENTORY" \
    ansible/phase03-shadow-verify-neutral-north.yml >"$OUT/independent-neutral.log" 2>&1 ||
    ! grep -Fq 'PHASE03_SHADOW_NEUTRAL_VERIFIED=True' "$OUT/independent-neutral.log"; then
  echo "[FAIL] Independent Shadow neutral verification failed: $OUT/independent-neutral.log" >&2
  echo 'PHASE03_SHADOW_ROLLBACK_ACCEPTANCE=FAIL'
  exit 1
fi
echo 'PHASE03_SHADOW_ROLLBACK_ACCEPTANCE=PASS'
echo 'PHASE03_SHADOW_NEUTRAL_ACCEPTANCE=PASS'
echo 'PHASE03_SHADOW_ACTIVE_ACCEPTANCE=NOT_TESTED'
echo 'NOTE: Clean up locally owned certificate/key artifacts separately after preserving training evidence.'
