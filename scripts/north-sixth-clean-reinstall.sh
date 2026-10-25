#!/usr/bin/env bash
# Reproduce NORTH from scratch; target ONLY the failed fifth bb3baf generation.
# This workflow is destructive to those five VMs. Preserve original backup.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
OLD="bb3baf-north-vmware"
INSTANCE="$ROOT/workspace/$OLD"
PROVIDER="$INSTANCE/provider"
REFERENCE="$HOME/Kingdoms-backups/8aafc9-north-l37plsk3"
PHASE="preflight"
EVIDENCE=""

abort() { echo "[BLOCKED] $*" >&2; exit 1; }
finish() {
  local rc=$?
  trap - EXIT
  if [[ -n "$EVIDENCE" ]]; then
    printf 'phase=%s\nexit_code=%s\nfinished_utc=%s\n' \
      "$PHASE" "$rc" "$(date -u +%FT%TZ)" >> "$EVIDENCE/summary.txt"
    echo "[EVIDENCE] $EVIDENCE"
  fi
  (( rc == 0 )) || echo "[FAILED] $PHASE: do not rerun destructive phases automatically" >&2
}
trap finish EXIT

if [[ $# != 2 || "$1" != "--run" ||
      "$2" != "--confirm-retire-bb3baf-and-reinstall" ]]; then
  echo "Usage: bash scripts/north-sixth-clean-reinstall.sh --run --confirm-retire-bb3baf-and-reinstall" >&2
  exit 2
fi
cd "$ROOT"
[[ "$EUID" -ne 0 && "$(git branch --show-current)" == "main" ]] ||
  abort "Must run as regular VMware desktop user on main"
[[ -d "$PROVIDER" && ! -L "$PROVIDER" && ! -L "$INSTANCE" ]] ||
  abort "Exact failed fifth NORTH provider absent or symlinked"
[[ -z "$(git status --porcelain --untracked-files=all)" ]] ||
  abort "Source checkout is dirty; preserve local files outside the repo first"
for tool in git python3 sudo vmrun vagrant flock pgrep sha256sum tee; do
  command -v "$tool" >/dev/null || abort "Missing prerequisite: $tool"
done
[[ -x "$HOME/.goad/.venv/bin/python" ]] || abort "Kingdoms Python venv absent"
[[ -d "$HOME/.goad" && ! -L "$HOME/.goad" &&
   ! -L "$HOME/.goad/.north-install-exclusive.lock" ]] ||
  abort "Shared NORTH installer lock path is unsafe"

# Cover all destructive phases with the same cross-checkout flock that
# goad_nomad.py uses. The fresh installer reacquires it after release.
exec 9>>"$HOME/.goad/.north-install-exclusive.lock"
flock -n 9 || abort "Another NORTH installer holds the lock"
if pgrep -af '[n]orth-install-observed.sh|[g]oad_nomad.py -t install|[v]agrant (up|provision|destroy)' >/dev/null; then
  abort "Another installer/Vagrant process is active"
fi
if pgrep -x vmware >/dev/null; then
  abort "Close VMware Workstation GUI before retiring NORTH host networking"
fi
[[ ! -L "$HOME/Kingdoms-evidence" && ! -L "$HOME/Kingdoms-backups" ]] ||
  abort "Evidence or backup root is symlinked"
[[ -f "$REFERENCE/backup-verified.marker" &&
   -f "$REFERENCE/other-artifacts.sha256" &&
   -f "$REFERENCE/instance/instance.json" &&
   ! -L "$REFERENCE" ]] ||
  abort "Verified original NORTH offline backup is missing"
( cd "$REFERENCE" && sha256sum -c other-artifacts.sha256 ) ||
  abort "Original offline backup source/host artifact hashes differ"
bash scripts/verify-test-source.sh || exit 1

# Exact metadata and all five Vagrant-registered VMX paths; no foreign running
# or powered-off VMware guest may depend on the NORTH-owned host networks.
export NORTH_RESET_ROOT="$ROOT" NORTH_RESET_ID="$OLD"
python3 - <<'PY'
import json, os, re, subprocess
from pathlib import Path
root=Path(os.environ["NORTH_RESET_ROOT"])
identity=os.environ["NORTH_RESET_ID"]
instance=root/"workspace"/identity
provider=instance/"provider"
def require(ok, msg):
    if not ok:
        raise SystemExit("[BLOCKED] " + msg)
meta=instance/"instance.json"
require(meta.is_file() and not meta.is_symlink(), "Exact NORTH instance metadata absent")
data=json.loads(meta.read_text())
require((data.get("id"),data.get("lab"),data.get("provider"),data.get("status")) ==
        (identity,"NORTH","vmware","not provided"),"NORTH instance/status mismatch")
