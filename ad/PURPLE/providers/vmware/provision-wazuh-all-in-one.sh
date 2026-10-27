#!/usr/bin/env bash
# PURPLE-WAZUH only: install the official Wazuh 4.14 single-node stack.
# Called by Vagrant after the Debian guest's static lab interface is configured.
# No monitoring stack is installed on any other PURPLE or KINGDOMS host.
set -Eeuo pipefail
umask 077

EXPECTED_IP="172.28.233.51"
WAZUH_VERSION="4.14"
WORK_DIR="/root/purple-wazuh-installer"
ASSISTANT_URL="https://packages.wazuh.com/${WAZUH_VERSION}/wazuh-install.sh"
SERVICES=(wazuh-manager wazuh-indexer wazuh-dashboard)

log() { printf '[PURPLE-WAZUH] %s\n' "$*"; }
fail() { printf '[PURPLE-WAZUH][BLOCKED] %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail "This provisioning script must run as root"
[[ -f /etc/os-release ]] || fail "Cannot identify the Linux distribution"
# shellcheck disable=SC1091
. /etc/os-release
if [[ "${ID:-}" != "debian" || "${VERSION_ID:-}" != "12" ]]; then
    fail "PURPLE's current Wazuh guest contract is Debian 12; found ${PRETTY_NAME:-unknown}"
fi
log "Debian 12 is not on Wazuh's recommended central-component OS list; no support override is used"

# The lab NIC must already be configured, before any network-fetched installer runs.
ip -4 -o address show | grep -Eq "[[:space:]]${EXPECTED_IP}/24([[:space:]]|$)" \
    || fail "Expected static lab IPv4 ${EXPECTED_IP}/24 is missing"

all_running=true
any_installed=false
for service in "${SERVICES[@]}"; do
    if ! systemctl is-active --quiet "$service"; then
        all_running=false
    fi
    if systemctl list-unit-files "${service}.service" --no-legend --no-pager 2>/dev/null \
            | grep -q "^${service}\\.service[[:space:]]"; then
        any_installed=true
    fi
done
if [[ "$all_running" == true ]]; then
    log "Wazuh manager, indexer and dashboard already active; preserving existing stack"
    exit 0
fi
if [[ "$any_installed" == true ]]; then
    fail "Partial or stopped Wazuh installation detected; refusing to reinstall and overwrite credentials/certificates"
fi

(( $(nproc) >= 4 )) || fail "Wazuh all-in-one needs at least 4 vCPUs; check PURPLE-WAZUH VM settings"
mem_kib=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
(( mem_kib >= 7000000 )) || fail "Wazuh all-in-one requires approximately 8 GiB RAM"
free_kib=$(df -Pk / | awk 'NR == 2 {print $4}')
(( free_kib >= 45 * 1024 * 1024 )) || fail "Less than 45 GiB free on /; Wazuh baseline requires sufficient disk space"

command -v curl >/dev/null || fail "curl is required by Wazuh's official installation assistant"
install -d -m 0700 "$WORK_DIR"
cd "$WORK_DIR"
log "Fetching the pinned Wazuh ${WAZUH_VERSION} official installation assistant"
curl -fSL --retry 3 --connect-timeout 15 --max-time 180 \
    "$ASSISTANT_URL" -o wazuh-install.sh \
    || fail "Cannot download the official Wazuh assistant"
chmod 0700 wazuh-install.sh

# The upstream assistant prints the generated admin password and creates
# a credentials archive. Restrict installer output to root, not Vagrant logs.
log "Installing all three Wazuh components; private logs remain in ${WORK_DIR}"
if ! bash ./wazuh-install.sh -a > "${WORK_DIR}/install.log" 2>&1; then
    fail "Wazuh assistant failed. Inspect ${WORK_DIR}/install.log in the guest (contains secrets). No forced reinstall attempted"
fi

# Wazuh generates random credentials; installation is NOT complete until
# they can be recovered from its official archive. Never scrape the
# installer's terminal log or export passwords into Vagrant/GitHub output.
ARCHIVE="${WORK_DIR}/wazuh-install-files.tar"
PASSWORD_MEMBER="wazuh-install-files/wazuh-passwords.txt"
[[ -s "$ARCHIVE" ]] || fail "Wazuh finished without its password archive: ${ARCHIVE}; preserve the private install.log for recovery"
if ! tar -tf "$ARCHIVE" | grep -Fqx "$PASSWORD_MEMBER"; then
    fail "Wazuh password archive exists but has no expected credentials entry; preserve it for inspection"
fi
if ! tar -xOf "$ARCHIVE" "$PASSWORD_MEMBER" | grep -Eq "indexer_username:[[:space:]]*['\"]?admin['\"]?"; then
    fail "Wazuh password archive has no admin account entry; preserve it for inspection"
fi
chown root:root "$ARCHIVE" "${WORK_DIR}/install.log"
chmod 0600 "$ARCHIVE" "${WORK_DIR}/install.log"
chmod 0700 "$WORK_DIR"
log "Generated Wazuh credentials saved in a verified root-only archive (not shown in logs)"

# Services may still need time for indexer and dashboard initialization.
for attempt in $(seq 1 60); do
    ready=true
    for service in "${SERVICES[@]}"; do
        systemctl is-active --quiet "$service" || ready=false
    done
    if [[ "$ready" == true ]]; then
        log "All Wazuh services active"
        log "Dashboard URL: https://${EXPECTED_IP}"
        log "Installer credentials/archive are root-only under ${WORK_DIR}"
        exit 0
    fi
    sleep 5
done
fail "Installer finished but Wazuh services are not all active; inspect private log and service status"
