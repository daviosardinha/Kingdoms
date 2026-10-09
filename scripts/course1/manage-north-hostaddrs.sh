#!/usr/bin/env bash
# Installs/removes ONLY NORTH address persistence, preserving GOAD reference.
# This does not modify /etc/vmware/networking or stop/start VMware.
set -Eeuo pipefail
readonly ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
readonly SOURCE="$ROOT/scripts/course1/kingdoms-north-vmnet-hostaddrs"
readonly SRC_SERVICE="$ROOT/ops/systemd/kingdoms-north-vmnet-hostaddrs.service"
readonly SRC_TIMER="$ROOT/ops/systemd/kingdoms-north-vmnet-hostaddrs.timer"
readonly TARGET="/usr/local/sbin/kingdoms-north-vmnet-hostaddrs"
readonly SERVICE="kingdoms-north-vmnet-hostaddrs.service"
readonly TIMER="kingdoms-north-vmnet-hostaddrs.timer"
readonly UNIT_DIR="/etc/systemd/system"

fail() { echo "[FAIL] NORTH host persistence: $*" >&2; exit 1; }
require_zero_guests() {
  # No host address maintenance while a VM is running initially.
  if pgrep -x vmware-vmx >/dev/null 2>&1; then
    fail "VMware guests are running; preserve reference maintenance window"
  fi
  # Distinguish pgrep errors from no matches.
  local rc=0
  pgrep -x vmware-vmx >/dev/null 2>&1 || rc=$?
  [[ $rc -eq 1 ]] || fail "VMware process enumeration failed"
}
protected_file() {
  local src="$1" dest="$2" mode="$3"
  [[ -f "$src" && ! -L "$src" ]] || fail "source missing/symlinked: $src"
  if [[ -e "$dest" || -L "$dest" ]]; then
    [[ -f "$dest" && ! -L "$dest" ]] || fail "target unsafe: $dest"
    cmp -s "$src" "$dest" || fail "target differs; refusing overwrite: $dest"
  else
    install -m "$mode" -D "$src" "$dest"
  fi
}
check_owned_file() {
  local src="$1" dest="$2"
  [[ -f "$dest" && ! -L "$dest" ]] && cmp -s "$src" "$dest" ||
    fail "target is not current Kingdoms NORTH-managed content: $dest"
}
[[ $# -ge 1 ]] || fail "usage: $0 {status|install|remove} [--confirm-host-addresses]"
case "$1" in
  status)
    [[ $# -eq 1 ]] || fail "status takes no confirmation flag"
    bash "$SOURCE" status
    if systemctl is-enabled "$TIMER" >/dev/null 2>&1; then
      echo "[PASS] NORTH host-address repair timer enabled"
    else
      echo "[WARN] NORTH host-address timer is not installed/enabled"
    fi
    ;;
  install)
    [[ $# -eq 2 && "$2" == "--confirm-host-addresses" ]] ||
      fail "explicit --confirm-host-addresses required"
    [[ $EUID -eq 0 ]] || fail "install requires sudo"
    require_zero_guests
    protected_file "$SOURCE" "$TARGET" 0755
    protected_file "$SRC_SERVICE" "$UNIT_DIR/$SERVICE" 0644
    protected_file "$SRC_TIMER" "$UNIT_DIR/$TIMER" 0644
    systemctl daemon-reload
    systemctl reset-failed "$SERVICE" >/dev/null 2>&1 || true
    systemctl start "$SERVICE" || fail "initial NORTH host-address repair failed"
    bash "$SOURCE" status
    systemctl enable --now "$TIMER" >/dev/null
    systemctl is-enabled "$TIMER" >/dev/null ||
      fail "NORTH host-address timer not enabled"
    echo "[PASS] NORTH host-address persistence installed without changing reference units"
    ;;
  remove)
    [[ $# -eq 2 && "$2" == "--confirm-host-addresses" ]] ||
      fail "explicit --confirm-host-addresses required"
    [[ $EUID -eq 0 ]] || fail "remove requires sudo"
    require_zero_guests
    check_owned_file "$SOURCE" "$TARGET"
    check_owned_file "$SRC_SERVICE" "$UNIT_DIR/$SERVICE"
    check_owned_file "$SRC_TIMER" "$UNIT_DIR/$TIMER"
    systemctl disable --now "$TIMER" >/dev/null
    systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    rm -- "$UNIT_DIR/$TIMER" "$UNIT_DIR/$SERVICE" "$TARGET"
    systemctl daemon-reload
    echo "[PASS] NORTH host-address persistence removed; network addresses not changed"
    ;;
  *) fail "usage: $0 {status|install|remove} [--confirm-host-addresses]" ;;
esac
