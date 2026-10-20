# WSLPE portless management migration - source-only design gate

**Status: TARGET ARCHITECTURE ONLY. No Vagrant, VMware, firewall, VM or Windows changes have been applied by this branch.**

## Why we are changing this

On the current Kali VMware host, WSLPE-WS01 is a standalone vulnerable
Windows training VM. Vagrant's VMware bootstrap has created host TCP
forwardings for guest 22, 5985, 5986 (observed 2212, 2210, 2211). The NAT
daemon exposes these as wildcard listeners, requiring compensating host INPUT
rules. NORTH's immutable network owner correctly noticed vmnet2 and these
new mappings. The 41 LPE scenario configurations must not be lost.

Crucial source finding: WSLPE's Ansible inventory **already** selects
`{{ip_range}}.31:5985`, not a forwarded Kali host TCP port. The Windows
read-only inspection similarly connects to that private guest address. The
remaining dependency is Vagrant/VMware guest bootstrap and lifecycle. Blindly
deleting port mappings can break Vagrant provisioning, VM startup and recovery.

## Target architecture, not the currently installed state

| Adapter | Provisioning stage | Exercise/release stage |
| --- | --- | --- |
| VMware Ethernet0 | NAT bootstrap (Vagrant only) | Persistently disconnected |
| Ethernet1 | Dedicated learner exercise private vmnet | Dedicated learner exercise private vmnet |
| Ethernet2 | Dedicated *different* operator host-only vmnet | Dedicated operator management vmnet |

These networks must be independent of each other, other WSLPE learners,
NORTH's vmnet10/20/30/99 and VMware default vmnet1/8. The vmnet names and
subnets must be chosen per host, not hardcoded into the course recipe.

The low-privileged training guest is deliberately vulnerable. A second NIC
does not, by itself, make privileged WinRM safe. The operator host must
continue to reject unexpected inbound/forwarded guest traffic, and Windows
must restrict management listeners/firewall rules to the operator-side path.
The operator credentials and management channel must not be delivered as
part of the learner environment.

## Required migration sequence

1. Preserve the existing WSLPE41 master, exact VMX, snapshots and journal.
   Preserve the verified temporary nftables three-port protection.
2. On a separate disposable WSLPE instance, prove a dedicated *management*
   VMware host-only network can be provisioned without changing NORTH's vmnets,
   shared VMware NAT service or another registered VM.
3. Validate the new guest management NIC and its separate /24, unique MAC,
   local Windows address and no default route. Keep learner and operator
   networks distinct and avoid duplicate registered learner-test guests on the
   same exercise vmnet.
4. From Kali, validate actual certificate-pinned HTTPS/WinRM management over
   the dedicated management network. Do not assume opening TCP/5986 is enough.
   Confirm the service is *not* accessible from the exercise interface.
5. Replace Vagrant's native port-forwarding dependency with a proven direct
   private-management transport. All stop/start, recovery, provisioning and
   WinRM/Ansible interactions must work without host forwarded ports.
6. On a powered-off disposable instance only, perform an exact, reversible
   NAT disconnection and scoped cleanup of *only that instance's* verified
   forwarding entries. Don't edit vmnet8 wholesale or remove rules for any
   other machine.
7. Prove the original forwarded ports are absent from both the native Vagrant
   registration and active host listeners. Test port reassignment, host
   restart, and failure/rollback. The three-port interim INPUT table must
   remain until its old listeners are gone.
8. Run a full clean fresh WSLPE41 install twice, each independently, plus
   41/41 scenario configuration acceptance and local learner tests before
   releasing or merging into main.
9. Revalidate NORTH's owner guard with an explicitly attested WSLPE vmnet
   co-tenant. Do not simply whitelist foreign VMware networking directives.

## Read-only source preview

On an existing native WSLPE instance, this is EXPECTED TO BLOCK because it
has only Ethernet0 NAT and Ethernet1 exercise vmnet:

```bash
cd "$HOME/kingdoms-wslpe45-pilot"
python3 -m unittest tests.test_wslpe_portless_management -v
python3 scripts/wslpe-portless-preview.py \
  --workspace "$HOME/kingdoms-lpe-standalone/workspace"
```

The preview reads instance registration, VMX, VMware subnet metadata and
`vagrant port` as the registration owner. It does not start, stop, migrate,
disconnect or reconfigure any virtual machine, NIC, VMware host service or
firewall. A blocked result is a correct finding until a separately approved
cutover exists.

**No claim is made that the portless cutover is implemented.** This branch
adds a hard source/lifecycle acceptance contract so subsequent Vagrant,
VMware and Windows changes cannot silently weaken host/learner isolation.
