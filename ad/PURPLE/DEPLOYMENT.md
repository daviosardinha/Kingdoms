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

### Guest operating-system hostnames (new installations)

The five VMware instance IDs and the **in-guest computer names** match:

| VM ID | Guest hostname | Applied by |
| --- | --- | --- |
| `PURPLE-DC01` | `PURPLE-DC01` | Ansible `settings/hostname` |
| `PURPLE-WS01` | `PURPLE-WS01` | Ansible `settings/hostname` |
| `PURPLE-LX01` | `PURPLE-LX01` | Vagrant Linux guest hostname capability |
| `PURPLE-WAZUH` | `PURPLE-WAZUH` | Vagrant Linux guest hostname capability |
| `PURPLE-C2` | `PURPLE-C2` | Vagrant Linux guest hostname capability |

This only changes how **future fresh installations** are provisioned.
For Windows, `ad/PURPLE/data/config.json` defines the names and the
existing Ansible `ad-servers.yml` role applies them before domain
promotion/member join. Windows Vagrant hostname actions are intentionally
not added: the Mayfly WinRM startup/recovery sequence is preserved.

For Linux, `ad/PURPLE/providers/vmware/Vagrantfile` passes the VM
name to Vagrant's existing `target.vm.hostname` support. The **existing
PURPLE-only lab NIC provisioner** also makes the lowercase Linux hostname
persistent in `/etc/hostname` (through `hostnamectl`), maintains
a unique `127.0.1.1` mapping in `/etc/hosts`, and sets cloud-init
`preserve_hostname: true` when cloud-init is installed. It runs before
Wazuh/Desktop/trainee provisioning, so new guests don't require manual
`sudo` hostname-resolution fixes. The action is idempotent and does
not alter the management NAT or other `/etc/hosts` entries.

For Windows, the existing Ansible `ad-servers.yml` hostname step is
still executed **before** `ad-parent_domain.yml` and `ad-members.yml`,
avoiding a later in-place DC rename. The existing domain-controller
role disables NAT-interface dynamic DNS registration and restricts DNS
listening to the lab-facing address, while the workstation role configures
lab-side DNS and joins `purple.lab`. No changes to the shared Ansible
playbook sequence, DNS registry, or domain security configuration are made.

IP addresses, MAC addresses, network ownership, `purple.lab`,
AD inventory keys, credentials, security tools and machine counts are
unchanged.

**Existing instance `ef5c0b-purple-vmware` is intentionally not renamed.**
No source update rewrites a generated Vagrantfile or changes a running
Windows domain computer identity. The old pilot's `c2` identity remains
supported by the guarded C2 add-on helper. To verify a **new** deployment,
run `hostname` on LX01/WAZUH/C2 and
`(Get-CimInstance Win32_ComputerSystem).Name` on DC01/WS01 after Ansible
completes. Do not attempt to rename an already-promoted DC with these
fresh-install source changes.

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

**Read-only checks after the first complete installation:** on the Kali host,
from the generated provider directory, run:

```bash
for vm in PURPLE-LX01 PURPLE-WAZUH PURPLE-C2; do vagrant ssh "$vm" -c 'hostname; getent hosts "$(hostname)"'; done
```

Expected Linux names: `purple-lx01`, `purple-wazuh`, `purple-c2`,
each resolving to `127.0.1.1`. On the Windows guests, confirm
`hostname` is `PURPLE-DC01` / `PURPLE-WS01`. On DC01, validate
`Get-DnsClient` excludes the NAT NIC from registration,
`Get-DnsServerSetting -All` listens on `172.28.233.30`, and direct
`Resolve-DnsName PURPLE-DC01.purple.lab -Server 172.28.233.30 -DnsOnly -NoHostsFile`
returns the lab IP only. On WS01, validate
`Test-ComputerSecureChannel -Server PURPLE-DC01.purple.lab` returns
`True` and `nltest /dsgetdc:purple.lab /force` locates the DC.
Keep these checks read-only; the fresh build should not require a manual
`netdom` rename or DNS record deletion.

These source checks do not replace an end-to-end fresh VMware deployment,
which still needs separate acceptance on an unused instance.

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

## 6. Restart the existing installed lab (no Vagrant WinRM boot handshake)

**Use the Kingdoms-style installed-instance lifecycle**, not a raw
`vagrant up`. On an existing PURPLE lab, Vagrant can time out while
waiting for WS01 WinRM even though the Windows desktop is fully running.
Ordinary `vagrant up` then aborts the rest of the five-machine startup.

On current `main`, the PURPLE console's `start` and
`start_vm <name>` are routed to `goad/purple_existing_start.py`.
The helper first checks **all five registered owned VMware VMX files**,
then powers on the requested guests in dependency order through
`vmrun -T ws start ... nogui`. **All guests are powered on before**
any subsequent WinRM/SSH readiness checks. A WS01 readiness failure is
reported without preventing LX01, WAZUH or C2 from starting.
Already-running guests are preserved. No VM is recreated, reprovisioned,
rearmed, reset or halted.

