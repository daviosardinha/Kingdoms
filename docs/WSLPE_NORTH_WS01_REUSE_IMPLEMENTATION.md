# WSLPE P1-C — Reuse NORTH WS01, remove every AD dependency

**Scope:** WSLPE-only feature branch. NORTH is read-only and unchanged.
**Status:** 36/36 NORTH parity and 24/24 owner-timer recovery tests accepted; VMware-owner list/scratch rehearsal pending.
WSLPE remains PROVIDED / NOT READY.

This is an implementation and acceptance map, not a separate VM stack.
The NORTH environment is our proven engineering reference; copying its
scripts wholesale would drag in domain controllers, NORTH routing, fixed
VMnets, AD principals and different network assumptions.

| Capability | Actual NORTH WS01 source | WSLPE adoption |
|---|---|---|
| Native VMware registration | \`scripts/lab-mode.sh\` \`vmx_for\`, \`is_running\` | Existing \`wslpe-stage2-inspect.py\` exact instance & registered VMX, **unchanged** |
| Controlled power transition | \`lab-mode.sh\` \`wait_stopped\`, \`wait_started\`, \`ensure_vm_nat_state\` | Source-verified same **stop → offline edit → start → verify** semantics, still locked without independent rollback |
| Offline NAT property | NORTH \`get_start_connected\`, \`set_start_connected\` | \`kingdoms/wslpe_nat_cutover_contract.py\`: *only* Ethernet0 startConnected TRUE → FALSE, preserve exact Ethernet1 and all other VMX bytes |
| NAT restoration | NORTH \`ensure_vm_nat_state\` | Strict SHA256 original/candidate manifest and pure exact-byte restore renderer, **no live restore enabled** |
| Runtime readiness | \`validate-ws01-runtime.sh\` and \`validate-network-segmentation-runtime.sh\` | Existing WSLPE Stage 2, NAT readiness, certificate-pin HTTPS, socket accept/deny/recovery, routing and NIC audits |
| Windows 10 foundation | \`ansible/ws01.yml\` | Already reuses \`settings/hostname\` and \`settings/eval_rearm\` in \`ansible/wslpe-foundation.yml\`, with local workgroup/Defender/UAC checks |
| User/rights and RDP | NORTH RDP evidence and release scripts | WSLPE-only SID-based RDP/NLA evidence + planned **local non-admin** learner, no NORTH principal |
| LPE exercises | NORTH \`windows_lpe\` role | Existing \`ansible/wslpe-lpe-test.yml\` imports the **same role**, WSLPE-local RunAs credential target/learner and one technique at a time |
| Host firewall | NORTH router \`nftables\` deployment/check syntax | Reuse existing WSLPE-only \`wslpe_winrm_guard.firewall_batch\` and \`wslpe_isolation_policy.render_host_filter\`. **Never copy NORTH router nft config** |
| Automation/persistence | NORTH's router-controlled policy install | **Still a blocker**: WSLPE runs Kali-side nftables, disabled boot service, dynamic WinRM forward, different boot-order requirements |

## Source now committed

- \`kingdoms/wslpe_nat_cutover_contract.py\`: byte-preserving, in-memory
  Ethernet0 NAT disconnect and SHA256-bound original recovery.
- \`scripts/wslpe-p1c-north-cutover-preview.py\`: re-reads NORTH lifecycle
  source, validates the one registered running WSLPE VMX and its dynamic
  subnet/VMnet/forwarded WinRM port, then generates **no file writes**.
- \`tests/test_wslpe_north_cutover_parity.py\`: negative source tests for
  duplicate/foreign VMX entries, changed Ethernet1, MAC conflicts,
  wrong restore checksums, and unapproved VM/NORTH mutations.
- \`scripts/wslpe-north-cutover-preview.sh\`: one command for source
  parity, shared Windows role contracts, existing nft rule contracts,
  and live WSLPE-only NAT VMX preview. Added to the larger source gate.

Run only this **read-only** batch at the next source checkpoint:

~~~bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
bash scripts/wslpe-north-cutover-preview.sh
~~~

No new Vagrant image, domain join, Ansible foundation apply, WinRM
configuration, new learner, VMware power operation, nftables write,
host service restart or NORTH check is performed. Vagrant and WSLPE
passwords are never printed or committed.

## Do not copy these NORTH dependencies

\`commonwkstn\` / domain DNS, \`ad-data\`, \`ad-servers\`, 
\`win_domain_membership\`, Domain-profile-only RDP rules,
\`settings/adjust_rights\` with domain principals,
NORTH \`vmnet10/20/30/99\`, \`lab-mode.sh\` runtime calls,
NORTH router policy files or any DC readiness checks.

## Exactly what's still required before actual cutover

The new *pure candidate* is not a VMware update. We still need a
WSLPE-only real owner-context shutdown and startup path with independently
proven rollback before touching the registered VMX. The host-only vmnet2
exposes Kali as an L2 neighbor of a future SYSTEM-level learner, so
permanent guest isolation is not solved by Ethernet0 NAT disconnection.
The Kali nft INPUT/FORWARD policy and dynamic forwarded WinRM guard
must survive host restart without touching global rules, and actual
IPv6/ARP/L2 denial or a host-disconnected learner network design must be
proved. Then local nonadministrator RDP and each LPE technique must be
separately accepted.

The implementation deliberately fails closed. **No NAT cutover or learner
release authorization is implied by preview success.**


## 2026-10-16 — Accepted NORTH parity and VMX preview

The operator ran `bash scripts/wslpe-north-cutover-preview.sh` on Kali.
The resulting output showed **36/36 regressions PASS** and the live
read-only preview completed. Exact registered `windows_10.vmx`,
Ethernet0=provisioning NAT, Ethernet1=`vmnet2`, exact forward TCP/2210,
SHA256 original/candidate values and in-memory byte-for-byte restore
were all confirmed.

This closes the **source parity and offline-candidate preview gate** only.
NAT is still connected, vmnet2 still reaches Kali at Layer 2, and neither
VMX write nor VMware lifecycle action was executed. NORTH has not been
modified.

### Host-side owner recovery rehearsal (new source)

The new `kingdoms/wslpe_owner_recovery.py`,
`scripts/wslpe-p1c-owner-recovery-check.py` and
`scripts/wslpe-p1c-recovery-rehearsal.sh` implement the next
WSLPE-specific gate, reused from NORTH's strict operator/VMX lifecycle
contract. In one run they check source parity, exact VMX ownership and
rehearse a **system systemd timer that runs as the same non-root VMX
owner**. The timer touches and removes a unique 0700-owned disposable
`/tmp` marker; no virtual machine is stopped or edited. This shows
whether a future VMX rollback could execute independently of an SSH
login in the right Unix account context.

Execute only the consolidated harmless rehearsal:

~~~bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
bash scripts/wslpe-p1c-recovery-rehearsal.sh
~~~

**Current status:** committed, runtime test still pending. A successful
rehearsal does **not** prove vmrun works from that transient service,
nor that a powered-off VMX rollback or host-reboot persistence works.
Those gates must be implemented and accepted before live NAT cutover.


## 2026-10-16 — Owner timer live acceptance and deeper recovery proof

The operator ran the source and owner-timer rehearsal on local Kali. The
terminal log showed **24/24 source tests PASS**, the exact registered
`windows_10.vmx` owner confirmed, NORTH lifecycle source parity PASS,
and a 3-second systemd timer executing under the actual VMX owner.
`WSLPE_OWNER_HOST_TIMER_FIRED=TRUE` and
`WSLPE_OWNER_RECOVERY_REHEARSAL=TRUE` both PASS. The marker was
temporary; **no VM shutdown, restart or VMX edit occurred**.

### Combined read-only VMware recovery gate (new source)

`kingdoms/wslpe_vmrun_recovery.py` and
`scripts/wslpe-p1c-owner-vmrun-worker.py` add an independent host timer
that executes only **`vmrun -T ws list`** in the verified owner account,
then strictly matches the registered exact WSLPE VMX path (not
`windows_10.vmx` basename alone). The timer writes only a 0600
temporary JSON result in a 0700 directory; the launcher validates its
owner, VMX identity and result before removing the temporary directory.

This tests whether the *same systemd context that would need to rescue a
cutover* can actually reach VMware Workstation without a login shell.
A disabled/missing VMware session, wrong UID, ambiguous VM inventory,
incorrect systemd state or missing result **fails closed**.

The same run exercises the NORTH-derived persistent Ethernet0 NAT change
on a **disposable copy** of the registered WSLPE VMX. It applies the
candidate in the scratch file, verifies the SHA256 before/after and
restores exactly the original bytes via
`guarded_original_restore`. The registered VMX is never written.

One operator command (feature branch, local Kali account):

~~~bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
bash scripts/wslpe-p1c-vmrun-recovery-gate.sh
~~~

**This newly committed batch has not yet run on Kali.** It performs
no VM/NAT/firewall changes and never contacts NORTH. Passing it will
show owner-context *read-only VMware access* and scratch-only VMX
restoration; it will **not** prove production VM shutdown/restart, a
real powered-off VMX replacement, host reboot protection or guest
ARP/L2 isolation. Those remain locked prerequisites for live NAT
cutover and learner release.


## 2026-10-16 — Owner-context VMware list and scratch restore accepted

Live Kali operator output for `bash scripts/wslpe-p1c-vmrun-recovery-gate.sh`
confirmed **30/30 source tests PASS**, exact WSLPE VM owner/VMX matched,
host-side transient owner timer fired, and `vmrun -T ws list` was
successfully executed by the independent systemd owner service.
The owner-side inventory showed **6 running VMware VMs**; only the exact
registered WSLPE VMX was selected as the recovery target.

The scratch (disposable file) recovery verified candidate render and
original restoration byte-for-byte, with distinct SHA256 values for
original and Ethernet0-only NAT-disabled candidate.
Markers: `WSLPE_SYSTEMD_VMRUN_LIST=TRUE`,
`WSLPE_SCRATCH_VMX_RESTORE_BYTE_EXACT=TRUE`, and
`WSLPE_VMWARE_OWNER_RECOVERY_READONLY_GATE=TRUE`.

This closes **owner-context VMware read access and scratch VMX restore**.
It does **NOT** prove `vmrun stop/start` under a timer, real VMX restore,
persistent firewall rules, NAT disconnect, or Layer-2 safety. Source and
runtime tests were read-only for VM/network components. NORTH unchanged.
