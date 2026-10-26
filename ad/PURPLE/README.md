# Purple Team (PURPLE) — independent four-VM VMware baseline

PURPLE is a new lab in KINGDOMS, based on MINILAB. It is developed **only**
on the dedicated `feature/purple-team-four-vm` branch. NORTH, WSLPE and
KINGDOMS lab definitions and networking ownership are unchanged.

| Guest | OS | Address | RAM |
| --- | --- | --- | --- |
| PURPLE-DC01 | Windows Server 2019 / Active Directory | 172.28.233.30 | 4 GB |
| PURPLE-WS01 | Windows 10 domain workstation | 172.28.233.31 | 4 GB |
| PURPLE-LX01 | Ubuntu 22.04 Desktop | 172.28.233.32 | 4 GB |
| PURPLE-WAZUH | Debian 12 / clean Wazuh host | 172.28.233.51 | 8 GB |

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

## Target installation command (not yet runtime tested)

```bash
./goad.sh -t install -l PURPLE -p vmware -ip 172.28.233
```

The provider checks vmnet4 **before starting any VM**. Do not run the
installation until the read-only preflight and generated Vagrantfile review
pass. Never create vmnet40 through the editor on the currently NORTH-owned
host, since NORTH's immutable verifier would reject it.

## Windows 10 workstation activation during fresh installs

The original MINILAB Windows boxes and network configuration are unchanged.
PURPLE adds **one** Windows-specific Vagrant shell provisioner to WS01:
after WinRM/network setup, apply a valid Windows product key, confirm activation,
then reboot and wait for WinRM to recover **before** AD Ansible provisioning.
DC01 and the Linux guests are unaffected.

The key is **never stored in Git or generated Vagrantfile**. Provide it to the
installation process as a temporary environment variable (do not type the
literal key into a command or commit it to a file):

```bash
cd ~/labs/purple-team/Kingdoms
read -rs -p 'PURPLE-WS01 Windows product key: ' PURPLE_WS01_PRODUCT_KEY
echo
export PURPLE_WS01_PRODUCT_KEY
sudo -v
./goad.sh -t install -l PURPLE -p vmware -ip 172.28.233
unset PURPLE_WS01_PRODUCT_KEY
```

A missing key causes the WS01 activation provisioner to fail clearly rather
than proceeding silently. A key that does not match the installed Windows
edition or cannot activate will also block WS01 provisioning. Use a legitimate
license for the **actual edition** in the Mayfly Windows 10 image; Windows
Enterprise Evaluation editions may require an appropriate non-evaluation image
or supported edition conversion, not just a product key.

The key passes transiently through Vagrant's sensitive environment-variable
mechanism and WinRM; it is not a hardware-backed secret store. Keep debug
logging disabled and protect the operator account. Vagrant's `sensitive: true`
masks provisioner environment values in normal output.

This hook applies to **newly generated PURPLE instances**. The already installed
`ef5c0b-purple-vmware` has a generated Vagrantfile from before the hook; do
not rebuild or automatically reprovision it. Activate that existing WS01
manually with a valid key if needed.

## Next phase

- Verify Debian VM disk meets Wazuh's storage requirements; expand if needed.
- Install the Wazuh all-in-one stack on Debian, enroll Windows and Ubuntu
  agents, configure Windows Sysmon, and validate the first detection.
- Preserve independent snapshots, health tests and Vagrant lifecycle.
- Replace intentionally vulnerable MINILAB credentials before use outside
  a fully isolated, synthetic-data learning environment.
