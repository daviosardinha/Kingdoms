#!/usr/bin/env bash
# Exact fresh-Windows WSLPE vmnet4 host address persistence install.
# No shared vmware-networks restarts, VMware guest actions or NORTH writes.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd -P)"
PY="$HOME/.goad/.venv/bin/python"
SOURCE="scripts/wslpe-vmnet4-hostaddr-keeper.py"
SERVICE="ops/systemd/kingdoms-wslpe-vmnet4-hostaddr.service"
TIMER="ops/systemd/kingdoms-wslpe-vmnet4-hostaddr.timer"
TARGET="/usr/local/libexec/kingdoms/wslpe-vmnet4-hostaddr-keeper.py"
UNIT="/etc/systemd/system/kingdoms-wslpe-vmnet4-hostaddr.service"
TIMER_UNIT="/etc/systemd/system/kingdoms-wslpe-vmnet4-hostaddr.timer"

cd "$ROOT"
[[ "$(git branch --show-current)" == "feature/wslpe41-fresh-full-installer" ]] || {
  echo "[BLOCKED] Wrong checkout/branch"; exit 2;
}
for file in "$SOURCE" "$SERVICE" "$TIMER"; do
  [[ -f "$file" && ! -L "$file" ]] || { echo "[BLOCKED] Missing/linked source"; exit 2; }
  git diff --quiet HEAD -- "$file" || { echo "[BLOCKED] Modified source"; exit 2; }
  git cat-file blob "HEAD:$file" | cmp - "$file" >/dev/null || {
    echo "[BLOCKED] Source differs from committed branch"; exit 2;
  }
done

[[ "$(vmrun -T ws list)" == "Total running VMs: 0" ]] || {
  echo "[BLOCKED] Shared VMware maintenance requires zero guests"; exit 2;
}
if pgrep -x vmware-vmx >/dev/null; then
  echo "[BLOCKED] VMware guests still running"; exit 2
fi
if [[ -e "$TARGET" || -L "$TARGET" || -e "$UNIT" || -L "$UNIT" ||
      -e "$TIMER_UNIT" || -L "$TIMER_UNIT" ]]; then
  echo "[BLOCKED] Existing vmnet4 persistence installation; review, do not overwrite"; exit 2
fi

sudo -v
echo "===== READ-ONLY COMMITTED VMNET4 GATE ====="
set +e
sudo "$PY" "$SOURCE" --check
code=$?
set -e
case "$code" in
  0) echo "[PASS] vmnet4 is already at .254" ;;
  1) echo "[READY] VMware reset vmnet4 to default .1, isolated repair allowed" ;;
  *) echo "[BLOCKED] vmnet4 committed-source or kernel validation failed"; exit 2 ;;
esac

echo "===== INSTALL AUTHORIZATION ====="
read -r -p "Type INSTALL-VMNET4-KEEPER to enable scoped host-only persistence: " YES </dev/tty
[[ "$YES" == "INSTALL-VMNET4-KEEPER" ]] || exit 2

echo "===== INSTALL IMMUTABLE ROOT-OWNED RUNTIME ====="
sudo install -d -o root -g root -m 0755 /usr/local/libexec/kingdoms
sudo install -o root -g root -m 0755 "$SOURCE" "$TARGET"
sudo install -o root -g root -m 0644 "$SERVICE" "$UNIT"
sudo install -o root -g root -m 0644 "$TIMER" "$TIMER_UNIT"
sudo systemctl daemon-reload

echo "===== APPLY ONLY VMNET4 HOST ADDRESS ====="
if ! sudo systemctl start kingdoms-wslpe-vmnet4-hostaddr.service; then
  echo "[BLOCKED] vmnet4 repair service failed; do not start guests"
  sudo journalctl -u kingdoms-wslpe-vmnet4-hostaddr.service -n 30 --no-pager || true
  exit 2
fi

sudo systemctl enable --now kingdoms-wslpe-vmnet4-hostaddr.timer
sudo /usr/bin/python3 "$TARGET" --check

echo "===== VERIFY PERIODIC CORRECTION ====="
# One completed timer interval must not introduce drift or fail the service.
sleep 18
sudo /usr/bin/python3 "$TARGET" --check
if systemctl is-failed --quiet kingdoms-wslpe-vmnet4-hostaddr.service; then
  echo "[BLOCKED] vmnet4 persistence service reported failure"; exit 2
fi

echo "===== VERIFY NORTH HOST ADDRESS RECOVERY (READ ONLY) ====="
# NORTH has an existing independent repair timer. Observe; never invoke or
# modify its helper, service, routing, or VMware network configuration.
NORTH_READY=0
for attempt in $(seq 1 12); do
  if ip -4 -o addr show dev vmnet10 | awk '{print $4}' | grep -Fxq '10.4.10.254/24' &&
     ip -4 -o addr show dev vmnet99 | awk '{print $4}' | grep -Fxq '10.4.99.254/24'; then
    NORTH_READY=1
    break
  fi
  sleep 2
done
if [[ "$NORTH_READY" -ne 1 ]]; then
  echo "[BLOCKED] NORTH host-only addresses not restored by their owner timer"
  echo "No NORTH or VMware network changes made by this installer"
  exit 2
fi
echo "[PASS] NORTH vmnet10/vmnet99 addresses recovered without WSLPE writes"

echo "===== VERIFY PRESERVED VMWARE NETWORKS ====="
ip -br -4 addr show | grep -E '^vmnet(1|2|3|4|8|10|99)[[:space:]]' || true
systemctl is-enabled kingdoms-wslpe-vmnet4-hostaddr.timer
systemctl is-active kingdoms-wslpe-vmnet4-hostaddr.timer

echo "[PASS] VMNET4_HOSTADDR_PERSISTENCE_INSTALLED"
echo "[NEXT] Check NORTH timer separately before starting any guest"