For the **existing pilot**, the locally modified
`goad/provider/vagrant/vmware.py` may prevent a guarded `git restore` and
the old console will continue calling `vagrant up` and `vagrant halt`.
The KINGDOMS provider now dispatches PURPLE's four console lifecycle
commands **before calling the inherited VMware provider**. That lets you
synchronize only the clean `vmware_kingdoms.py` and
`purple_existing_start.py`, without touching local `vmware.py` edits.

With all earlier `vagrant up/halt` controllers exited, close the console,
then from Kali update only those two files. The guarded command refuses
to overwrite either when it has local changes:

```bash
cd ~/labs/purple-team/Kingdoms && git fetch origin main && if [ -z "$(git status --porcelain -- goad/provider/vagrant/vmware_kingdoms.py goad/purple_existing_start.py)" ]; then cp -a goad/provider/vagrant/vmware_kingdoms.py "/tmp/purple-kingdoms-provider.$(date +%s).bak" && git restore --source=FETCH_HEAD --worktree -- goad/provider/vagrant/vmware_kingdoms.py goad/purple_existing_start.py && "$HOME/.goad/.venv/bin/python" -m py_compile goad/provider/vagrant/vmware_kingdoms.py goad/purple_existing_start.py && echo '[PASS] PURPLE console start/stop synchronized; vmware.py preserved'; else echo '[BLOCKED] Local lifecycle file changes: inspect before merging'; git status --short -- goad/provider/vagrant/vmware_kingdoms.py goad/purple_existing_start.py; fi
```

Reopen `./goad.sh` afterward. The PURPLE console should now use direct
VMware lifecycle for both start and stop, even if the local base provider
remains modified. Do not run a generic `git pull`, `git reset --hard`,
or overwrite your local modifications.

If you deliberately prefer not to change *any* checkout source yet,
you can still use the following temporary standalone command:

```bash
cd ~/labs/purple-team/Kingdoms && git fetch origin refs/heads/main && git show FETCH_HEAD:goad/purple_existing_start.py > /tmp/purple-existing-start.py && PYTHONPATH="$PWD" "$HOME/.goad/.venv/bin/python" /tmp/purple-existing-start.py --provider-dir "$PWD/workspace/ef5c0b-purple-vmware/provider"
```

The code verifies Windows guests through authenticated WinRM on the
lab-facing interface, using the existing fixed Mayfly `vagrant`
management credential. It checks Linux SSH reachability and can request
one targeted WinRM service restart through authenticated VMware Tools.
If WinRM, AD services or networking are still unavailable, the start
reports **incomplete readiness**, but leaves powered-on machines intact
for investigation. Do not misinterpret VMware desktop visibility as
successful domain authentication or lab readiness.

### Shut down an installed lab without Vagrant's WinRM halt

PURPLE's `stop` and `stop_vm <name>` console commands now use the same
bounded local VMware shutdown lifecycle as KINGDOMS. The helper validates
the registered VMX identities and checks that **no previous Vagrant up/halt
controller for this PURPLE instance is still active**. It never sends a
process-group kill, touches VM monitors, resets snapshots, or recreates VMs.

Shut down members first in order **C2 → WAZUH → LX01 → WS01 → DC01**.
For each running VM, request a VMware Tools **soft** shutdown (host command
capped at 45 seconds), then give the guest up to 120 seconds to stop.
Only if VMware positively confirms it remains running does the helper use
a **hard** stop as a last resort, followed by a bounded 30-second final
power-state check. A timed-out soft-stop can already have been accepted by
Windows; this grace period prevents premature hard power-off.
An unreadable VMware running inventory **never** authorizes a hard stop.
A hard stop can cause data loss, especially on Wazuh; the fallback is only
used when graceful shutdown is proven unsuccessful.

If WS01 still runs after all attempts, the helper continues with other
independent guests but **preserves DC01** and reports an incomplete stop.
If any guest cannot be verified as stopped, it returns an error rather
than claiming success. `stop_vm` affects only the specified registered
guest and refuses to stop DC01 while WS01 is running.

On your existing pilot, after the old `vagrant halt` controller has
completely exited, run only the latest helper without pulling over your
local changes:

```bash
cd ~/labs/purple-team/Kingdoms && git fetch origin refs/heads/main && git show FETCH_HEAD:goad/purple_existing_start.py > /tmp/purple-existing-start.py && PYTHONPATH="$PWD" "$HOME/.goad/.venv/bin/python" /tmp/purple-existing-start.py --action stop --provider-dir "$PWD/workspace/ef5c0b-purple-vmware/provider"
```

To start the same installed range afterward:

```bash
PYTHONPATH="$PWD" "$HOME/.goad/.venv/bin/python" /tmp/purple-existing-start.py --action start --provider-dir "$PWD/workspace/ef5c0b-purple-vmware/provider"
```

**Fresh install is unchanged** and still uses Vagrant provisioning;
the direct VMware helper is only for already-installed guests. Raw
`vagrant up` / `vagrant halt` is not the supported PURPLE cold-start
or shutdown workflow.

## 7. Manual security activities

Beyond the baseline OS/VM provisioning and the existing Wazuh bootstrap,
operator activities stay manual: Sliver C2 installation, listeners, operator
profiles, payload handling, emulation exercises, telemetry validation,
Sysmon and Wazuh detection engineering. Do not expose a weak-password
lab to uncontrolled or production networks.
