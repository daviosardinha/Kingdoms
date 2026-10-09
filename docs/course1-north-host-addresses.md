# NORTH host adapter recovery (after VMware vmnet allocation)

Observed on Kali 2026-10-09, with zero running VMware guests:
- Reference vmnet10 = 10.4.10.254/24, vmnet99 = 10.4.99.254/24.
- vmnet11/12/13 were created and /dev/vmnet11/12/13 exist.
- VMware Workstation assigned vmnet11 = 10.41.10.1/24 and
  vmnet13 = 10.41.99.1/24; these are WRONG for the attacker/host.
- There must be NO host interface on vmnet12.
- NORTH router will own 10.41.10.1 and 10.41.99.1.
- Course 1's host-side addresses must be 10.41.10.254 and
  10.41.99.254. No route to parent domain should bypass the router.

The reference Kingdoms host-address persistence fix already runs a
\`goad-nomad-vmnet-hostaddrs.timer\` for vmnet10 and vmnet99. NORTH
reuses that **validated Kingdoms pattern**, but with independent
\`kingdoms-north-vmnet-hostaddrs.service\` and \`.timer\`.
Neither reference systemd file nor reference interface will be edited.

## Source-controlled files

- \`scripts/course1/kingdoms-north-vmnet-hostaddrs\`:
  \`status\` is read-only; \`repair\` is root-only and modifies only vmnet11
  and vmnet13, refusing any unexpected IPs. It checks vmnet10/99 before
  and after, and rejects a host interface on vmnet12.
- \`ops/systemd/kingdoms-north-vmnet-hostaddrs.service\`:
  one-shot repair action, with VMware vmnet device guards.
- \`ops/systemd/kingdoms-north-vmnet-hostaddrs.timer\`:
  periodic repair every 15 seconds after a service run (VMware Workstation
  may recreate adapters or drop manually set host addresses).
- \`scripts/course1/manage-north-hostaddrs.sh\`: explicit privileged
  \`install --confirm-host-addresses\` and matching \`remove\`, requiring
  ALL VMware guests stopped. Existing unrelated systemd files are never
  overwritten. \`status\` is read-only.

## Validation workflow

The original read-only \`inspect_host_fit\` rejects an already-present
vmnet by design. Once a Course 1 network has been intentionally allocated,
that is NOT a collision. \`goad.course1_vmnet_phase\` distinguishes
UNALLOCATED and ALLOCATED by requiring either none or ALL of the proposed
vmnets, verifies exact VMware subnet hints, preserves original reference
host addresses, and checks registered guest/MAC conflicts by reusing the
original collision gate after removing only fully verified NORTH-owned
network evidence. Partial or surprising state fails closed.

Until address repair, \`validate-course1.sh --survey-host\` should report
\`NORTH_HOST_ADDRESSES_PENDING\`, not fail due to false network collisions.
Once corrected, it reports \`NORTH_HOST_ADDRESSES_READY\`. Neither status
authorizes Course 1 guest installation, lifecycle actions or attacks.

**One read-only acceptance after the commit is pushed:**

\`\`\`bash
cd "$HOME/kingdoms-course1-src"
git pull --ff-only
bash scripts/course1/validate-course1.sh --survey-host
\`\`\`

**After tests pass**, while all reference VMware guests remain stopped and
the maintenance window is active, use the separate privileged operation:

\`\`\`bash
sudo bash scripts/course1/manage-north-hostaddrs.sh install --confirm-host-addresses
bash scripts/course1/manage-north-hostaddrs.sh status
\`\`\`

Inspect service/timer state and routes before restarting reference guests.
Do NOT rerun \`maintain-vmware-networks.sh apply\`; its additive network
transaction already succeeded. Its recorded backup ID is
\`c1-20261009T220236Z-8a928dcd\`.

Recovery sequence, if explicitly required and all VMware VMs are stopped:
first remove NORTH-specific persistence with
\`sudo bash scripts/course1/manage-north-hostaddrs.sh remove --confirm-host-addresses\`,
then use the backed-up VMware network transaction **rollback** with the
recorded backup ID. The removal command does not revert host address
assignments by itself; removal of the VMware networks would remove those
interfaces. Existing Kingdoms reference host-address repair continues
independently. Do not start reference VMs until reference network recovery
and parent/child AD readiness are verified.

The host-address action is a new, real privileged host change. It is not
part of the offline regression suite and is never run automatically.