owned=set()
for name in ("GOAD-ROUTER","GOAD-DC01","GOAD-DC02","GOAD-SRV02","GOAD-WS01"):
    reg=provider/".vagrant"/"machines"/name/"vmware_desktop"/"id"
    require(reg.is_file() and not reg.is_symlink(), "VMX ID absent: " + name)
    vmx=Path(reg.read_text().strip())
    require(vmx.is_absolute() and vmx.is_file() and not vmx.is_symlink() and
            vmx.resolve().is_relative_to(reg.parent.resolve()) and
            vmx.resolve().is_relative_to(instance.resolve()),"Foreign VMX: " + name)
    owned.add(str(vmx.resolve()))
require(len(owned)==5, "Five distinct original NORTH VMX files required")
r=subprocess.run(["vmrun","-T","ws","list"],capture_output=True,text=True,
                 check=True,timeout=45).stdout.splitlines()
require(bool(r) and re.fullmatch(r"Total running VMs: \d+",r[0].strip()),
        "VMware running inventory malformed")
require(int(r[0].rsplit(":",1)[1])==len(r)-1,"VMware running count mismatch")
require(all(str(Path(x.strip()).resolve()) in owned for x in r[1:]),
        "Foreign running VMware VM detected")
inv=Path.home()/".vmware"/"inventory.vmls"
if inv.exists():
    require(inv.is_file() and not inv.is_symlink(),"Unsafe VMware user VM inventory")
    for line in inv.read_text(errors="replace").splitlines():
        m=re.fullmatch(r'\s*vmlist\d+\.config\s*=\s*"([^"]+)"\s*',line)
        if not m: continue
        foreign=Path(m.group(1))
        require(not foreign.is_symlink(),"Symlinked VMX in inventory")
        if not foreign.is_file() or str(foreign.resolve()) in owned: continue
        attached=set(re.findall(r'^\s*ethernet\d+\.vnet\s*=\s*"(vmnet\d+)"',
                                foreign.read_text(errors="replace"),re.I|re.M))
        require(not attached.intersection({"vmnet10","vmnet20","vmnet99"}),
                "Foreign VMware VM uses owned NORTH vmnets: "+str(foreign))
print("[PASS] FAILED_FIFTH_NORTH_INSTANCE_AND_NO_FOREIGN_GUEST_CONFLICTS")
PY

sudo -v || exit 1
sudo -n env "NORTH_OLD_PROVIDER=$PROVIDER" python3 - <<'PY'
import json, os
from pathlib import Path
f=Path("/etc/vmware/kingdoms-course1-owner.json")
if not f.is_file() or f.is_symlink():
    raise SystemExit("[BLOCKED] NORTH network ownership receipt absent")
owner=json.loads(f.read_text())
if owner.get("profile")!="NORTH" or owner.get("provider")!=os.environ["NORTH_OLD_PROVIDER"]:
    raise SystemExit("[BLOCKED] Host network owner does not match the exact fifth instance")
print("[PASS] EXACT_NORTH_VMNET_OWNER")
PY

mkdir -p -m 700 "$HOME/Kingdoms-evidence"
EVIDENCE="$(mktemp -d "$HOME/Kingdoms-evidence/north-sixth-clean-XXXXXXXX")"
chmod 700 "$EVIDENCE"
printf 'original=%s\nsource=%s\nstarted_utc=%s\nverified_backup=%s\n' \
  "$OLD" "$(git rev-parse HEAD)" "$(date -u +%FT%TZ)" "$REFERENCE" > "$EVIDENCE/summary.txt"
echo "[EVIDENCE] $EVIDENCE"
mkdir -m 700 "$EVIDENCE/old-failure"
cp -p "$INSTANCE/instance.json" "$EVIDENCE/old-failure/"
if [[ -d "$INSTANCE/install-timings" ]]; then
  cp -a "$INSTANCE/install-timings" "$EVIDENCE/old-failure/"
fi
if [[ -f "$INSTANCE/.north-install-recovery.jsonl" ]]; then
  cp -p "$INSTANCE/.north-install-recovery.jsonl" "$EVIDENCE/old-failure/"
fi
echo "[PASS] PRIOR_FAILURE_EVIDENCE_PRESERVED"

stage() {
  PHASE="$1"
  shift
  echo "===== $PHASE ====="
  if "$@" 2>&1 | tee "$EVIDENCE/$PHASE.log"; then
    echo "PASS $PHASE" >> "$EVIDENCE/summary.txt"
  else
    abort "$PHASE failed"
  fi
}

