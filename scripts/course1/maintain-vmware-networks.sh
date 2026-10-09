#!/usr/bin/env bash
# Kingdoms Course 1 dedicated VMware network maintenance. Never power VMs.
# Run from the clean, upstream-matched feature branch; no reference edits.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

usage() {
  cat <<'EOF'
Usage:
  bash scripts/course1/maintain-vmware-networks.sh plan
  bash scripts/course1/maintain-vmware-networks.sh apply --confirm-maintenance
  bash scripts/course1/maintain-vmware-networks.sh rollback BACKUP_ID --confirm-maintenance

plan: read-only host/network survey; safe while reference VMs run.
apply: requires all VMware guests stopped, privileged backup, additive
       configuration change and verified VMware service restart. No VM start.
rollback: explicit restore using BACKUP_ID, requires guests stopped.
Host .254 addresses/persistence, instance install and guest operations are
NOT handled by this script. Use only in an approved maintenance window.
EOF
}

fail() {
  printf '[FAIL] %s\n' "$*" >&2
  exit 1
}

[[ $# -ge 1 ]] || { usage; exit 2; }
action="$1"
shift
case "$action" in
  plan) [[ $# -eq 0 ]] || fail "plan takes no arguments" ;;
  apply) [[ $# -eq 1 && "$1" == "--confirm-maintenance" ]] ||
           fail "apply needs --confirm-maintenance" ;;
  rollback)
    [[ $# -eq 2 && "$2" == "--confirm-maintenance" ]] ||
       fail "rollback needs BACKUP_ID --confirm-maintenance"
    backup_id="$1"
    [[ "$backup_id" =~ ^c1-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$ ]] ||
       fail "invalid backup identity"
    ;;
  *) usage; fail "unknown maintenance action: $action" ;;
esac

command -v git >/dev/null || fail "git missing"
command -v python3 >/dev/null || fail "python3 missing"
readonly head="$(git rev-parse HEAD)"
bash scripts/verify-test-source.sh "$head"

confirm=I_APPROVE_KINGDOMS_COURSE1_VMWARE_NETWORK_MAINTENANCE
if [[ "$action" == "rollback" ]]; then
  command -v sudo >/dev/null || fail "sudo required for rollback"
  sudo python3 -m goad.course1_vmnet_transaction \
    --rollback "$backup_id" --confirm "$confirm"
  exit 0
fi

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/kingdoms-course1-maint.XXXXXXXX)"
cleanup() { rm -rf -- "$tmp_dir"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
readonly snapshot="$tmp_dir/host.json"
python3 -m goad.course1_host_survey --check --json-only > "$snapshot"
python3 -m goad.course1_vmnet_maintenance \
  --proposal docs/course1-network-candidate.example.json \
  --snapshot "$snapshot"

if [[ "$action" == "plan" ]]; then
  echo "[BLOCKED] Read-only plan; no host changes have occurred"
  exit 0
fi

# Never power off reference guests implicitly. Operator must shut down using
# the existing validated Kingdoms lifecycle and verify guest state first.
if pgrep -x vmware-vmx >/dev/null 2>&1; then
  fail "VMware guests still running; stop ALL VMware guests before applying"
fi
python3 - "$snapshot" <<'PY'
import json
import sys
from pathlib import Path
report = json.loads(Path(sys.argv[1]).read_text())
if report["running_vm_count"] != 0:
    raise SystemExit("[FAIL] VMware snapshot is not a stopped-guest snapshot")
if report["registered_inventory"]["library_status"] != "INSPECTED":
    raise SystemExit("[FAIL] registered VMware inventory is incomplete")
print("[PASS] no running VMware guests in fresh snapshot")
PY

command -v sudo >/dev/null || fail "sudo required for network maintenance"
sudo python3 -m goad.course1_vmnet_transaction \
  --apply --proposal docs/course1-network-candidate.example.json \
  --snapshot "$snapshot" --confirm "$confirm"
echo "[BLOCKED] Course 1 deployment still disabled; host-address persistence pending"
