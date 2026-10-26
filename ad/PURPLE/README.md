# Purple Team (PURPLE) — four-VM VMware lab

Purple Team is an independent lab recipe based on KINGDOMS' existing
`ad/MINILAB`, not an edit of NORTH, KINGDOMS, or WSLPE.
The pilot AD domain is `purple.lab`.

| Guest | OS | Address | RAM |
| --- | --- | --- | --- |
| PURPLE-DC01 | Windows Server 2019 / AD | 192.168.240.30 | 4 GB |
| PURPLE-WS01 | Windows 10 domain workstation | 192.168.240.31 | 4 GB |
| PURPLE-LX01 | Ubuntu 22.04 Desktop | 192.168.240.32 | 4 GB |
| PURPLE-WAZUH | Debian 12, clean host for Wazuh | 192.168.240.51 | 8 GB |

All four are declared in one Vagrantfile. Windows uses the existing GOAD
Ansible MINILAB provisioning; Ubuntu Server is automatically converted to
Desktop via a Vagrant shell provisioner. Debian is an OS-only guest for now:
**Wazuh software, agents and Sysmon are NOT installed in this phase**.

## Box dependencies

Pinned/cached VMware Desktop images on the test laptop:

- `StefanScherer/windows_2019` 2021.05.15
- `mayfly/windows10` 2024.01.06
- `bento/ubuntu-22.04` 202510.26.0
- `bento/debian-12` 202510.26.0

Ubuntu Desktop package installation still requires the guest's temporary NAT
access; a desktop reboot may be required. Wazuh disk space must be checked
before installing its manager/indexer/dashboard on Debian.

## Host-network ownership and automation

**Do not use the VMware Virtual Network Editor to create vmnet40 manually.**
The automated bootstrap uses a root-owned additive ownership record, backed
up under NORTH's existing global VMware transaction lock. The immutable
NORTH owner is left unchanged.

- PURPLE network: `vmnet40`, `192.168.240.0/24`, host-only, no VMware
  DHCP or NAT on that network; host adapter `192.168.240.1`
- Fixed MAC-bound VMware lab adapters for all four guests
- Existing Vagrant management NAT remains during provisioning
- Existing NORTH owner, protected routes, IPs, vmnets and MACs are preserved
- Unexpected preexisting vmnet40, occupied subnets, running guests, unsafe
  owner files, or an interrupted transaction block the installation
- On the first successful transaction, only explicitly attested vmnet40
  declarations may be normalized out for NORTH's regular strict verifier
- An unexpected network mutation or unsafe rollback blocks rather than
  erasing somebody else's configuration

**This first pilot requires an already-installed, fully verified NORTH
network owner on the SAME VMware host.** That is a coexistence guard, not
an AD or dependency relationship between PURPLE and NORTH guests. General
standalone Purple Team host bootstrap is a later development task.

**Running VMs must be stopped** before the VMware service restart. Use
the existing NORTH `./goad.sh` console `stop` command and check
`vmrun list` reports zero running VMs. Leave `vmware-netcfg` closed and
do not have another host-network editor applying changes concurrently.

### Dry run: no VMware network edits

```bash
cd ~/labs/purple-team/Kingdoms
git pull --ff-only
python3 -m unittest tests.test_purple_lab_source tests.test_purple_vmware_network -v
sudo -v
sudo -n python3 -m goad.purple_vmware_network plan
```

The plan validates installed NORTH ownership and checks for conflicting
networks, routes, VMs and registered VMX/MACs. It does not write anything.
If it reports `[BLOCKED]`, do not run the install or manually fabricate
owner receipts.

### Single-command installation (runtime NOT YET ACCEPTED)

```bash
./goad.sh -t install -l PURPLE -p vmware -ip 192.168.240
```

The PURPLE VMware provider invokes the guarded bootstrap **before Vagrant
creates guests**, then the normal GOAD provisioner handles MINILAB-style
Active Directory. Only invoke this on a disposable/approved test host after
a successful dry run and a reviewed backup. This branch has **passed
offline source CI**, but the full VMware network transaction and all four
guest installs have not yet been validated on real hardware.

To inspect a previously committed vmnet40 after bootstrap:

```bash
sudo -n python3 -m goad.purple_vmware_network verify
bash scripts/purple-vmware-preflight.sh
```

The shell preflight is for **post-install verification**: it must fail when
vmnet40 does not yet exist.

## Monitoring and isolation caveats

- Wazuh manager, indexer, dashboard, Wazuh agents and Sysmon are phase 2.
- The Linux VM is a normal guest; it does not auto-enroll into AD.
- The copied MINILAB includes intentionally weak/demo credentials. Do not
  bridge it to a company network or use real company data.
- Vagrant's provisioning NAT is still connected. This is **not yet**
  NORTH-style deny-by-default exercise isolation and is unsuitable for
  untrusted payloads or malware detonation.
- Do not enable the existing `wazuh` extension: it would create an unwanted
  *fifth* Wazuh VM based on Ubuntu, not provision PURPLE-WAZUH Debian.
- Do not merge this PR until a clean host setup and failure-path restoration
  have been proven, along with four-guest and AD runtime checks.
