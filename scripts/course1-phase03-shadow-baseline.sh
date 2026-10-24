#!/usr/bin/env bash
# Course 1 NORTH Shadow Credentials: capture an immutable per-run baseline.
# No directory mutation, relay, coercion, VM reset or overwrite of legacy baseline.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ $# -ne 3 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ || "$2" != --capture || "$3" != --confirm ]]; then
  echo 'Usage: bash scripts/course1-phase03-shadow-baseline.sh <NORTH-instance-id> --capture --confirm' >&2
  exit 2
fi
INSTANCE="$1"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
LAB_INVENTORY="$ROOT/ad/NORTH/data/inventory"
INSTANCE_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
MODE="$PROVIDER/.goad-nomad-mode"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
EVIDENCE_ROOT="$HOME/Kingdoms-evidence"

for path in "$PROVIDER" "$LAB_INVENTORY" "$INSTANCE_INVENTORY" "$ROOT/ad/NORTH/data/config.json"; do
  [[ -e "$path" && ! -L "$path" ]] || {
    echo "[BLOCKED] Missing or linked NORTH input: $path" >&2
    exit 2
  }
done
[[ -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] || {
  echo '[BLOCKED] NORTH instance is not in exercise mode' >&2
  exit 2
}
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] Expected Ansible environment unavailable' >&2; exit 2; }
command -v flock >/dev/null || { echo '[BLOCKED] flock unavailable' >&2; exit 2; }
command -v sha256sum >/dev/null || { echo '[BLOCKED] sha256sum unavailable' >&2; exit 2; }

exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Another Phase 03 acceptance holds the lock' >&2; exit 2; }

if pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' >/dev/null; then
  echo '[BLOCKED] Active poisoning or relay runtime; stop it before baseline capture' >&2
  exit 2
fi

[[ ! -L "$EVIDENCE_ROOT" ]] || { echo '[BLOCKED] Evidence directory is symlinked' >&2; exit 2; }
mkdir -p -m 700 "$EVIDENCE_ROOT"
EVIDENCE="$(mktemp -d "$EVIDENCE_ROOT/phase03-shadow-baseline-XXXXXXXX")"
chmod 700 "$EVIDENCE"
BASELINE="$EVIDENCE/shadow-baseline.json"
printf 'Instance: %s\nEvidence: %s\n' "$INSTANCE" "$EVIDENCE"

echo '[RUN] Verify current NORTH source and installed network ownership (read-only)'
if ! bash scripts/course1-rollout.sh --installed "$PROVIDER" >"$EVIDENCE/owner.log" 2>&1; then
  echo "[BLOCKED] Source or VMnet ownership verification failed: $EVIDENCE/owner.log" >&2
  exit 1
fi
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"

echo '[RUN] Verify empty WS01 KeyCredentialLink, SELF permission and KDC certificate (read-only)'
if ! "$ANSIBLE" -i "$LAB_INVENTORY" -i "$INSTANCE_INVENTORY" \
    ansible/phase03-shadow-preflight.yml >"$EVIDENCE/preflight.log" 2>&1; then
  echo "[BLOCKED] Shadow prerequisites failed: $EVIDENCE/preflight.log" >&2
  exit 1
fi
for marker in \
  'PHASE03_SHADOW_PREFLIGHT_COMPLETE=True' \
  'PHASE03_SHADOW_KCL_EMPTY=True' \
  'PHASE03_SHADOW_SELF_VALIDATED_WRITE=True' \
  'PHASE03_SHADOW_CERTUTIL_RC=0'; do
  grep -Fq "$marker" "$EVIDENCE/preflight.log" || {
    echo "[BLOCKED] Missing prerequisite: $marker" >&2
    exit 1
  }
done
grep -Eq 'PHASE03_SHADOW_KDC_CERT_COUNT=[1-9][0-9]*' "$EVIDENCE/preflight.log" || {
  echo '[BLOCKED] No KDC certificate confirmed' >&2
  exit 1
}

[[ ! -e "$BASELINE" && ! -L "$BASELINE" ]] || {
  echo '[BLOCKED] Selected baseline already exists' >&2
  exit 2
}
echo '[RUN] Capture fresh per-run NORTH Shadow baseline (read-only)'
export KINGDOMS_PHASE03_SHADOW_BASELINE="$BASELINE"
if ! "$ANSIBLE" -i "$LAB_INVENTORY" -i "$INSTANCE_INVENTORY" \
    ansible/phase03-shadow-baseline.yml >"$EVIDENCE/capture.log" 2>&1; then
  echo "[FAIL] Baseline capture failed: $EVIDENCE/capture.log" >&2
  exit 1
fi
python3 - "$BASELINE" <<'PY'
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
meta = path.lstat()
if not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_uid != os.getuid():
    raise SystemExit('[BLOCKED] Shadow baseline owner/type/mode mismatch')
data = json.loads(path.read_text(encoding='utf-8'))
if data.get('Version') != 1 or data.get('Target') != 'WS01$':
    raise SystemExit('[BLOCKED] Wrong Shadow baseline version or target')
if (data.get('KCLPresent') is not False or data.get('KCLCount') != 0
        or data.get('KCLValues') != []):
    raise SystemExit('[BLOCKED] Shadow KCL is not in its original empty state')
dn = data.get('TargetDN', '')
if not dn.lower().endswith('dc=north,dc=sevenkingdoms,dc=local'):
    raise SystemExit('[BLOCKED] Shadow target is outside NORTH')
sid = data.get('TargetSID', '')
if not sid.startswith('S-1-5-21-'):
    raise SystemExit('[BLOCKED] Missing WS01 target SID')
timestamp = datetime.fromisoformat(data['CapturedUTC'].replace('Z', '+00:00'))
if timestamp.tzinfo is None:
    raise SystemExit('[BLOCKED] Captured time has no timezone')
print('PHASE03_SHADOW_BASELINE_NEUTRAL=True')
print('PHASE03_SHADOW_BASELINE_TARGET=WS01$')
print('PHASE03_SHADOW_BASELINE_KCL_COUNT=0')
PY
sha256sum "$BASELINE" >"$EVIDENCE/shadow-baseline.sha256"
chmod 600 "$EVIDENCE/shadow-baseline.sha256"
echo 'PHASE03_SHADOW_BASELINE_CAPTURE=PASS'
echo 'PHASE03_SHADOW_ACTIVE_ACCEPTANCE=NOT_TESTED'
echo "Baseline: $BASELINE"
echo "Evidence: $EVIDENCE"
