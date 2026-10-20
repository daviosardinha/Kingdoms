#!/usr/bin/env bash
# NORTH Phase 04 LPE verification: no apply/reset; no VM lifecycle operations.
# Stored RunAs validation temporarily modifies then restores SeBatchLogonRight.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

usage() {
  echo 'Usage: bash scripts/course1-phase04-acceptance.sh <NORTH-instance-id> --plan'
  echo '       bash scripts/course1-phase04-acceptance.sh <NORTH-instance-id> --validate --confirm-transient-right'
}
if [[ $# -lt 2 || $# -gt 3 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ ]]; then
  usage >&2; exit 2
fi
INSTANCE="$1"
ACTION="$2"
case "$ACTION" in
  --plan) [[ $# == 2 ]] || { usage >&2; exit 2; } ;;
  --validate) [[ $# == 3 && "$3" == --confirm-transient-right ]] ||
    { usage >&2; exit 2; } ;;
  *) usage >&2; exit 2 ;;
esac

echo 'NORTH — MODULE 04 LOCAL PRIVILEGE ESCALATION ACCEPTANCE'
echo "Instance: $INSTANCE"
echo 'Target: GOAD-WS01 | Rickon: NORTH\rickon.stark (non-admin RDP foothold)'
echo 'Profile: full-lpe / 20 promoted techniques'
echo 'Reset, re-apply and VM lifecycle actions: DISABLED'
if [[ "$ACTION" == --plan ]]; then
  echo 'PLAN_ONLY=True'
  echo 'PHASE04_LPE_ACTIVE_ACCEPTANCE=NOT_TESTED'
  exit 0
fi

PROVIDER="$ROOT/workspace/$INSTANCE/provider"
MODE="$PROVIDER/.goad-nomad-mode"
DATA="$ROOT/ad/NORTH/data/inventory"
INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
GLOBAL="$ROOT/globalsettings.ini"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
for path in "$PROVIDER" "$DATA" "$INVENTORY" "$GLOBAL"; do
  [[ -e "$path" && ! -L "$path" ]] ||
    { echo "[BLOCKED] NORTH path missing or linked: $path" >&2; exit 2; }
done
[[ -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] ||
  { echo '[BLOCKED] Exact NORTH instance not in exercise mode' >&2; exit 2; }
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] Ansible unavailable' >&2; exit 2; }
command -v flock >/dev/null || { echo '[BLOCKED] flock unavailable' >&2; exit 2; }

exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || { echo '[BLOCKED] Another acceptance is active' >&2; exit 2; }
[[ ! -L "$HOME/Kingdoms-evidence" ]] ||
  { echo '[BLOCKED] Evidence root is symlinked' >&2; exit 2; }
mkdir -p -m 700 "$HOME/Kingdoms-evidence"
EVIDENCE="$(mktemp -d "$HOME/Kingdoms-evidence/phase04-lpe-XXXXXXXX")"
chmod 700 "$EVIDENCE"
echo "Evidence: $EVIDENCE"
fail() {
  echo "[FAIL] $*" >&2
  echo 'PHASE04_LPE_ACTIVE_ACCEPTANCE=FAIL'
  echo "Evidence: $EVIDENCE"
  exit 1
}

echo '[RUN] Exact installed NORTH source and network owner'
bash scripts/course1-rollout.sh --installed "$PROVIDER" >"$EVIDENCE/00-owner.log" 2>&1 ||
  fail 'NORTH installed ownership/source validation failed'
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"

echo '[RUN] Verify WS01 NORTH foothold, Rickon non-admin status and security controls'
"$ANSIBLE" -i "$DATA" -i "$INVENTORY" -i "$GLOBAL" \
  ansible/course1-phase04-foothold.yml >"$EVIDENCE/01-foothold.log" 2>&1 ||
  fail 'Rickon foothold preflight failed'
for marker in \
  PHASE04_WS01_NORTH_DOMAIN=PASS \
  PHASE04_WS01_RICKON_NONADMIN_RDP=PASS \
  PHASE04_WS01_SECURITY_CONTROLS=PASS; do
  grep -Fq "$marker" "$EVIDENCE/01-foothold.log" ||
    fail "Foothold output missing $marker"
done

echo '[RUN] Validate all 20 seeded scenarios without resetting or re-applying'
echo 'NOTE: Stored RunAs validation temporarily grants and restores SeBatchLogonRight.'
"$ANSIBLE" -i "$DATA" -i "$INVENTORY" -i "$GLOBAL" \
  ansible/windows-lpe.yml \
  -e windows_lpe_action=validate \
  -e windows_lpe_profile=full-lpe \
  -e windows_lpe_validate_state=vulnerable \
  >"$EVIDENCE/02-lpe-validation.log" 2>&1 ||
  fail '20-technique profile validation failed'

CATALOG=(
  unquoted_service_path weak_service_dacl weak_service_binary_permissions
  weak_service_registry_permissions service_dll_hijacking path_search_order_hijacking
  always_install_elevated registry_run_keys writable_startup_folder
  scheduled_task_binary_permissions scheduled_task_directory_permissions
  unattend_credentials powershell_history_credentials hardcoded_application_credentials
  stored_runas_credentials stored_winlogon_credentials sebackup_privilege
  seimpersonate_privilege writable_program_directory insecure_service_registry
)
count=0
for technique in "${CATALOG[@]}"; do
  marker="WINDOWS_LPE_${technique^^}=VULNERABLE"
  grep -Fq "$marker" "$EVIDENCE/02-lpe-validation.log" ||
    fail "Missing vulnerable-state marker: $technique"
  count=$((count+1))
done
[[ $count == 20 ]] || fail 'Wrong validated catalog count'
echo "PHASE04_LPE_SCENARIOS_VERIFIED=$count"
echo 'PHASE04_LPE_FULL_PROFILE=PASS'
echo 'PHASE04_LPE_ACTIVE_ACCEPTANCE=PASS'
echo 'PHASE04_LPE_ESCALATION_PROOF=NOT_TESTED'
echo 'NOTE: One real Rickon-to-SYSTEM exploit and cleanup remain curriculum acceptance.'
echo "Evidence: $EVIDENCE"
