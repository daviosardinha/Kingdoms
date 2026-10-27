#!/usr/bin/env bash
# Read Wazuh's generated password archive only on the selected PURPLE-WAZUH.
# Default action checks availability without printing secrets.
# --show is an explicitly requested interactive secret disclosure on the caller's terminal.
set -Eeuo pipefail
set +x

usage() {
    echo "Usage: bash scripts/purple-wazuh-credentials.sh --provider-dir /absolute/PURPLE/provider [--status|--show]" >&2
    exit 2
}
provider=""
action="status"
while (($#)); do
    case "$1" in
        --provider-dir) (($# >= 2)) || usage; provider="$2"; shift 2 ;;
        --status) action="status"; shift ;;
        --show) action="show"; shift ;;
        *) usage ;;
    esac
done
[[ "$provider" = /* && "$provider" != *"/../"* ]] || usage
[[ "$provider" =~ /[a-f0-9]{6}-purple-vmware/provider$ ]] ||
    { echo "[BLOCKED] Exact PURPLE VMware instance provider required" >&2; exit 1; }
[[ -f "$provider/Vagrantfile" &&
   -f "$provider/.vagrant/machines/PURPLE-WAZUH/vmware_desktop/id" ]] ||
    { echo "[BLOCKED] Registered PURPLE-WAZUH Vagrant guest not found" >&2; exit 1; }
[[ "$action" != "show" || -t 1 ]] ||
    { echo "[BLOCKED] --show requires an interactive terminal (no log/pipe capture)" >&2; exit 1; }

# Both locations are supported: automated installs and the existing manual pilot.
# The remote command reveals passwords only for an explicit interactive --show.
remote='sudo bash -lc '"'"'
  set -e
  member=wazuh-install-files/wazuh-passwords.txt
  for archive in /root/purple-wazuh-installer/wazuh-install-files.tar /root/wazuh-install-files.tar; do
      if [ -s "$archive" ] && tar -tf "$archive" | grep -Fqx "$member"; then
          test "$(stat -c %u "$archive")" = 0 || { echo "[BLOCKED] Password archive is not root-owned" >&2; exit 1; }
          if [ '"$action"' = show ]; then
              tar -xOf "$archive" "$member"
          else
              printf "[PASS] Recoverable Wazuh credentials: %s (root-owned, not displayed)\\n" "$archive"
          fi
          exit 0
      fi
  done
  echo "[BLOCKED] Wazuh password archive is missing or invalid" >&2
  exit 1
'"'"''
(
  cd "$provider"
  if [[ "$action" == "show" ]]; then
      echo "[NOTICE] Showing Wazuh credentials on your local terminal only. Do not paste or screenshot this output." >&2
  fi
  vagrant ssh PURPLE-WAZUH -c "$remote"
)
