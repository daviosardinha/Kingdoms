#!/usr/bin/env bash
# NORTH Phase 03 active acceptance — stage 1: mutation-disabled HTTP to LDAPS.
# Other attack chains stay explicitly NOT_TESTED until their rollback gates exist.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/course1-phase03-acceptance.sh <NORTH-instance-id> --plan
  bash scripts/course1-phase03-acceptance.sh <NORTH-instance-id> --run-http-ldaps --confirm
  bash scripts/course1-phase03-acceptance.sh <NORTH-instance-id> --prepare-rbcd --confirm
  bash scripts/course1-phase03-acceptance.sh <NORTH-instance-id> --verify-rbcd <captured-baseline.json>

--plan is read-only.
--prepare-rbcd captures a private RBCD baseline; no AD changes or relay.
--verify-rbcd independently compares the live state with a captured baseline.
--run-http-ldaps validates NORTH, performs exactly one mutation-disabled
HTTP->LDAPS relay and checks scoped cleanup. All other attack paths remain NOT_TESTED.
USAGE
}
if [[ $# -lt 2 || $# -gt 3 || ! "$1" =~ ^[A-Za-z0-9_-]+-north-vmware$ ]]; then
  usage >&2
  exit 2
fi
INSTANCE="$1"
ACTION="$2"
case "$ACTION" in
  --plan) [[ $# == 2 ]] || { usage >&2; exit 2; } ;;
  --run-http-ldaps) [[ $# == 3 && "$3" == --confirm ]] || { usage >&2; exit 2; } ;;
  --prepare-rbcd) [[ $# == 3 && "$3" == --confirm ]] || { usage >&2; exit 2; } ;;
  --verify-rbcd) [[ $# == 3 ]] || { usage >&2; exit 2; } ;;
  *) usage >&2; exit 2 ;;
esac

PROVIDER="$ROOT/workspace/$INSTANCE/provider"
DATA_INVENTORY="$ROOT/ad/NORTH/data/inventory"
INSTANCE_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
MODE="$PROVIDER/.goad-nomad-mode"

for required in "$PROVIDER" "$DATA_INVENTORY" "$INSTANCE_INVENTORY" "$ROOT/ad/NORTH/data/config.json"; do
  [[ -e "$required" ]] || { printf '[BLOCKED] Missing NORTH input: %s\n' "$required" >&2; exit 2; }
done

echo '============================================================'
echo 'NORTH — PHASE 03 ACTIVE ATTACK ACCEPTANCE'
echo '============================================================'
echo "Instance: $INSTANCE"
echo '01 HTTP -> LDAPS read-only relay                 : IMPLEMENTED'
echo '02 LLMNR/NBT-NS/mDNS and NetNTLMv2               : NOT_TESTED'
echo '03 SMB relay, interactive sessions and SOCKS     : NOT_TESTED'
echo '04 mitm6/WPAD, DHCPv6 and reset                  : NOT_TESTED'
echo '05 RBCD, S4U and rollback                        : NOT_TESTED'
echo '06 Shadow Credentials, PKINIT and rollback       : NOT_TESTED'
echo '07 ADIDNS update, tombstone and rollback         : NOT_TESTED'
echo '08 WebDAV with Rickon and rollback               : NOT_TESTED'
echo '09 Coercion, DPAPI and LSASS                      : NOT_TESTED'
echo 'PHASE03_FULL_ATTACK_ACCEPTANCE=NOT_TESTED'
if [[ "$ACTION" == --plan ]]; then
  echo 'PLAN_ONLY=True'
  exit 0
fi

# RBCD preparation has its own exact-owner lock and evidence-only run contract.
# It does not enter the HTTP relay execution or finalizer below.
if [[ "$ACTION" == --prepare-rbcd ]]; then
  exec bash scripts/course1-phase03-rbcd-baseline.sh "$INSTANCE" --capture --confirm
fi

# Independent neutral-state audit uses the captured baseline; no AD changes.
if [[ "$ACTION" == --verify-rbcd ]]; then
  exec bash scripts/course1-phase03-rbcd-neutral.sh "$INSTANCE" "$3"
fi

[[ -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] || {
  echo '[BLOCKED] NORTH must be in recorded exercise mode' >&2
  exit 2
}
[[ -x "$HOME/.goad/.venv/bin/ansible-playbook" ]] || {
  echo '[BLOCKED] Expected Ansible environment missing' >&2
  exit 2
}
command -v flock >/dev/null || { echo '[BLOCKED] flock is missing' >&2; exit 2; }

LOCK="$PROVIDER/.course1-phase03-acceptance.lock"
exec 9>"$LOCK"
flock -n 9 || { echo '[BLOCKED] Acceptance already running' >&2; exit 2; }

export ROOT INSTANCE PROVIDER
export KINGDOMS_PHASE03_PROFILE=NORTH
export KINGDOMS_PHASE03_DATA_INVENTORY="$DATA_INVENTORY"
export KINGDOMS_PHASE03_PROVIDER_INVENTORY="$INSTANCE_INVENTORY"
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export TARGET=10.4.10.11

EVIDENCE="$HOME/Kingdoms-evidence/phase03-active-$(date +%Y%m%d-%H%M%S)"
mkdir -p -m 700 "$EVIDENCE"
SUMMARY="$EVIDENCE/summary.txt"
: > "$SUMMARY"
# The legacy relay launcher empties WORK. Use a fresh private directory,
# never the default folder containing previous local lab evidence.
export WORK="$EVIDENCE/http-ldaps-runtime"

START_ATTEMPTED=0
PROOF=NOT_TESTED
CURRENT_STAGE=preflight

run_step() {
  local name="$1" expected="$2" limit="$3"
  shift 3
  local file="$EVIDENCE/$name.log" rc=0
  CURRENT_STAGE="$name"
  printf '[RUN] %s\n' "$name"
  timeout --signal=TERM "$limit" "$@" > "$file" 2>&1 || rc=$?
  if (( rc != 0 )) || ! grep -Fq "$expected" "$file"; then
    printf '[FAIL] %s (rc=%s)\n' "$name" "$rc" >&2
    printf 'FAIL | %s | rc=%s\n' "$name" "$rc" >> "$SUMMARY"
    printf 'Log: %s\n' "$file" >&2
    return 1
  fi
  printf '[PASS] %s\n' "$name"
  printf 'PASS | %s\n' "$name" >> "$SUMMARY"
}

finalize() {
  local status="$?"
  trap - EXIT INT TERM
  set +e
  local cleanup_failure=0
  # Even a partially failed listener start is followed by the scoped
  # original stop helper and independent callback/neutral verification.
  if (( START_ATTEMPTED )); then
    run_step 90-listener-stop 'PHASE03_HTTP_LDAPS_RUNTIME_STOPPED=True' 90 \
      bash scripts/phase03/stop-http-ldaps-readonly-relay.sh || cleanup_failure=1
    run_step 91-callback-clean 'PHASE03_HTTP_LDAPS_CALLBACK_CLEAN=True' 150 \
      bash scripts/phase03/verify-http-ldaps-callback-clean.sh || cleanup_failure=1
    run_step 92-neutral 'PHASE03_HTTP_LDAPS_PREFLIGHT_COMPLETE=True' 90 \
      bash scripts/phase03/check-http-ldaps-readonly-relay.sh || cleanup_failure=1
  fi

  echo
  echo '=============== PHASE 03 ACTIVE SUMMARY ==============='
  cat "$SUMMARY"
  if (( status == 0 && cleanup_failure == 0 )) && [[ "$PROOF" == PASS ]]; then
    echo 'PHASE03_HTTP_LDAPS_ACTIVE_ACCEPTANCE=PASS' | tee -a "$SUMMARY"
    echo 'PHASE03_FULL_ATTACK_ACCEPTANCE=NOT_TESTED' | tee -a "$SUMMARY"
    echo "Evidence: $EVIDENCE"
    exit 0
  fi
  echo 'PHASE03_HTTP_LDAPS_ACTIVE_ACCEPTANCE=FAIL' | tee -a "$SUMMARY"
  echo 'PHASE03_FULL_ATTACK_ACCEPTANCE=NOT_TESTED' | tee -a "$SUMMARY"
  if (( cleanup_failure )); then
    echo '[BLOCKED] Cleanup was not verified. Do not run further attack scenarios.' >&2
  else
    echo "[NOT READY] Failed step: $CURRENT_STAGE" >&2
  fi
  echo "Evidence: $EVIDENCE"
  exit 1
}
trap finalize EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Preconditions must pass before the first listener or guest task is created.
run_step 00-prerequisites 'PHASE03_READONLY_ACCEPTANCE=PASS' 540 \
  bash scripts/course1-phase03-preflight.sh "$INSTANCE"
run_step 01-callback-before 'PHASE03_HTTP_LDAPS_CALLBACK_CLEAN=True' 150 \
  bash scripts/phase03/verify-http-ldaps-callback-clean.sh
run_step 02-neutral 'PHASE03_HTTP_LDAPS_PREFLIGHT_COMPLETE=True' 90 \
  bash scripts/phase03/check-http-ldaps-readonly-relay.sh

START_ATTEMPTED=1
run_step 03-listener 'PHASE03_HTTP_LDAPS_RUNTIME_READY=True' 120 \
  bash scripts/phase03/start-http-ldaps-readonly-relay.sh
run_step 04-ws01-callback 'PHASE03_HTTP_LDAPS_TRIGGER_COMPLETE=True' 150 \
  bash scripts/phase03/trigger-http-ldaps-readonly-relay.sh
run_step 05-proof 'PHASE03_HTTP_LDAPS_PROVEN=True' 45 \
  bash scripts/phase03/prove-http-ldaps-readonly-relay.sh
PROOF=PASS
# EXIT trap always performs listener stop and scoped residual-state checks.
