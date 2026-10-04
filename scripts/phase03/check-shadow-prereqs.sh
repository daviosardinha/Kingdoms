#!/usr/bin/env bash
# Read-only NORTH Shadow Credentials prerequisite assessment.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
PLAYBOOK="$ROOT/ansible/phase03-shadow-preflight.yml"
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

echo '===== SHADOW CREDENTIALS READ-ONLY PREFLIGHT ====='
echo 'Target: WS01$'
echo

if pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' >/dev/null; then
  echo 'FAIL: Phase 03 attack runtime is active; use a neutral state for preflight' >&2
  pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' || true
  exit 1
fi

NTLMRELAYX="$(command -v impacket-ntlmrelayx 2>/dev/null || command -v ntlmrelayx.py 2>/dev/null || true)"
[[ -n "$NTLMRELAYX" ]] || { echo 'FAIL: ntlmrelayx not found' >&2; exit 1; }
HELP="$("$NTLMRELAYX" -h 2>&1 || true)"
for option in --shadow-credentials --shadow-target --pfx-password --export-type --cert-outfile-path; do
  grep -Fq -- "$option" <<<"$HELP" || { echo "FAIL: ntlmrelayx missing $option" >&2; exit 1; }
done
echo 'PASS: installed ntlmrelayx exposes required Shadow Credentials options'

command -v certipy-ad >/dev/null 2>&1 || { echo 'FAIL: certipy-ad not found' >&2; exit 1; }
echo "PASS: $(certipy-ad -v 2>&1 | head -n1)"

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo 'FAIL: ansible-playbook not found' >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"