stage 01-destroy-fifth bash ./goad.sh -t destroy -l NORTH -p vmware -i "$OLD"
PHASE="02-prove-fifth-destroy"
python3 - <<'PY'
import os, subprocess
from pathlib import Path
provider=Path(os.environ["NORTH_RESET_ROOT"])/"workspace"/os.environ["NORTH_RESET_ID"]/"provider"
running=subprocess.run(["vmrun","-T","ws","list"],capture_output=True,
                       text=True,check=True,timeout=45).stdout.strip()
if running!="Total running VMs: 0":
    raise SystemExit("[BLOCKED] Guest remains powered on")
for name in ("GOAD-ROUTER","GOAD-DC01","GOAD-DC02","GOAD-SRV02","GOAD-WS01"):
    reg=provider/".vagrant"/"machines"/name/"vmware_desktop"/"id"
    if reg.exists() or reg.is_symlink():
        raise SystemExit("[BLOCKED] Old VMware registration remains: "+name)
for f in provider.rglob("*"):
    if f.is_file() and f.suffix.lower() in (".vmx",".vmdk",".vmsd",".vmsn",".vmem",".nvram"):
        raise SystemExit("[BLOCKED] Old VM storage remains: "+str(f))
print("[PASS] ALL_FIFTH_NORTH_VMWARE_GUESTS_REMOVED")
PY

# Only retire owner-journal-verified vmnet10/20/99. The retirement module
# preserves vmnet2/8 and refuses unknown NAT rules/foreign vmnet declarations.
sudo -v || exit 1
stage 03-owner-retirement-plan sudo -n env "PYTHONPATH=$ROOT" \
  python3 -m goad.course1_network_retire plan --provider-dir "$PROVIDER"
grep -Fq '[PASS] NORTH_RETIREMENT_PLAN_READY' "$EVIDENCE/03-owner-retirement-plan.log" ||
  abort "Owned vmnet retirement plan readiness not proven"
stage 04-retire-north-vmnets sudo -n env "PYTHONPATH=$ROOT" \
  python3 -m goad.course1_network_retire apply --provider-dir "$PROVIDER"
grep -Fq '[PASS] NORTH_OWNED_NETWORKS_RETIRED' "$EVIDENCE/04-retire-north-vmnets.log" ||
  abort "NORTH-owned vmnets retirement not proven"

PHASE="05-archive-old-workspace"
[[ ! -L "$INSTANCE" && ! -L "$PROVIDER" &&
   -f "$INSTANCE/instance.json" ]] || abort "Old workspace changed before archive"
mv -- "$INSTANCE" "$EVIDENCE/retired-fifth-workspace"
[[ ! -e "$INSTANCE" ]] || abort "Old workspace remains in active workspace"
echo "[PASS] FAILED_FIFTH_WORKSPACE_ARCHIVED"

# Stock supervised installer acquires its own host-wide lock.
flock -u 9
exec 9>&-
stage 06-new-clean-install bash scripts/north-install-observed.sh --new

PHASE="07-sixth-receipt"
NEW_ID="$(python3 - <<'PY'
import json
from pathlib import Path
base=Path.cwd()/"workspace"
instances=[]
for p in base.glob("*-north-vmware"):
    f=p/"instance.json"
    if not f.is_file() or f.is_symlink(): continue
    s=json.loads(f.read_text())
    if s.get("lab")=="NORTH" and s.get("provider")=="vmware":
        instances.append((p,s))
if len(instances)!=1:
    raise SystemExit("[BLOCKED] Expected exactly one NORTH instance after reinstall")
p,s=instances[0]
mode=p/"provider"/".goad-nomad-mode"
if (p.name=="bb3baf-north-vmware" or s.get("id")!=p.name or
    s.get("status")!="installed" or not mode.is_file() or
    mode.read_text().strip()!="exercise"):
    raise SystemExit("[BLOCKED] New NORTH not installed/exercise")
receipts=list((p/"install-timings").glob("*.json"))
if len(receipts)!=1:
    raise SystemExit("[BLOCKED] New NORTH install receipt missing/ambiguous")
receipt=json.loads(receipts[0].read_text())
if (receipt.get("status")!="completed" or
    receipt.get("provider_success") is not True or
    receipt.get("instance_id")!=p.name):
    raise SystemExit("[BLOCKED] New NORTH provider/Ansible installation incomplete")
print(p.name)
PY
)"
echo "new_instance=$NEW_ID" | tee -a "$EVIDENCE/summary.txt"
stage 08-new-runtime-validation bash ./goad.sh -t validate -l NORTH -p vmware -i "$NEW_ID"
grep -Fq '[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS' "$EVIDENCE/08-new-runtime-validation.log" ||
  abort "New NORTH authenticated runtime acceptance not proven"
echo "[PASS] NORTH_SIXTH_FRESH_INSTALL_AND_RUNTIME=PASS"
echo "[NEW_INSTANCE] $NEW_ID"
