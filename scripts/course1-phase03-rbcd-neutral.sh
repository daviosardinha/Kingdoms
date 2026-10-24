#!/usr/bin/env bash
# Independent read-only NORTH RBCD verification against an exact captured baseline.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ $# != 2 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ ]]; then
  echo 'Usage: bash scripts/course1-phase03-rbcd-neutral.sh <NORTH-instance-id> <absolute-baseline-path>' >&2
  exit 2
fi
INSTANCE="$1"
BASELINE="$2"
BASELINE_DIR="$(dirname -- "$BASELINE")"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
LAB_INVENTORY="$ROOT/ad/NORTH/data/inventory"
MODE="$PROVIDER/.goad-nomad-mode"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"

# Never select "latest" or a shared baseline, or accept a symlink.
[[ "$BASELINE" == "$HOME"/Kingdoms-evidence/phase03-rbcd-baseline-*/rbcd-baseline.json ]] || {
  echo '[BLOCKED] Require the exact path from a previous NORTH RBCD capture' >&2
  exit 2
}
[[ -f "$BASELINE" && ! -L "$BASELINE" && -f "$BASELINE_DIR/rbcd-baseline.sha256" ]] || {
  echo '[BLOCKED] Baseline or SHA-256 proof missing' >&2
  exit 2
}
[[ -d "$PROVIDER" && -f "$INVENTORY" && -f "$LAB_INVENTORY" ]] || {
  echo '[BLOCKED] Exact NORTH instance or inventory missing' >&2
  exit 2
}
[[ -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] || {
  echo '[BLOCKED] NORTH instance must be in exercise mode' >&2
  exit 2
}
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] Ansible missing' >&2; exit 2; }
command -v flock >/dev/null || { echo '[BLOCKED] flock unavailable' >&2; exit 2; }

# Prevent comparing state while another acceptance mutates the directory.
exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Another Phase 03 acceptance is active' >&2; exit 2; }

python3 - "$BASELINE" <<'PY'
import os
import stat
import sys
from pathlib import Path

baseline = Path(sys.argv[1])
parent = baseline.parent
proof = parent / "rbcd-baseline.sha256"
for path, mode in ((parent, 0o700), (baseline, 0o600), (proof, 0o600)):
    metadata = path.lstat()
    correct_type = stat.S_ISDIR if path == parent else stat.S_ISREG
    if not correct_type(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != mode or metadata.st_uid != os.getuid():
        raise SystemExit(f"[BLOCKED] Invalid owner/type/mode for {path}")
PY

sha256sum --check --status "$BASELINE_DIR/rbcd-baseline.sha256" || {
  echo '[BLOCKED] RBCD baseline integrity mismatch' >&2
  exit 2
}
EVIDENCE="$(mktemp -d "$HOME/Kingdoms-evidence/phase03-rbcd-neutral-$(date +%Y%m%d-%H%M%S)-XXXXXXXX")"
chmod 700 "$EVIDENCE"

echo '[RUN] Installed NORTH ownership check'
if ! bash scripts/course1-rollout.sh --installed "$PROVIDER" >"$EVIDENCE/installed.log" 2>&1; then
  echo "[BLOCKED] Installed NORTH ownership check failed: $EVIDENCE" >&2
  exit 1
fi

export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"
echo '[RUN] Comparing live RBCD state with captured baseline (read-only)'
if ! timeout --signal=TERM 150 "$ANSIBLE" \
  -i "$LAB_INVENTORY" -i "$INVENTORY" \
  ansible/phase03-rbcd-verify-neutral.yml >"$EVIDENCE/neutral.log" 2>&1 ||
  ! grep -Fq 'PHASE03_RBCD_NEUTRAL_VERIFIED=True' "$EVIDENCE/neutral.log"; then
  echo "[FAIL] RBCD state mismatch: $EVIDENCE" >&2
  echo 'PHASE03_RBCD_NEUTRAL_ACCEPTANCE=FAIL'
  exit 1
fi
echo 'PHASE03_RBCD_NEUTRAL_ACCEPTANCE=PASS'
echo 'PHASE03_RBCD_ACTIVE_ACCEPTANCE=NOT_TESTED'
echo "Evidence: $EVIDENCE"
