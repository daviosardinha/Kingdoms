#!/usr/bin/env bash
# Restore the controlled Phase 03 RBCD exercise to its exact captured AD baseline,
# then delete only the local ephemeral password/ticket material created by the lab.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
BASELINE="${BASELINE:-${KINGDOMS_PHASE03_RBCD_BASELINE:-$HOME/.config/kingdoms/phase03-rbcd-baseline.json}}"
SECRET_FILE="${SECRET_FILE:-$HOME/.config/kingdoms/phase03-rbcd-password}"
WORK="${WORK:-/tmp/kingdoms-phase03-rbcd-s4u}"
PLAYBOOK="$ROOT/ansible/phase03-rbcd-rollback.yml"
DATA_INVENTORY="${KINGDOMS_PHASE03_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_PHASE03_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"

find_ansible_playbook() {
  local c
  for c in     "$(command -v ansible-playbook 2>/dev/null || true)"     "$ROOT/.venv/bin/ansible-playbook"     "$ROOT/venv/bin/ansible-playbook"     "$HOME/.goad/.venv/bin/ansible-playbook"     "$HOME/.local/bin/ansible-playbook"; do
    [[ -n "$c" && -x "$c" ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

cd "$ROOT" || exit 1
[[ "$BASELINE" == /* && -f "$BASELINE" && ! -L "$BASELINE" ]] || {
  echo 'FAIL: rollback baseline must be an existing, absolute regular file' >&2; exit 1
}
export KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"

echo '===== RBCD ROLLBACK PREFLIGHT ====='
test -f "$BASELINE" || {
  echo "FAIL: captured RBCD baseline is missing: $BASELINE" >&2
  exit 1
}
[[ "$(stat -Lc '%a' "$BASELINE")" == "600" ]] || {
  echo 'FAIL: RBCD baseline must be mode 600' >&2
  exit 1
}

if pgrep -af '(^|[ /])mitm6([ ]|$)|(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py)([ ]|$)' >/dev/null; then
  echo 'FAIL: Phase 03 poisoning/relay runtime is still active; stop it before rollback' >&2
  pgrep -af '(^|[ /])mitm6([ ]|$)|(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py)([ ]|$)' || true
  exit 1
fi

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || {
  echo 'FAIL: ansible-playbook not found' >&2
  exit 1
}

echo 'PASS: exact captured baseline is available'
echo 'PASS: no mitm6/ntlmrelayx runtime remains'
echo

echo '===== RESTORE ACTIVE DIRECTORY BASELINE ====='
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"

echo
echo '===== REMOVE LOCAL EPHEMERAL MATERIAL ====='
rm -f -- "$SECRET_FILE"
rm -rf -- "$WORK"

[[ ! -e "$SECRET_FILE" ]] || {
  echo "FAIL: secret file still exists: $SECRET_FILE" >&2
  exit 1
}
[[ ! -e "$WORK" ]] || {
  echo "FAIL: S4U working directory still exists: $WORK" >&2
  exit 1
}

echo 'PASS: local PHASE03RBCD password removed'
echo 'PASS: local RBCD Kerberos caches and helper files removed'
echo "INFO: baseline retained for audit/verification: $BASELINE"
echo 'PASS: RBCD rollback complete'
