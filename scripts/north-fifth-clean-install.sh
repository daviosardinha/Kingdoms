#!/usr/bin/env bash
# One-host NORTH fifth install: offline backup -> verify -> retire -> reinstall.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "$BASH_SOURCE")/.." && pwd -P)"
cd "$ROOT"
OLD="8aafc9-north-vmware"
if [[ $# -ne 2 || "$1" != "--run" ||
      "$2" != "--confirm-retire-installed-north-after-backup" ]]; then
  echo "Usage: bash scripts/north-fifth-clean-install.sh --run --confirm-retire-installed-north-after-backup" >&2
  exit 2
fi
[[ "$EUID" -ne 0 && "$(git branch --show-current)" == main ]] || {
  echo "[BLOCKED] Run as ordinary VMware desktop user on main" >&2; exit 2;
}
for tool in rsync sha256sum vmrun vagrant flock git sudo tar python3 pgrep; do
  command -v "$tool" >/dev/null || { echo "[BLOCKED] Missing $tool" >&2; exit 2; }
done
[[ -x "$HOME/.goad/.venv/bin/python" ]] || {
  echo "[BLOCKED] Kingdoms Python virtualenv missing" >&2; exit 2;
}
INSTANCE="$ROOT/workspace/$OLD"
PROVIDER="$INSTANCE/provider"
[[ -d "$PROVIDER" && ! -L "$PROVIDER" ]] || {
  echo "[BLOCKED] Exact original NORTH provider missing" >&2; exit 2;
}
[[ ! -L "$HOME/Kingdoms-backups" ]] || {
  echo "[BLOCKED] Backup root is a symlink" >&2; exit 2;
}
if pgrep -x vmware >/dev/null; then
  echo "[BLOCKED] Close VMware Workstation GUI before this workflow" >&2; exit 2;
fi
LOCK="$PROVIDER/.course1-phase03-acceptance.lock"
[[ ! -L "$LOCK" ]] || {
  echo "[BLOCKED] Original NORTH lifecycle lock is a symlink" >&2; exit 2;
}
exec 9>"$LOCK"
flock -n 9 || { echo "[BLOCKED] Another NORTH lifecycle is active" >&2; exit 2; }

# No VM is touched until source, exact ownership and runtime are proven.
bash scripts/verify-test-source.sh || exit 1
"$HOME/.goad/.venv/bin/python" -m goad.course1_full_backup preflight --root "$ROOT" || exit 1
sudo -v || exit 1
sudo -n bash scripts/setup-vmware-networks.sh --north verify --provider-dir "$PROVIDER" || exit 1

mkdir -p -m 700 "$HOME/Kingdoms-backups"
chmod 700 "$HOME/Kingdoms-backups"
BACKUP="$(mktemp -d "$HOME/Kingdoms-backups/8aafc9-north-XXXXXXXX")"
chmod 700 "$BACKUP"
mkdir -m 700 "$BACKUP/host" "$BACKUP/logs"
SUMMARY="$BACKUP/summary.txt"
printf 'original=%s\nsource=%s\nstarted_utc=%s\n' \
  "$OLD" "$(git rev-parse HEAD)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$SUMMARY"
