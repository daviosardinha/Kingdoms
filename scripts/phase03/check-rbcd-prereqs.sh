#!/usr/bin/env bash
# Read-only NORTH RBCD preflight. No directory object is changed.
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
PLAYBOOK="$ROOT/ansible/phase03-rbcd-preflight.yml"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"

find_ansible_playbook() {
  local c
  for c in \
    "$(command -v ansible-playbook 2>/dev/null || true)" \
    "$ROOT/.venv/bin/ansible-playbook" \
    "$ROOT/venv/bin/ansible-playbook" \
    "$HOME/.goad/.venv/bin/ansible-playbook" \
    "$HOME/.local/bin/ansible-playbook"; do
    [[ -n "$c" && -x "$c" ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

cd "$ROOT" || exit 1

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

echo '===== RBCD READ-ONLY PREFLIGHT ====='
echo 'Target: WS01$'
echo 'Candidate computer reserved for later proof: PHASE03RBCD$'
echo

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || {
  echo 'FAIL: ansible-playbook not found' >&2
  exit 1
}

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
"$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$PLAYBOOK"
