#!/usr/bin/env bash
set -Eeuo pipefail

# One-command, source-first Kingdoms Course 1 acceptance.
# This intentionally does NOT install a VM, create vmnets, set routes,
# start services, invoke Ansible against guests, or change any firewall.
# The only live host interaction is a READ-ONLY collision preflight.
#
# Usage: bash scripts/validate-course1.sh [--skip-host]
# Run after git pull --ff-only; source identity is checked, not updated.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SKIP_HOST=0
case "${1:-}" in
  "") ;;
  --skip-host|--source-only) SKIP_HOST=1 ;;
  -h|--help)
    cat <<'USAGE'
Kingdoms Course 1 — complete source/unit regression and host-readiness gate

Usage:
  bash scripts/validate-course1.sh
  bash scripts/validate-course1.sh --skip-host

Default runs all Python unit tests, all Course 1 source/topology/route/
VMware configuration previews (10.4 and independent 10.5 vmnets),
the original full-Kingdoms source acceptance contract, and a final
read-only collision check against the *clean, pre-install* Kali host.

--skip-host verifies source only (for CI, or after vmnets are installed).
A clean-host collision check is supposed to block on an installed lab.
No live Vagrant, Ansible, VM, systemd, or network mutations are performed.

First update your checkout: git pull --ff-only
USAGE
    exit 0 ;;
  *)
    echo "[ERROR] Unknown argument: $1" >&2
    echo "Usage: bash scripts/validate-course1.sh [--skip-host]" >&2
    exit 2 ;;
