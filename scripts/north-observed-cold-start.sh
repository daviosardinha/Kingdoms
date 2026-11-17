#!/usr/bin/env bash
# One instrumented NORTH cold start, no snapshot/reset/provisioning/retry.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$ROOT"
if [[ $# != 3 || ! "$1" =~ ^[0-9a-f]{6}-north-vmware$ ||
      "$2" != --run || "$3" != --confirm-one-cold-start ]]; then
    echo "Usage: bash scripts/north-observed-cold-start.sh <id> --run --confirm-one-cold-start" >&2
    exit 2
fi
ID="$1"
PROVIDER="$ROOT/workspace/$ID/provider"
MODE="$PROVIDER/.goad-nomad-mode"
PY="$HOME/.goad/.venv/bin/python"
if [[ -v GOAD_PYTHON ]]; then PY="$GOAD_PYTHON"; fi
fail() { echo "[BLOCKED] $*" >&2; exit 1; }
for tool in sudo vmrun tcpdump timeout flock ip tar date; do
    command -v "$tool" >/dev/null || fail "Missing required command: $tool"
done
[[ -x "$PY" ]] || fail "Managed Python missing: $PY"
[[ -d "$PROVIDER" && ! -L "$PROVIDER" && ! -L "$MODE" &&
   "$(cat "$MODE" 2>/dev/null)" == exercise ]] ||
    fail "NORTH must be in recorded exercise mode"
[[ ! -L "$HOME/Kingdoms-evidence" ]] || fail "Evidence root is a symlink"
bash scripts/verify-test-source.sh
SHA="$(git rev-parse HEAD)"
"$PY" - "$ROOT/workspace/$ID" "$ID" <<'PY'
from pathlib import Path
import json, sys
base, ident = Path(sys.argv[1]), sys.argv[2]
meta = base / "instance.json"
assert meta.is_file() and not meta.is_symlink()
record = json.loads(meta.read_text())
assert (record.get("id"), record.get("lab"), record.get("provider"),
        record.get("status")) == (ident, "NORTH", "vmware", "installed")
for vm in ("GOAD-ROUTER", "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"):
    reg = base / "provider/.vagrant/machines" / vm / "vmware_desktop/id"
    assert reg.is_file() and not reg.is_symlink(), vm
    vmx = Path(reg.read_text().strip())
    assert vmx.is_file() and not vmx.is_symlink(), vm
    assert vmx.resolve().is_relative_to(reg.parent.resolve()), vm
print("[PASS] Installed NORTH VM registration proof")
PY
[[ ! -L "$PROVIDER/.course1-phase03-acceptance.lock" ]] ||
    fail "Unsafe lifecycle lock"
exec 9>"$PROVIDER/.course1-phase03-acceptance.lock"
flock -n 9 || fail "NORTH acceptance lock held by another process"
sudo -v
sudo -n bash scripts/setup-vmware-networks.sh --north verify \
    --provider-dir "$PROVIDER" >/dev/null ||
    fail "NORTH vmnet ownership not verified"
ip -4 -o addr show dev vmnet10 | grep -Fq "10.4.10.254/24" ||
    fail "NORTH vmnet10 host address absent"
mkdir -p -m 700 "$HOME/Kingdoms-evidence"
EVIDENCE="$(mktemp -d "$HOME/Kingdoms-evidence/north-observed-cold-start-XXXXXXXX")"
chmod 700 "$EVIDENCE"
CAP_PID=0
printf 'instance=%s\nsource=%s\nstatus=NOT_CERTIFIED\nstarted_utc=%s\n' \
    "$ID" "$SHA" "$(date -u +%FT%TZ)" > "$EVIDENCE/manifest.txt"
