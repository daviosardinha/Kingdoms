# WSLPE P1-C — Remote SSH operator workflow

**Status: remote support implemented in source; first live remote preflight pending.**
NORTH remains frozen, WSLPE remains `PROVIDED`. This does not authorize
learner access or permanently apply firewall rules.

## Why this exists

The previous local-console-only shell guard correctly blocked the owner's
attempt to run the WSLPE host-firewall pilot over SSH from a phone. Remote
Kingdoms operations are an intentional use case; simply removing the guard
would risk losing the management SSH path during host firewall changes.

The new WSLPE-only workflow keeps the existing approved host policy and
adds a separate safety layer:

1. Validate an actual SSH session with both client and server IPv4 addresses.
   Reject clients/servers on the WSLPE exercise subnet, loopback-only
   access, ambiguous `ip -j -4 route get <SSH client>`, and a return
   route over the vulnerable WSLPE VMnet. **No packets are sent to NORTH**.
2. Confirm the exact running registered WSLPE VMX and unique exercise
   VMnet, verify no other running VMX uses it, reject collisions with the
   dedicated proposed nftables table, and pass local nft `--check`.
3. Prove a **real host-side transient systemd timer actually fires** by
   scheduling a root-owned `/run/kingdoms-wslpe-remote-check-<random>.done`
   sentinel and waiting for that exact file. Clean up the sentinel afterward.
   This is a harmless host *runtime artifact*, not a Windows/VMware/firewall
   change. It does not prove survival of a Kali host reboot or a broken
   systemd manager.
4. Verify certificate-pinned, authenticated WSLPE HTTPS/5986 using its
   existing (not newly hardcoded) WSLPE Ansible credentials.
5. A later *explicitly confirmed* remote pilot redoes these checks,
   arms an **independent host timer BEFORE applying** the nftables
   candidate, installs only `inet kingdoms_wslpe_exercise`, verifies
   exact rule identity and management HTTPS, and requires an automatic
   rollback after 120 seconds. NAT is never disconnected.
6. A separate read-only `--verify` works after SSH reconnection. It
   checks that the table is absent and WSLPE authenticated HTTPS is still
   functional. An unexpected table remains a blocker, not a silent PASS.

The remote route guard has no capacity to alter NORTH, host routing,
Vagrant, VMware, nftables, NTLM credentials, DNS or Windows settings.
The only potential host modification in the default preflight is the
temporary randomized /run sentinel created by its real timer test.

## Operator commands over SSH (one source-of-truth launcher)

First, update the feature branch and run the **safe preflight**:

```bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
bash scripts/wslpe-remote-operator.sh
```

The default command runs regressions, verified HTTPS and route/timer
preflight. It **does not apply nftables**, reboot any machine, or change
VMware NAT. It requires normal `sudo -v` for the harmless /run timer.

Expected success marker:

```text
[PASS] REMOTE_WSLPE_ROLLBACK_PREFLIGHT=TRUE
[PASS] WSLPE_REMOTE_OPERATOR_PREFLIGHT=TRUE
[NO FIREWALL CHANGES] No nft rule installed or NAT modification
```

**Do not start the live pilot until the first remote preflight passes and
the evidence is reviewed.** The explicitly state-changing invocation is:

```bash
bash scripts/wslpe-remote-operator.sh --execute
```

It requires entering `PILOT WSLPE HOST FILTER` via an interactive
SSH TTY. It runs the independent host timer proof *again* before
installing the 120-second WSLPE-only table, waits for expiry and
verifies removal and authenticated HTTPS. This may temporarily interfere
with a management session if route/path assumptions are wrong; use a
reconnectable SSH session and keep a practical host recovery option.

If the phone/SSH connection drops after the pilot was started, wait
at least 140 seconds and reconnect. The timer was registered on the
Kali host, not in the SSH shell. Then run:

```bash
bash scripts/wslpe-remote-operator.sh --verify
```

**Never** remove SSH guard checks, hardcode bootstrap passwords,
ignore HTTPS certificate errors, flush the whole firewall, restart host-wide
VMware networking, or use NORTH's lab-mode command as a shortcut.

## Limits and acceptance

The smoke timer only demonstrates that the host's transient systemd
timer infrastructure executed a safe command; it cannot guarantee all
possible service failures, loss of power, OS crash, or systemd corruption.
The temporary nft rollback requires Kali to remain running.

A passing firewall pilot proves timed removal and operator HTTPS, but
still **does not prove guest-to-host packet denial, ARP/L2 isolation, NAT
removal, nft rule persistence across host reboot, or safe learner SYSTEM
privilege escalation**. These remain separate acceptance gates.

P1-C is not complete until *packet-path negative tests* and an approved
WSLPE-only, recoverable NAT cutover are designed and proven.


## 2026-10-16 — Remote operator pilot: runtime PASS

The operator executed the confirmed `scripts/wslpe-remote-operator.sh --execute` via mobile SSH on Kali. The provided terminal evidence shows:

- Source regression: **31 tests PASS**.
- WSLPE certificate-verified authenticated WinRM HTTPS: **PASS**, domain-free identity PASS, credentials sourced from the existing WSLPE configuration.
- SSH return path: `tailscale0`, not `vmnet2` — **PASS**.
- Independent host timer *smoke test actually fired* — **PASS**.
- Transient WSLPE-only nftables filter on `vmnet2` installed successfully — **PASS**.
- HTTPS operator access survived the active filter — **PASS**.
- Scheduled rollback window elapsed; `WSLPE_PILOT_TABLE_ABSENT=TRUE` — **PASS**.
- Verified post-rollback authenticated HTTPS: `WSLPE_POST_ROLLBACK_HTTPS=TRUE` — **PASS**.
- Launcher completion: `WSLPE_REMOTE_PILOT_ROLLBACK_AND_HTTPS=TRUE` — **PASS**.

**Scope:** No NORTH, VM, Windows, provisioning NAT or permanent host firewall modification was performed by this pilot. The temporary WSLPE-only table was confirmed absent after the rollback window. Table absence alone does **not** prove that the rollback systemd timer was the precise removal cause; the independent earlier smoke test proves only that timer infrastructure can execute.

**Next acceptance gates:** (1) controlled WSLPE guest-to-Kali packet filtering tests with negative controls (include IPv4/IPv6 and host service paths), (2) independent isolation proof for ARP/L2, hypervisor and NORTH despite intended learner SYSTEM privileges, (3) bounded, exactly registered WSLPE-only provisioning NAT handoff/reconnect with out-of-band recovery, (4) durable firewall/guard persistence across host restart, and (5) local learner RDP access. All remain **unverified/locked**, and WSLPE status remains `PROVIDED`, not `READY`.

Do not modify NORTH, reuse its `lab-mode.sh`, disconnect NAT or promote learner access on the strength of this pilot alone.
