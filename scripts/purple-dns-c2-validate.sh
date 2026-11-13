#!/usr/bin/env bash
# PURPLE DNS C2 read-only runtime validator. Does not create DNS records or change VMs.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
if [[ $# != 2 || "$1" != "--instance-dir" ]]; then
  echo "Usage: bash scripts/purple-dns-c2-validate.sh --instance-dir ABSOLUTE_PURPLE_INSTANCE_PATH" >&2
  exit 2
fi
INSTANCE="$2"
[[ "$INSTANCE" == /* && ! -L "$INSTANCE" && -d "$INSTANCE" ]] || { echo "[BLOCKED] Invalid instance path" >&2; exit 2; }
[[ "$(basename "$INSTANCE")" =~ ^[a-fA-F0-9]{6,}-purple-vmware$ ]] || { echo "[BLOCKED] Not a PURPLE lab instance" >&2; exit 2; }
INSTANCE="$(cd "$INSTANCE" && pwd -P)"
PROVIDER="$INSTANCE/provider"
INV="$INSTANCE/inventory"
LAB_INV="$ROOT/ad/PURPLE/data/inventory"
CFG="$ROOT/ad/PURPLE/data/config.json"
for file in "$PROVIDER/Vagrantfile" "$INV" "$LAB_INV" "$CFG" "$ROOT/playbooks.yml" "$ROOT/ansible/purple-dns-c2-verify.yml"; do
  [[ -f "$file" && ! -L "$file" ]] || { echo "[BLOCKED] Required source or inventory missing: $file" >&2; exit 2; }
done
grep -Eq '^dc01[[:space:]]+ansible_host=172[.]28[.]233[.]30([[:space:]]|$)' "$INV" || {
  echo "[BLOCKED] Unexpected PURPLE-DC01 inventory" >&2; exit 2;
}
grep -Eq '^ws01[[:space:]]+ansible_host=172[.]28[.]233[.]31([[:space:]]|$)' "$INV" || {
  echo "[BLOCKED] Unexpected PURPLE-WS01 inventory" >&2; exit 2;
}
command -v dig >/dev/null || { echo "[BLOCKED] dig is unavailable" >&2; exit 2; }
command -v vagrant >/dev/null || { echo "[BLOCKED] vagrant is unavailable" >&2; exit 2; }
if [[ -x "$HOME/.goad/.venv/bin/ansible-playbook" ]]; then
  ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
else
  ANSIBLE="$(command -v ansible-playbook || true)"
fi
[[ -n "$ANSIBLE" && -x "$ANSIBLE" ]] || { echo "[BLOCKED] Ansible is unavailable" >&2; exit 2; }

echo "=== PURPLE DNS C2 READ-ONLY VALIDATOR ==="
echo "[SOURCE] $(git -C "$ROOT" rev-parse HEAD)"
echo "[SOURCE] Checking fresh-install manifest and provisioning regression"
(cd "$ROOT" && python3 -m unittest tests.test_purple_dns_c2_source -q)
echo "[PASS] PURPLE fresh-install source wiring"

echo "[DNS] Querying PURPLE-DC01 directly, no records changed"
for expected in "purple-c2.purple.lab. 172.28.233.60" "purple-lx01.purple.lab. 172.28.233.32"; do
  read -r hostname address <<< "$expected"
  actual="$(dig +time=3 +tries=1 +short @172.28.233.30 "$hostname" A)"
  if [[ "$actual" != "$address" ]]; then
    echo "[FAIL] $hostname expected $address, received: $actual" >&2
    exit 1
  fi
  echo "[PASS] $hostname resolves to $actual"
done
referral="$(dig +time=3 +tries=1 +norecurse +noall +answer +authority @172.28.233.30 c2.purple.lab. NS)"
if ! grep -Eiq 'c2[.]purple[.]lab[.].*[[:space:]]NS[[:space:]]+purple-c2[.]purple[.]lab[.]' <<< "$referral"; then
  echo "[FAIL] c2.purple.lab NS delegation does not point to purple-c2.purple.lab" >&2
  printf '%s\n' "$referral"
  exit 1
fi
echo "[PASS] c2.purple.lab delegates to purple-c2.purple.lab"

echo "[LINUX] Inspecting live LX01 resolver and querying through systemd-resolved"
(
  cd "$PROVIDER"
  vagrant ssh PURPLE-LX01 -c 'set -eu; iface=""; for p in /sys/class/net/*; do if [ "$(cat "$p/address")" = "00:50:56:10:04:32" ]; then iface="$(basename "$p")"; break; fi; done; test -n "$iface"; resolvectl dns "$iface" | grep -F "172.28.233.30"; resolvectl domain "$iface" | grep -F "~purple.lab"; resolvectl query purple-c2.purple.lab | grep -F "172.28.233.60"'
)
echo "[PASS] LX01 resolver is configured for purple.lab and resolves PURPLE-C2"

echo "[WINDOWS] Checking WS01 DNS settings and normal hostname resolution (read-only)"
TMP="$(mktemp -d /tmp/purple-dns-validate.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
python3 - "$CFG" "$TMP/auth.json" <<'PY'
import json, os, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if data["lab"]["hosts"]["dc01"]["domain"] != "purple.lab":
    raise SystemExit("[BLOCKED] Unexpected source domain")
password = data["lab"]["domains"]["purple.lab"]["domain_password"]
if not password:
    raise SystemExit("[BLOCKED] Missing lab WinRM credential")
with open(sys.argv[2], "x", encoding="utf-8") as stream:
    json.dump({
        "ansible_user": "administrator@purple.lab",
        "ansible_password": password,
        "ansible_connection": "winrm",
        "ansible_winrm_transport": "ntlm",
        "ansible_winrm_server_cert_validation": "ignore",
    }, stream)
os.chmod(sys.argv[2], 0o600)
PY
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
"$ANSIBLE" -i "$LAB_INV" -i "$INV" -e "@$TMP/auth.json" --limit ws01 "$ROOT/ansible/purple-dns-c2-verify.yml"
echo "[PASS] WS01 DNS verification playbook completed"

echo "[PASS] PURPLE_DNS_C2_INFRASTRUCTURE_READY=1"
echo "[NOTE] This validates DNS infrastructure, not an active Sliver UDP/53 listener or implant traffic."
