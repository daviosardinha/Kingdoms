#!/usr/bin/env bash
# Create the temporary hostname needed by Windows WebDAV semantics.
set -euo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
BASELINE="${BASELINE:-$HOME/.config/kingdoms/phase03-webdav-dns-baseline.json}"
WORK="${WORK:-$HOME/.config/kingdoms/phase03-webdav-dns}"
ZONE="${ZONE:-north.sevenkingdoms.local}"
RECORD="${RECORD:-phase03-webdav}"
FQDN="$RECORD.$ZONE"
TARGET_IP="${TARGET_IP:-10.4.10.254}"
DC_IP="${DC_IP:-10.4.10.11}"
DNS_SERVER="${DNS_SERVER:-winterfell.north.sevenkingdoms.local}"
REALM="${REALM:-NORTH.SEVENKINGDOMS.LOCAL}"
PRINCIPAL="${WEBDAV_DNS_PRINCIPAL:-hodor@$REALM}"
KRB5_CONFIG_FILE="$WORK/krb5.conf"
TGT_CACHE="$WORK/webdav-dns.ccache"
UPDATE_FILE="$WORK/nsupdate-add.txt"

cd "$ROOT"

bash "$ROOT/scripts/phase03/assert-wpad-exercise-clean.sh"

[[ -f "$BASELINE" ]] || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }
python3 - "$BASELINE" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
if d['RecordExists'] or d['NodeExists']:
    raise SystemExit('FAIL: support name existed in captured baseline')
print('PASS: WebDAV DNS support baseline is empty')
PY

for cmd in kinit klist nsupdate dig; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "FAIL: $cmd not found" >&2; exit 1; }
done

if dig @"$DC_IP" "$FQDN" A +time=2 +tries=1 +short | grep -q .; then
  echo "FAIL: $FQDN already resolves" >&2
  exit 1
fi

umask 077
rm -rf "$WORK"
mkdir -p "$WORK"

cat >"$KRB5_CONFIG_FILE" <<EOF
[libdefaults]
 default_realm = $REALM
 dns_lookup_kdc = false
 dns_lookup_realm = false
 rdns = false

[realms]
 $REALM = {
  kdc = $DC_IP
 }

[domain_realm]
 .$ZONE = $REALM
 $ZONE = $REALM
EOF

export KRB5_CONFIG="$KRB5_CONFIG_FILE"
export KRB5CCNAME="FILE:$TGT_CACHE"

echo "PRINCIPAL=$PRINCIPAL"
echo 'INFO: kinit will prompt for the lab password; it is not stored by this script.'
kinit "$PRINCIPAL"
klist -c "$TGT_CACHE"

cat >"$UPDATE_FILE" <<EOF
server $DNS_SERVER
zone $ZONE.
update add $FQDN. 300 A $TARGET_IP
send
answer
EOF

nsupdate -g -v "$UPDATE_FILE"
ANSWER="$(dig @"$DC_IP" "$FQDN" A +time=2 +tries=1 +short | tail -n1)"
echo "PHASE03_WEBDAV_DNS_ANSWER=$ANSWER"
[[ "$ANSWER" == "$TARGET_IP" ]] || { echo "FAIL: expected $TARGET_IP" >&2; exit 1; }
echo 'PHASE03_WEBDAV_DNS_SUPPORT_CREATED=True'
