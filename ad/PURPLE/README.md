# Purple Team (PURPLE) — independent four-VM VMware baseline

PURPLE is a new lab in KINGDOMS, based on MINILAB. It is developed **only**
on the dedicated `feature/purple-team-four-vm` branch. NORTH, WSLPE and
KINGDOMS lab definitions and networking ownership are unchanged.

| Guest | OS | Address | RAM |
| --- | --- | --- | --- |
| PURPLE-DC01 | Windows Server 2019 / Active Directory | 172.28.233.30 | 4 GB |
| PURPLE-WS01 | Windows 10 domain workstation | 172.28.233.31 | 4 GB |
| PURPLE-LX01 | Ubuntu 22.04 Desktop | 172.28.233.32 | 4 GB |
| PURPLE-WAZUH | Debian 12 / clean Wazuh host | 172.28.233.51 | 8 GB, 4 vCPUs |

All four guests are created through one Vagrant/VMware provider file. The
Windows machines retain standard MINILAB/GOAD AD provisioning. Ubuntu 22.04
Server is converted to Desktop by an automatic package installation.
Debian is OS-only for now: Wazuh software and agents are **not installed**.

## Laptop pilot: reuse existing unallocated VMware segment

NORTH maintains an immutable /etc/vmware/networking owner record and rejects
new host network declarations. To avoid ANY changes to NORTH branches or
the installed NORTH checkout, PURPLE initially uses existing **host-only
vmnet4** (172.28.233.0/24, VMware DHCP/NAT disabled). This vmnet is already
present in the laptop's baseline. No new vmnet is created in this stage.
We must **prove vmnet4 is not used by another registered VM** before
starting. The PURPLE preflight checks the network, host route and registered
VMX/MAC ownership, and fails closed on conflicts.

PURPLE itself still automatically creates all four VMs and configures
static IPs on their lab-facing NICs, plus Ubuntu Desktop packages.
The Vagrant management NAT adapter remains attached during provisioning,
so this is not a malware-safe, deny-by-default exercise environment.

On an entirely fresh host, dedicated vmnet creation can later be automated
inside PURPLE without dependence on NORTH. On a shared NORTH-owned host,
introducing an additional vmnet requires a host-wide ownership design; it
must never silently rewrite or bypass NORTH's existing owner. That
future task is intentionally not implemented in this pilot.

## Cached box sources

- mayfly/windows_server2019 (original MINILAB box)
- mayfly/windows10 2024.01.06
- bento/ubuntu-22.04 202510.26.0 (Desktop packages installed by shell)
- bento/debian-12 202510.26.0

## Read-only preflight

```bash
cd ~/labs/purple-team/Kingdoms
git pull --ff-only
python3 -m unittest tests.test_purple_lab_source tests.test_purple_vmware_network -v
bash scripts/purple-vmware-preflight.sh
```

No NORTH checkout/source update is required. The preflight checks only
existing VMware state; it performs no host networking edits.

## Installation command

```bash
./goad.sh -t install -l PURPLE -p vmware -ip 172.28.233
```

The provider checks vmnet4 **before starting any VM**. Do not run the
installation until the read-only preflight and generated Vagrantfile review
pass. Never create vmnet40 through the editor on the currently NORTH-owned
host, since NORTH's immutable verifier would reject it.

## Windows 10 Enterprise Evaluation maintenance

PURPLE-WS01 uses the **same evaluation rearm strategy as KINGDOMS and NORTH**:
`ansible/roles/settings/eval_rearm/tasks/main.yml`. The Mayfly Windows 10
box is a time-based evaluation image. This is **not** a purchased-product-key
activation flow. No key or environment variable is needed.

During a new PURPLE installation, the provider explicitly brings up DC01,
then starts WS01 **without running Vagrant Windows provisioners**. The initial
WS01 Vagrant wait is bounded to 360 seconds. If it cannot complete, the
provider reuses the hardened NORTH/KINGDOMS Vagrant-controller cleanup and
does not begin guest recovery while a Vagrant controller remains active.

The provider then runs `scripts/purple-ws01-vmware-eval.py --fresh-install`
through authenticated VMware Tools, independently of Vagrant's forwarded
WinRM. This invokes the same conditional `TIMEBASED_EVAL` / `slmgr /rearm`
strategy as KINGDOMS/NORTH. When no grace remains, it rearms and reboots only
WS01, verifies the reboot timestamp changed, and requires positive evaluation
grace. A usable evaluation never consumes a rearm or forces a licensing reboot.
If rearm was completed but installation was interrupted, the helper detects
and resumes the successful pending rearm instead of consuming another.

