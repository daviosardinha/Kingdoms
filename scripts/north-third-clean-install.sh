#!/usr/bin/env bash
# Third clean NORTH installation after main integration: exact-instance destructive reset.
# Scope: 57bbec-north-vmware only. Preserve other VMware owners and networks.
# Existing lifecycle evidence in ~/Kingdoms-evidence is not modified.
set -Eeuo pipefail
umask 077

EXPECTED_ID="57bbec-north-vmware"
EXPECTED_BRANCH="main"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
INSTANCE="$ROOT/workspace/$EXPECTED_ID"
PROVIDER="$INSTANCE/provider"
PHASE="preflight"
LOGDIR=""
NEW_ID=""

die() { printf '[BLOCKED] %s\n' "$*" >&2; exit 1; }
stage() { PHASE="$1"; printf '\n===== %s =====\n' "$PHASE"; }
on_error() {
  result=$?
  printf '\n[FAILED] %s (exit %s)\n' "$PHASE" "$result" >&2
  if [[ -n "$LOGDIR" ]]; then
    printf '[EVIDENCE] %s\n' "$LOGDIR" >&2
  fi
  exit "$result"
}
trap on_error ERR

[[ "${1:-}" == "--confirm-third-install" && "$#" -eq 1 ]] ||
  die "Usage: bash scripts/north-one-shot-clean-reinstall.sh --confirm-third-install"
[[ "${EUID}" -ne 0 ]] || die "Run as desktop user, not root"
[[ "$PWD" == "$ROOT" ]] || die "Run from repository root: $ROOT"
[[ -d "$ROOT/.git" || -f "$ROOT/.git" ]] || die "Not a Git checkout"
[[ "$(git branch --show-current)" == "$EXPECTED_BRANCH" ]] ||
  die "Wrong Git branch; refusing destructive operation"
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] ||
  die "Working tree is dirty; preserve uncommitted work first"
[[ -x "$HOME/.goad/.venv/bin/python" ]] || die "Kingdoms Python virtualenv missing"
[[ -d "$INSTANCE" && ! -L "$INSTANCE" && -d "$PROVIDER" && ! -L "$PROVIDER" ]] ||
  die "Exact existing NORTH instance/provider not present"

# Source and provenance verification is completed BEFORE any destructive action.
# A complete other lab or a partially finished AD deployment is never destroyed.
stage "VERIFY SOURCE IS CLEAN AND EXACTLY origin/main"
bash scripts/verify-test-source.sh || die "Source is not synced with GitHub"
[[ "$(git branch --show-current)" == "main" ]] || die "Refusing non-main source"
[[ "$(git rev-parse HEAD)" == "$(git rev-parse refs/remotes/origin/main)" ]] ||
  die "HEAD is not the exact merged origin/main commit"

stage "VERIFY EXACT INSTALLED NORTH INSTANCE AND ALL OTHER VMWARE GUESTS"
export KINGDOMS_RESET_ROOT="$ROOT" KINGDOMS_RESET_ID="$EXPECTED_ID"
"$HOME/.goad/.venv/bin/python" - <<'PY'
import json
import os
import re
import subprocess
from pathlib import Path

root = Path(os.environ["KINGDOMS_RESET_ROOT"])
identity = os.environ["KINGDOMS_RESET_ID"]
instance = root / "workspace" / identity
provider = instance / "provider"
names = {"GOAD-ROUTER", "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"}
owned_nets = {"vmnet10", "vmnet20", "vmnet99"}

def require(condition, reason):
    if not condition:
        raise SystemExit("[BLOCKED] " + reason)

require(instance.resolve() == instance and provider.resolve() == provider,
        "NORTH instance path contains an unexpected symlink")
meta_path = instance / "instance.json"
require(meta_path.is_file() and not meta_path.is_symlink(), "Instance metadata missing/unsafe")
meta = json.loads(meta_path.read_text(encoding="utf-8"))
require((meta.get("id"), meta.get("lab"), meta.get("provider"), meta.get("status")) ==
        (identity, "NORTH", "vmware", "installed"),
        "Not the exact previously installed NORTH reference instance")
