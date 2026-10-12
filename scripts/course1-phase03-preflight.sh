#!/usr/bin/env bash
# NORTH Course 1 Phase 03: consolidated, non-destructive prerequisite audit.
# No attacks, relays, coercion, host resets, baseline-file overwrites or AD writes.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ $# -ne 1 || ! "$1" =~ ^[a-zA-Z0-9_-]+-north-vmware$ ]]; then
  echo 'Usage: bash scripts/course1-phase03-preflight.sh <existing-NORTH-instance-id>' >&2
  exit 2
fi

INSTANCE="$1"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
INSTANCE_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
LAB_INVENTORY="$ROOT/ad/NORTH/data/inventory"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
MODE="$PROVIDER/.goad-nomad-mode"

for required in "$PROVIDER" "$INSTANCE_INVENTORY" "$LAB_INVENTORY" "$ROOT/ad/NORTH/data/config.json"; do
  [[ -e "$required" ]] || { printf '[BLOCKED] Missing NORTH input: %s\n' "$required" >&2; exit 2; }
done
[[ -f "$MODE" && "$(tr -d '[:space:]' < "$MODE")" == exercise ]] || {
  echo '[BLOCKED] NORTH must be in exercise mode; no changes made' >&2
  exit 2
}
[[ -x "$ANSIBLE" ]] || { echo '[BLOCKED] Kingdoms Ansible virtualenv not found' >&2; exit 2; }

EVIDENCE="$HOME/Kingdoms-evidence/phase03-batch-$(date +%Y%m%d-%H%M%S)"
mkdir -p -m 700 "$EVIDENCE"
SUMMARY="$EVIDENCE/summary.txt"
: > "$SUMMARY"

export ROOT INSTANCE PROVIDER
export KINGDOMS_PHASE03_PROFILE=NORTH
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"

PASS=0
FAIL=0
WARN=0
check_markers() {
  local id="$1" log="$2"
  case "$id" in
    00-owner)
      grep -Fq '[PASS] NORTH source and installed VMnet ownership verified (read-only)' "$log"
      ;;
    01-baseline)
      grep -Fq 'POISON THE WELLS BASELINE PREREQUISITES PASSED' "$log" &&
      grep -Eq 'FAIL:[[:space:]]*0' "$log"
      ;;
    02-rbcd)
      grep -Fq 'PHASE03_RBCD_EXISTING=False' "$log" &&
      grep -Fq 'PHASE03_RBCD_CANDIDATE_EXISTS=False' "$log" &&
      grep -Fq 'PHASE03_RBCD_SELF_CAN_WRITE=True' "$log" &&
      grep -Eq 'PHASE03_RBCD_MAQ=[1-9][0-9]*' "$log"
      ;;
    03-shadow)
      grep -Fq 'PHASE03_SHADOW_PREFLIGHT_COMPLETE=True' "$log" &&
      grep -Fq 'PHASE03_SHADOW_KCL_EMPTY=True' "$log" &&
      grep -Fq 'PHASE03_SHADOW_SELF_VALIDATED_WRITE=True' "$log" &&
      grep -Eq 'PHASE03_SHADOW_KDC_CERT_COUNT=[1-9][0-9]*' "$log" &&
      grep -Fq 'PHASE03_SHADOW_CERTUTIL_RC=0' "$log"
      ;;
    04-adidns)
      grep -Fq 'PHASE03_ADIDNS_PREFLIGHT_COMPLETE=True' "$log" &&
      grep -Fq 'PHASE03_ADIDNS_BROAD_CREATE_DNSNODE=True' "$log" &&
      grep -Fq 'PHASE03_ADIDNS_NODE=phase03-adidns;EXISTS=False' "$log"
      ;;
    05-webdav)
      grep -Fq 'PHASE03_WEBDAV_PREFLIGHT_COMPLETE=True' "$log" &&
      grep -Fq 'PHASE03_WEBDAV_WEBCLIENT_EXISTS=True' "$log" &&
      grep -Fq 'PHASE03_WEBDAV_RICKON_PROFILE_EXISTS=True' "$log" &&
      grep -Fq 'PHASE03_WEBDAV_RICKON_DESKTOP_EXISTS=True' "$log" &&
      grep -Fq 'PHASE03_WEBDAV_CANDIDATE_LNK_EXISTS=False' "$log" &&
      grep -Fq 'PHASE03_WEBDAV_CANDIDATE_URL_EXISTS=False' "$log" &&
      grep -Eq 'PHASE03_WEBDAV_QUSER_STATUS=(NO_ACTIVE_SESSIONS|SESSIONS_PRESENT)' "$log"
      ;;
    06-rdp-cert)
      grep -Eq 'RDP_SHA256=[0-9A-Fa-f]{64}' "$log"
      ;;
    07-wpad-tools)
      grep -Fq 'PHASE03_WPAD_CAPABILITY_SNAPSHOT_COMPLETE=True' "$log" &&
      ! grep -Eq '^NOT_SUPPORTED: (-6|-wh)([[:space:]]|$)' "$log"
      ;;
    08-ldap-relay)
      grep -Eq 'FAIL:[[:space:]]*0' "$log"
      ;;
    09-http-ldaps)
      grep -Fq 'PHASE03_HTTP_LDAPS_PREFLIGHT_COMPLETE=True' "$log"
      ;;
    10-rickon)
      grep -Eq 'FAIL:[[:space:]]*0' "$log"
      ;;
    *)
      return 1
      ;;
  esac
}

