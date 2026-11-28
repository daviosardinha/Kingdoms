#!/usr/bin/env bash
# NORTH-only diagnostic: compare WS01 machine trust with and without runtime NAT.
# No VM reboot, account reset, rejoin, firewall, route, or persistent NIC change.
set -Eeuo pipefail

root="$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)"
instance="${1:-}"
[[ "${instance}" =~ ^[0-9a-f]{6}-north-vmware$ ]] ||
    { echo "Usage: bash scripts/probe-north-ws01-nat-dependency.sh <instance-id>-north-vmware" >&2; exit 2; }

provider="${root}/workspace/${instance}/provider"
inventory="${root}/workspace/${instance}/inventory"
base_inventory="${root}/ad/NORTH/data/inventory"
[[ -d "${provider}" && -f "${inventory}" && -f "${base_inventory}" ]] ||
    { echo "[BLOCKED] NORTH instance provider or inventory missing" >&2; exit 2; }
[[ "$(cat "${provider}/.goad-nomad-mode" 2>/dev/null || true)" == "exercise" ]] ||
    { echo "[BLOCKED] NORTH is not in exercise mode" >&2; exit 2; }
vmx_id="${provider}/.vagrant/machines/GOAD-WS01/vmware_desktop/id"
[[ -f "${vmx_id}" ]] || { echo "[BLOCKED] NORTH WS01 Vagrant VMX ID missing" >&2; exit 2; }
vmx="$(cat "${vmx_id}")"
[[ "${vmx}" == "${provider}/.vagrant/machines/GOAD-WS01/vmware_desktop/"* && -f "${vmx}" ]] ||
    { echo "[BLOCKED] Refusing to inspect a foreign or missing VMX: ${vmx}" >&2; exit 2; }
grep -Eiq '^[[:space:]]*ethernet0\.startConnected[[:space:]]*=[[:space:]]*"FALSE"' "${vmx}" ||
    { echo "[BLOCKED] Persistent NORTH WS01 NAT must remain disabled" >&2; exit 2; }
vmrun -T ws list | grep -Fxq -- "${vmx}" ||
    { echo "[BLOCKED] Owned NORTH WS01 VM is not running" >&2; exit 2; }

ansible="${HOME}/.goad/.venv/bin/ansible"
[[ -x "${ansible}" ]] || { echo "[BLOCKED] GOAD Ansible virtualenv not found" >&2; exit 2; }
export ANSIBLE_CONFIG="${root}/ansible/ansible.cfg"

ps_probe="$(cat <<'POWERSHELL'
$ErrorActionPreference = 'Continue'
$dc = 'winterfell.north.sevenkingdoms.local'
Write-Output ('HOST=' + $env:COMPUTERNAME)
$profiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue | ForEach-Object { "$($_.InterfaceAlias)=$($_.NetworkCategory)" }
Write-Output ('PROFILES=' + ($profiles -join ','))
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notmatch '^(127|169\.254)\.' } | ForEach-Object { "$($_.InterfaceAlias)=$($_.IPAddress)" }
Write-Output ('IPV4=' + ($ips -join ','))
$dns = Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { "$($_.InterfaceAlias):$($_.ServerAddresses -join ',')" }
Write-Output ('DNS=' + ($dns -join ';'))
$routes = Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.DestinationPrefix -in @('0.0.0.0/0','10.4.10.0/24') } | ForEach-Object { "$($_.DestinationPrefix) via $($_.NextHop) if=$($_.InterfaceIndex) metric=$($_.RouteMetric)" }
Write-Output ('ROUTES=' + ($routes -join ';'))
Write-Output ('SECURE_CHANNEL=' + (Test-ComputerSecureChannel -Server $dc -ErrorAction SilentlyContinue))
$sc = (& nltest.exe '/sc_query:north.sevenkingdoms.local' 2>&1 | Out-String).Trim()
Write-Output ('SC_QUERY_RC=' + $LASTEXITCODE)
Write-Output ('SC_QUERY=' + ($sc -replace '[\r\n]+', ' '))
exit 0
POWERSHELL
)"

probe() {
    local phase="$1"
    printf '\n========== %s ==========\n' "${phase}"
    "${ansible}" ws01 -i "${base_inventory}" -i "${inventory}" \
        -m ansible.windows.win_shell -a "${ps_probe}"
}

nat_touched=0
cleanup() {
    local rc=$?
    trap - EXIT
    if (( nat_touched )); then
        if vmrun -T ws disconnectNamedDevice "${vmx}" ethernet0 >/dev/null 2>&1; then
            echo "[RESTORED] NORTH WS01 runtime NAT disconnected after interrupted probe"
        else
            echo "[CRITICAL] Could not restore NORTH WS01 runtime NAT. Disconnect ethernet0 on this exact VMX immediately: ${vmx}" >&2
            rc=1
        fi
    fi
    exit "${rc}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Ensure a known, disconnected starting point.
vmrun -T ws disconnectNamedDevice "${vmx}" ethernet0 >/dev/null 2>&1 || true
probe "NORTH_WS01_ISOLATED_BEFORE"

nat_touched=1
vmrun -T ws connectNamedDevice "${vmx}" ethernet0 >/dev/null
echo "[TEMPORARY] Only NORTH GOAD-WS01 ethernet0 connected; persistent setting unchanged"
sleep 12
probe "NORTH_WS01_NAT_CONNECTED"

vmrun -T ws disconnectNamedDevice "${vmx}" ethernet0 >/dev/null
nat_touched=0
echo "[RESTORED] NORTH GOAD-WS01 ethernet0 disconnected"
sleep 8
probe "NORTH_WS01_ISOLATED_AFTER"
grep -Eiq '^[[:space:]]*ethernet0\.startConnected[[:space:]]*=[[:space:]]*"FALSE"' "${vmx}" ||
    { echo "[FAIL] Persistent NAT changed unexpectedly" >&2; exit 1; }
echo "[PASS] NORTH WS01 NAT comparison complete; persistent NAT still FALSE."