mode = provider / ".goad-nomad-mode"
require(mode.is_file() and not mode.is_symlink() and mode.read_text().strip() == "exercise",
        "Previous NORTH provider is not recorded in exercise mode")
receipt_dir = instance / "install-timings"
receipts = sorted(receipt_dir.glob("*.json")) if receipt_dir.is_dir() else []
require(len(receipts) == 1 and not receipts[0].is_symlink(),
        "Expected exactly one previous successful-install receipt")
receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
require(receipt.get("status") == "completed" and receipt.get("provider_success") is True,
        "Previous receipt does not prove a completed native NORTH install")

registrations = {}
base = provider / ".vagrant" / "machines"
if base.exists():
    for machine in base.iterdir():
        require(machine.is_dir() and machine.name in names, "Unexpected registered machine")
        ident = machine / "vmware_desktop" / "id"
        if not ident.exists():
            continue
        require(ident.is_file() and not ident.is_symlink(), "Unsafe Vagrant ID")
        path = Path(ident.read_text(encoding="utf-8").strip())
        require(path.is_absolute() and path.is_file() and not path.is_symlink()
                and path.resolve().is_relative_to(machine.resolve())
                and path.resolve().is_relative_to(provider.resolve()),
                "Foreign/missing VMX in instance registration: " + machine.name)
        registrations[machine.name] = path.resolve()

result = subprocess.run(["vmrun", "-T", "ws", "list"],
                        capture_output=True, text=True, timeout=25)
require(result.returncode == 0, "Cannot query VMware live inventory")
lines = [x.strip() for x in result.stdout.splitlines() if x.strip()]
require(lines and re.fullmatch(r"Total running VMs: \d+", lines[0]),
        "Ambiguous VMware running guest output")
require(len(lines) - 1 == int(lines[0].rsplit(":", 1)[1]),
        "VMware running guest count disagrees")
registered_paths = set(registrations.values())
for line in lines[1:]:
    require(Path(line).resolve() in registered_paths,
            "Another or unregistered VM is running: " + line)

inventory = Path.home() / ".vmware" / "inventory.vmls"
if inventory.exists():
    require(inventory.is_file() and not inventory.is_symlink(), "VMware library unsafe")
    for line in inventory.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.fullmatch(r'\s*vmlist\d+\.config\s*=\s*"([^"]+)"\s*', line)
        if not m:
            continue
        vmx = Path(m.group(1))
        if vmx.is_symlink():
            require(False, "Symlinked VMware library VMX requires review: " + str(vmx))
        if not vmx.is_file() or vmx.resolve().is_relative_to(provider.resolve()):
            continue
        contents = vmx.read_text(encoding="utf-8", errors="replace")
        attached = set(re.findall(
            r'^\s*ethernet\d+\.vnet\s*=\s*"(vmnet\d+)"',
            contents, re.I | re.M))
        require(not ({v.lower() for v in attached} & owned_nets),
                "Foreign registered powered-off VM depends on NORTH vmnet: " + str(vmx))

gui = subprocess.run(["pgrep", "-x", "vmware"], capture_output=True, text=True)
require(gui.returncode == 1,
        "Close VMware Workstation GUI before network retirement (or process check failed)")
print("[PASS] EXACT_INSTALLED_INSTANCE_AND_SUCCESS_RECEIPT")
print("[PASS] TARGET_REGISTERED_VMX=" + ",".join(sorted(registrations)))
print("[PASS] NO_RUNNING_FOREIGN_GUESTS")
print("[PASS] NO_REGISTERED_FOREIGN_NORTH_NETWORK_USERS")
print("[PASS] VMWARE_GUI_CLOSED")
PY

stage "ESTABLISH PRIVILEGED NETWORK RETIREMENT AUTHORIZATION"
sudo -v

