# WSLPE P1-C — Reuse NORTH WS01, remove every AD dependency

**Scope:** WSLPE-only feature branch. NORTH is read-only and unchanged.
**Status:** Exact-VMX source implementation prepared; runtime validation pending.
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
