#!/usr/bin/env bash
# Single read-only NORTH readiness dashboard; never starts/stops/provisions guests.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
umask 077
REFRESH=0
case "${1:-}" in
  "") ;;
  --refresh) REFRESH=1 ;;
  -h|--help)
    cat <<'USAGE'
Usage: bash scripts/course1/check-install-readiness.sh [--refresh]

One NORTH installation-readiness command. Runs the full Kingdoms regression
and host/network survey once per clean Git commit. Later checks reuse the
passing source tests but resurvey real VMware host/network state each time.
--refresh forces the complete suite again. NEVER starts, stops or modifies VMs.
Detailed restricted logs: ~/.local/state/kingdoms/course1
USAGE
    exit 0 ;;
  *) echo "[FAIL] Usage: $0 [--refresh]" >&2; exit 1 ;;
esac

fail() { echo "[FAIL] $*" >&2; exit 1; }
for binary in git python3; do
  command -v "$binary" >/dev/null || fail "missing $binary"
done
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] ||
  fail "Git working tree is dirty; refusing cached validation"
HEAD="$(git rev-parse --verify HEAD)" || fail "cannot identify current commit"
UPSTREAM="$(git rev-parse --verify '@{upstream}' 2>/dev/null)" ||
  fail "no configured upstream"
[[ "$HEAD" == "$UPSTREAM" ]] || fail "local HEAD differs from upstream; git pull --ff-only"

STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/kingdoms/course1"
mkdir -p -m 0700 -- "$STATE_DIR"
[[ ! -L "$STATE_DIR" ]] || fail "refusing symlinked result directory"
chmod 0700 "$STATE_DIR"
CACHE="$STATE_DIR/offline-pass.txt"
LOG="$STATE_DIR/readiness-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
SNAPSHOT="$STATE_DIR/.snapshot-$$.json"
PHASE="$STATE_DIR/.phase-$$.json"
trap 'rm -f -- "$SNAPSHOT" "$PHASE"' EXIT

printf '\nKINGDOMS NORTH — INSTALLATION READINESS\n'
printf 'Commit: %.12s\n' "$HEAD"
printf 'Detailed log: %s\n\n' "$LOG"

CACHED=0
TESTS=unknown
if [[ "$REFRESH" == 0 && -f "$CACHE" && ! -L "$CACHE" ]]; then
  read -r SAVED_SHA SAVED_TESTS < "$CACHE" || true
  if [[ "${SAVED_SHA:-}" == "$HEAD" && "${SAVED_TESTS:-}" =~ ^[0-9]+$ ]]; then
    CACHED=1
    TESTS="$SAVED_TESTS"
  fi
fi

if [[ "$CACHED" == 0 ]]; then
  echo '[INFO] Running complete source regression + live VMware survey once...'
  if ! bash scripts/course1/validate-course1.sh --survey-host > "$LOG" 2>&1; then
    echo '[FAIL] Kingdoms validation failed; final details:' >&2
    tail -n 35 "$LOG" >&2
    exit 1
  fi
  read -r TESTS PHASE_RESULT < <(python3 - "$LOG" "$HEAD" <<'PY'
import re
import sys
from pathlib import Path
report = Path(sys.argv[1]).read_text(encoding="utf-8")
sha = sys.argv[2]
counts = re.findall(r"Ran (\d+) tests in [\d.]+s\s+OK", report)
if not counts or f"[PASS] All offline Course 1 validation gates passed at {sha}" not in report:
    raise SystemExit("[FAIL] Passing offline suite evidence is missing")
if '"reference_host_addresses_preserved": true' not in report:
    raise SystemExit("[FAIL] Reference addresses were not proved intact")
if '"registered_inventory_complete": true' not in report:
    raise SystemExit("[FAIL] Registered VMware inventory was incomplete")
phase = ("NORTH_HOST_ADDRESSES_READY"
         if '"status": "NORTH_HOST_ADDRESSES_READY"' in report else "NOT_READY")
print(counts[-1], phase)
PY
  ) || fail "Could not verify complete validation evidence; log: $LOG"
  if [[ "$PHASE_RESULT" != NORTH_HOST_ADDRESSES_READY ]]; then
    echo "[BLOCKED] NORTH host addresses not ready; log: $LOG"
    exit 2
  fi
  printf '%s %s\n' "$HEAD" "$TESTS" > "$CACHE"
  echo "[PASS] Offline source regression ($TESTS tests; Ruby/Bash/Ansible included)"
  echo '[PASS] NORTH vmnet11/12/13, .254 host addresses and reference protections'
