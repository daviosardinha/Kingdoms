# Standalone WSLPE three-port management guard

**Status: operator candidate, not a boot-time or external-reachability release approval.**

The host currently has native VMware NAT management listeners on
`0.0.0.0:2210`, `0.0.0.0:2211` and `0.0.0.0:2212`.
The existing `kingdoms_wslpe_winrm` input/drop chain protects only TCP 2210.
The new guard is a separate `kingdoms_wslpe_management` nftables table and
protects all three discovered native Vagrant forwards without removing or
changing the original WinRM guard.

## Native instance and noninteractive operator preflight

Use the current source checkout with a **known original WSLPE native workspace**,
not the fresh Git feature checkout's empty workspace.

```bash
cd "$HOME/kingdoms-wslpe45-pilot"
sudo python3 scripts/wslpe-management-firewall.py \
  --workspace "$HOME/kingdoms-lpe-standalone/workspace"
```

This read-only command must resolve the unique original native WSLPE
registration and its VMX. It reads `vagrant port WSLPE-WS01` in the original
provider directory under the sudo invoker's owner context. Every host port
must be uniquely held by `vmnet-nat`. Unknown or additional Vagrant forwards
and unexpected nftables objects fail closed.

Only once that preflight and the generated diff are reviewed may the
operator explicitly request the in-memory guard with the exact dynamic
ports. **Example values below reflect the observed host on 2026-10-20 and
MUST be replaced if Vagrant dynamically reassigns ports.**

```bash
sudo python3 scripts/wslpe-management-firewall.py \
  --workspace "$HOME/kingdoms-lpe-standalone/workspace" \
  --apply --confirm-ports '22=2212,5985=2210,5986=2211'
```

The script creates its own table/chain atomically and checks the Vagrant
mapping and owner again after the transaction. It never flushes arbitrary
host chains, stops VMware services or changes NORTH's vmnets or VM power.
The pre-existing 2210 guard remains untouched.

## Non-negotiable release gates

- [ ] Verify nftables JSON for the exact three incoming port drops.
- [ ] Check loopback-only operator access and independent off-host negative reachability for TCP 2210/2211/2212. Default iptables INPUT ACCEPT does **not** prove an off-host path is reachable by itself.
- [ ] Block VM startup until the live guard is verified. A rule in memory
      is **not persistent** across reboot; VMware may bind NAT sockets before
      an ordinary post-boot guard service starts.
- [ ] Account for dynamic Vagrant port reassignment. The old port must remain
      protected until no longer listening and the new exact port must be
      guarded before the guest starts.
- [ ] Validate existing `kingdoms_wslpe_winrm` 2210 guard remains functional.
- [ ] Keep WSLPE learner-test VM off while sharing vmnet2 with native WSLPE.
- [ ] Only after these are proven should NORTH's separate root-owned
      WSLPE peer record be approved and the NORTH stop/start tests rerun.

Source unit tests alone cannot certify Linux host isolation, boot ordering,
NAT daemon behavior or the course fresh-install acceptance.
