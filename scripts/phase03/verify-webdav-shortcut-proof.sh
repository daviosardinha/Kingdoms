#!/usr/bin/env bash
# Verify the Rickon shortcut and prove a WS01 request reached the Kali observer.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
WORK="${WORK:-$HOME/.config/kingdoms/phase03-webdav}"
HTTP_LOG="$WORK/http.log"
PCAP="$WORK/webdav-shortcut.pcap"
PLAYBOOK="$ROOT/ansible/phase03-webdav-shortcut-verify.yml"
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

[[ -f "$HTTP_LOG" ]] || { echo "FAIL: observer HTTP log missing: $HTTP_LOG" >&2; exit 1; }
[[ -f "$PCAP" ]] || { echo "FAIL: observer PCAP missing: $PCAP" >&2; exit 1; }

if grep -Fq '10.4.10.31' "$HTTP_LOG"; then
  echo 'PHASE03_WEBDAV_REMOTE_REQUEST=True'
  grep -F '10.4.10.31' "$HTTP_LOG" | tail -n 10
else
  echo 'FAIL: observer has no HTTP request from WS01 (10.4.10.31)' >&2
  echo 'INFO: keep the shortcut in place; we may need to refresh the Rickon Explorer desktop explicitly' >&2
  exit 1
fi

if [[ -s "$PCAP" ]]; then
  echo 'PHASE03_WEBDAV_TCP_EVIDENCE=True'
else
  echo 'FAIL: observer PCAP is empty' >&2
  exit 1
fi

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo 'FAIL: ansible-playbook not found' >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"

echo 'PHASE03_WEBDAV_VERIFY_COMPLETE=True'
