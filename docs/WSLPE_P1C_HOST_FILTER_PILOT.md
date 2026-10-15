# WSLPE P1-C — Bounded host firewall pilot and rollback

**Status:** Implemented in source, **NOT APPLIED**. NORTH frozen. WSLPE remains `PROVIDED`, NOT `READY`.

## Verified baseline

The operator's one-shot 2026-10-15 read-only audit returned **29/29 source tests PASS** and **0 blocked checks**. The unique registered WSLPE VMX uses dedicated `vmnet2` (`172.28.231.0/24`), Kali host `172.28.231.1`, guest `172.28.231.31`; no other **running** VMware VMX explicitly claims vmnet2. The nft candidate passed check-mode syntax inspection. The existing Windows 9/9 baseline, WSMan/RDP/NLA configuration and pinned authenticated HTTPS/5986 checks passed. The provisioning NAT NIC remains connected; nftables service persistence and external packet-path isolation are not proved.

## Implementation

`scripts/wslpe-p1c-host-filter-pilot.py` is a new WSLPE-only *default read-only* tool. It uses the previously audited native WSLPE instance, registered running VMX, VMware interface/subnet/route metadata and the co-tenant scan to render the existing candidate from `kingdoms/wslpe_isolation_policy.py`.

Before any later explicitly confirmed pilot, it requires the proposed nftables table to be absent (no overwrite) and validates the candidate through `sudo -n nft -c -f -`, which never applies the rules.

The opt-in, temporary host-filter mode is **not authorized for live execution yet**. It additionally:

1. Proves certificate-verified authenticated HTTPS management is healthy *before* a change, using the existing WSLPE inventory credential automatically. No new plaintext secret, no alternate HTTP fallback.
2. Registers an independent **systemd transient timer** to remove **only** the table `inet kingdoms_wslpe_exercise` after 120–300 seconds. The timer must be confirmed active **before** installing any nftables rule.
3. Applies the isolated nftables candidate without flushing existing tables. Only the dedicated WSLPE vmnet can match its INPUT/FORWARD filtering. NORTH and the existing separate WSLPE forwarded-WinRM guard table are not referenced by the candidate.
4. Verifies expected table/chain/rule identities, priorities and actions, then repeats authenticated HTTPS management. On post-installation verification failure, immediately removes only the WSLPE-owned table. The independent rollback timer remains armed as another recovery path even if the calling process terminates unexpectedly.
5. Reports that NAT remains attached and learner release is blocked.

A separately confirmed manual rollback mode targets **only** the dedicated table; it does not touch any other host rules. Do not issue broad `nft flush ruleset`, restart VMware NAT, or run NORTH's lifecycle scripts.

### Important safety limits

- The pilot's timer and exact table removal reduce the risk of temporary host firewall testing, but **are not a substitute for a proven operator console, root recovery or a reboot-persistence design**. Never test an actual rule change remotely unless independent host/VMware recovery is available.
- Linux `inet` INPUT/FORWARD hooks do not cover ARP/other Layer 2, VMware bridge/switching, other virtual NICs, or traffic escaping through the attached provisioning NAT. **A learner with SYSTEM privileges must be assumed capable of altering guest networking**.
- No attempt is made to disconnect VMware NAT, restart any host networking service, modify Windows user rights, change Windows Defender/Firewall, or contact NORTH.
- The isolated nft table is transient: host reboot persistence is intentionally not installed. Permanent filtering, guard persistence, host/L2 isolation, and later exact-VMX NAT disconnect need their own reviewed rollback contract and runtime proof.
- Existing Vagrant bootstrap credentials remain a development-only operator secret, **not** a learner credential. They must be rotated/replaced before learner access.
- All current networking checks are local development checks; do not claim a commercial hosted learner deployment is isolated or Windows evaluation licensing is commercially suitable.

## One-command read-only preview

After updating the **feature branch**, run:

```bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
bash scripts/wslpe-p1c-pilot-preview.sh
```

The preview performs source regression tests, a certificate-verified WinRM HTTPS recheck (reusing the existing WSLPE Ansible inventory credential), local nft syntax verification and target/collision/co-tenant checks. It asks for `sudo` only for read-only host rule inspection. **It does not arm the timer or install firewall rules.**

Successful preview evidence must include:
- all new and existing WSLPE unit tests PASS
- `[PASS] WSLPE_AUTHENTICATED_HTTPS=TRUE`
- `[PASS] Host nftables syntax check accepted (NOT APPLIED)`
- `[NO CHANGES]` to NORTH, Windows, VMware, nftables and host routing

## Future pilot (requires separate explicit operator approval)

Only after the read-only output is inspected, an independent Kali/VMware recovery path is proven, and the command is reviewed can the owner invoke the *state-changing* mode. The exact required confirmation string is `PILOT WSLPE HOST FILTER`. The systemd automatic rollback runs within the configured 120–300 second window; a manual rollback mode also exists with a different exact confirmation string.

Do not infer permanent safety from a successful, timed pilot. Before making this persistent, plan cross-reboot host filtering, port guard survival, authenticated operator HTTPS reachability throughout any NAT removal, verified guest-to-host and guest-to-NORTH denial from a fully compromised local SYSTEM guest, and local non-admin learner RDP ingress.

## Completion gates

- Source and dry-run tests PASS: **pending new operator run**.
- Timed nft pilot and exact rollback PASS: **not executed**.
- Durable host protections and external recovery: **not verified**.
- WSLPE-only NAT handoff without NORTH: **locked**.
- Standalone local learner RDP and 20 LPE scenario acceptance: **pending**.

**No part of this source-only preparation promotes WSLPE from PROVIDED to READY.**
