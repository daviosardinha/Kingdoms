# WSLPE fresh-install automatic network pilot

**Branch:** `feature/wslpe-fresh-install-auto-network-pilot`  
**Status:** source-gated, disposable guest-only Stage 1; not the released 41-scenario installer.

This is an additive WSLPE-only feature branch. It does not change the full
KINGDOMS/NORTH recipes, networking, existing instances, vmnet ownership, snapshots
or the current WSLPE master. It does not unlock normal `-t install -l WSLPE`,
nor mark a Windows instance READY.

## Candidate selection

- Use the existing Linux/VMware `wslpe-check-host-network.py` parsing and
  overlap checking against all host IPv4 interfaces, all routing tables/VPNs,
  and `/etc/vmware/networking`, preceded by strict VMware VNET syntax/duplicate
  checks.
- Try `172.28.231.0/24` through `172.28.254.0/24`, then
  `172.29.200.0/24` through `172.29.254.0/24`, then
  `172.30.200.0/24` through `172.30.254.0/24`; choose the first
  collision-free visible subnet. The Windows guest receives `<prefix>.31`.
- No specific vmnet number is assigned. The preexisting VMware Vagrant provider
  determines the actual `private_network` attachment during boot.
- The chosen prefix is preserved in the native Kingdoms `instance.json`.
  It must never be automatically recalculated on start/reset.
- This is not a globally serialized allocator: other Vagrant/VMware processes
  could allocate a network after inspection. The pilot rechecks the exact live
  networking hash and proposed subnet **after** the 13-stage acceptance gate.
  Do not treat source-only acceptance as proof of final vmnet or learner isolation.

## Step 1 — Read-only host preview, safe alongside NORTH

Use a **separate clone of the repository**, never rebase/pull this branch over
an active NORTH or WSLPE checkout. On your operator Kali host:

```bash
git clone --branch feature/wslpe-fresh-install-auto-network-pilot --single-branch \
  https://github.com/daviosardinha/Kingdoms.git \
  "$HOME/kingdoms-wslpe-fresh-pilot"

cd "$HOME/kingdoms-wslpe-fresh-pilot"
./goad.sh -t wslpe-network-plan -l WSLPE -p vmware
```

This task uses **read-only** network discovery. NORTH's five running guests and
the existing WSLPE master can stay running. No `sudo`, `vmware-networks`,
Vagrant, instances, host interfaces, firewall or virtual machine is mutated.

If the plan reports a candidate, it proves only that no overlap is visible to
this checker. It does not create a VMware host-only network or prove a ready VM.

## Step 2 — Disposable clean-host guest-only boot

This is intended for a compatible separate clean VMware host, **not the current
operator host with registered NORTH and the validated WSLPE master**. Preserve
the master VM and both snapshots. A VMware snapshot does not replace a separate
backup; deleting the whole VM can also delete its snapshot chain.

On the clean host, with no running VMware guests and no registered WSLPE
instances, clone the same pilot branch and use:

```bash
cd "$HOME/kingdoms-wslpe-fresh-pilot"
./goad.sh -t wslpe-fresh-pilot -l WSLPE -p vmware -m local \
  --confirm-wslpe-fresh-pilot
```

The guard verifies that the host has no running VMware guests/processes or
identifiable WSLPE master in the standard Workstation/Vagrant inventories.
The existing 13-stage preboot gate, native `LabManager`, `LabInstance` and
VMware provider then create and boot exactly one `WSLPE-WS01`. A failed boot
leaves evidence in its own checkout workspace; **do not auto-retry, reset or
delete it**. Success means the guest is independently registered and running,
status `PROVIDED`, not `READY`.

**NOT in this pilot:** Windows learner creation, independent operator
management-network handoff, 20 foundational techniques, 21 added techniques,
JEA recovery, 41/41 vulnerable configuration proof, learner exploit/reset,
or a second reproducible clean install. These are separate release acceptance
gates. Do not merge to `main` solely because this pilot boots Windows.

## What to collect for acceptance

Record the exact pilot commit, the console output from read-only planning and
Stage 1 boot, newly created instance ID and `instance.json`, its rendered
Vagrantfile, VMX network adapter allocation, Windows guest address and the
13-stage gate result. Keep passwords, management TLS material, machine indices
and private VMX paths outside public GitHub issues/PR comments.

**NORTH and the original WSLPE golden master must remain unchanged.**
