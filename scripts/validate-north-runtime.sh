#!/usr/bin/env bash
# Read-only NORTH runtime acceptance. Never re-enters provisioning mode.
# Full six-Windows-VM KINGDOMS acceptance remains a separate, unchanged path.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PROVIDER="${GOAD_PROVIDER_DIR:-}"
fail() { printf '[BLOCKED] NORTH runtime: %s\n' "$*" >&2; exit 1; }
pass() { printf '[PASS] %s\n' "$*"; }

[[ "${GOAD_LAB_PROFILE:-}" == "NORTH" ]] || fail "GOAD_LAB_PROFILE must be NORTH"
[[ "$PROVIDER" == /* && -d "$PROVIDER" && ! -L "$PROVIDER" ]] ||
  fail "Missing exact absolute NORTH provider directory"
[[ -d "$ROOT/.git" ]] || fail "Not in the tracked KINGDOMS clone"

for cmd in python3 vmrun ip sudo ssh; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency $cmd"
done
[[ -x "$HOME/.goad/.venv/bin/ansible-playbook" ]] ||
  fail "Kingdoms Ansible environment missing"
[[ -f "$ROOT/ad/NORTH/data/inventory" &&
   -f "$(dirname "$PROVIDER")/inventory" &&
   -f "$ROOT/ansible/north-exercise-health-readonly.yml" ]] ||
  fail "NORTH inventory or read-only AD check missing"

echo "===== NORTH EXERCISE-MODE VALIDATION ====="
printf '[INFO] Provider: %s\n' "$PROVIDER"
printf '[INFO] No Vagrant up/down, host routes, NAT reconnection, AD repair or exercise-mode transition\n'

# Strict source and on-disk guest identity check before any WinRM traffic.
export KINGDOMS_NORTH_VALIDATOR_ROOT="$ROOT" KINGDOMS_NORTH_VALIDATOR_PROVIDER="$PROVIDER"
python3 - <<'PY'
import json
import os
import re
import subprocess
from pathlib import Path

root = Path(os.environ["KINGDOMS_NORTH_VALIDATOR_ROOT"])
provider = Path(os.environ["KINGDOMS_NORTH_VALIDATOR_PROVIDER"])
instance = provider.parent
expected = {
    "GOAD-DC01": ("vmnet20", "005056202010"),
    "GOAD-DC02": ("vmnet10", "005056201011"),
    "GOAD-SRV02": ("vmnet10", "005056201022"),
    "GOAD-WS01": ("vmnet10", "005056201031"),
}
names = set(expected) | {"GOAD-ROUTER"}
def check(value, message):
    if not value:
        raise SystemExit("[BLOCKED] " + message)

check(provider == (root / "workspace" / instance.name / "provider")
      and re.fullmatch(r"[a-f0-9]{6}-north-vmware", instance.name)
      and provider.resolve() == provider and instance.resolve() == instance
      and not provider.is_symlink(), "Provider identity is not canonical")
meta = instance / "instance.json"
check(meta.is_file() and not meta.is_symlink(), "Instance metadata absent or unsafe")
data = json.loads(meta.read_text(encoding="utf-8"))
check((data.get("id"), data.get("lab"), data.get("provider"), data.get("status")) ==
      (instance.name, "NORTH", "vmware", "installed"), "Instance is not installed NORTH")
mode_file = provider / ".goad-nomad-mode"
check(mode_file.is_file() and not mode_file.is_symlink()
      and mode_file.read_text(encoding="utf-8").strip() == "exercise",
      "Mode must remain exercise")
run = subprocess.run(["vmrun", "-T", "ws", "list"],
                     capture_output=True, text=True, timeout=20, check=False)
check(run.returncode == 0, "Unable to query VMware running guests")
lines = [x.strip() for x in run.stdout.splitlines() if x.strip()]
check(lines and re.fullmatch(r"Total running VMs: \d+", lines[0]),
      "VMware running inventory is ambiguous")
check(int(lines[0].split(":")[1]) == len(lines)-1,
      "VMware running inventory count is inconsistent")
running = {str(Path(p).resolve()) for p in lines[1:]}
for vm in names:
    ident = provider / ".vagrant" / "machines" / vm / "vmware_desktop" / "id"
    check(ident.is_file() and not ident.is_symlink(), f"{vm} VMware ID absent or unsafe")
    vmx = Path(ident.read_text(encoding="utf-8").strip())
    check(vmx.is_file() and not vmx.is_symlink()
          and vmx.resolve().is_relative_to(ident.parent.resolve()),
          f"{vm} registered VMX is missing/foreign")
    check(str(vmx.resolve()) in running, f"{vm} is not running")
    if vm not in expected:
        continue
    text = vmx.read_text(encoding="utf-8")
    config = dict((k.lower(), v) for k,v in re.findall(
        r'^\s*([\w.]+)\s*=\s*"([^"]*)"', text, re.M))
    vmnet, mac = expected[vm]
    actual_mac = re.sub(r'[^0-9a-f]', '', config.get("ethernet1.address", "").lower())
    check(config.get("ethernet0.startconnected", "").upper() == "FALSE",
          f"{vm} NAT adapter not persistently disabled")
    check(config.get("ethernet0.connectiontype", "").lower() == "nat"
          and config.get("ethernet1.connectiontype", "").lower() == "custom"
          and config.get("ethernet1.vnet", "") == vmnet and actual_mac == mac.lower(),
          f"{vm} canonical VMnet/MAC contract differs")
    print(f"[PASS] {vm}: exact VMX running, {vmnet}, persistent NAT off")
print("[PASS] NORTH_FIVE_OWNED_VMS_RUNNING")
print("[PASS] NORTH_INSTANCE_INSTALLED_EXERCISE")
PY

echo "===== NORTH HOST NETWORK OWNERSHIP ====="
sudo -v
sudo -n bash "$ROOT/scripts/setup-vmware-networks.sh" --north verify \
  --provider-dir "$PROVIDER" || fail "Installed NORTH host network ownership failed"
pass "NORTH_HOST_NETWORK_OWNER_VERIFIED"

echo "===== EXERCISE SEGMENTATION ====="
python3 - <<'PY'
import json
import subprocess

def check(cond, what):
    if not cond:
        raise SystemExit("[BLOCKED] " + what)
for dev, cidr in (("vmnet10", "10.4.10.254/24"), ("vmnet99", "10.4.99.254/24")):
    res = subprocess.run(["ip", "-j", "-4", "addr", "show", "dev", dev],
                         text=True, capture_output=True, check=False)
    check(res.returncode == 0, f"Host {dev} missing")
    records = json.loads(res.stdout)
    addrs = [f"{a['local']}/{a['prefixlen']}" for item in records
             for a in item.get("addr_info",[]) if a.get("family") == "inet"]
    check(cidr in addrs, f"Host {dev} address not canonical")
res = subprocess.run(["ip", "link", "show", "dev", "vmnet20"],
                     capture_output=True, check=False)
check(res.returncode != 0, "Protected vmnet20 host interface is exposed")
route = subprocess.run(["ip", "-j", "-4", "route", "show", "table", "all"],
                       capture_output=True, text=True, check=False)
check(route.returncode == 0, "Cannot inspect host routes")
routes = json.loads(route.stdout)
check(not any(r.get("dst") in ("10.4.20.0/24","10.4.30.0/24") for r in routes),
      "Temporary protected-zone host route remains")
print("[PASS] NORTH_HOST_ISOLATION_AND_NO_PROTECTED_ROUTES")
PY

router="$(GOAD_PROVIDER_DIR="$PROVIDER" bash "$ROOT/scripts/router-ssh.sh" \
  'sudo -n nft list chain inet goad_nomad forward')" ||
  fail "Router forwarding-chain attestation unavailable"
printf '%s\n' "$router" | grep -Fq 'policy drop;' ||
  fail "Router forward policy is not default-deny"
printf '%s\n' "$router" | grep -Eq 'ip saddr 10\.4\.10\.11 ip daddr 10\.4\.20\.10' ||
  fail "Missing child-to-parent DC exception"
printf '%s\n' "$router" | grep -Eq 'ip saddr 10\.4\.20\.10 ip daddr 10\.4\.10\.11' ||
  fail "Missing parent-to-child DC exception"
pass "NORTH_ROUTER_DENY_BY_DEFAULT_AND_DC_EXCEPTIONS"

echo "===== EXERCISE-SIDE HOST SERVICE READINESS ====="
python3 - <<'PY'
import socket
targets = [
    ("WINTERFELL WinRM", "10.4.10.11", 5986),
    ("WINTERFELL SMB", "10.4.10.11", 445),
    ("CASTELBLACK WinRM", "10.4.10.22", 5986),
    ("CASTELBLACK SMB", "10.4.10.22", 445),
    ("WS01 WinRM", "10.4.10.31", 5986),
    ("WS01 RDP", "10.4.10.31", 3389),
]
for label, ip, port in targets:
    try:
        with socket.create_connection((ip, port), timeout=5):
            pass
    except OSError as exc:
        raise SystemExit(f"[BLOCKED] {label} unavailable: {exc}")
    print(f"[PASS] {label}: {ip}:{port}")
PY

echo "===== NORTH READ-ONLY ACTIVE DIRECTORY VALIDATION ====="
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
temp_log="$(mktemp "${TMPDIR:-/tmp}/north-exercise-ad.XXXXXXXX.log")"
trap 'rm -f "$temp_log"' EXIT
(
  cd "$ROOT/ansible"
  "$HOME/.goad/.venv/bin/ansible-playbook" \
    -i "$ROOT/ad/NORTH/data/inventory" \
    -i "$(dirname "$PROVIDER")/inventory" \
    "$ROOT/ansible/north-exercise-health-readonly.yml"
) 2>&1 | tee "$temp_log" || fail "NORTH AD/domain-time health checks failed"
for host in WINTERFELL CASTELBLACK WS01; do
  grep -Fq "NORTH_EXERCISE_AD_HEALTH=PASS host=$host" "$temp_log" ||
    fail "Missing successful authenticated AD proof for $host"
done
pass "NORTH_AD_IDENTITY_TIME_TRUST_READY"

# Verify no validation operation has changed the recorded exercise state.
[[ "$(cat "$PROVIDER/.goad-nomad-mode")" == "exercise" ]] ||
  fail "Validation changed the recorded exercise mode"
pass "NORTH_EXERCISE_MODE_PRESERVED"
echo "[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS"