else
  echo "[PASS] Offline source regression cached for unchanged commit ($TESTS tests)"
  echo '[INFO] Independently resurveying live host, registered VMX and IPs...'
  if ! python3 -m goad.course1_host_survey --check --json-only > "$SNAPSHOT" 2> "$LOG"; then
    echo '[FAIL] VMware host inventory incomplete:' >&2
    tail -n 25 "$LOG" >&2
    exit 1
  fi
  if ! python3 - "$SNAPSHOT" "$PHASE" >> "$LOG" 2>&1 <<'PY'
import json
import sys
from pathlib import Path
from goad.course1_vmnet_phase import inspect_network_phase
snapshot = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
plan = json.loads(Path("docs/course1-network-candidate.example.json").read_text(encoding="utf-8"))
phase = inspect_network_phase(plan, snapshot)
Path(sys.argv[2]).write_text(json.dumps(phase), encoding="utf-8")
if phase["status"] != "NORTH_HOST_ADDRESSES_READY":
    raise SystemExit("NORTH .254 host addresses not ready")
if not phase["reference_host_addresses_preserved"]:
    raise SystemExit("reference host addresses changed")
if not snapshot["registered_inventory"]["complete"]:
    raise SystemExit("VMware registered inventory incomplete")
print("[PASS] Current host/network state: " + phase["status"])
PY
  then
    echo '[FAIL] NORTH network/read-only collision check failed:' >&2
    tail -n 25 "$LOG" >&2
    exit 1
  fi
  echo '[PASS] NORTH vmnet11/12/13, .254 host addresses and reference protections'
fi

# Query the ACTUAL patched Kingdoms source gates, never a decorative checklist.
if ! python3 - <<'PY'
from goad.course_catalog import course_manifest, refuse_course_mutation
from goad.kingdoms_vmware_profile import binding_for
from goad.provider.provider_factory import ProviderFactory
from goad.provider.course_preview import PreviewCourseProvider
manifest = course_manifest("NORTH")
binding = binding_for("NORTH")
provider = ProviderFactory.get_provider("vmware", "NORTH", None)
if manifest["state"] != "PREVIEW_ONLY_NOT_INSTALLABLE":
    raise SystemExit("NORTH release status changed: inspect before deploying")
if not refuse_course_mutation("NORTH", "install"):
    raise SystemExit("NORTH instance creation unexpectedly authorized")
if binding.segmented_install_enabled or not isinstance(provider, PreviewCourseProvider):
    raise SystemExit("NORTH provider mutation guard differs from approved baseline")
print("[PASS] Original Kingdoms and NORTH install mutation protections intact")
PY
then
  fail "Release guards have changed unexpectedly; manual source review required"
fi

python3 - <<'PY'
import shutil
from pathlib import Path
p = Path("/proc/meminfo")
if p.exists():
    data = {}
    for line in p.read_text().splitlines():
        key, _, val = line.partition(":")
        if key in ("MemAvailable", "MemTotal"):
            data[key] = int(val.strip().split()[0]) // 1024
    available = data.get("MemAvailable")
    if available is not None:
        # 3000 + 3000 + 6000 + 4000 + 768 MB for NORTH's Vagrant guests.
        print(f"[INFO] RAM available: {available} MiB; NORTH guest allocation: ~16,768 MB")
        if available < 19000:
            print("[WARN] Low available RAM for concurrent reference + NORTH; check host capacity before installation")
free_gib = shutil.disk_usage(Path.cwd()).free // (1024**3)
print(f"[INFO] Free checkout-filesystem storage: {free_gib} GiB (VM disks may be elsewhere)")
if free_gib < 40:
    print("[WARN] Verify actual VMware VM storage; fewer than 40 GiB available on checkout mount")
PY

printf '\nINSTALLATION MILESTONES\n'
echo '[PASS] Native Kingdoms NORTH recipe, static regressions and host networks'
echo '[BLOCKED] Shared VMware install/start/stop provider still GOAD-only'
echo '[BLOCKED] NORTH NAT/AD readiness, WinRM and exercise isolation unproven'
echo '[BLOCKED] First disposable NORTH Vagrant/Ansible installation not attempted'
echo '[BLOCKED] SQL/Phase 03 live validation follows first successful installation'
printf '\nRESULT: NOT INSTALLABLE YET; no guest, host network, or installed lab was changed.\n'
printf 'Detailed log: %s\n' "$LOG"
exit 2
