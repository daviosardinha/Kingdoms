#!/usr/bin/env bash
# PURPLE only. Permit the pinned Sliver server to bind privileged DNS UDP/53.
# Sliver is installed during the course, not during initial lab provisioning.
set -Eeuo pipefail
if [[ $# != 1 || ! "$1" =~ ^--(apply|verify)$ ]]; then
  echo "Usage: bash scripts/purple-sliver-dns-bind-capability.sh --apply|--verify" >&2
  exit 2
fi
mode="$1"
ssh vagrant@172.28.233.60 bash -s -- "$mode" <<'REMOTE'
set -Eeuo pipefail
mode="$1"
[[ "$(hostname -s)" == "purple-c2" && "$(id -un)" == "vagrant" ]] || {
  echo "[BLOCKED] Expected PURPLE-C2 and vagrant" >&2
  exit 2
}
bin="$HOME/.local/bin/sliver-server"
[[ -f "$bin" && ! -L "$bin" && -x "$bin" ]] || {
  echo "[BLOCKED] Pinned Sliver server executable not found or unsafe" >&2
  exit 2
}
expected="6c54ea94961f15de22bb765911b850d054e66f69069e4b799ab7cc3134e8ef36"
actual="$(sha256sum "$bin" | awk '{print $1}')"
[[ "$actual" == "$expected" ]] || {
  echo "[BLOCKED] Sliver server SHA256 differs from course-pinned v1.7.9" >&2
  exit 2
}
if [[ "$mode" == "--apply" ]]; then
  if [[ ! -x /usr/sbin/setcap || ! -x /usr/sbin/getcap ]]; then
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y libcap2-bin
  fi
  sudo /usr/sbin/setcap cap_net_bind_service=+ep "$bin"
fi
[[ -x /usr/sbin/getcap ]] || { echo "[BLOCKED] getcap is unavailable" >&2; exit 2; }
capabilities="$(/usr/sbin/getcap "$bin")"
printf '%s\n' "$capabilities"
grep -Eq 'cap_net_bind_service=ep$' <<< "$capabilities" || {
  echo "[FAIL] Missing CAP_NET_BIND_SERVICE on the pinned Sliver executable" >&2
  exit 1
}
echo "[PASS] PURPLE_SLIVER_DNS_BIND_CAPABILITY_READY=1"
echo "[NOTE] This capability takes effect when Sliver is next started; it does not restart the current process."
REMOTE
