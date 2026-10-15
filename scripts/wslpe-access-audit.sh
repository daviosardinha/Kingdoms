#!/usr/bin/env bash
# Read-only WSLPE access evidence through the existing trusted Ansible plane.
# No Windows/VMware configuration writes, lifecycle calls, or NORTH access.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$HOME/.goad/.venv/bin/python"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
[[ -x "$PY" && -x "$ANSIBLE" ]] || {
  echo '[BLOCKED] Existing GOAD/Kingdoms Python and Ansible environment missing'
  exit 1
}
cd "$ROOT"
"$PY" -m unittest discover -s tests -p 'test_wslpe_access_audit.py' -v

# Resolve only the native, unique, operator-owned WSLPE instance. Never
# hardcode a previous instance ID or accept a NORTH inventory here.
INVENTORY="$("$PY" - <<'PY'
import importlib.util
from pathlib import Path
root = Path.cwd()
path = root / 'scripts/wslpe-stage2-inspect.py'
spec = importlib.util.spec_from_file_location('wslpe_access_loader', path)
if spec is None or spec.loader is None:
    raise SystemExit('[BLOCKED] Native WSLPE state inspector missing')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
instance, metadata = mod.find_instance(mod.WORKSPACE)
vmx = mod.locate_registered_vm(instance)
inventory = instance / 'inventory'
if not inventory.is_file() or inventory.is_symlink():
    raise SystemExit('[BLOCKED] WSLPE native operator inventory missing')
if metadata.get('lab') != 'WSLPE' or not vmx.is_file():
    raise SystemExit('[BLOCKED] WSLPE native identity unverified')
print(inventory)
PY
)"
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
echo 'KINGDOMS WSLPE | SOURCE-BASED READ-ONLY ACCESS AUDIT'
"$ANSIBLE" \
  -i "$INVENTORY" \
  -i "$ROOT/ad/WSLPE/data/inventory_disable_vagrant" \
  --limit ws01 \
  "$ROOT/ansible/wslpe-access-audit.yml"
echo '[NOT VERIFIED] HTTPS certificate trust, authenticated HTTPS, learner RDP and NAT exercise cutover'