audit_stage() {
  local id="$1" description="$2" severity="$3"
  shift 3
  local output="$EVIDENCE/$id.log" rc=0
  printf '\n[RUN] %s — %s\n' "$id" "$description"
  "$@" > "$output" 2>&1 || rc=$?
  if [[ "$rc" -eq 0 ]] && check_markers "$id" "$output"; then
    printf '[PASS] %s\n' "$description"
    printf 'PASS | %s | %s\n' "$id" "$description" >> "$SUMMARY"
    PASS=$((PASS+1))
  elif [[ "$severity" == optional ]]; then
    printf '[WARN] %s (rc=%d; optional local runtime configuration)\n' "$description" "$rc"
    printf 'WARN | %s | %s | rc=%s\n' "$id" "$description" "$rc" >> "$SUMMARY"
    WARN=$((WARN+1))
  else
    printf '[FAIL] %s (rc=%d)\n' "$description" "$rc" >&2
    printf 'FAIL | %s | %s | rc=%s\n' "$id" "$description" "$rc" >> "$SUMMARY"
    FAIL=$((FAIL+1))
  fi
  printf '      Log: %s\n' "$output"
}

north_playbook() {
  local name="$1"
  "$ANSIBLE" -i "$LAB_INVENTORY" -i "$INSTANCE_INVENTORY" \
    "$ROOT/ansible/$name"
}

north_readiness() {
  EVIDENCE="$EVIDENCE/phase03-readiness" bash scripts/validate-phase03-readiness.sh
}

echo '============================================================'
echo 'NORTH — PHASE 03 ALL-IN-ONE READ-ONLY PREFLIGHT'
echo '============================================================'
echo "Instance : $INSTANCE"
echo "Evidence : $EVIDENCE"
echo 'Scope    : Preconditions only; no exploitation or state-changing validation'

audit_stage 00-owner 'NORTH source + installed network ownership' required \
  bash scripts/course1-rollout.sh --installed "$PROVIDER"

# Refuse to query guests if source/ownership was not verified.
if (( FAIL != 0 )); then
  echo '[BLOCKED] Host ownership gate failed; subsequent checks not attempted' >&2
  printf 'PHASE03_READONLY_ACCEPTANCE=BLOCKED\n' >> "$SUMMARY"
  exit 1
fi

audit_stage 01-baseline 'Phase 03 network, poisoning, SMB/LDAP and MSSQL baseline' required \
  north_readiness
audit_stage 02-rbcd 'RBCD WS01$ rights + clean baseline' required \
  north_playbook phase03-rbcd-preflight.yml
audit_stage 03-shadow 'Shadow Credentials WS01$ + KDC certificate' required \
  north_playbook phase03-shadow-preflight.yml
audit_stage 04-adidns 'ADIDNS dynamic DNS and controlled record baseline' required \
  north_playbook phase03-adidns-preflight.yml
audit_stage 05-webdav 'WebDAV/WebClient and Rickon desktop state inspection' required \
  north_playbook phase03-webdav-shortcut-preflight.yml

# A missing interactive Explorer/RDP session is not a WebDAV fixture failure.
# Keep the prereq audit green while clearly separating interactive readiness.
if grep -Fq 'PASS | 05-webdav |' "$SUMMARY" &&
    grep -Fq 'PHASE03_WEBDAV_RICKON_EXPLORER=False' "$EVIDENCE/05-webdav.log"; then
  printf '[WARN] No live Rickon Explorer session; WebDAV victim-interaction proof still pending\n'
  printf 'WARN | 05-webdav-session | Rickon desktop interaction not active\n' >> "$SUMMARY"
  WARN=$((WARN+1))
fi
audit_stage 06-rdp-cert 'WS01 RDP certificate read-only inspection' required \
  north_playbook phase03-read-ws01-rdp-cert.yml
audit_stage 07-wpad-tools 'mitm6 / WPAD / relay runtime CLI capabilities' required \
  bash scripts/phase03/check-wpad-runtime-capabilities.sh
audit_stage 08-ldap-relay 'SMB → LDAPS relay operator prerequisites' required \
  bash scripts/phase03/check-ldap-readonly-relay.sh
audit_stage 09-http-ldaps 'HTTP → LDAPS relay operator prerequisites' required \
  bash scripts/phase03/check-http-ldaps-readonly-relay.sh

# This local victim-service contract depends on owner-only credential and RDP
# pin files, intentionally absent from Git. Report as unresolved separately.
audit_stage 10-rickon 'Optional headless Rickon victim-session prerequisites' optional \
  bash scripts/phase03/check-rickon-prereqs.sh

echo
echo '============================================================'
echo 'NORTH — PHASE 03 PREREQUISITE SUMMARY'
echo '============================================================'
cat "$SUMMARY"
printf '\nPASS: %d\nWARN: %d\nFAIL: %d\nEvidence: %s\n' "$PASS" "$WARN" "$FAIL" "$EVIDENCE"
echo 'PHASE03_ATTACK_CHAIN_ACCEPTANCE=NOT_TESTED'
if (( FAIL == 0 )); then
  echo 'PHASE03_READONLY_ACCEPTANCE=PASS' | tee -a "$SUMMARY"
  echo '[PASS] All required non-destructive Phase 03 gates passed.'
  if (( WARN != 0 )); then
    echo '[WARN] Optional local-runtime gates need review before active proof.'
  fi
  exit 0
fi
echo 'PHASE03_READONLY_ACCEPTANCE=FAIL' | tee -a "$SUMMARY"
echo '[NOT READY] Review failed-stage logs; nothing was reset or reprovisioned.' >&2
exit 1