Only **after** evaluation verification does Vagrant execute WS01's original
WinRM/networking provisioners; Linux machines are brought up afterward,
then normal AD Ansible provisioning runs. The provider fails closed if either
the VMware Tools recovery or subsequent Windows/WinRM provisioning fails.
The software does not disable evaluation services or bypass licensing.

**Fresh-install caveat:** before Vagrant's `fix_ip.ps1` runs, the new WS01
lab-facing NIC may not yet have `172.28.233.31`. The helper's special
`--fresh-install` mode tolerates a temporarily missing lab IP only if both
VMware adapters are up; it does not weaken identity checks for manual
recovery of existing installed instances.

**Validation:** the original four-VM PURPLE pilot and a separate manual
VMware Tools WS01 rearm/reboot have been tested live. The *new fully automatic
first-boot orchestration* has passing offline regressions but still needs a
fresh-instance end-to-end test. Do not assume success until that run is verified.

Fresh install:

```bash
./goad.sh -t install -l PURPLE -p vmware -ip 172.28.233
```

**Recovery of the already installed ef5c0b instance:** VMware Tools can
authenticate and execute guest processes even when Vagrant forwarded WinRM
hangs. Use the repository-owned helper instead of manual PowerShell or another
Vagrant install. It verifies the exact running WS01 VMX, checks the Windows
client and lab IP, copies the source rearm script to the guest, runs it through
VMware Tools, reboots **only WS01 if rearm was actually needed**, waits for
VMware Tools, and verifies the post-reboot evaluation state.

```bash
cd ~/labs/purple-team/Kingdoms
git pull --ff-only
python3 scripts/purple-ws01-vmware-eval.py \
  --provider-dir "$PWD/workspace/ef5c0b-purple-vmware/provider"
```

If a previous helper run printed `PURPLE_WS01_EVAL=REARMED` but stopped
before reboot (for example, an old boot-timestamp output bug), **do not
invoke the normal recovery again**. Its prior `slmgr /rearm` has already
succeeded. Instead resume the outstanding reboot and verification only:

```bash
python3 scripts/purple-ws01-vmware-eval.py \
  --provider-dir "$PWD/workspace/ef5c0b-purple-vmware/provider" \
  --resume-pending-rearm
```

The resume mode requires `REARMED` and `PASS` markers from the selected
guest's preserved result file before changing anything. It does not repeat
the licensing command. It probes the current boot, reboots only WS01,
then requires a **different boot timestamp** and nonexpired evaluation.

The helper requires the original Mayfly `vagrant/vagrant` local test account
to retain working VMware Tools guest access, as verified on this instance.
It is deliberately scoped to PURPLE-WS01 and never reconfigures VMware
networks or any other guest. The same helper now runs **automatically** during
new PURPLE installations; manual invocation remains a bounded recovery option
for already-created instances. Only the new installation path uses
`--fresh-install` to handle an as-yet-unconfigured Windows lab NIC.


### Wazuh installation readiness

PURPLE-WAZUH is configured with **4 vCPUs and 8 GiB RAM**, matching the Wazuh
all-in-one quickstart recommendation for 1–25 agents. The installed pilot
`ef5c0b` was generated with 2 vCPUs before this change; its generated
Vagrantfile must be synchronized and that one VM restarted to apply the
additional CPUs (not reinstalled). The pilot's 62 GiB root filesystem
provides enough disk capacity for initial Wazuh testing.

Wazuh 4.14 provides Debian-family DEB packages, but current quickstart
recommendations explicitly list Ubuntu/RHEL-family operating systems rather
than Debian 12. Debian 12 therefore needs an installation smoke test and
must not be represented as a vendor-recommended Wazuh server OS.

## Next phase

- Verify Debian VM disk meets Wazuh's storage requirements; expand if needed.
- Install the Wazuh all-in-one stack on Debian, enroll Windows and Ubuntu
  agents, configure Windows Sysmon, and validate the first detection.
- Preserve independent snapshots, health tests and Vagrant lifecycle.
- Replace intentionally vulnerable MINILAB credentials before use outside
  a fully isolated, synthetic-data learning environment.
