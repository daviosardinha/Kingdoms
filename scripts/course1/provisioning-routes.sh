#!/usr/bin/env bash
# NORTH-only temporary route to parent AD. Never modify reference routes.
set -Eeuo pipefail
readonly NORTH_IF=vmnet11 ROUTER_NORTH=10.41.10.1 PARENT_NET=10.41.20.0/24
readonly HOSTADDR_HELPER=/usr/local/sbin/kingdoms-north-vmnet-hostaddrs
fail() { echo "[FAIL] NORTH route: $*" >&2; exit 1; }
route_exact() { ip -4 route show exact "${PARENT_NET}"; }
require_root() { [[ ${EUID} -eq 0 ]] || fail "requires root"; }
verify_north() {
  [[ -x "${HOSTADDR_HELPER}" ]] || fail "NORTH host-address helper missing"
  "${HOSTADDR_HELPER}" status || fail "NORTH/reference addresses not ready"
  ip -4 -o addr show dev vmnet11 | awk '{print $4}' |
    grep -Fxq '10.41.10.254/24' || fail "vmnet11 address mismatch"
  ip -4 -o addr show dev vmnet13 | awk '{print $4}' |
    grep -Fxq '10.41.99.254/24' || fail "vmnet13 address mismatch"
}
enable_routes() {
  require_root
  verify_north
  local existing
  existing="$(route_exact)"
  [[ -z "$existing" || "$existing" == "${PARENT_NET} via ${ROUTER_NORTH} dev ${NORTH_IF}" ]] ||
    fail "refusing to overwrite foreign route: $existing"
  ping -c 1 -W 1 "${ROUTER_NORTH}" >/dev/null 2>&1 ||
    fail "NORTH router gateway unreachable"
  ip -4 route replace "${PARENT_NET}" via "${ROUTER_NORTH}" dev "${NORTH_IF}"
  echo "[PASS] NORTH parent provisioning route enabled"
}
disable_routes() {
  require_root
  local existing
  existing="$(route_exact)"
  [[ -n "$existing" ]] || { echo "[PASS] NORTH route already absent"; return 0; }
  [[ "$existing" == "${PARENT_NET} via ${ROUTER_NORTH} dev ${NORTH_IF}" ]] ||
    fail "refusing to remove foreign route: $existing"
  ip -4 route del "${PARENT_NET}" via "${ROUTER_NORTH}" dev "${NORTH_IF}"
  echo "[PASS] NORTH parent provisioning route removed"
}
case "${1:-status}" in
  status) echo "[INFO] NORTH route: $(route_exact)" ;;
  enable) [[ $# -eq 1 ]] || fail "usage: enable"; enable_routes ;;
  disable) [[ $# -eq 1 ]] || fail "usage: disable"; disable_routes ;;
  *) fail "usage: $0 {status|enable|disable}" ;;
esac