printf 'BACKUP_VERIFIED=NO\nFIFTH_INSTALL=NOT_CERTIFIED\n' >> "$SUMMARY"
PHASE="preflight"
BACKUP_VERIFIED=0
KEEPALIVE=0
finish() {
  local rc=$?
  trap - EXIT INT TERM
  if [[ "$KEEPALIVE" != 0 ]]; then
    kill "$KEEPALIVE" 2>/dev/null || true
    wait "$KEEPALIVE" 2>/dev/null || true
  fi
  if ((rc != 0)); then
    echo "FAILED | phase=$PHASE | rc=$rc | backup_verified=$BACKUP_VERIFIED" | tee -a "$SUMMARY" >&2
    echo "[BLOCKED] Do not automatically repeat destruction, network retirement or install." >&2
    echo "[BLOCKED] Never boot archived and newly deployed NORTH guests together." >&2
  fi
  printf 'ended_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$SUMMARY"
  echo "[BACKUP] $BACKUP"
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
(
  while sleep 50; do sudo -n -v >/dev/null 2>&1 || exit 1; done
) &
KEEPALIVE=$!

stage() {
  local title="$1" rc=0
  shift
  PHASE="$title"
  echo "===== $title ====="
  "$@" 2>&1 | tee "$BACKUP/logs/$title.log" || rc=$?
  if ((rc != 0)); then echo "[FAILED] $title rc=$rc" >&2; return "$rc"; fi
  echo "PASS | $title" | tee -a "$SUMMARY"
}
helper() {
  "$HOME/.goad/.venv/bin/python" -m goad.course1_full_backup "$1" \
    --root "$ROOT" --backup "$BACKUP"
}
stage 01-baseline-validation bash ./goad.sh -t validate -l NORTH -p vmware -i "$OLD"
grep -Fq '[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS' "$BACKUP/logs/01-baseline-validation.log" || {
  echo "[BLOCKED] Original AD/exercise acceptance marker absent" >&2; exit 1;
}

# Stage 1: Power off the original five guests with Kingdoms' own controller.
stage 02-offline-stop bash ./goad.sh -t stop -l NORTH -p vmware -i "$OLD"
stage 03-confirm-offline helper offline

# Stage 2: Backup complete instance and Vagrant box bases, then hash source/copy.
stage 04-space-preflight helper space
PHASE="05-backup-original-vms"
echo "===== $PHASE ====="
rsync -aH --sparse --numeric-ids -- "$INSTANCE/" "$BACKUP/instance/"
printf 'PASS | %s\n' "$PHASE" | tee -a "$SUMMARY"
PHASE="06-backup-vagrant-home"
echo "===== $PHASE ====="
rsync -aH --sparse --numeric-ids -- "$HOME/.vagrant.d/" "$BACKUP/vagrant-home/"
printf 'PASS | %s\n' "$PHASE" | tee -a "$SUMMARY"
if [[ -f "$HOME/.vmware/inventory.vmls" && ! -L "$HOME/.vmware/inventory.vmls" ]]; then
  cp -p "$HOME/.vmware/inventory.vmls" "$BACKUP/host/vmware-inventory.vmls"
fi
stage 07-backup-source git bundle create "$BACKUP/source-main.bundle" --all
stage 08-backup-host sudo -n tar -C / -cpf \
  "$BACKUP/host/vmware-and-systemd.tar" etc/vmware etc/systemd/system etc/hosts
sudo -n chown "$(id -u):$(id -g)" "$BACKUP/host/vmware-and-systemd.tar"
chmod 600 "$BACKUP/host/vmware-and-systemd.tar"
stage 09-check-host-tar tar -tf "$BACKUP/host/vmware-and-systemd.tar"
stage 10-byte-verify helper verify-copy
stage 11-check-source-bundle git bundle verify "$BACKUP/source-main.bundle"
(
  cd "$BACKUP"
  sha256sum source-main.bundle host/vmware-and-systemd.tar > other-artifacts.sha256
  sha256sum -c other-artifacts.sha256
)
PHASE="12-seal-backup"
printf 'NORTH original instance, all Vagrant boxes and host/source archives verified\n' \
  > "$BACKUP/backup-verified.marker"
chmod 600 "$BACKUP/backup-verified.marker"
BACKUP_VERIFIED=1
echo 'BACKUP_VERIFIED=YES' | tee -a "$SUMMARY"
echo "[PASS] NORTH_FULL_OFFLINE_BACKUP_VERIFIED"

# Stage 3: Only now may Vagrant destroy the original five VMs.
[[ "$BACKUP_VERIFIED" == 1 && -f "$BACKUP/backup-verified.marker" ]] || exit 1
stage 13-destroy-original bash ./goad.sh -t destroy -l NORTH -p vmware -i "$OLD"
stage 14-confirm-destroy helper post-destroy

# Stage 4: Original owner's vmnet10, vmnet20, vmnet99 only; never vmnet2/8.
stage 15-retirement-plan sudo -n env "PYTHONPATH=$ROOT" \
  python3 -m goad.course1_network_retire plan --provider-dir "$PROVIDER"
stage 16-retire-owned-vmnets sudo -n env "PYTHONPATH=$ROOT" \
  python3 -m goad.course1_network_retire apply --provider-dir "$PROVIDER"
stage 17-remove-retired-workspace helper remove-old

# Stage 5: A truly new NORTH generation via the stock public command.
stage 18-fifth-fresh-install bash ./goad.sh -t install -l NORTH -p vmware
PHASE="19-verify-new-install-receipt"
NEW_ID="$(helper discover-new)"
[[ "$NEW_ID" =~ ^[a-f0-9]{6}-north-vmware$ && "$NEW_ID" != "$OLD" ]] || {
  echo "[FAILED] Fifth instance receipt or ID invalid" >&2; exit 1;
}
echo "new_instance=$NEW_ID" | tee -a "$SUMMARY"
stage 20-new-runtime-validation bash ./goad.sh -t validate -l NORTH -p vmware -i "$NEW_ID"
grep -Fq '[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS' "$BACKUP/logs/20-new-runtime-validation.log" || {
  echo "[FAILED] New installation runtime acceptance marker absent" >&2; exit 1;
}
echo 'FIFTH_INSTALL=PASS' | tee -a "$SUMMARY"
echo "[PASS] NORTH_UNINTERRUPTED_FIFTH_INSTALL_AND_RUNTIME=PASS"
echo "[NEW_INSTANCE] $NEW_ID"
echo "[BACKUP] $BACKUP"
