#!/usr/bin/env bash
# Capture the exact pre-attack state for the temporary WebDAV DNS support record.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
PLAYBOOK="$ROOT/ansible/phase03-webdav-dns-baseline.yml"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-webdav-dns-baseline.json}"
DATA_INVENTORY="${KINGDOMS_PHASE03_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_PHASE03_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"

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
ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo "FAIL: ansible-playbook not found" >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$PLAYBOOK"

[[ -f "$BASELINE" ]] || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }
[[ "$(stat -Lc '%a' "$BASELINE")" == "600" ]] || { echo "FAIL: baseline must be mode 600" >&2; exit 1; }

python3 - "$BASELINE" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print(f"RECORD_EXISTS={d['RecordExists']}")
print(f"RECORD_COUNT={d['RecordCount']}")
print(f"NODE_EXISTS={d['NodeExists']}")
print(f"NODE_TOMBSTONED={d['NodeTombstoned']}")
if d['RecordExists'] or d['NodeExists']:
    raise SystemExit('FAIL: phase03-webdav DNS support name is not pristine')
print('PHASE03_WEBDAV_DNS_BASELINE_VALID=True')
PY
