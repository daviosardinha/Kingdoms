# PURPLE — Deployment and Credential Reference

**Scope:** KINGDOMS `PURPLE` VMware Workstation lab, `purple.lab`,
host-only `vmnet4` / `172.28.233.0/24`.

The five-VM deployment is unattended with **fixed, known training account
passwords**. The only password-generation exception is the **Wazuh installer**:
its initial dashboard admin password is displayed **once** when fresh
provisioning succeeds. No custom training passwords are requested interactively.

> **Training environment only.** All listed fixed credentials are intentionally
> weak or reused and must not be used on production or internet-exposed systems.
> VMware management NAT (`vmnet8`) can enable outbound access while connected.

## 1. Machine inventory

| VMware machine | Guest OS | Lab address | Role | Resources |
| --- | --- | --- | --- | --- |
| `PURPLE-DC01` | Windows Server 2019 | `172.28.233.30` | AD DS / DNS | 2 vCPU, 4 GB |
| `PURPLE-WS01` | Windows 10 | `172.28.233.31` | Windows endpoint | 2 vCPU, 4 GB |
| `PURPLE-LX01` | Ubuntu 22.04 Desktop | `172.28.233.32` | Linux endpoint / Sliver trainee | 2 vCPU, 4 GB |
| `PURPLE-WAZUH` | Debian 12 | `172.28.233.51` | Wazuh all-in-one | 4 vCPU, 8 GB |
| `PURPLE-C2` | Debian 12 | `172.28.233.60` | C2 server (manual Sliver installation) | 2 vCPU, 4 GB |

The Linux endpoints retain their Vagrant-managed SSH access. The additional
`vmnet8` NAT adapter is used for package provisioning and management;
lab-side communication uses `vmnet4`.

## 2. Fixed accounts (no prompts)

| System | Identity | Fixed lab password | Notes |
| --- | --- | --- | --- |
| `PURPLE-DC01` | `PURPLE\Administrator` | `8dCT-DJjgScp` | AD domain administrator |
| `PURPLE-WS01` | `.\Administrator` | `EP+xh7Rk6j90` | Windows local administrator |
| `PURPLE-LX01` | `sliver.trainee` | **`sliver123`** | Non-admin standard account |
| `PURPLE-DC01` / `PURPLE-WS01` | `vagrant` | `vagrant` | Vagrant provisioning / WinRM transport |

Additional domain identities defined in `ad/PURPLE/data/config.json`:

| Domain identity | Fixed password | Training groups |
| --- | --- | --- |
| `PURPLE\alice` | `spongebob` | Domain Admins, wsadmin |
| `PURPLE\bob` | `superman` | wsadmin |
| `PURPLE\carol` | `123456789` | Domain Admins, wsadmin |
| `PURPLE\dave` | `rockyou` | wsrdp |

`PURPLE-LX01`, `PURPLE-WAZUH`, and `PURPLE-C2` also retain the
`vagrant` **SSH key-based** administrative transport. Guest SSH keys are
deployment transport keys, not user-defined training account passwords.

The trainee account is created automatically by
`ad/PURPLE/providers/vmware/provision-sliver-trainee.sh`. Its fixed password
is applied from a salted SHA-512 hash by the guest provisioner. On
reprovisioning, the same hash is enforced. The guest is checked for a valid
home directory, Bash login shell, standard file execution rights, no sudo
permissions, and no privileged group memberships.

## 3. Wazuh credentials: one automatic exception

Wazuh 4.14's all-in-one installer generates passwords for its internal
components. We preserve this vendor behavior. **After first-time installation
succeeds and all services are active**, Vagrant output displays:

```text
[PURPLE-WAZUH] Dashboard URL: https://172.28.233.51
[PURPLE-WAZUH] Wazuh initial dashboard username: admin
[PURPLE-WAZUH][INITIAL PASSWORD - SAVE SECURELY] <vendor-generated-password>
```

The admin password appears **once on initial success**, not on ordinary
restarts or subsequent idempotent provisioning. Store it securely. Because
you requested console output, be aware it can also appear in saved terminal
or Vagrant logs. The complete vendor credentials archive remains root-only
inside `/root/purple-wazuh-installer/`.

For the **already-installed** pilot, read preserved credentials without
reinstalling Wazuh:

```bash
cd ~/labs/purple-team/Kingdoms
bash scripts/purple-wazuh-credentials.sh --provider-dir "$PWD/workspace/ef5c0b-purple-vmware/provider" --status
bash scripts/purple-wazuh-credentials.sh --provider-dir "$PWD/workspace/ef5c0b-purple-vmware/provider" --show
```

**OS support caveat:** Debian 12 is not among Wazuh's recommended
all-in-one OS baselines. If Wazuh's official assistant rejects it, the lab
install will fail closed. Do not assume fresh-install Wazuh validation
without an end-to-end smoke test.

## 4. Fresh deployment

From the KINGDOMS checkout on the VMware Kali host:

```bash
cd ~/labs/purple-team/Kingdoms
python3 -m unittest tests.test_purple_lab_source tests.test_purple_sliver_trainee tests.test_purple_vmware_network -v
bash scripts/purple-vmware-preflight.sh
./goad.sh -t install -l PURPLE -p vmware -ip 172.28.233
```

No password selection is required. The installer brings up all five machines,
creates `sliver.trainee` with `sliver123`, and runs Wazuh's own installer
which displays the generated admin password when it finishes successfully.
Sliver itself remains uninstalled until the manual training exercise.

## 5. Existing deployed pilot: update LX01 only

Git changes do not rewrite the generated Vagrantfile at
`workspace/ef5c0b-purple-vmware/provider`. Do not rerun a complete lab
installation, reconfigure `vmnet4`, or reprovision the other guests.

Run only the current source-owned trainee provisioner through the existing
Vagrant SSH path on a **running PURPLE-LX01**:

```bash
cd ~/labs/purple-team/Kingdoms
git fetch origin refs/heads/main
git show FETCH_HEAD:ad/PURPLE/providers/vmware/provision-sliver-trainee.sh > /tmp/purple-provision-sliver-trainee.sh
(cd workspace/ef5c0b-purple-vmware/provider &&
  vagrant upload /tmp/purple-provision-sliver-trainee.sh /tmp/purple-provision-sliver-trainee.sh PURPLE-LX01 &&
  vagrant ssh PURPLE-LX01 -c 'sudo bash /tmp/purple-provision-sliver-trainee.sh --ensure && sudo bash /tmp/purple-provision-sliver-trainee.sh --verify; status=$?; sudo rm -f /tmp/purple-provision-sliver-trainee.sh; exit "$status"')
```

Successful markers:

```text
PURPLE_SLIVER_TRAINEE_PRESENT=PASS
PURPLE_SLIVER_TRAINEE_SUDO=DENIED
PURPLE_SLIVER_TRAINEE_LOGIN_SHELL=PASS
PURPLE_SLIVER_TRAINEE_HOME_EXEC=PASS
PURPLE_SLIVER_TRAINEE_PASSWORD_LOGIN=CONFIGURED
```

The script emits the actual UID and group list too. It does not reset the
Vagrant SSH transport or install security tools.

## 6. Manual security activities

Beyond the baseline OS/VM provisioning and the existing Wazuh bootstrap,
operator activities stay manual: Sliver C2 installation, listeners, operator
profiles, payload handling, emulation exercises, telemetry validation,
Sysmon and Wazuh detection engineering. Do not expose a weak-password
lab to uncontrolled or production networks.
