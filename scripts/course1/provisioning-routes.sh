#!/usr/bin/env bash
# NORTH-only temporary route to parent AD. Never modify reference routes.
set -Eeuo pipefail
readonly NORTH_IF=vmnet11 ROUTER_NORTH=10.41.10.1 PARENT_NET=10.41.20.0/24
readonly HOSTADDR_HELPER=/usr/local/sbin/kingdoms-north-vmnet-hostaddrs
readonly COURSE1_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
fail() { echo "[FAIL] NORTH route: $*" >&2; exit 1; }
route_exact() { ip -4 route show exact "${PARENT_NET}"; }
route_state() {
  local evidence
  evidence="$(ip -j -4 route show exact "${PARENT_NET}")" ||
    fail "cannot read structured NORTH parent route"
  printf '%s' "$evidence" | python3 "${COURSE1_ROOT}/goad/course1_route_state.py" \
    --network "$PARENT_NET" --gateway "$ROUTER_NORTH" \
    --device "$NORTH_IF" --host-source '10.41.10.254' ||
    fail "cannot classify existing parent route"
}
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
  local state
  state="$(route_state)" || fail "parent route inspection failed"
  [[ "$state" != foreign ]] ||
    fail "refusing to overwrite foreign route: $(route_exact)"
  ping -c 1 -W 1 "${ROUTER_NORTH}" >/dev/null 2>&1 ||
    fail "NORTH router gateway unreachable"
  if [[ "$state" == owned ]]; then
    echo "[PASS] NORTH parent provisioning route already owned (no change)"
    return 0
  fi
  [[ "$state" == absent ]] || fail "unexpected route state"
  # Unlike replace, add fails closed if another process installed a route
  # between classification and mutation. Never overwrite that new route.
  ip -4 route add "${PARENT_NET}" via "${ROUTER_NORTH}" dev "${NORTH_IF}" ||
    fail "parent route appeared/changed during creation; no overwrite attempted"
  [[ "$(route_state)" == owned ]] ||
    fail "created parent route did not match NORTH identity"
  echo "[PASS] NORTH parent provisioning route enabled"
}
disable_routes() {
  require_root
  local state
  state="$(route_state)" || fail "parent route inspection failed"
  [[ "$state" == absent ]] && { echo "[PASS] NORTH route already absent"; return 0; }
  [[ "$state" == owned ]] ||
    fail "refusing to remove foreign route: $(route_exact)"
  ip -4 route del "${PARENT_NET}" via "${ROUTER_NORTH}" dev "${NORTH_IF}" ||
    fail "parent route changed during removal"
  [[ "$(route_state)" == absent ]] ||
    fail "NORTH parent route cleanup not confirmed"
  echo "[PASS] NORTH parent provisioning route removed"
}
case "${1:-status}" in
  status)
    state="$(route_state)" || fail "route status could not be verified"
    echo "[INFO] NORTH route identity: $state; observed: $(route_exact)"
    [[ "$state" != foreign ]] ||
      fail "unexpected/foreign parent route; refusing installation retry"
    ;;
  enable) [[ $# -eq 1 ]] || fail "usage: enable"; enable_routes ;;
  disable) [[ $# -eq 1 ]] || fail "usage: disable"; disable_routes ;;
  *) fail "usage: $0 {status|enable|disable}" ;;
esac