esac
if (( $# > 1 )); then
  echo "[ERROR] Too many arguments" >&2
  exit 2
fi

for binary in git python3 bash ruby; do
  if ! command -v "$binary" >/dev/null 2>&1; then
    echo "[BLOCKED] Required validation dependency missing: $binary" >&2
    exit 1
  fi
done

STARTED=$SECONDS
PASSED=0
STAGES=0
FAILURE=0
LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/kingdoms-course1-validate.XXXXXXXX")"
cleanup() {
  if (( FAILURE == 0 )); then
    rm -rf -- "$LOG_DIR"
  fi
}
trap cleanup EXIT

stage() {
  local name="$1"
  shift
  STAGES=$((STAGES + 1))
  local logfile="$LOG_DIR/$(printf '%02d' "$STAGES").log"
  printf '\n[%02d] %s\n' "$STAGES" "$name"
  if "$@" > "$logfile" 2>&1; then
    PASSED=$((PASSED + 1))
    printf '[PASS] %s\n' "$name"
    # Keep the terminal concise while showing the actual test count.
    if [[ "$name" == "All Kingdoms and Course 1 unit tests" ]]; then
      grep -E '^Ran [0-9]+ tests? in|^OK$' "$logfile" || true
    fi
  else
    local code=$?
    FAILURE=1
    printf '\n[FAIL] %s (exit %s)\n' "$name" "$code" >&2
    printf '[DETAILS] %s\n' "$logfile" >&2
    tail -n 100 "$logfile" >&2 || true
    printf '\n[SUMMARY] %d/%d stages passed in %ds\n' "$PASSED" "$STAGES" "$((SECONDS-STARTED))" >&2
    printf '[STOPPED] Fix this stage before any NORTH install; log directory: %s\n' "$LOG_DIR" >&2
    exit 1
  fi
}

check_python_source() {
  python3 - <<'PY'
from pathlib import Path

# Syntax only, without writing __pycache__ files or importing modules.
sources = list(Path("goad").rglob("*.py"))
sources += list(Path("tests").glob("test_*.py"))
sources += [Path("goad_nomad.py"), Path("goad.py")]
if not sources:
    raise SystemExit("No Kingdoms Python source found")
for path in sorted(set(sources)):
    compile(path.read_bytes(), str(path), "exec")
print(f"[PASS] {len(set(sources))} Python source files compile")
PY
}

check_shell_source() {
  local path
  local -a scripts=(
    scripts/validate-course1.sh
    scripts/setup-vmware-networks.sh
    scripts/check-vmware-networks.sh
    scripts/provisioning-routes.sh
    scripts/lab-mode.sh
    scripts/check-vmware-instance-conflicts.sh
    scripts/verify-test-source.sh
    scripts/validate-goad-kingdoms-install-source.sh
    scripts/validate-network-segmentation-source.sh
    ad/NORTH/providers/vmware/router/provision.sh
  )
  for path in "${scripts[@]}"; do
    [[ -f "$path" ]] || { printf '[FAIL] Missing %s\n' "$path"; return 1; }
    bash -n "$path" || return 1
  done
  printf '[PASS] %d Kingdoms entrypoints parse as Bash\n' "${#scripts[@]}"
}

check_ruby_source() {
  ruby -c ad/NORTH/providers/vmware/Vagrantfile
  ruby -c ad/GOAD/providers/vmware/Vagrantfile
}

alternate=(--network-base 10.5.0.0/16
           --vmnet north=11 --vmnet sevenkingdoms=21
           --vmnet management=98)

printf '============================================================\n'
printf 'KINGDOMS COURSE 1 — UNIFIED SOURCE & HOST VALIDATION\n'
printf '============================================================\n'
printf 'Branch: %s\n' "$(git branch --show-current)"
printf 'Commit: %s\n' "$(git rev-parse --short HEAD)"
printf 'Mode:   %s\n' "$([[ "$SKIP_HOST" == 1 ]] && echo SOURCE_ONLY || echo SOURCE_AND_CLEAN_HOST)"
printf 'Runtime VM creation and network writes: DISABLED\n'

stage "Git source-of-truth and upstream identity" bash scripts/verify-test-source.sh
stage "Python syntax: all Kingdoms modules and unit tests" check_python_source
stage "Bash syntax: Kingdoms and NORTH lifecycle entrypoints" check_shell_source
stage "Ruby syntax: NORTH and full Kingdoms Vagrantfiles" check_ruby_source

# Discover all test_*.py files automatically. New tests and new Course 1
# modules join this gate without another hand-edited unittest command.
stage "All Kingdoms and Course 1 unit tests" \
  python3 -m unittest discover -s tests -p 'test_*.py'

stage "NORTH static source and 21-play Ansible manifest" \
  python3 -m goad.course1_source_preflight
stage "Full Kingdoms clean-install source compatibility" \
  bash scripts/validate-goad-kingdoms-install-source.sh

stage "NORTH default topology 10.4" python3 -m goad.kingdoms_topology
stage "NORTH default five coherent VM/Ansible/router artifacts" \
  python3 -m goad.course1_artifact_render
stage "NORTH alternate topology 10.5" python3 -m goad.kingdoms_topology "${alternate[@]}"
stage "NORTH alternate coherent VM/Ansible/router artifacts" \
  python3 -m goad.course1_artifact_render "${alternate[@]}"

stage "Default parent-domain route preview" \
  bash scripts/provisioning-routes.sh --north plan
stage "Alternate parent-domain route preview" \
  bash scripts/provisioning-routes.sh --north plan "${alternate[@]}"
stage "Default additive VMware vmnet configuration preview" \
  bash scripts/setup-vmware-networks.sh --north plan
stage "Alternate additive VMware vmnet configuration preview" \
  bash scripts/setup-vmware-networks.sh --north plan "${alternate[@]}"
stage "Default safe host .254 repair unit preview" \
  bash scripts/setup-vmware-networks.sh --north hostaddr-plan
stage "Alternate safe host .254 repair unit preview" \
  bash scripts/setup-vmware-networks.sh --north hostaddr-plan "${alternate[@]}"

if (( SKIP_HOST )); then
  printf '\n[SKIP] Live clean-host collision check (--skip-host)\n'
else
  # The clean-host gate must be LAST: it is expected to block once an
  # independently owned lab's vmnets exist. Never modify anything here.
  stage "Live READ-ONLY clean-host vmnet/IP/VMX collision check" \
    python3 -m goad.course1_network_preflight
fi

printf '\n============================================================\n'
printf '[PASS] %d/%d validation stages passed in %ds\n' "$PASSED" "$STAGES" "$((SECONDS-STARTED))"
printf '[SOURCE] All unit tests, syntax, Kingdoms contracts and 10.4/10.5 previews validated\n'
if (( SKIP_HOST )); then
  printf '[HOST] Not checked (explicit source-only mode)\n'
else
  printf '[HOST] Clean-host network ownership checked read-only\n'
fi
printf '[SAFETY] NORTH install/start/reset remains BLOCKED until runtime wiring passes\n'
printf '============================================================\n'
