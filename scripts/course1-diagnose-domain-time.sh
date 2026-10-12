#!/usr/bin/env bash
# NORTH restart failure: non-mutating W32Time and AD time-authority diagnosis.
# Does not start/stop guests, sync clocks, configure Windows services or change routing.
set -uo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2
if [[ $# -ne 1 || ! "$1" =~ ^[a-zA-Z0-9_-]+-north-vmware$ ]]; then
    echo 'Usage: bash scripts/course1-diagnose-domain-time.sh <existing-NORTH-instance-id>' >&2
    exit 2
fi

INSTANCE="$1"
PROVIDER="$ROOT/workspace/$INSTANCE/provider"
KINGDOMS_DIAG_DATA_INVENTORY="$ROOT/ad/NORTH/data/inventory"
KINGDOMS_DIAG_PROVIDER_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"
export ROOT KINGDOMS_DIAG_DATA_INVENTORY KINGDOMS_DIAG_PROVIDER_INVENTORY
for path in "$PROVIDER" "$KINGDOMS_DIAG_DATA_INVENTORY" "$KINGDOMS_DIAG_PROVIDER_INVENTORY"; do
    [[ -e "$path" ]] || { echo "[BLOCKED] Missing installed NORTH input: $path" >&2; exit 2; }
done

EVIDENCE="$HOME/Kingdoms-evidence/north-domain-time-$(date +%Y%m%d-%H%M%S)"
mkdir -p -m 700 "$EVIDENCE"
SUMMARY="$EVIDENCE/summary.txt"
: > "$SUMMARY"
PASS=0
FAIL=0

diagnose() {
    local id="$1" title="$2" file="$3" rc=0
    local logfile="$EVIDENCE/$id.log"
    printf '\n[RUN] %s\n' "$title"
    if [[ "$id" == 00-network ]]; then
        timeout 45 bash "$file" status > "$logfile" 2>&1 || rc=$?
    else
        timeout 210 bash "$file" > "$logfile" 2>&1 || rc=$?
    fi
    if (( rc == 0 )) && { [[ "$id" == 00-network ]] && grep -Fq "GOAD_NOMAD LAB MODE" "$logfile" ||
        grep -Eq 'KINGDOMS_.*_TIME_DIAGNOSTIC_COMPLETE=True|KINGDOMS_NORTH_TIMESERV_DIAGNOSTIC_COMPLETE=True' "$logfile"; }; then
        echo "[PASS] $title"
        printf 'PASS | %s | %s\n' "$id" "$title" >> "$SUMMARY"
        PASS=$((PASS+1))
    else
        echo "[FAIL] $title (rc=$rc); this is diagnostic reachability, not proof of AD damage" >&2
        printf 'FAIL | %s | %s | rc=%s\n' "$id" "$title" "$rc" >> "$SUMMARY"
        FAIL=$((FAIL+1))
    fi
    echo "      Log: $logfile"
}

echo '============================================================'
echo 'KINGDOMS NORTH — DOMAIN TIME RESTART DIAGNOSIS (READ ONLY)'
echo '============================================================'
echo "Instance: $INSTANCE"
echo "Evidence: $EVIDENCE"
echo 'No repairs, restarts, time resyncs, snapshots or routing changes are attempted.'

# Snapshot recovery was interrupted mid-isolation; record actual router/NAT
# state without trying to repair, reset, restart or transition any adapter.
GOAD_LAB_PROFILE=NORTH
GOAD_PROVIDER_DIR="$PROVIDER"
export GOAD_LAB_PROFILE GOAD_PROVIDER_DIR
diagnose 00-network 'Current router forwarding, protected routes and Windows NAT state' \
    scripts/lab-mode.sh

diagnose 01-srv02 'CASTELBLACK identity, secure channel and W32Time' \
    scripts/diagnostics/diagnose-srv02-domain-time.sh
diagnose 02-north 'WINTERFELL and CASTELBLACK time advertising comparison' \
    scripts/diagnostics/diagnose-north-timeserv-advertising.sh
diagnose 03-root 'KINGSLANDING and WINTERFELL forest time hierarchy' \
    scripts/diagnostics/diagnose-forest-root-time.sh

echo
echo '============================================================'
echo 'DIAGNOSTIC COLLECTION SUMMARY'
echo '============================================================'
cat "$SUMMARY"
printf 'PASS: %d\nFAIL: %d\nEvidence: %s\n' "$PASS" "$FAIL" "$EVIDENCE"
echo 'NOTE: A diagnostic collection PASS is not a domain-time readiness PASS.'
if (( FAIL != 0 )); then
    echo '[ATTENTION] One or more diagnostics could not complete. Inspect their logs.'
    exit 1
fi
echo '[PASS] Read-only diagnostic evidence collected.'
exit 0
