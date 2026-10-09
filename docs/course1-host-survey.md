# Kingdoms Course 1 — VMware host read-only survey

Status: observed host configuration only. Course 1 deployment remains blocked.

## Operator workflow

Continue using the single consolidated command, now with an optional host
survey flag:

    cd "$HOME/kingdoms-course1-src" && git pull --ff-only && bash scripts/course1/validate-course1.sh --survey-host

The default command (without --survey-host) still runs the offline suite.
The extra stage **never** edits networking or virtualization state. It reads:

- Linux interface IPv4 addresses using `ip -j address show`;
- Linux IPv4 route tables using `ip -j route show table all`;
- configured VMware virtual networks from `/etc/vmware/networking`,
  discovered VMware vmnet devices/directories and active interface names;
- running VMware VMX list via `vmrun -T ws list`;
- *only* Ethernet network settings from listed VMX files.

Sensitive VMX non-network settings are never printed. Full filesystem paths
are not printed: each VM uses a short SHA256-derived identifier plus its
folder/VMX basenames. The script requires no sudo and does not execute
Vagrant, VM power changes, systemctl, ip route modifications or VMware
network configuration changes.

## Result semantics

`OBSERVED_SNAPSHOT` means the four key visibility sources completed: Linux
interface list, IPv4 route list, VMware networking configuration and vmrun
inventory with readable running VMX network settings. It does **not** prove
that an absent vmnet is free: VMware may have dormant or unregistered guests
or reservations outside the surveyed data.

`INCOMPLETE` exits nonzero and provides a structured list of missing data.
Do not interpret missing access or missing VMware binaries as free networks.

Both statuses explicitly report `candidate_allocation_authorized=false`
and `deployment_authorized=false`. Review the output before proposing a
per-instance allocation. PR #30 remains draft and the original Kingdoms
reference lab must not be modified.

After this survey, we will design the explicit four-VM router/Vagrant/Ansible
address mapping, audit its effect on NORTH attack traffic, and only then
introduce a disposable deployment and separate live regression gates.
