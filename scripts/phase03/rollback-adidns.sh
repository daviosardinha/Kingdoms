#!/usr/bin/env bash
# Restore the reserved Phase 03 ADIDNS name using the original record owner's retained Kerberos context.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-adidns-baseline.json}"
WORK="${WORK:-$HOME/.config/kingdoms/phase03-adidns}"
ZONE="${ZONE:-north.sevenkingdoms.local}"
RECORD="${RECORD:-phase03-adidns}"
FQDN="$RECORD.$ZONE"
DC_IP="${DC_IP:-10.4.10.11}"
DNS_SERVER="${DNS_SERVER:-winterfell.north.sevenkingdoms.local}"
LDAP_URI="${LDAP_URI:-ldap://winterfell.north.sevenkingdoms.local}"
NODE_DN="DC=$RECORD,DC=$ZONE,CN=MicrosoftDNS,DC=DomainDnsZones,DC=north,DC=sevenkingdoms,DC=local"
KRB5_CONFIG_FILE="$WORK/krb5.conf"
TGT_CACHE="$WORK/adidns.ccache"
UPDATE_FILE="$WORK/nsupdate-delete.txt"
PLAYBOOK="$ROOT/ansible/phase03-adidns-rollback.yml"
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

echo '===== ADIDNS OWNER-CONTEXT ROLLBACK ====='

[[ -f "$BASELINE" ]] || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }
[[ "$(stat -Lc '%a' "$BASELINE")" == "600" ]] || { echo 'FAIL: baseline must be mode 600' >&2; exit 1; }

python3 - "$BASELINE" <<'PY'
import json, sys
data=json.load(open(sys.argv[1], encoding='utf-8'))
assert data['Zone']=='north.sevenkingdoms.local'
assert data['RecordName']=='phase03-adidns'
if data['RecordExists'] or data['NodeExists']:
    raise SystemExit('FAIL: automatic rollback is scoped only to an absent captured baseline')
print('PASS: captured ADIDNS baseline requires record/node absence')
PY

for cmd in dig nsupdate ldapsearch ldapdelete klist; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "FAIL: $cmd not found" >&2; exit 1; }
done

if command -v dpkg >/dev/null 2>&1; then
  if ! dpkg -s libsasl2-modules-gssapi-mit >/dev/null 2>&1; then
    echo 'FAIL: OpenLDAP GSSAPI SASL support is missing.' >&2
    echo 'Install it on Kali with:' >&2
    echo '  sudo apt install -y libsasl2-modules-gssapi-mit' >&2
    exit 1
  fi
fi

[[ -f "$KRB5_CONFIG_FILE" ]] || { echo "FAIL: retained Kerberos config missing: $KRB5_CONFIG_FILE" >&2; exit 1; }
[[ -f "$TGT_CACHE" ]] || { echo "FAIL: retained Hodor ticket cache missing: $TGT_CACHE" >&2; exit 1; }

export KRB5_CONFIG="$KRB5_CONFIG_FILE"
export KRB5CCNAME="FILE:$TGT_CACHE"

echo
echo '===== VERIFY RETAINED OWNER TICKET ====='
klist -c "$TGT_CACHE"

echo
echo '===== REMOVE LIVE DNS RECORD IF STILL PRESENT ====='
ANSWER="$(dig @"$DC_IP" "$FQDN" A +time=2 +tries=1 +short || true)"
if [[ -n "$ANSWER" ]]; then
  cat >"$UPDATE_FILE" <<EOF
server $DNS_SERVER
zone $ZONE.
update delete $FQDN. A
send
answer
EOF
  nsupdate -g -v "$UPDATE_FILE"
else
  echo 'PASS: authoritative DNS already has no A record'
fi

echo
echo '===== INSPECT BACKING DNSNODE AS ORIGINAL OWNER ====='

set +e
LDAP_RESULT="$(ldapsearch -LLL -Y GSSAPI -Q -H "$LDAP_URI" -b "$NODE_DN" -s base '(objectClass=dnsNode)' dn dNSTombstoned 2>&1)"
LDAP_RC=$?
set -e

if [[ "$LDAP_RC" -eq 0 ]]; then
  printf '%s\n' "$LDAP_RESULT"
  echo
  echo 'INFO: base-scope LDAP search returned the reserved dnsNode'
  echo 'INFO: deleting that exact node as its owner using Hodor Kerberos credentials'
  ldapdelete -Y GSSAPI -Q -H "$LDAP_URI" "$NODE_DN"
elif [[ "$LDAP_RC" -eq 32 ]] || grep -qi 'No such object' <<<"$LDAP_RESULT"; then
  echo 'PASS: backing dnsNode is already absent'
else
  printf '%s\n' "$LDAP_RESULT" >&2
  echo "FAIL: could not determine dnsNode state (ldapsearch RC=$LDAP_RC)" >&2
  exit 1
fi

echo
echo '===== EXACT BASELINE VERIFICATION ====='

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo 'FAIL: ansible-playbook not found' >&2; exit 1; }

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ANSIBLE_PLAYBOOK"   -i "$DATA_INVENTORY"   -i "$PROVIDER_INVENTORY"   "$PLAYBOOK"

ANSWER="$(dig @"$DC_IP" "$FQDN" A +time=2 +tries=1 +short || true)"
[[ -z "$ANSWER" ]] || { echo "FAIL: DNS still resolves to $ANSWER" >&2; exit 1; }

rm -rf -- "$WORK"

echo 'PASS: ADIDNS record/node restored to exact absent baseline'
echo 'PASS: retained Kerberos/update ephemera removed'
echo "INFO: baseline retained for audit: $BASELINE"
echo 'PHASE03_ADIDNS_ROLLBACK_COMPLETE=True'