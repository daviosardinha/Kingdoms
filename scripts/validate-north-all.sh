#!/usr/bin/env bash
# NORTH-only one-shot acceptance: source, exercise-mode runtime, course
# readiness and all 20 LPE vulnerable-state assertions. No attack execution,
# VM lifecycle, AD writes, or network mode transitions.
# Explicit exception: stored_runas_credentials validate temporarily grants
# and restores SeBatchLogonRight; requires --confirm-transient-right.
set -Eeuo pipefail
umask 077

usage() {
  printf 'Usage: bash scripts/validate-north-all.sh <six-hex>-north-vmware --confirm-transient-right [--rdp-mode legacy|headless]\n' >&2
}
if [[ ( $# -ne 2 && $# -ne 4 ) || ! "${1:-}" =~ ^[a-f0-9]{6}-north-vmware$ || "${2:-}" != --confirm-transient-right ]]; then
  usage
  exit 2
fi
RDP_MODE=legacy
if [[ $# -eq 4 ]]; then
  [[ "$3" == --rdp-mode && ( "$4" == legacy || "$4" == headless ) ]] || { usage; exit 2; }
  RDP_MODE="$4"
fi
readonly RDP_MODE
readonly INSTANCE="$1"
readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly PROVIDER="$ROOT/workspace/$INSTANCE/provider"
readonly DATA_INVENTORY="$ROOT/ad/NORTH/data/inventory"
readonly INSTANCE_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
readonly GLOBAL="$ROOT/globalsettings.ini"
readonly ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
readonly MODE_FILE="$PROVIDER/.goad-nomad-mode"
readonly EVIDENCE_ROOT="$HOME/Kingdoms-evidence"

cd "$ROOT"
[[ -f "$ROOT/.git" || -d "$ROOT/.git" ]] || { echo '[BLOCKED] Not a Git checkout or worktree' >&2; exit 2; }
[[ "$(git rev-parse --show-toplevel)" == "$ROOT" ]] || { echo '[BLOCKED] Git root mismatch' >&2; exit 2; }
for file in "$DATA_INVENTORY" "$INSTANCE_INVENTORY" "$GLOBAL" "$MODE_FILE"; do
  [[ -f "$file" && ! -L "$file" ]] || { echo "[BLOCKED] Missing/linked NORTH file: $file" >&2; exit 2; }
done
[[ -d "$PROVIDER" && ! -L "$PROVIDER" && "$(cat "$MODE_FILE")" == exercise ]] ||
  { echo '[BLOCKED] Exact NORTH provider must remain in exercise mode' >&2; exit 2; }
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] GOAD Ansible virtualenv missing' >&2; exit 2; }
[[ ! -L "$EVIDENCE_ROOT" ]] || { echo '[BLOCKED] Evidence root must not be a symlink' >&2; exit 2; }
mkdir -p -m 700 "$EVIDENCE_ROOT"
readonly EVIDENCE="$(mktemp -d "$EVIDENCE_ROOT/north-all-$INSTANCE-XXXXXXXX")"
readonly RESULTS="$EVIDENCE/results.tsv"
printf 'stage\tstatus\texit_code\tlog\n' > "$RESULTS"
# Capture the operator/host Python BEFORE adding the GOAD Ansible venv to PATH.
# The Ansible venv may have no pytest; host pytest is a separate dependency.
HOST_PYTEST_PYTHON="$(command -v python3)"
if ! "$HOST_PYTEST_PYTHON" -m pytest --version >/dev/null 2>&1; then
  for candidate in /usr/bin/python3 /usr/local/bin/python3; do
    if [[ -x "$candidate" ]] && "$candidate" -m pytest --version >/dev/null 2>&1; then
      HOST_PYTEST_PYTHON="$candidate"
      break
    fi
  done
fi
readonly HOST_PYTEST_PYTHON
echo "Host test Python: $HOST_PYTEST_PYTHON"
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export ROOT INSTANCE PROVIDER
export GOAD_PROVIDER_DIR="$PROVIDER"
export GOAD_LAB_PROFILE=NORTH
export PATH="$HOME/.goad/.venv/bin:$PATH"

# Keep a single NORTH-only acceptance run; never intervene in other VMs.
exec 9>"$PROVIDER/.north-all-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Another NORTH all-in-one acceptance is running' >&2; exit 2; }
echo '===== NORTH SINGLE-SHOT ACCEPTANCE ====='
echo "Instance: $INSTANCE"
echo "Provider: $PROVIDER"
echo "RDP bot contract: $RDP_MODE (legacy is the installed default; headless requires a separately verified handover)"
echo "Evidence: $EVIDENCE"
echo 'No install, destroy, reset, account rejoin, poisoning, relay or credential dumping.'
echo 'Stored RunAs test temporarily changes then restores SeBatchLogonRight.'
echo

success=0
failure=0
run_stage() {
  local name="$1" marker="$2" log="$3"
  shift 3
  local rc=0
  printf '\n[RUN] %s\n' "$name"
  if "$@" >"$EVIDENCE/$log" 2>&1; then
    if [[ -z "$marker" ]] || grep -Fq -- "$marker" "$EVIDENCE/$log"; then
      printf '[PASS] %s\n' "$name"
      success=$((success + 1))
      printf '%s\tPASS\t0\t%s\n' "$name" "$log" >>"$RESULTS"
      return 0
    fi
    rc=86
    echo "[MISSING] Expected marker: $marker" >>"$EVIDENCE/$log"
  else
    rc=$?
  fi
  printf '[FAIL] %s (rc=%s, log=%s)\n' "$name" "$rc" "$EVIDENCE/$log" >&2
  tail -n 18 "$EVIDENCE/$log" >&2 || true
  failure=$((failure + 1))
  printf '%s\tFAIL\t%s\t%s\n' "$name" "$rc" "$log" >>"$RESULTS"
  return 1
}
finish() {
  local exitcode="$1"
  python3 - "$RESULTS" "$EVIDENCE" "$INSTANCE" "$exitcode" "$RDP_MODE" <<'PY'
import csv
import json
import sys
from pathlib import Path
src, path, instance, rc, rdp_mode = sys.argv[1:]
with open(src, newline='', encoding='utf-8') as stream:
    results = list(csv.DictReader(stream, delimiter='\t'))
pass_count = sum(r['status'] == 'PASS' for r in results)
fail_count = sum(r['status'] == 'FAIL' for r in results)
report = {
    'rdp_contract': rdp_mode,
    'instance': instance,
    'readiness': 'PASS' if not fail_count and int(rc) == 0 else 'FAIL',
    'pass': pass_count, 'fail': fail_count,
    'phases': results,
    'phase03_fixture_exploitability': 'NOT_PROVEN_BY_INSPECTION',
    'phase03_active_attack_chains': 'NOT_TESTED',
    'phase04_Rickon_to_SYSTEM_exploit': 'NOT_TESTED',
    'mutations': 'No attack or lifecycle changes; LPE validation temporarily grants/restores SeBatchLogonRight'
}
Path(path, 'summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('\n===== NORTH VALIDATION SUMMARY =====')
for item in results:
    print(f"[{item['status']}] {item['stage']}: {item['log']}")
print(f'PASS={pass_count} FAIL={fail_count}')
print(f'RDP_BOT_CONTRACT={rdp_mode}')
print('PHASE03_FIXTURE_EXPLOITABILITY=NOT_PROVEN_BY_INSPECTION')
print('PHASE03_ACTIVE_ATTACK_CHAINS=NOT_TESTED')
print('PHASE04_RICKON_TO_SYSTEM_EXPLOIT=NOT_TESTED')
print(f'NORTH_ALL_READINESS={report["readiness"]}')
print(f'EVIDENCE={path}')
PY
  exit "$exitcode"
}
# Stop before guest tests if the source cannot be trusted.
run_stage source-synchronization '' source-sync.log bash scripts/verify-test-source.sh || finish 1
run_stage north-source-gate 'GOAD Kingdoms clean-install source gate passed' source-gate.log bash scripts/validate-goad-kingdoms-install-source.sh || finish 1
run_stage north-source-unit-regression '' north-tests.log "$HOST_PYTEST_PYTHON" -m pytest -q tests/test_north_*.py tests/test_course1_*.py || finish 1

# Runtime ownership guard is required before any course probes can contact guests.
sudo -v || finish 1
run_stage north-runtime-before 'NORTH_RUNTIME_ACCEPTANCE=PASS' runtime-before.log \
  bash ./goad.sh -t validate -l NORTH -p vmware -i "$INSTANCE" || finish 1

# These existing scripts only perform read/probe actions against the lab.
run_stage phase01-anonymous-and-http 'PASS: ' phase01.log \
  python3 scripts/validate-phase01.py --out "$EVIDENCE/phase01" || true
run_stage phase02-rdp-smb-mssql-http '[READY] 02' phase02.log \
  env KINGDOMS_PHASE02_PROFILE=NORTH PHASE02_RDP_BOT_MODE="$RDP_MODE" \
    EVIDENCE="$EVIDENCE/phase02" bash scripts/validate-phase02-readiness.sh || true
run_stage phase03-poisoning-relay-readiness '[READY] 03' phase03.log \
  env KINGDOMS_PHASE03_PROFILE=NORTH EVIDENCE="$EVIDENCE/phase03" \
    bash scripts/validate-phase03-readiness.sh || true

# Run the NORTH-specific AD fixture preflights DIRECTLY with the exact NORTH
# inventories: their legacy shell wrappers default to unrelated GOAD paths.
# Diagnostic preflights may print unfavorable states and still exit zero.
# Verify each probe actually ran, but call this an inspection, not proof that
# the associated attack works. Preserve all raw evidence for human review.
for spec in rbcd shadow adidns webdav-shortcut; do
  case "$spec" in
    rbcd) marker='PHASE03_RBCD_TARGET=WS01

# One existing explicit-approval validator covers Rickon's low-privilege
# foothold and proves all 20 LPE scenarios in their seeded vulnerable state.
run_stage phase04-full-20-lpe 'PHASE04_LPE_ACTIVE_ACCEPTANCE=PASS' phase04.log \
  bash scripts/course1-phase04-acceptance.sh "$INSTANCE" --validate --confirm-transient-right || true

# Always reprove isolation/AD trust after all guest-facing checks.
run_stage north-runtime-after 'NORTH_RUNTIME_ACCEPTANCE=PASS' runtime-after.log \
  bash ./goad.sh -t validate -l NORTH -p vmware -i "$INSTANCE" || true
run_stage north-instance-status 'Network Mode' status.log \
  bash ./goad.sh -t status -l NORTH -p vmware -i "$INSTANCE" || true

if (( failure > 0 )); then finish 1; else finish 0; fi
 ;;
    shadow) marker='PHASE03_SHADOW_PREFLIGHT_COMPLETE=True' ;;
    adidns) marker='PHASE03_ADIDNS_PREFLIGHT_COMPLETE=True' ;;
    webdav-shortcut) marker='PHASE03_WEBDAV_PREFLIGHT_COMPLETE=True' ;;
  esac
  run_stage "phase03-$spec-inspection" "$marker" "phase03-$spec.log" \
    "$ANSIBLE" -i "$DATA_INVENTORY" -i "$INSTANCE_INVENTORY" -i "$GLOBAL" \
    "ansible/phase03-$spec-preflight.yml" || true
done

# One existing explicit-approval validator covers Rickon's low-privilege
# foothold and proves all 20 LPE scenarios in their seeded vulnerable state.
run_stage phase04-full-20-lpe 'PHASE04_LPE_ACTIVE_ACCEPTANCE=PASS' phase04.log \
  bash scripts/course1-phase04-acceptance.sh "$INSTANCE" --validate --confirm-transient-right || true

# Always reprove isolation/AD trust after all guest-facing checks.
run_stage north-runtime-after 'NORTH_RUNTIME_ACCEPTANCE=PASS' runtime-after.log \
  bash ./goad.sh -t validate -l NORTH -p vmware -i "$INSTANCE" || true
run_stage north-instance-status 'Network Mode' status.log \
  bash ./goad.sh -t status -l NORTH -p vmware -i "$INSTANCE" || true

if (( failure > 0 )); then finish 1; else finish 0; fi
