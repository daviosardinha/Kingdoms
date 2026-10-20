# NORTH / WSLPE peer-owned VMware network coexistence

Status: **source-only candidate, not approved for live stop/start**.

The original NORTH VMnet owner record, baseline SHA, journal, network adapters and VM guest state remain unchanged. This change never installs its peer-owner record automatically.

## Operator observations, 2026-10-20

- Native NORTH instance ac9fda-north-vmware still has five running VMs.
- Native WSLPE registration d986ad-wslpe-vmware contains WSLPE-WS01.
- WSLPE's exercise adapter is vmnet2, 172.28.231.0/24, with host address 172.28.231.1 and guest 172.28.231.31.
- Current vmnet8 mappings include 2210 -> 172.28.231.31:5985, 2211 -> 172.28.231.31:5986 and 2212 -> 172.28.231.31:22.
- A second learner-test VM also uses vmnet2 and is NOT isolated from the native WSLPE VM if both are powered on.

## Proposed fail-closed attestation

1. No peer-owner record means the original NORTH verifier still rejects the unrecorded VMware network.
2. A reviewed root-owned 0600 /etc/vmware/kingdoms-wslpe-peer-owner.json is required before the new peer exception is considered.
3. That record pins ONE native WSLPE VMX and generated Vagrantfile, exact file SHA256s, a dedicated non-overlapping /24 exercise network and the three management forwarding mappings.
4. The real VMware NIC assignments, Vagrant guest IP and host interface IPv4 address must match the record.
5. Only exact approved declarations may be subtracted from NORTH's comparison. Every other new network statement and NAT forward remains blocked.
6. NORTH's committed owner SHA and journal must never be rewritten merely to silence drift.

## Live release blockers

- Prove whether VMware NAT daemon listeners are bound to 0.0.0.0 and whether current nftables controls effectively restrict inbound WinRM/SSH host ports.
- Attest the current NAT forwarding provenance and VMX ownership independently; don't infer security from Vagrant's host_ip=127.0.0.1 alone.
- Verify no unrelated powered-on VM shares the peer vmnet and no unapproved forwarding or bridge connects NORTH to WSLPE.
- Obtain explicit review before creating any root-owned peer authorization file; this feature creates NO such file.
- Run read-only owner verification and subsequently canonical NORTH stop/start after the above security checks pass.

## Source verification

Run: python3 -m unittest tests.test_course1_peer_vmnet tests.test_course1_vmnet_config tests.test_course1_host_network_apply -v

Passing CI tests does not certify host isolation, full WSLPE fresh installation or end-to-end NORTH restart acceptance.