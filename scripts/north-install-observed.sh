#!/usr/bin/env bash
# NORTH supervised install: full restricted logs, no uncontrolled retry.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
if [[ $# -eq 1 && "$1" == "--new" ]]; then
  CMD=(bash ./goad.sh -t install -l NORTH -p vmware)
elif [[ $# -eq 2 && "$1" == "--instance" && "$2" =~ ^[a-f0-9]{6}-north-vmware$ ]]; then
  CMD=(bash ./goad.sh -t install -l NORTH -p vmware -i "$2")
else
  echo "Usage: bash scripts/north-install-observed.sh {--new|--instance <NORTH-ID>}" >&2
  exit 2
fi
[[ "$EUID" -ne 0 ]] || { echo "[BLOCKED] Do not run as root" >&2; exit 2; }
bash scripts/verify-test-source.sh || exit 1
[[ ! -L "$HOME/Kingdoms-evidence" ]] || { echo "[BLOCKED] Symlinked evidence root" >&2; exit 2; }
mkdir -p -m 700 "$HOME/Kingdoms-evidence"
DIR="$(mktemp -d "$HOME/Kingdoms-evidence/north-observed-install-XXXXXXXX")"
chmod 700 "$DIR"
LOG="$DIR/installer.log"
SUMMARY="$DIR/summary.txt"
printf "source_sha=%s\nstarted_utc=%s\n" "$(git rev-parse HEAD)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$SUMMARY"
echo "[INFO] NORTH private installer log may include sensitive AD provisioning output"
echo "[EVIDENCE] $DIR"
set +e
"${CMD[@]}" 2>&1 | tee "$LOG"
STATUSES=("${PIPESTATUS[@]}")
set -e
RC="${STATUSES[0]}"
if (( STATUSES[1] != 0 )); then
  echo "[FAILED] Installer log could not be written completely" >&2
  RC=1
fi
printf "installer_exit=%s\nfinished_utc=%s\n" "$RC" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$SUMMARY"
if (( RC != 0 )); then
  {
    date -u
    echo "===== Running VMware machines ====="
    vmrun -T ws list || true
    echo "===== NORTH recovery event journals ====="
    for folder in "$ROOT"/workspace/*-north-vmware; do
      [[ -d "$folder" && ! -L "$folder" ]] || continue
      file="$folder/.north-install-recovery.jsonl"
      if [[ -f "$file" && ! -L "$file" ]]; then
        echo "instance=$(basename "$folder")"
        cat "$file"
      fi
    done
    echo "===== Recent installer errors ====="
    grep -Ei "\[FAIL\]|\[BLOCKED\]|\[ERROR\]|ERROR!|Error:|Traceback|refusing|failed|timed out|unreachable" "$LOG" | tail -n 100 || true
  } > "$DIR/failure-diagnostics.txt" 2>&1
  chmod 600 "$DIR/failure-diagnostics.txt"
  echo "[FAILED] NORTH installation rc=$RC"
  echo "[EVIDENCE] $DIR"
  echo "[BLOCKED] No automatic full installer replay or network cleanup."
  exit "$RC"
fi
echo "[PASS] NORTH_SUPERVISED_INSTALL_COMMAND_SUCCEEDED"
echo "[EVIDENCE] $DIR"
