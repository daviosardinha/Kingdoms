# WSLPE disposable operator management NIC candidate

**Experimental/source-only. Do not run a Vagrant bootstrap or change the existing WSLPE-WS01 master with this candidate.**

## Verified starting point

- Existing native WSLPE workspace is a two-NIC VMware guest. Ethernet0 is Vagrant bootstrap NAT; Ethernet1 is the dedicated learner exercise network vmnet2.
- VMware/Vagrant forwards guest TCP 5985/5986/22 to Kali TCP 2210/2211/2212. The interim three-port input firewall has been installed on the operator's host but is not reboot-persistent.
- The operator's read-only preflight found no subnet collision with candidate `172.28.232.0/24`, but has **not** allocated vmnet3 or verified it against every external/routed peer.
- The validated WSLPE41 master, learner clone, snapshots, NORTH, and current network rules must remain untouched.

## What the code implements

Within the WSLPE-specific Ruby recipe ONLY, setting the explicit experimental mode to `preview` attaches one provider adapter request at VMware **slot 2** via the existing shared template `v.network_adapter` support. It does not mutate the shared template or change the default WSLPE two-NIC layout. It rejects existing native WSLPE VM registrations in the generated Vagrant provider folder.

The CLI runs the WSLPE recipe in an ephemeral temporary directory and compares the Ruby result to expected metadata. It never runs Vagrant or creates a host vmnet. Default Vagrant/Windows/NAT behavior remains unchanged.

Source-preview command after pulling reviewed feature code:

```bash
cd "$HOME/kingdoms-wslpe45-pilot"
python3 -m unittest tests.test_wslpe_disposable_management_preview -v
python3 scripts/wslpe-disposable-management-preview.py \
  --exercise-prefix 172.28.231 \
  --management-prefix 172.28.232 \
  --management-vmnet vmnet3
```

Note that vmnet3 is a **proposed ID**, not verified or created. Run independent host-only vmnet ownership and subnet allocation checks before later attempting a disposable VM.

## What it explicitly does not implement

- No vmnet3 adapter creation, Windows static management IP, NIC MAC binding, WinRM HTTPS certificate pinning, per-interface Windows Firewall restrictions or guest-isolation validation.
- No migration of Vagrant's communicator to `config.winrm.host` / port 5986. HashiCorp documents this API, but actual VMware provider behavior needs a disposable VM proof.
- No disabling Vagrant's default WinRM/SSH forwarding. These remain live under the **existing master** until the new management channel is verified.
- No VMware VMX file edits, no NAT disconnect, no installation workflow integration, no release authorization, no NORTH changes.

## Next engineering steps

1. Use an independent, genuinely disposable WSLPE instance, never the 41-scenario master or learner clone.
2. Design and source-test a separate VMware vmnet allocation transaction without touching any existing network settings. Confirm VMnet ID, address, host adapter, ownership and backup/rollback.
3. Prove that a new management NIC really attaches at slot 2 under the current Vagrant VMware version; inspect VMX and Windows MAC/adapter index before Windows changes.
4. Configure Windows management IPv4 on that NIC with no default gateway and restrict WinRM HTTPS with trusted certificate and firewall remote-address/interface scoping. Exercise NIC must not have privileged management reachability.
5. Switch the **disposable** Vagrant WinRM communicator to the management IP after the NIC is configured. Prove Vagrant provision/halt/up/restore without host forwards, including failed start rollback.
6. Only then detach provisioning NAT while powered off and remove the precise Vagrant NAT forwards, with the existing Kali three-port guard retained until listeners are gone.
7. Repeat WSLPE41 fresh builds twice and NORTH coexistence checks before merging installers into main.

**A passed source test does not mean the additional NIC has been attached or that Kali no longer has NAT listeners.**