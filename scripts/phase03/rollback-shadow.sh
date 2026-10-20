#!/usr/bin/env bash
# Restore WS01 msDS-KeyCredentialLink to the exact captured baseline and remove only Shadow Credentials ephemera.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-shadow-baseline.json}"
WORK="${WORK:-$HOME/.config/kingdoms/phase03-shadow}"
PLAYBOOK="$ROOT/ansible/phase03-shadow-rollback.yml"
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

echo '===== SHADOW CREDENTIALS ROLLBACK PREFLIGHT ====='
[[ -f "$BASELINE" ]] || { echo "FAIL: captured Shadow Credentials baseline missing: $BASELINE" >&2; exit 1; }
[[ "$(stat -Lc '%a' "$BASELINE")" == '600' ]] || { echo 'FAIL: baseline must be mode 600' >&2; exit 1; }

if pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' >/dev/null; then
  echo 'FAIL: Phase 03 poisoning/relay runtime is still active; stop it with Ctrl+C before rollback' >&2
  pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' || true
  exit 1
fi

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo 'FAIL: ansible-playbook not found' >&2; exit 1; }

echo 'PASS: exact captured baseline is available'
echo 'PASS: no Phase 03 relay/poisoning runtime remains'
echo

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"

echo
echo '===== REMOVE SHADOW CREDENTIALS EPHEMERA ====='
rm -rf -- "$WORK"
rm -f -- /tmp/kingdoms-shadow-relay.sh
[[ ! -e "$WORK" ]] || { echo "FAIL: Shadow Credentials work directory remains: $WORK" >&2; exit 1; }

echo 'PASS: generated certificate/private-key/password material removed'
echo "INFO: exact baseline retained for audit: $BASELINE"
echo 'PHASE03_SHADOW_ROLLBACK_COMPLETE=True'
