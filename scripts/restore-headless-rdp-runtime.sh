#!/usr/bin/env bash
# Explicit repair for the validated Kingdoms headless RDP runtime baseline.
# This is not part of normal lab execution. It restores known runtime drift:
# legacy WINTERFELL connect_bot disabled + permanent Rickon service active.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
PLAYBOOK="$ROOT/ansible/restore-headless-rdp-runtime.yml"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"
RICKON_SERVICE='kingdoms-phase03-rickon.service'

[[ "${1:-}" == '--confirm' ]] || {
  echo 'Usage: bash scripts/restore-headless-rdp-runtime.sh --confirm' >&2
  exit 2
}

cd "$ROOT"

bash scripts/verify-test-source.sh

ANSIBLE=''
for c in   "$(command -v ansible-playbook 2>/dev/null || true)"   "$HOME/.goad/.venv/bin/ansible-playbook"   "$ROOT/.venv/bin/ansible-playbook"; do
  [[ -n "$c" && -x "$c" ]] || continue
  ANSIBLE="$c"
  break
done
[[ -n "$ANSIBLE" ]] || { echo 'FAIL: ansible-playbook not found' >&2; exit 1; }

echo '===== RESTORE LEGACY CONNECT_BOT HEADLESS CONTRACT ====='
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"

echo
echo '===== ENSURE PERMANENT RICKON FIXTURE ====='
bash scripts/phase03/sync-ws01-rdp-pin.sh
systemctl --user start "$RICKON_SERVICE"

for attempt in $(seq 1 24); do
  if bash scripts/phase03/validate-rickon-session.sh; then
    echo 'KINGDOMS_HEADLESS_RDP_RUNTIME_RESTORED=True'
    exit 0
  fi
  echo "INFO: waiting for permanent Rickon session... attempt=$attempt/24"
  sleep 5
done

echo 'FAIL: permanent Rickon session did not recover within 120 seconds' >&2
systemctl --user status "$RICKON_SERVICE" --no-pager -l >&2 || true
exit 1
