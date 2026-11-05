#!/usr/bin/env bash
# PURPLE-LX01 only: create/verify a standard, non-admin Sliver trainee.
# No passwords, keys, sudoers changes, installed tools, or other guest changes.
set -euo pipefail

ACCOUNT="sliver.trainee"
HOME_DIR="/home/$ACCOUNT"
EXPECTED_IP="172.28.233.32/24"
MODE="${1:---ensure}"
# Public, synthetic training credential. Only the salted crypt hash belongs
# in executable source; the corresponding lab-only password is documented in
# ad/PURPLE/DEPLOYMENT.md. NEVER reuse this account outside the isolated lab.
FIXED_PASSWORD_HASH='$6$dgsIO1th926L.8bc$hveg.SfOeMnQzK1hK35dzy5RSSy.tyg5k/rwcXDIPBSTDouH99qS1wIFytV4t./zyol6.bwLBGJimqdE41eV7.'

die() {
    printf '[PURPLE-LX01][BLOCKED] %s\n' "$*" >&2
    exit 1
}

[[ "$MODE" == "--ensure" || "$MODE" == "--verify" ]] ||
    die "Usage: $0 [--ensure|--verify]"
[[ "$(id -u)" == "0" ]] || die "Root privileges required for account provisioning/verification"
[[ -f /etc/os-release ]] || die "Cannot identify the guest OS"
# shellcheck disable=SC1091
. /etc/os-release
[[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "22.04" ]] ||
    die "Refusing changes outside PURPLE-LX01 Ubuntu 22.04"
ip -o -4 addr show | grep -Fq "inet $EXPECTED_IP" ||
    die "Expected PURPLE-LX01 lab IP $EXPECTED_IP not found"
getent passwd vagrant >/dev/null || die "Existing Vagrant SSH identity missing"
[[ -x /bin/bash ]] || die "Interactive bash shell not available"

if ! getent passwd "$ACCOUNT" >/dev/null; then
    [[ "$MODE" == "--ensure" ]] || die "Account is absent (verify mode never creates users)"
    [[ ! -e "$HOME_DIR" && ! -L "$HOME_DIR" ]] ||
        die "Account absent but home already exists; refusing to change its ownership"
    if getent group "$ACCOUNT" >/dev/null; then
        die "Account absent but its group name is already allocated"
    fi
    # The dot is intentional. Ubuntu 22.04 useradd supports --badname.
    # -U gives the trainee its own group, never sudo/admin membership.
    useradd --badname --create-home --user-group \
        --home-dir "$HOME_DIR" --shell /bin/bash \
        --comment "PURPLE Sliver trainee (standard user)" "$ACCOUNT"
    echo "PURPLE_SLIVER_TRAINEE_CREATED=1"
else
    echo "PURPLE_SLIVER_TRAINEE_EXISTING=1"
fi

# Never silently change pre-existing accounts; refuse drift instead.
getent passwd "$ACCOUNT" >/dev/null ||
    die "Account creation did not become visible through NSS"
awk -F: -v name="$ACCOUNT" '$1 == name { found=1 } END { exit !found }' /etc/passwd ||
    die "Account must be locally defined in /etc/passwd"
IFS=: read -r actual_name _ uid primary_gid _ actual_home actual_shell \
    < <(getent passwd "$ACCOUNT")
[[ "$actual_name" == "$ACCOUNT" ]] || die "Account identity mismatch"
[[ "$uid" =~ ^[0-9]+$ ]] && (( uid >= 1000 && uid < 60000 )) ||
    die "Account is not assigned a normal non-root UID"
[[ "$actual_home" == "$HOME_DIR" && "$actual_shell" == "/bin/bash" ]] ||
    die "Unexpected home directory or login shell"
[[ -d "$HOME_DIR" && ! -L "$HOME_DIR" ]] ||
    die "Home directory missing or unsafe symlink"
[[ "$(stat -c '%u' "$HOME_DIR")" == "$uid" ]] ||
    die "Home directory is not owned by the trainee"
[[ "$(id -g "$ACCOUNT")" == "$primary_gid" ]] ||
    die "Account primary group mismatch"

# Privileged group membership is not acceptable, even with a denied sudo rule.
for group in $(id -nG "$ACCOUNT"); do
    case "$group" in
        root|sudo|admin|wheel|docker|lxd|lxc|libvirt|libvirt-qemu|kvm|disk|shadow|adm|systemd-journal)
            die "Disallowed privileged group membership: $group" ;;
    esac
done

# sudo -l may return zero EVEN for denied users. Only an explicit denial
# verifies lack of sudo privileges; unexpected output/errors fail closed.
if command -v sudo >/dev/null 2>&1; then
    sudo_report="$(LC_ALL=C sudo -n -l -U "$ACCOUNT" 2>&1)" || true
    [[ "$sudo_report" == *"User $ACCOUNT is not allowed to run sudo on"* ]] ||
        die "Sudo policy is not an unambiguous denial for the trainee"
fi

# Enforce the same known training password on first install/reprovisioning.
# Only the salted hash enters chpasswd via stdin. No plaintext, no prompt,
# no external host secret, no password/hashed credential in process arguments.
if [[ "$MODE" == "--ensure" ]]; then
    current_hash="$(getent shadow "$ACCOUNT" | cut -d: -f2)"
    if [[ "$current_hash" != "$FIXED_PASSWORD_HASH" ]]; then
        printf '%s:%s\n' "$ACCOUNT" "$FIXED_PASSWORD_HASH" | chpasswd --encrypted ||
            die "Failed to apply fixed lab password"
    fi
    unset current_hash
fi
[[ "$(getent shadow "$ACCOUNT" | cut -d: -f2)" == "$FIXED_PASSWORD_HASH" ]] ||
    die "Lab password hash does not match expected value"

# Test a genuine login shell, own-home write/execute access, and execution
# of a standard unprivileged binary, without requiring a password.
runuser -l "$ACCOUNT" -c '
    set -eu
    test "$HOME" = "/home/sliver.trainee"
    test "$SHELL" = "/bin/bash"
    test -w "$HOME" && test -x "$HOME"
    test -x /bin/true && /bin/true
    probe="$(mktemp "$HOME/.purple-trainee.XXXXXXXX")"
    trap "rm -f -- \"$probe\"" EXIT
    printf "#!/bin/sh\nexit 0\n" > "$probe"
    chmod 700 "$probe"
    "$probe"
' || die "Login shell or standard home-file execution failed"

echo "PURPLE_SLIVER_TRAINEE_PRESENT=PASS"
echo "PURPLE_SLIVER_TRAINEE_UID=$(id -u "$ACCOUNT")"
echo "PURPLE_SLIVER_TRAINEE_GROUPS=$(id -nG "$ACCOUNT")"
echo "PURPLE_SLIVER_TRAINEE_SUDO=DENIED"
echo "PURPLE_SLIVER_TRAINEE_LOGIN_SHELL=PASS"
echo "PURPLE_SLIVER_TRAINEE_HOME_EXEC=PASS"
# Password is pre-defined by the lab fixture. No interactive prompt.
case "$(passwd -S "$ACCOUNT" | awk '{print $2}')" in
    P) echo "PURPLE_SLIVER_TRAINEE_PASSWORD_LOGIN=CONFIGURED" ;;
    *) die "Trainee password is missing or locked" ;;
esac
