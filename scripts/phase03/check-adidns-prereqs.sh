#!/usr/bin/env bash
# Read-only NORTH ADIDNS prerequisite assessment. No DNS/AD object is modified.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
PLAYBOOK="$ROOT/ansible/phase03-adidns-preflight.yml"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"
DC_IP="${DC_IP:-10.4.10.11}"
ZONE="${ZONE:-north.sevenkingdoms.local}"
CANDIDATE="${CANDIDATE:-phase03-adidns}"

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

echo '===== ADIDNS READ-ONLY PREFLIGHT ====='
echo "ZONE=$ZONE"
echo "CANDIDATE=$CANDIDATE"
echo

if pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' >/dev/null; then
  echo 'FAIL: Phase 03 attack runtime is active; ADIDNS preflight requires neutral state' >&2
  pgrep -af '(^|[ /])(impacket-ntlmrelayx|ntlmrelayx[.]py|Responder[.]py|responder|mitm6)([ ]|$)' || true
  exit 1
fi
echo 'PASS: neutral Phase 03 runtime'

echo
echo '===== DNS REACHABILITY / READ-ONLY QUERIES ====='

if command -v dig >/dev/null 2>&1; then
  if dig @"$DC_IP" "$ZONE" SOA +time=2 +tries=1 +short | grep -q .; then
    echo "PASS: DNS SOA query answered by $DC_IP"
  else
    echo "WARN: no SOA answer from $DC_IP"
  fi

  WPAD_ANSWER="$(dig @"$DC_IP" "wpad.$ZONE" A +time=2 +tries=1 +short || true)"
  CANDIDATE_ANSWER="$(dig @"$DC_IP" "$CANDIDATE.$ZONE" A +time=2 +tries=1 +short || true)"

  [[ -n "$WPAD_ANSWER" ]] && echo "INFO: wpad.$ZONE resolves to $WPAD_ANSWER" || echo "INFO: wpad.$ZONE has no A answer"
  [[ -n "$CANDIDATE_ANSWER" ]] && echo "INFO: $CANDIDATE.$ZONE resolves to $CANDIDATE_ANSWER" || echo "PASS: $CANDIDATE.$ZONE has no A answer"
else
  echo 'WARN: dig is not installed; skipping direct DNS queries'
fi

echo
echo '===== KALI ADIDNS TOOL INVENTORY ====='

for tool_name in bloodyAD adidnsdump dnstool.py nsupdate ldapsearch; do
  if command -v "$tool_name" >/dev/null 2>&1; then
    echo "FOUND: $tool_name -> $(command -v "$tool_name")"
  else
    echo "NOT_FOUND: $tool_name"
  fi
done

for candidate_file in \
  "$HOME/krbrelayx/dnstool.py" \
  "$HOME/tools/krbrelayx/dnstool.py" \
  "/opt/krbrelayx/dnstool.py" \
  "/usr/share/krbrelayx/dnstool.py"; do
  [[ -f "$candidate_file" ]] && echo "FOUND_DNSTOOL=$candidate_file"
done

echo
echo '===== ACTIVE DIRECTORY / DNS SERVER PREFLIGHT ====='

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || {
  echo 'FAIL: ansible-playbook not found' >&2
  exit 1
}

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
"$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$PLAYBOOK"

echo
echo '===== FINAL REPOSITORY STATE ====='
git status --short --branch
