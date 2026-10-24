#!/usr/bin/env bash
# Remove the temporary WebDAV DNS support record and any owner-created tombstone.
# Safe to rerun: if the retained Kerberos context is already gone, verify exact absence and return success.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
WORK="${WORK:-$HOME/.config/kingdoms/phase03-webdav-dns}"
ZONE="${ZONE:-north.sevenkingdoms.local}"
RECORD="${RECORD:-phase03-webdav}"
FQDN="$RECORD.$ZONE"
DNS_SERVER="${DNS_SERVER:-winterfell.north.sevenkingdoms.local}"
LDAP_URI="${LDAP_URI:-ldap://winterfell.north.sevenkingdoms.local}"
NODE_DN="DC=$RECORD,DC=$ZONE,CN=MicrosoftDNS,DC=DomainDnsZones,DC=north,DC=sevenkingdoms,DC=local"
KRB5_CONFIG_FILE="$WORK/krb5.conf"
TGT_CACHE="$WORK/webdav-dns.ccache"
UPDATE_FILE="$WORK/nsupdate-delete.txt"
RESET_VERIFY_PLAYBOOK="$ROOT/ansible/phase03-webdav-dns-reset-verify.yml"
DATA_INVENTORY="${KINGDOMS_PHASE03_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_PHASE03_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"

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

verify_reset() {
  local ansible_playbook="$1"

  ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" "$ansible_playbook" \
    -i "$DATA_INVENTORY" \
    -i "$PROVIDER_INVENTORY" \
    "$RESET_VERIFY_PLAYBOOK"
}

cd "$ROOT"

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || { echo "FAIL: ansible-playbook not found" >&2; exit 1; }

if [[ ! -f "$KRB5_CONFIG_FILE" || ! -f "$TGT_CACHE" ]]; then
  echo 'INFO: retained WebDAV DNS Kerberos context is absent; checking whether rollback already completed'
  verify_reset "$ANSIBLE_PLAYBOOK"
  echo 'PHASE03_WEBDAV_DNS_SUPPORT_ALREADY_CLEAN=True'
  echo 'PHASE03_WEBDAV_DNS_SUPPORT_ROLLBACK_COMPLETE=True'
  exit 0
fi

export KRB5_CONFIG="$KRB5_CONFIG_FILE"
export KRB5CCNAME="FILE:$TGT_CACHE"

cat >"$UPDATE_FILE" <<EOF
server $DNS_SERVER
zone $ZONE.
update delete $FQDN. A
send
answer
EOF

nsupdate -g -v "$UPDATE_FILE" || true

set +e
LDAP_RESULT="$(ldapsearch -LLL -Y GSSAPI -Q -H "$LDAP_URI" -b "$NODE_DN" -s base '(objectClass=dnsNode)' dn dNSTombstoned 2>&1)"
LDAP_RC=$?
set -e

if [[ "$LDAP_RC" -eq 0 ]]; then
  printf '%s\n' "$LDAP_RESULT"
  ldapdelete -Y GSSAPI -Q -H "$LDAP_URI" "$NODE_DN"
elif [[ "$LDAP_RC" -ne 32 ]]; then
  printf '%s\n' "$LDAP_RESULT" >&2
  echo "FAIL: could not determine WebDAV DNS node state" >&2
  exit 1
fi

ANSWER="$(dig @10.4.10.11 "$FQDN" A +time=2 +tries=1 +short || true)"
[[ -z "$ANSWER" ]] || { echo "FAIL: DNS still resolves to $ANSWER" >&2; exit 1; }

rm -rf -- "$WORK"

verify_reset "$ANSIBLE_PLAYBOOK"

echo 'PHASE03_WEBDAV_DNS_SUPPORT_ROLLBACK_COMPLETE=True'
