#!/usr/bin/env bash
# NORTH-only router SSH bound to an instance provider, never reference GOAD.
set -Eeuo pipefail
provider="${GOAD_PROVIDER_DIR:?Set GOAD_PROVIDER_DIR to NORTH instance provider}"
[[ -d "$provider" && ! -L "$provider" && -f "$provider/Vagrantfile" ]] ||
  { echo 'NORTH instance provider missing/unsafe' >&2; exit 1; }
for vmnet in vmnet11 vmnet12 vmnet13; do
  grep -Fq ":vnet => \"$vmnet\"" "$provider/Vagrantfile" ||
    { echo "wrong NORTH instance: missing $vmnet" >&2; exit 1; }
done
state="$provider/.vagrant/machines/GOAD-ROUTER/vmware_desktop"
[[ -s "$state/id" ]] || { echo 'NORTH router not materialized' >&2; exit 1; }
key="$state/private_key"
[[ -s "$key" ]] || key="${VAGRANT_HOME:-${HOME}/.vagrant.d}/insecure_private_key"
[[ -s "$key" ]] || { echo 'router SSH key missing' >&2; exit 1; }
addresses="$(ip -4 -o addr show dev vmnet13 | awk '{print $4}')"
if grep -Eq '^10\.41\.99\.1/' <<< "$addresses"; then
  echo 'host owns NORTH router gateway 10.41.99.1' >&2; exit 1
fi
grep -Fxq '10.41.99.254/24' <<< "$addresses" ||
  { echo 'NORTH host management address missing' >&2; exit 1; }
exec ssh -i "$key" -p 22 \
  -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=5 \
  -o ServerAliveInterval=5 -o ServerAliveCountMax=2 \
  -o StrictHostKeyChecking=accept-new \
  -o "UserKnownHostsFile=$state/management_known_hosts" \
  vagrant@10.41.99.1 "$@"
