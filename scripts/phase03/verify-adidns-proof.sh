#!/usr/bin/env bash
# Independently verify the controlled ADIDNS record in DNS and Active Directory.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
PLAYBOOK="$ROOT/ansible/phase03-adidns-verify.yml"
DATA_INVENTORY="${KINGDOMS_PHASE03_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_PHASE03_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"
DC_IP="${DC_IP:-10.4.10.11}"
FQDN="${FQDN:-phase03-adidns.north.sevenkingdoms.local}"
EXPECTED_IP="${EXPECTED_IP:-10.4.10.254}"

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

ANSWER="$(dig @"$DC_IP" "$FQDN" A +time=2 +tries=1 +short | tail -n1)"
echo "PHASE03_ADIDNS_VERIFY_DNS_ANSWER=$ANSWER"
[[ "$ANSWER" == "$EXPECTED_IP" ]] || { echo "FAIL: DNS answer does not match $EXPECTED_IP" >&2; exit 1; }

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo 'FAIL: ansible-playbook not found' >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"

echo 'PHASE03_ADIDNS_VERIFY_COMPLETE=True'
