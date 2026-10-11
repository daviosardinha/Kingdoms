#!/usr/bin/env bash
set -Eeuo pipefail

# Kingdoms Course 1 — one-command release engineering gate.
#
# This is an orchestrator, not an alternate installer. NEVER bypass the
# existing Kingdoms VMware provider or its NORTH fail-closed guard.
#
# The current revision intentionally supports read-only work only:
#  --all       full source+clean-host validation and all-five readiness report
#  --source    same report, without live host inspection
#  --plan      immediate source-only readiness report, no test execution
#  --deploy    fail closed until integration and live acceptance are implemented
#
# Adding a live action later requires a reviewed adapter to the existing
# transactional VMware setup, owned hostaddr unit install, native NORTH
# provider lifecycle, and a real post-install acceptance suite.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:---all}"
[[ $# -le 1 ]] || { echo '[ERROR] Only one mode is accepted' >&2; exit 2; }

case "$MODE" in
  --help|-h)
    cat <<'USAGE'
Kingdoms Course 1 — single-entrypoint development and release gate

Usage:
  bash scripts/course1-rollout.sh             # all existing tests + host gate + five-point readiness
  bash scripts/course1-rollout.sh --source    # same, no live clean-host inspection
  bash scripts/course1-rollout.sh --plan      # fast, read-only engineering status
  bash scripts/course1-rollout.sh --deploy    # BLOCKED until the missing runtime integrations are reviewed

A green source/host validator is not permission to install NORTH.
This command NEVER creates VMs, edits VMware networking, writes systemd
assets, provisions AD, or changes the firewall.
USAGE
    exit 0
    ;;
  --all|--source|--plan|--deploy) ;;
  *) echo "[ERROR] Unknown mode: $MODE" >&2; exit 2 ;;
esac

# The deployment entrypoint is deliberately unavailable while the native
# shared provider still treats NORTH as an unwired source-only profile.
# No child process, privilege prompt, VM/network action may precede this refusal.
if [[ "$MODE" == --deploy ]]; then
  echo '[BLOCKED] NORTH deployment remains disabled in the shared provider.' >&2
  echo '[NEXT] Finish and test the five runtime contracts before exposing deployment.' >&2
  exit 3
fi

if [[ "$MODE" == --all ]]; then
  bash scripts/validate-course1.sh
elif [[ "$MODE" == --source ]]; then
  bash scripts/validate-course1.sh --skip-host
fi

# Review source, not a mutable host flag. Any missing/ambiguous contract
# refuses release. This stage does not import or execute provider code.
python3 - "$ROOT" <<'PY'
import ast
from pathlib import Path
import sys

root = Path(sys.argv[1])
def source(name):
    path = root / name
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Missing/unsafe project source: " + name)
    return path.read_text(encoding="utf-8")

try:
    transaction = source("goad/course1_vmnet_transaction.py")
    hostaddr = source("goad/course1_hostaddrs.py")
    kingdoms = source("goad/provider/vagrant/vmware_kingdoms.py")
    nomad = source("goad/provider/vagrant/vmware_nomad.py")
    validator = source("scripts/validate-course1.sh")
    ast.parse(transaction)
    ast.parse(hostaddr)
    ast.parse(kingdoms)
    ast.parse(nomad)
except (RuntimeError, SyntaxError, OSError) as exc:
    print("[BLOCKED] Readiness audit cannot establish source identity:", exc, file=sys.stderr)
    sys.exit(2)

print("\n============================================================")
print("COURSE 1 — ALL FIVE ENGINEERING AND ACCEPTANCE GATES")
print("============================================================")
transaction_source = "execute_testable_network_transaction" in transaction
hostaddr_source = "render_hostaddr_assets" in hostaddr
unwired = "def _course1_unwired(self):" in kingdoms
goad_only = "return self.lab_name == 'GOAD'" in nomad
complete_validation = "unittest discover -s tests -p 'test_*.py'" in validator
items = (
    ("[01] VMware transaction + restart/rollback",
     "SOURCE READY / LIVE APPLY BLOCKED" if transaction_source else "SOURCE MISSING",
     "No reviewed live VMware/netmap callback adapter and real rollback acceptance"),
    ("[02] Managed .254 systemd persistence",
     "ASSET RENDERER READY / INSTALL BLOCKED" if hostaddr_source else "SOURCE MISSING",
     "No verified ownership-aware helper/service/timer installation transaction"),
    ("[03] Existing NORTH provider and installer",
     "BLOCKED" if unwired or goad_only else "REVIEW REQUIRED",
     "NORTH guard and GOAD-only lifecycle must not be bypassed"),
    ("[04] Full source and clean-host validation",
     "AUTOMATED" if complete_validation else "CONTRACT MISSING",
     "Run --all to execute; source/host checks do not prove deployed AD"),
    ("[05] First deployment + AD/SQL/Phase 03 acceptance",
     "NOT EXECUTED",
     "Requires wired provider, actual VMs and non-destructive runtime proof"),
)
for label, status, details in items:
    print(f"{label}: {status}")
    print(f"     {details}")
print("\n[SAFETY] No VMware, Vagrant, Ansible, IP or systemd modifications performed.")
print("[BLOCKED] Release is not install-ready; do not manually override the NORTH guard.")
sys.exit(3)
PY
