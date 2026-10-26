# Purple Team (PURPLE) — four-VM VMware baseline

A **separate** lab definition in Kingdoms, based on `ad/MINILAB`.
The domain remains a MINILAB-style simple AD environment, renamed to
`purple.lab`, and retains the original MINILAB vulnerability/demo fixtures.
Nothing in NORTH, KINGDOMS, or WSLPE is modified.

| Vagrant VM | Guest | IP suffix | RAM | Provisioned |
| --- | --- | --- | --- | --- |
| PURPLE-DC01 | Windows Server 2019 (AD DC) | .30 | 4 GB | Standard MINILAB/GOAD Ansible |
| PURPLE-WS01 | Windows 10 (domain workstation) | .31 | 4 GB | Standard MINILAB/GOAD Ansible |
| PURPLE-LX01 | Ubuntu 22.04 Desktop | .32 | 4 GB | Bento base + GNOME desktop install |
| PURPLE-WAZUH | Debian 12 (Wazuh target host) | .51 | 8 GB | OS only; Wazuh not installed yet |

**RAM: 20 GB guests** plus the host. All four VMs are defined in the same
Vagrantfile and brought up with a single command.

## Source-only preflight

The first four-machine source tests passed on 2026-10-26. This is not
a runtime or VM networking acceptance test.

Create a **separate checkout** from `main`. The existing NORTH instance
must remain untouched. Before any install, check `vmrun list`,
`ip -br -4 addr`, `ip route`, and VMware Virtual Network Editor to select
a subnet free of conflict with existing VM networks, VPNs and host routes.
For example, `192.168.240` is only a candidate, not pre-approved.

For a reliable local pilot, PURPLE pins the **locally cached VMware boxes**
`StefanScherer/windows_2019` (2021.05.15) and `mayfly/windows10`
(2024.01.06). The AD scenario is copied from MINILAB; the server box
source is intentionally changed because the StefanScherer version is
already installed and proven in the NORTH test environment.
Linux boxes come from the same Vagrant Cloud registry:
`bento/debian-12` and `bento/ubuntu-22.04` (both pinned to
202510.26.0). Debian is already cached locally; Ubuntu 22.04 must be
added to the cache before installing. The latter is a server
base transformed into **Ubuntu Desktop** by the guest provisioning script;
the desktop installation adds significant download time and takes effect
on the next graphical boot.

### Dedicated VMware network (must be configured before installation)

Purple Team uses a new **host-only vmnet40**, with no VMware DHCP or NAT
service on that segment. **Do not repurpose** any existing vmnet or modify
NORTH's vmnet10/20/99. All four guests have a VMware custom NIC pinned
to vmnet40, with these static IPs:
- DC01 192.168.240.30
- WS01 192.168.240.31
- LX01 192.168.240.32
- WAZUH 192.168.240.51
- VMware host 192.168.240.254/24

**Host network creation is not automated in this PR.** Only add vmnet40
after scheduling a maintenance window and stopping NORTH/all other VMware
VMs: applying VMware virtual network configuration can interrupt live
guests. In VMware Workstation Virtual Network Editor (Linux:
`sudo vmware-netcfg`, if installed), add `vmnet40`, choose **Host-only**,
set subnet `192.168.240.0` with mask `255.255.255.0`, disable VMware
DHCP and NAT for this segment, and set the host adapter address to
`192.168.240.254/24`. Do not change any existing VMware networks.

After configuring vmnet40, verify it without mutating anything:

```bash
bash scripts/purple-vmware-preflight.sh
python3 -m unittest tests.test_purple_lab_source -v
```

The preflight script fails if vmnet40 is missing or mismatched.
Linux guest IPs are configured through a MAC-bound Vagrant shell provisioner
with a reboot-persistent oneshot service. Windows lab IPs use the existing
`fix_ip.ps1` helper with the MAC and **no GOAD/NORTH route**.

**Provisioning caveat:** Windows and Linux guests retain their default
Vagrant NAT adapter for downloading packages and running Ansible. This is a
transitional lab build, not an egress-isolated attack range. Don't execute
untrusted malware or assume NORTH-style fail-closed exercise isolation.
Keep this installation disconnected from corporate networks and use benign
telemetry generation for the demonstration.

Once network preflight is complete, **installation command**:

```bash
./goad.sh -t install -l PURPLE -p vmware -ip 192.168.240
```

This command is a target for runtime acceptance, **not yet validated in
a live VMware deployment**. A plain `vagrant up` from the generated
instance provider folder will create all four VM definitions; the GOAD
launcher additionally runs AD provisioning.

## Deliberately postponed

- Install Wazuh on **Debian 12** and enroll DC01/WS01/LX01.
- Add Sysmon configuration and detection smoke tests.
- Verify/expand the Debian system disk before Wazuh installation;
  official all-in-one sizing commonly requires ~50 GB for a small lab.
- Add snapshots, fail-closed health checks and fresh-install acceptance.
- Replace default MINILAB credentials and vulnerabilities with a
  controlled demo fixture before any non-isolated use.
- Build a long-term box-mirror strategy. HashiCorp has announced
  retirement of the HCP Vagrant registry on **31 December 2026**.

**Important:** The existing `wazuh` extension creates its own **Ubuntu**
Wazuh VM. Do not enable it with this lab, or you will create an unwanted
fifth machine. We will adapt its installation roles for PURPLE-WAZUH.

## Isolation

The source uses the original MINILAB VMware private-network mechanism.
This is **not** the NORTH segmented lifecycle or its fail-closed network
ownership system. Do not assume it can coexist safely with a running
NORTH lab until explicit route/vmnet/VMX preflight and a first installation
in a disposable environment have passed. Do not bridge vulnerable guests
onto a company network.
