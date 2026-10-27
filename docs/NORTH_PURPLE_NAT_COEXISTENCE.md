# NORTH + PURPLE coexistence — VMware NAT forwarding proof

**State:** Proposed compatibility fix on a review branch; existing host untouched.

## Observed October 27, 2026

An installed NORTH Course 1 instance (`0da0a9-north-vmware`) could not start
while independently installed PURPLE (`ef5c0b-purple-vmware`) existed.
`--north verify` failed with `New NAT forwarding is outside approved
Vagrant management`, despite `--north diagnose` reporting `TOPOLOGY PASS`.

VMware had added these rules under its NAT network vmnet8:

```text
add_nat_portfwd 8 tcp 2200 172.28.233.31 5985
add_nat_portfwd 8 tcp 2201 172.28.233.31 5986
add_nat_portfwd 8 tcp 2202 172.28.233.31 22
```

`vagrant port PURPLE-WS01` confirmed exactly the corresponding guest/host
ports (5985→2200, 5986→2201, 22→2202).

**Critical distinction:** a Vagrant port declaration does not prove that
the NAT forwarding route to a *host-only* guest address will function.
This update permits owner-aware NORTH **verification**, not a claim
that WinRM forwarding works; repairing that guest-management path belongs
to PURPLE's lifecycle work.

## Contract

- NORTH's original root-owned owner, backup, journal and live vmnet topology
  checks remain unchanged.
- Default remains **deny** for any foreign subnet in a NAT forwarding rule.
- A one-time explicit operator command reads the registered PURPLE-WS01
  Vagrant VMX pointer, generated Vagrantfile IP and **actual `vagrant port`
  output under the original desktop user**, then compares those exact three
  rules to the VMware networking file.
- Only after matching evidence may it write a root-owned mode-0600
  receipt under `/etc/vmware/kingdoms-course1-foreign-vagrant.json`,
  bound to the immutable NORTH owner bytes and PURPLE VMX pointer bytes.
- Subsequent NORTH startup accepts only those three exact rules, *provided*
  they remain present unchanged and the verified PURPLE VMX and generated
  Vagrantfile remain the same.
- Unknown host ports, guest ports, other subnets, a different VMX, missing
  receipt, changed vmnet topology or extra NAT entries must still fail closed.
- This command does **not** edit `/etc/vmware/networking`, restart vmnets,
  stop/start guests, or reconfigure PURPLE/NORTH.

## On the verified pilot host (explicit one-time registration)

**Only after the branch is reviewed and used in the NORTH checkout:**

```bash
cd ~/kingdoms-north-fresh-test
sudo -v
sudo bash scripts/setup-vmware-networks.sh --north register-foreign-nat \
  --north-provider "$PWD/workspace/0da0a9-north-vmware/provider" \
  --purple-provider "$HOME/labs/purple-team/Kingdoms/workspace/ef5c0b-purple-vmware/provider"
```

Then from the same checkout:

```bash
sudo bash scripts/setup-vmware-networks.sh --north verify \
  --provider-dir "$PWD/workspace/0da0a9-north-vmware/provider"
```

A passed verification permits attempting the existing NORTH console `start`,
subject to all other NORTH preflights. There is **no automatic owner
bypass and no silent receipt installation** during startup.

If the port mappings change, stop and re-review; never edit a root-owned
receipt by hand or simply broaden an allowed CIDR.

## Engineering acceptance

- Offline unit tests cover exact receipt generation/reader, stale identity,
  malformed or changed ports, unauthorized forwarding, and NORTH topology
  preservation.
- Source CI must pass against the actual NORTH development branch.
- **Live verification pending:** confirm receipt works with *actual* root
  owner, VMware guest identity and Vagrant port data; start NORTH with
  PURPLE unchanged, then confirm NORTH exercise-mode isolation and PURPLE
  Wazuh/AD data remain available.
- Integrate the same owner-driven scheme into the planned single-root
  lab registry; do not rely on fixed temporary checkout directories.
