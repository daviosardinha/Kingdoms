# Kingdoms Course 1 — VMware network maintenance plan

Current validated operator evidence: commit `ebedf82`, **205/205**
unit tests PASS, with six running and eight registered VMware guests.
All registered VMX files were readable; none exposed a known collision
with proposed vmnet11 / vmnet12 / vmnet13 or the Course 1 MAC identities.

## Why this requires a maintenance window

The current installed reference Kingdoms VMware host networking script
(`scripts/setup-vmware-networks.sh`) stops and restarts
`/usr/bin/vmware-networks` to modify `/etc/vmware/networking`. It
**refuses to run while any vmware-vmx guest is running**. That guard is
deliberate: changing VMware networking underneath live reference domain
controllers and guests would create an avoidable outage or lab instability.

We must **not** call that script to add Course 1 networks because it
also owns vmnet10/20/30/99 and rewrites their definitions. Instead the
new maintenance design is additive and independent.

## Planned delta (NOT applied)

| Segment | New VMware network | Subnet | Host adapter |
|---|---|---|---|
| NORTH | vmnet11 | 10.41.10.0/24 | Yes, 10.41.10.254 |
| SEVENKINGDOMS | vmnet12 | 10.41.20.0/24 | No |
| MANAGEMENT | vmnet13 | 10.41.99.0/24 | Yes, 10.41.99.254 |

DHCP disabled on all three; VMware NAT is not configured on the new
segments. The router will own the `.1` gateway for each segment.
Course 1 router has no ESSOS adapter or subnet.

The read-only `goad.course1_vmnet_maintenance` module now:

- Rechecks proposal collision fit against **the same** one-time host
  snapshot used by the rest of `validate-course1.sh --survey-host`.
- Requires a complete registered VMware library, including powered-off
  guests; an absent/unreadable library blocks maintenance planning.
- Inspects `/etc/vmware/networking` without modifying it, refuses
  duplicate existing network keys and unexpected VNET directive syntax.
- Generates the **exact additive lines** required for the three new
  networks. The original VMware config is retained as an unchanged
  prefix; the report provides SHA256 fingerprints of old/new content.
- Reports `MAINTENANCE_WINDOW_REQUIRED` when VMware VMs are running.
  Even when none are running, report is
  `HOST_CHANGE_REQUIRES_EXPLICIT_APPROVAL`. Both have
  `allocation_authorized=false` and `deployment_authorized=false`.

## Execution gates before any change

1. Agree on a maintenance window and orderly shutdown for reference
   guests. Preserve verified backup/recovery evidence for all guests.
2. Verify the exact registered/unregistered VM identities again, and
   confirm Workstation accepts the proposed custom vmnet numbers.
3. Build and review an **explicitly authorized apply + rollback**
   operation: privileged `/etc/vmware/networking` backup and additive
   change, `vmware-networks` restart, validation of all *existing*
   reference network definitions and new networks, host adapter
   `.254` address persistence for NORTH/MANAGEMENT, and a rollback
   that restores the original config on failure.
4. Boot and validate the existing reference domain controllers/services
   before a disposable, nonreference Course 1 router smoke test.

The change is **not** approved or implemented merely by the successful
maintenance plan. Do not run the reference network setup script while
reference VMs are on.

## One operator command

```bash
cd "$HOME/kingdoms-course1-src" && git pull --ff-only && bash scripts/course1/validate-course1.sh --survey-host
```

One run reports static source checks, candidate integrity, live
running/registered guest collision evidence, and the proposed config
delta. No VMware VM, vmnet, host address or route is modified.
