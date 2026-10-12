#!/usr/bin/env bash
# Reconcile a completed NORTH restore with a later successful read-only audit.
# Does not run git fetch, start/stop/reset guests, or modify network/AD.
set -Eeuo pipefail
umask 077
if [[ $# != 2 ]]; then
  echo 'Usage: bash scripts/course1-restart-finalize.sh <north-restart-acceptance-dir> <later-phase03-batch-dir>' >&2
  exit 2
fi
BASE="$HOME/Kingdoms-evidence"
RUN="$1"
POST="$2"
reject() { echo "[BLOCKED] Recovery evidence reconciliation: $*" >&2; exit 2; }
[[ "$RUN" == "$BASE"/north-restart-acceptance-* && "$POST" == "$BASE"/phase03-batch-* ]] ||
  reject 'both paths must be explicit Kingdoms evidence directories'
for dir in "$BASE" "$RUN" "$POST"; do
  [[ -d "$dir" && ! -L "$dir" ]] || reject "missing/symlink directory: $dir"
done
RUN="$(realpath -e "$RUN")"
POST="$(realpath -e "$POST")"
[[ "$RUN" == "$BASE"/north-restart-acceptance-* && "$POST" == "$BASE"/phase03-batch-* ]] ||
  reject 'evidence directory resolved outside allowed root'
OLD="$RUN/summary.txt"
NEW="$POST/summary.txt"
[[ -f "$OLD" && -f "$NEW" && ! -L "$OLD" && ! -L "$NEW" ]] ||
  reject 'missing or linked evidence summary'
[[ "$NEW" -nt "$OLD" ]] ||
  reject 'successful follow-up must occur after the original run'
grep -Fxq 'instance=ac9fda-north-vmware' "$OLD" ||
  reject 'wrong source instance'

for stage in 00-installed initial-readiness \
  cold-1-stop cold-1-start cold-1-readiness \
  cold-2-stop cold-2-start cold-2-readiness snapshot-restore; do
  grep -Fq "PASS | $stage |" "$OLD" ||
    reject "missing verified earlier stage: $stage"
done
grep -Fq 'FAIL | restored-readiness rc=1' "$OLD" ||
  reject 'original post-restore failure is not recorded'
grep -Fxq 'RESTART_RESTORE_RELIABILITY=NOT_CERTIFIED' "$OLD" ||
  reject 'original runner was not recorded as uncertified'
grep -Fq '[FAIL] NORTH source + installed network ownership (rc=1)' \
  "$RUN/restored-readiness.log" ||
  reject 'original failure was not the owner gate'

# Require positive evidence that the first stop was an external DNS fetch
# failure, not an actual VMware owner mismatch or failed AD prerequisite.
FAILED_BATCH="$(sed -n 's/^Evidence : //p' "$RUN/restored-readiness.log" | head -n1)"
[[ "$FAILED_BATCH" == "$BASE"/phase03-batch-* && -f "$FAILED_BATCH/00-owner.log" ]] ||
  reject 'missing original nested owner log'
grep -Fq 'Could not resolve host: github.com' "$FAILED_BATCH/00-owner.log" ||
  reject 'cannot prove the first stop was transient GitHub DNS'

grep -Fxq 'PHASE03_READONLY_ACCEPTANCE=PASS' "$NEW" ||
  reject 'later read-only restored state did not pass'
[[ "$(grep -Ec '^PASS \| [0-9][0-9]-' "$NEW")" == 11 ]] ||
  reject 'not all eleven required Phase 03 gates passed'
! grep -Eq '^FAIL \|' "$NEW" ||
  reject 'later audit contains a failed stage'
[[ -f "$POST/00-owner.log" ]] || reject 'later owner log missing'
grep -Fq '[PASS] NORTH source and installed VMnet ownership verified (read-only)' \
  "$POST/00-owner.log" ||
  reject 'later audit did not prove live installed owner'

# New file, do not modify either original evidence summary.
OUT="$RUN/reconciled-recovery-acceptance.txt"
[[ ! -e "$OUT" && ! -L "$OUT" ]] ||
  reject 'reconciliation evidence already exists; refusing overwrite'
{
  echo 'instance=ac9fda-north-vmware'
  echo "original_run=$RUN"
  echo "successful_post_restore_batch=$POST"
  echo 'original_failure=external_github_dns_during_repeated_online_source_fetch'
  echo 'NORTH_REPEATED_COLD_START=PASS'
  echo 'NORTH_SNAPSHOT_RESTORE=PASS'
  echo 'NORTH_POST_RESTORE_READINESS=PASS'
  echo 'RESTART_RESTORE_RELIABILITY=PASS'
  echo 'RECOVERY_EVIDENCE_RECONCILIATION=PASS'
  echo 'NOTE: Original runner remains NOT_CERTIFIED; this record reconciles independent follow-up evidence.'
} > "$OUT"
chmod 600 "$OUT"
cat "$OUT"
echo "Evidence: $OUT"
