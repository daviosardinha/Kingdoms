#!/usr/bin/env bash
# Start WebClient for the controlled WebDAV shortcut proof without changing startup mode.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-webdav-baseline.json}"
PLAYBOOK="$ROOT/ansible/phase03-webdav-client-runtime.yml"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"

find_ansible_playbook() {
  local candidate_file
  for candidate_file in \
    "$(command -v ansible-playbook 2>/dev/null || true)" \
    "$ROOT/.venv/bin/ansible-playbook" \
    "$ROOT/venv/bin/ansible-playbook" \
    "$HOME/.goad/.venv/bin/ansible-playbook" \
    "$HOME/.local/bin/ansible-playbook"; do
    [[ -n "$candidate_file" && -x "$candidate_file" ]] || continue
    printf '%s\n' "$candidate_file"
    return 0
  done
  return 1
}

cd "$ROOT"

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

[[ -f "$BASELINE" ]] || { echo "FAIL: WebDAV baseline missing: $BASELINE" >&2; exit 1; }

python3 - "$BASELINE" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
if d['WebClientState'] != 'Stopped' or d['WebClientStartMode'] != 'Manual':
    raise SystemExit('FAIL: unexpected WebClient baseline')
print('PASS: WebClient baseline is Stopped/Manual')
PY

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo "FAIL: ansible-playbook not found" >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$PLAYBOOK"