LOGDIR="$(mktemp -d "$HOME/north-reset-XXXXXX")"
printf '[EVIDENCE] Private reset logs: %s\n' "$LOGDIR"
cp -p "$INSTANCE/instance.json" "$LOGDIR/old-instance.json"
printf '[SOURCE] %s\n' "$(git rev-parse HEAD)" > "$LOGDIR/source-commit.txt"
printf '[PREVIOUS_EVIDENCE] %s\n' "$HOME/Kingdoms-evidence/north-lifecycle-H73tfcMF" > "$LOGDIR/previous-diagnostics-reference.txt"
cp -p "$INSTANCE"/install-timings/*.json "$LOGDIR/"
run_logged() {
  printf '[EXEC]'
  printf ' %q' "$@"
  printf '\n'
  "$@" 2>&1 | tee -a "$LOGDIR/operations.log"
}

stage "DESTROY EXACT NORTH VAGRANT INSTANCE"
run_logged bash ./goad.sh -t destroy -l NORTH -p vmware -i "$EXPECTED_ID"

stage "VERIFY VMWARE DESTROY BEFORE TOUCHING HOST NETWORKING"
"$HOME/.goad/.venv/bin/python" - <<'PY'
import os
import subprocess
from pathlib import Path

root = Path(os.environ["KINGDOMS_RESET_ROOT"])
instance = root / "workspace" / os.environ["KINGDOMS_RESET_ID"]
provider = instance / "provider"
result = subprocess.run(["vmrun", "-T", "ws", "list"],
                        capture_output=True, text=True, timeout=25)
if result.returncode or result.stdout.strip() != "Total running VMs: 0":
    raise SystemExit("[BLOCKED] Cannot retire VMware networks while any VM runs")
proc = subprocess.run(["pgrep", "-x", "vmware-vmx"], capture_output=True)
if proc.returncode != 1:
    raise SystemExit("[BLOCKED] A VMware guest process still exists")
for machine in ("GOAD-ROUTER", "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"):
    ident = provider / ".vagrant" / "machines" / machine / "vmware_desktop" / "id"
    if ident.exists() or ident.is_symlink():
        raise SystemExit("[BLOCKED] Vagrant registration survived destroy: " + machine)
for file in provider.rglob("*"):
    if file.is_file() and file.suffix.lower() in (
        ".vmx", ".vmdk", ".vmsn", ".vmsd", ".vmem", ".nvram"
    ):
        raise SystemExit("[BLOCKED] Guest storage survived Vagrant destroy: " + str(file))
print("[PASS] ALL_VMS_STOPPED_AND_NO_OLD_GUEST_REGISTRATIONS")
print("[PASS] NO_GUEST_DISKS_REMAIN_IN_OWNED_PROVIDER")
PY

stage "PLAN EXACT NORTH NETWORK RETIREMENT (READ-ONLY)"
run_logged sudo env "PYTHONPATH=$ROOT" python3 -m goad.course1_network_retire plan --provider-dir "$PROVIDER"

stage "RETIRE EXACT OWNED NORTH VMNETS, PRESERVING FOREIGN CONFIGURATION"
run_logged sudo env "PYTHONPATH=$ROOT" python3 -m goad.course1_network_retire apply --provider-dir "$PROVIDER"

stage "VERIFY OLD OWNER AND NETWORKS ARE GONE"
"$HOME/.goad/.venv/bin/python" - <<'PY'
from pathlib import Path
import subprocess
owner = Path("/etc/vmware/kingdoms-course1-owner.json")
if owner.exists() or owner.is_symlink():
    raise SystemExit("[BLOCKED] Previous NORTH network owner survives retirement")
config = Path("/etc/vmware/networking").read_text(encoding="utf-8")
for number in (10,20,99):
    if any(line.startswith(f"answer VNET_{number}_") for line in config.splitlines()):
        raise SystemExit(f"[BLOCKED] vmnet{number} remains configured")
    if subprocess.run(["ip", "link", "show", "dev", f"vmnet{number}"],
                      capture_output=True).returncode == 0:
        raise SystemExit(f"[BLOCKED] vmnet{number} link remains")
if any(line.lstrip().startswith("add_nat_portfwd ") for line in config.splitlines()):
    raise SystemExit("[BLOCKED] NAT forwarding remains configured")
print("[PASS] OLD_NORTH_VMNET_OWNERSHIP_RETIRED")
print("[PASS] NO_OLD_NORTH_VMNET_LINKS_OR_NAT_FORWARDING")
PY

stage "REMOVE ONLY THE NOW-DESTROYED NORTH WORKSPACE"
"$HOME/.goad/.venv/bin/python" - <<'PY'
import json
import os
import shutil
from pathlib import Path
root = Path(os.environ["KINGDOMS_RESET_ROOT"])
instance = root / "workspace" / os.environ["KINGDOMS_RESET_ID"]
meta = json.loads((instance / "instance.json").read_text(encoding="utf-8"))
if meta.get("id") != instance.name or meta.get("lab") != "NORTH" or (
    instance.resolve() != instance or instance.is_symlink()
):
    raise SystemExit("[BLOCKED] Refusing unrelated workspace removal")
if any((instance / "provider" / ".vagrant" / "machines" / name /
        "vmware_desktop" / "id").exists() for name in (
        "GOAD-ROUTER", "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"
)):
    raise SystemExit("[BLOCKED] VMware machine IDs reappeared")
shutil.rmtree(instance)
if instance.exists():
    raise SystemExit("[BLOCKED] Old workspace removal incomplete")
print("[PASS] EXACT_PREVIOUS_NORTH_WORKSPACE_REMOVED")
PY

stage "ONE-COMMAND FRESH NORTH INSTALLATION"
run_logged bash ./goad.sh -t install -l NORTH -p vmware

stage "DISCOVER AND CHECK NEW INSTANCE STATE"
NEW_ID="$("$HOME/.goad/.venv/bin/python" - <<'PY'
import json
import os
from pathlib import Path
root = Path(os.environ["KINGDOMS_RESET_ROOT"]) / "workspace"
candidates = []
for p in root.iterdir():
    f = p / "instance.json"
    if not f.is_file() or f.is_symlink():
        continue
    j = json.loads(f.read_text(encoding="utf-8"))
    if j.get("lab") == "NORTH" and j.get("provider") == "vmware":
        candidates.append((p, j))
if len(candidates) != 1:
    raise SystemExit("[BLOCKED] Expected exactly one new NORTH instance")
p, state = candidates[0]
if (state.get("id") != p.name or p.name == os.environ["KINGDOMS_RESET_ID"]
        or state.get("status") != "installed"
        or (p / "provider" / ".goad-nomad-mode").read_text().strip() != "exercise"):
    raise SystemExit("[BLOCKED] New NORTH instance is not installed in exercise mode")
print(p.name)
PY
)"
printf '[PASS] NEW_NORTH_INSTANCE=%s\n' "$NEW_ID"
printf '%s\n' "$NEW_ID" > "$LOGDIR/new-instance-id"

stage "RUN NORTH RUNTIME ACCEPTANCE"
run_logged bash ./goad.sh -t validate -l NORTH -p vmware -i "$NEW_ID"
grep -Fq 'GOAD_NOMAD runtime validation passed; instance status is installed'   "$LOGDIR/operations.log" || die "Runtime validation did not report PASS"

stage "FINAL STATUS AND INSTALL RECEIPT"
run_logged bash ./goad.sh -t status -l NORTH -p vmware -i "$NEW_ID"
"$HOME/.goad/.venv/bin/python" - "$NEW_ID" <<'PY'
import json
import sys
from pathlib import Path
root = Path.cwd()
identity = sys.argv[1]
instance = root / "workspace" / identity
state = json.loads((instance / "instance.json").read_text())
mode = (instance / "provider" / ".goad-nomad-mode").read_text().strip()
receipts = list((instance / "install-timings").glob("*.json"))
successful = []
for receipt in receipts:
    content = json.loads(receipt.read_text())
    if content.get("provider_success") is True and content.get("status") == "completed":
        successful.append(receipt)
if state.get("status") != "installed" or mode != "exercise" or len(successful) != 1:
    raise SystemExit("[BLOCKED] Final metadata/mode/install receipt acceptance failed")
print("[PASS] NEW_NORTH_INSTALL_RECEIPT_COMPLETE")
print("[PASS] NORTH_STATUS_INSTALLED")
print("[PASS] NORTH_EXERCISE_MODE")
PY

stage "COMPLETE"
printf '[PASS] NORTH_FRESH_INSTALL_3=PASS\n'
printf '[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS\n'
printf '[INSTANCE] %s\n' "$NEW_ID"
printf '[EVIDENCE] %s\n' "$LOGDIR"
