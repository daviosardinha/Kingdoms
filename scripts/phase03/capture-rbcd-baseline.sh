#!/usr/bin/env bash
# Capture the exact pre-attack RBCD state locally before any mutation.
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
BASELINE="${BASELINE:-${KINGDOMS_PHASE03_RBCD_BASELINE:-$HOME/.config/kingdoms/phase03-rbcd-baseline.json}}"
PLAYBOOK="$ROOT/ansible/phase03-rbcd-baseline.yml"
DATA_INVENTORY="${KINGDOMS_PHASE03_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_PHASE03_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"

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
[[ "$BASELINE" == /* && ! -L "$BASELINE" ]] || { echo 'FAIL: baseline path must be absolute and not a symlink' >&2; exit 1; }
if [[ "$BASELINE" != "$HOME/.config/kingdoms/phase03-rbcd-baseline.json" && -e "$BASELINE" ]]; then
  echo "FAIL: baseline already exists, refusing overwrite: $BASELINE" >&2; exit 1
fi
export KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"

echo '===== CAPTURE RBCD BASELINE ====='

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

echo
echo '===== VERIFY LOCAL BASELINE ====='
test -f "$BASELINE" || { echo "FAIL: baseline file missing: $BASELINE" >&2; exit 1; }
stat -Lc 'owner=%U mode=%a size=%s' "$BASELINE"
python3 -m json.tool "$BASELINE"
