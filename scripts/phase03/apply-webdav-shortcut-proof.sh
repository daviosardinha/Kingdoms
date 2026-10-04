#!/usr/bin/env bash
# Deploy the controlled Rickon .lnk after the HTTP observer is already listening.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-webdav-baseline.json}"
PLAYBOOK="$ROOT/ansible/phase03-webdav-shortcut-apply.yml"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"

find_ansible_playbook() {
  local candidate_file
  for candidate_file in     "$(command -v ansible-playbook 2>/dev/null || true)"     "$ROOT/.venv/bin/ansible-playbook"     "$ROOT/venv/bin/ansible-playbook"     "$HOME/.goad/.venv/bin/ansible-playbook"     "$HOME/.local/bin/ansible-playbook"; do
    [[ -n "$candidate_file" && -x "$candidate_file" ]] || continue
    printf '%s\n' "$candidate_file"
    return 0
  done
  return 1
}

cd "$ROOT"

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

[[ -f "$BASELINE" ]] || { echo "FAIL: WebDAV baseline missing: $BASELINE" >&2; exit 1; }
[[ "$(stat -Lc '%a' "$BASELINE")" == "600" ]] || { echo 'FAIL: baseline must be mode 600' >&2; exit 1; }

python3 - "$BASELINE" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding='utf-8'))
assert d['Target']=='WS01'
assert d['User']=='NORTH\\rickon.stark'
if d['CandidateLnkExists'] or d['CandidateUrlExists']:
    raise SystemExit('FAIL: reserved shortcut existed in captured baseline')
print('PASS: exact absent shortcut baseline confirmed')
PY

if ! sudo ss -H -lntp 2>/dev/null | grep -Eq ':80[[:space:]]'; then
  echo 'FAIL: no TCP/80 observer is listening; run scripts/phase03/start-webdav-shortcut-observer.sh first' >&2
  exit 1
fi

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo 'FAIL: ansible-playbook not found' >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"
