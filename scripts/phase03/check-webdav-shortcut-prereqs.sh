#!/usr/bin/env bash
# Read-only WS01 WebDAV/.lnk/.url victim-interaction prerequisite assessment.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
PLAYBOOK="$ROOT/ansible/phase03-webdav-shortcut-preflight.yml"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"
WS01_IP="${WS01_IP:-10.4.10.31}"

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

echo '===== WEBDAV / SHORTCUT READ-ONLY PREFLIGHT ====='

if pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' >/dev/null; then
  echo 'FAIL: Phase 03 attack runtime is active; WebDAV preflight requires neutral state' >&2
  pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' || true
  exit 1
fi
echo 'PASS: neutral Phase 03 runtime'

echo
echo '===== KALI LISTENER STATE ====='

for port in 80 445; do
  if sudo ss -H -lnt 2>/dev/null | grep -Eq ":$port[[:space:]]"; then
    echo "WARN: TCP/$port already has a listener"
    sudo ss -H -lntp 2>/dev/null | grep -E ":$port[[:space:]]" || true
  else
    echo "PASS: TCP/$port is free"
  fi
done

echo
echo '===== KALI TOOL INVENTORY ====='

for tool_name in responder impacket-ntlmrelayx tcpdump curl python3; do
  if command -v "$tool_name" >/dev/null 2>&1; then
    echo "FOUND: $tool_name -> $(command -v "$tool_name")"
  else
    echo "NOT_FOUND: $tool_name"
  fi
done

echo
echo '===== RICKON HEADLESS SESSION ====='

if sudo ss -ntp 2>/dev/null | grep -q "$WS01_IP:3389"; then
  echo 'PASS: Kali has an active RDP connection to WS01'
else
  echo 'WARN: no active Kali RDP connection to WS01 was observed'
fi

echo
echo '===== WS01 WEBDAV / EXPLORER STATE ====='

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || {
  echo 'FAIL: ansible-playbook not found' >&2
  exit 1
}

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"

echo
echo '===== FINAL REPOSITORY STATE ====='
git status --short --branch
