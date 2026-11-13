#!/usr/bin/env bash
# Scoped, in-place DNS C2 prerequisite deployment for an installed PURPLE lab.
# Never call the full installer, recreate machines or touch other labs.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# != 3 || "$1" != "--instance-dir" || "$3" != "--apply" ]]; then
  echo "Usage: bash scripts/purple-dns-c2-apply.sh --instance-dir ABSOLUTE_PURPLE_INSTANCE_PATH --apply" >&2
  exit 2
fi
INSTANCE="$2"
[[ "$INSTANCE" == /* && ! -L "$INSTANCE" && -d "$INSTANCE" ]] || { echo "[BLOCKED] Invalid instance directory" >&2; exit 2; }
[[ "$(basename "$INSTANCE")" =~ ^[a-fA-F0-9]{6,}-purple-vmware$ ]] || { echo "[BLOCKED] Not a PURPLE instance" >&2; exit 2; }
INSTANCE="$(cd "$INSTANCE" && pwd -P)"
PROVIDER="$INSTANCE/provider"
INV="$INSTANCE/inventory"
LAB_INV="$ROOT/ad/PURPLE/data/inventory"
PLAY="$ROOT/ansible/purple-dns-c2.yml"
NIC="$ROOT/ad/PURPLE/providers/vmware/configure-linux-interface.sh"
CONFIG="$ROOT/ad/PURPLE/data/config.json"
for item in "$INV" "$LAB_INV" "$PLAY" "$NIC" "$CONFIG" "$PROVIDER/Vagrantfile" "$PROVIDER/.vagrant/machines/PURPLE-DC01/vmware_desktop/id" "$PROVIDER/.vagrant/machines/PURPLE-LX01/vmware_desktop/id"; do
  [[ -f "$item" && ! -L "$item" ]] || { echo "[BLOCKED] Missing or unsafe PURPLE input: $item" >&2; exit 2; }
done
grep -Eq '^[[:space:]]*dc01[[:space:]]+ansible_host=172[.]28[.]233[.]30([[:space:]]|$)' "$INV" || { echo "[BLOCKED] DC01 inventory IP mismatch" >&2; exit 2; }
if [[ -x "$HOME/.goad/.venv/bin/ansible-playbook" ]]; then
  ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
else
  ANSIBLE="$(command -v ansible-playbook || true)"
fi
[[ -n "$ANSIBLE" && -x "$ANSIBLE" ]] || { echo "[BLOCKED] Ansible unavailable" >&2; exit 2; }
command -v vagrant >/dev/null || { echo "[BLOCKED] Vagrant unavailable" >&2; exit 2; }
command -v dig >/dev/null || { echo "[BLOCKED] dig unavailable" >&2; exit 2; }
TMP="$(mktemp -d /tmp/purple-dns-apply.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
python3 - "$CONFIG" "$TMP/auth.json" <<'PY'
import json, os, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
if data["lab"]["hosts"]["dc01"]["domain"] != "purple.lab":
    raise SystemExit("Unexpected domain in source")
pwd = data["lab"]["domains"]["purple.lab"]["domain_password"]
if not pwd:
    raise SystemExit("Empty domain admin credential")
with open(sys.argv[2], "x", encoding="utf-8") as f:
    json.dump({
        "ansible_user": "administrator@purple.lab",
        "ansible_password": pwd,
        "ansible_connection": "winrm",
        "ansible_winrm_transport": "ntlm",
        "ansible_winrm_server_cert_validation": "ignore"
    }, f)
os.chmod(sys.argv[2], 0o600)
PY
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
echo "[CHECK] Parse playbook and restrict to the existing dc01"
"$ANSIBLE" -i "$LAB_INV" -i "$INV" -e "@$TMP/auth.json" --limit dc01 "$PLAY" --syntax-check
"$ANSIBLE" -i "$LAB_INV" -i "$INV" -e "@$TMP/auth.json" --limit dc01 "$PLAY" --list-hosts | tee "$TMP/targets"
grep -Eq 'hosts [(]1[)]:' "$TMP/targets" && grep -Eq '^[[:space:]]+dc01[[:space:]]*$' "$TMP/targets" || { echo "[BLOCKED] Target inventory is not exactly dc01" >&2; exit 2; }
echo "[APPLY] DNS A records and c2.purple.lab delegation on PURPLE-DC01 only"
"$ANSIBLE" -i "$LAB_INV" -i "$INV" -e "@$TMP/auth.json" --limit dc01 "$PLAY"
echo "[VERIFY] Published records from PURPLE-DC01 DNS"
for pair in "purple-c2.purple.lab. 172.28.233.60" "purple-lx01.purple.lab. 172.28.233.32"; do
  read -r name ip <<< "$pair"
  response="$(dig +time=3 +tries=1 +short @172.28.233.30 "$name" A)"
  [[ "$response" == "$ip" ]] || { echo "[FAIL] $name expected $ip got $response" >&2; exit 1; }
  echo "[PASS] $name -> $response"
done
referral="$(dig +time=3 +tries=1 +norecurse +noall +answer +authority @172.28.233.30 c2.purple.lab. NS)"
grep -Eiq 'c2[.]purple[.]lab[.].*[[:space:]]NS[[:space:]]+purple-c2[.]purple[.]lab[.]' <<< "$referral" || {
  printf '%s\n' "$referral"
  echo "[FAIL] Delegation NS referral not visible" >&2
  exit 1
}
echo "[PASS] c2.purple.lab NS delegation"
echo "[APPLY] Only LX01's existing lab-NIC script, with split DNS"
(
  cd "$PROVIDER"
  vagrant upload "$NIC" /tmp/purple-lx01-dns-source.sh PURPLE-LX01
  vagrant ssh PURPLE-LX01 -c 'sudo bash /tmp/purple-lx01-dns-source.sh 172.28.233.32 00:50:56:10:04:32'
  vagrant ssh PURPLE-LX01 -c 'resolvectl query purple-c2.purple.lab'
)
echo "[PASS] DNS prerequisite provisioning applied and LX01 resolved the C2 hostname"
echo "[NOTE] Sliver UDP/53 service and DNS C2 data exchange are NOT yet validated"
