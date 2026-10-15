# WSLPE Windows networking lifecycle

**Operator-only development contract. Not yet learner-ready.** This is a WSLPE-specific extraction of the Windows NIC lifecycle semantics already demonstrated by NORTH, rather than an invocation of NORTH's routing, AD or domain services.

## What we confirmed

The independent native WSLPE instance has booted to Kingdoms status \`PROVIDED\`. Stage 2 fixture tests passed, but the actual bootstrap WinRM guest TCP/5985 forward was observed on host TCP/2210 **listening on 0.0.0.0**. Running as root, \`ss\` and \`lsof\` both identified the owner as **vmnet-nat**, not the Python/Kingdoms console. The Vagrantfile's \`host_ip: 127.0.0.1\` cannot by itself be accepted as security evidence because the **actual daemon socket** is wildcard-bound.

NORTH already has a proven two-phase pattern:

- **Provisioning**: VMware Ethernet0 NAT attached for controlled Vagrant/WinRM bootstrap while Ethernet1 carries the exercise network.
- **Exercise**: Ethernet0 persistently disconnected, Windows guest managed through its trusted exercise interface. NORTH verifies \`ethernet0.startConnected=FALSE\`, the appropriate dedicated Ethernet1 VMnet, and direct Windows services after transition.
- **Rollback/restore**: preserve the mode contract instead of blindly invoking Vagrant \`up\` or reconnecting management NAT.

Source references: \`scripts/lab-mode.sh\`, \`scripts/validate-ws01-runtime.sh\`, \`scripts/validate-network-segmentation-runtime.sh\`, and \`goad/provider/vagrant/vmware_kingdoms.py\`.

**Do not call those NORTH scripts with WSLPE.** They assume a router, AD infrastructure, and fixed NORTH-owned VMnets. WSLPE must be an isolated one-guest implementation using the same **invariants**, not the entire NORTH lifecycle implementation.

## New WSLPE-only compensating management-port guard

New operator-only files:

- \`kingdoms/wslpe_winrm_guard.py\`: pure rule/owner validation of a dedicated nftables input chain, matching exactly one dynamically discovered WinRM forwarded TCP port.
- \`scripts/wslpe-winrm-firewall.py\`: **read-only by default**. Its \`--apply --confirm-port <current-port>\` is an explicit **privileged host firewall mutation**, scoped to the WSLPE port. It checks the native instance and running VM registration, proves the port's current socket is owned by \`vmnet-nat\`, refuses to overwrite another existing nftables table, and verifies the result after applying.
- \`scripts/wslpe-stage2-inspect.py\`: continues to demand loopback management isolation. Because the NAT daemon may genuinely bind \`0.0.0.0\`, it may instead accept the **exact runtime nftables input/drop JSON rule plus privileged owner proof** as an explicitly labeled *compensating control*. It never describes a wildcard-bound socket as loopback-bound.
- \`tests/test_wslpe_winrm_guard.py\` and expanded \`tests/test_wslpe_stage2_inspect.py\`: exercise malicious/incorrect firewall JSON, wrong ports, wrong ownership and no-guard failure behavior.

The rule created by the guarded command is in its **own** \`inet kingdoms_wslpe_winrm\` table, with one input hook and:

\`\`\`text
meta iifname != "lo" tcp dport <actual_WSLPE_host_port> drop
\`\`\`

This is not a firewall flush, a Vagrant reload, or a VMware NAT restart. It does **not** rewrite vmnet8 or touch a NORTH guest. The nftables rule is **runtime-only**. It may disappear after a host reboot, at which point the checker must fail closed. A subsequent course release must define and verify the rule's lifecycle/persistence, a clean removal path, and an independent remote-reachability test. A stage-2 pass does **not** by itself mean the guest is safe for learner access.

### First bounded operator check

After pulling and running the new source tests, **audit** the real WSLPE host port using the existing native instance (the operator's current port was TCP/2210):

\`\`\`bash
cd "$HOME/kingdoms-lpe-standalone"
python3 -m unittest discover -s tests -p 'test_wslpe_winrm_guard.py' -v
python3 -m unittest discover -s tests -p 'test_wslpe_nic_contract.py' -v
sudo python3 scripts/wslpe-winrm-firewall.py
\`\`\`

The audit intentionally exits nonzero when the protective rule is absent. **Only when the audit proves that TCP/2210 still belongs to WSLPE's vmnet-nat and the operator approves a one-port change**, execute:

\`\`\`bash
sudo python3 scripts/wslpe-winrm-firewall.py --apply --confirm-port 2210
\`\`\`

**Never copy the 2210 port number to another host without first discovering that host's actual WSLPE forward.** No change is allowed for an ambiguous instance, changed listener owner, an already present foreign rule/table or a mismatch in the explicit confirmation.

If successful, verify actual Windows guest state and the exercise NIC. The following checks **do not change any VM or networking state**:

\`\`\`bash
sudo -v
bash scripts/wslpe-stage2-acceptance.sh
python3 scripts/wslpe-exercise-network-preflight.py
\`\`\`

The Windows baseline and exercise NIC checks are separate. The exercise-network preflight intentionally fails if Vagrant's generated private network did not map to a **dedicated, unshared** host-only VMware vmnet, if its configured subnet is not the WSLPE instance subnet, or if there is no matching host interface. **Do not fix that by moving WSLPE onto vmnet8 or a NORTH VMnet.**

## Planned WSLPE-specific exercise handoff, NOT IMPLEMENTED YET

We must validate the following gates before disconnecting WSLPE's NAT adapter:

1. Prove \`ethernet0\` is the current NAT provisioning adapter and \`ethernet1\` is a **separate dedicated host-only vmnet**, not vmnet1, vmnet8, or vmnet10/20/30/99. \`kingdoms/wslpe_nic_contract.py\` and \`scripts/wslpe-exercise-network-preflight.py\` encode this requirement without changing the guest.
2. Validate that the actual dedicated host-only vmnet and the Windows guest match the native instance's configured private /24, and ensure no other guest uses that exercise segment.
3. Verify an independent, authenticated **direct WinRM HTTPS management path** to the WSLPE exercise IP from the trusted operator host. Do not disconnect NAT first and hope for recovery.
4. Implement a WSLPE-specific bounded mode transition that disconnects NAT for this exact VMX, persists \`ethernet0.startConnected=FALSE\` safely, verifies Ethernet1 remained present and the Windows machine remains reachable, and fails closed with a WSLPE-only rollback plan. **Do not invoke NORTH's lab-mode script.**
5. Prove wildcard NAT forwarding is no longer reachable from untrusted interfaces after guest isolation. A disconnected guest NIC alone is not proof that the host NAT daemon has retired its listener.
6. Only then proceed to non-admin local learner provisioning, the original 20 LPE scenarios, and the additional 15 planned scenarios.

**No automatic exercise-mode cutover is enabled in this revision.** This is deliberate: the current guest NIC-to-vmnet mapping and direct WinRM path have not yet been observed. We must inspect them before making irreversible or potentially disruptive guest changes.

For future clean VMware hosts, network IDs and the private prefix are discovered per host. For a future VPS/AWS implementation, only the learner/lab contract is shared; it requires a provider-specific virtual NIC and access adapter, not VMware vmnet names.