echo "[EVIDENCE] $EVIDENCE"
state() {
    {
        date -u
        printf 'recorded_mode='
        cat "$MODE" || true
        vmrun -T ws list || true
        ip -4 route show 10.4.20.0/24 || true
        for vm in GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01; do
            vmx="$(cat "$PROVIDER/.vagrant/machines/$vm/vmware_desktop/id")"
            printf '%s ' "$vm"
            grep -Ei '^ethernet0\.startConnected\s*=' "$vmx" || true
        done
    } > "$EVIDENCE/$1.txt" 2>&1
}
finish() {
    rc="$1"
    trap - EXIT INT TERM
    if (( CAP_PID != 0 )); then
        kill -TERM "$CAP_PID" 2>/dev/null || true
        wait "$CAP_PID" 2>/dev/null || true
    fi
    state final-state || true
    if [[ -s "$EVIDENCE/ntp.pcap" ]]; then
        tcpdump -nn -tttt -vvv -r "$EVIDENCE/ntp.pcap" \
            > "$EVIDENCE/ntp-decoded.txt" 2> "$EVIDENCE/ntp-decode-errors.txt" || true
        tcpdump -nn -q -r "$EVIDENCE/ntp.pcap" \
            > "$EVIDENCE/ntp-directions.txt" 2>/dev/null || true
    fi
    if (( rc != 0 )); then
        echo "status=FAILED; no automatic retry or recovery" >> "$EVIDENCE/manifest.txt"
    fi
    date -u +'%FT%TZ' >> "$EVIDENCE/end-utc.txt"
    tar -czf "$EVIDENCE.tar.gz" -C "$EVIDENCE" . || true
    echo "[EVIDENCE] $EVIDENCE"
    echo "[ARCHIVE] $EVIDENCE.tar.gz"
    exit "$rc"
}
trap 'finish "$?"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
stage() {
    label="$1"
    task="$2"
    echo "[RUN] $label"
    if ! ./goad.sh -t "$task" -l NORTH -p vmware -i "$ID" \
        > "$EVIDENCE/$label.log" 2>&1; then
        tail -n 80 "$EVIDENCE/$label.log" >&2
        echo "[FAIL] $label. Do not automatically retry." >&2
        return 1
    fi
    echo "[PASS] $label"
}
stage 01-baseline validate
grep -Fq '[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS' \
    "$EVIDENCE/01-baseline.log" || fail "Baseline failed"
state before-stop
stage 02-stop stop
running="$(vmrun -T ws list)" || fail "Cannot verify stopped VMs"
for vm in GOAD-ROUTER GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01; do
    vmx="$(cat "$PROVIDER/.vagrant/machines/$vm/vmware_desktop/id")"
    ! printf '%s\n' "$running" | grep -Fxq "$vmx" ||
        fail "NORTH VM still running: $vm"
done
[[ "$(cat "$MODE")" == exercise ]] || fail "Exercise mode changed"
state after-stop
# Capture NtpClient source UDP/123 (not /stripchart ephemeral-source traffic).
echo "[INFO] Passive vmnet10 UDP/123 capture starts before VM power-on"
sudo -n timeout --signal=INT --kill-after=5 1250 \
    tcpdump -i vmnet10 -n -U -s 0 -w - \
    'udp port 123 and (host 10.4.10.11 or host 10.4.10.22 or host 10.4.10.31)' \
    > "$EVIDENCE/ntp.pcap" 2> "$EVIDENCE/capture-stderr.txt" &
CAP_PID=$!
sleep 2
kill -0 "$CAP_PID" 2>/dev/null || fail "Packet capture exited before start"
[[ -s "$EVIDENCE/ntp.pcap" ]] || fail "Packet capture never initialized"
stage 03-start start
stage 04-acceptance validate
grep -Fq '[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS' \
    "$EVIDENCE/04-acceptance.log" || fail "Runtime acceptance missing"
grep -Fq 'instance status is installed' \
    "$EVIDENCE/04-acceptance.log" || fail "Installed status missing"
[[ "$(cat "$MODE")" == exercise ]] || fail "Exercise mode not preserved"
echo "status=PASS; one observed cold start accepted" >> "$EVIDENCE/manifest.txt"
echo "[PASS] NORTH_OBSERVED_COLD_START_1=PASS"
