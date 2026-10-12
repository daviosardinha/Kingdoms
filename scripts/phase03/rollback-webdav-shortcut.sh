#!/usr/bin/env bash
# Restore the WS01 WebDAV shortcut fixture and remove only ephemeral observer evidence.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-webdav-baseline.json}"
WORK="${WORK:-$HOME/.config/kingdoms/phase03-webdav}"
PLAYBOOK="$ROOT/ansible/phase03-webdav-shortcut-rollback.yml"
DATA_INVENTORY="${KINGDOMS_PHASE03_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_PHASE03_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"

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

echo '===== WEBDAV SHORTCUT ROLLBACK ====='

[[ -f "$BASELINE" ]] || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }
[[ "$(stat -Lc '%a' "$BASELINE")" == "600" ]] || { echo 'FAIL: baseline must be mode 600' >&2; exit 1; }

if sudo ss -H -lntp 2>/dev/null | grep -Eq ':80[[:space:]]'; then
  echo 'FAIL: TCP/80 observer is still running; stop it with Ctrl+C before rollback' >&2
  exit 1
fi

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo 'FAIL: ansible-playbook not found' >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"

rm -rf -- "$WORK"
[[ ! -e "$WORK" ]] || { echo "FAIL: WebDAV work directory remains: $WORK" >&2; exit 1; }

echo 'PASS: WebDAV observer/runtime evidence removed'
echo "INFO: exact baseline retained for audit: $BASELINE"
echo 'PHASE03_WEBDAV_ROLLBACK_COMPLETE=True'
