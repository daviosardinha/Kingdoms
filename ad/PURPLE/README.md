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

Create a **separate checkout** from `main`. The existing NORTH instance
must remain untouched. Before any install, check `vmrun list`,
`ip -br -4 addr`, `ip route`, and VMware Virtual Network Editor to select
a subnet free of conflict with existing VM networks, VPNs and host routes.
For example, `192.168.240` is only a candidate, not pre-approved.

The original MINILAB VMware Windows box names were retained as *sources*:
`mayfly/windows_server2019` and `mayfly/windows10`.
Linux boxes come from the same Vagrant Cloud registry:
`bento/debian-12` and `bento/ubuntu-22.04`. The latter is a server
base transformed into **Ubuntu Desktop** by the guest provisioning script;
the desktop installation adds significant download time and takes effect
on the next graphical boot.

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
