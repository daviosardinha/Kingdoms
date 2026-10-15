# WSLPE network portability and provider boundary

**Status: design/contract gate, not deployed or runtime-validated.**

WSLPE is an independent Windows Local Privilege Escalation lab under the Kingdoms operator-only control plane. It is **not** dependent on a NORTH installation, a domain controller, a fixed VMware `vmnet` number, or any infrastructure reachable from its student-facing exercise interface.

## What the current VMware recipe actually does

- `ad/WSLPE/providers/vmware/Vagrantfile` supplies exactly one `WSLPE-WS01` Windows guest, a pinned box, and an IP derived from the selected instance `ip_range`.
- `template/provider/vmware/Vagrantfile` uses Vagrant's default VMware management connectivity and adds `target.vm.network :private_network, ip: box[:ip]` unless a specific lab opts out. **WSLPE does not opt out.**
- The private-network declaration does **not** explicitly select `vmnet8`, `vmnet10`, or another named vmnet. VMware/Vagrant decides which virtual network implements the private-network request at deployment time. This must be inspected on the resulting VM.
- On a conventional VMware Workstation installation, `vmnet8` is the default NAT network, but it must be discovered rather than assumed on every host. The NAT/management interface is **not** automatically the WSLPE exercise interface.
- The `172.28.231.0/24` prefix is a **candidate for this operator's machine**, not a Kingdoms-wide default. The default provider/lab instance `ip_range` must be reviewed and explicitly selected per deployment.

## Network roles, not hard-coded vmnets

| Role | Current local VMware implementation | Future provider |
| --- | --- | --- |
| Operator management and temporary provisioning | Provider-managed VMware management/NAT, often vmnet8 | Provider-specific trusted management path, never learner-facing control plane |
| WSLPE exercise interface | Isolated Vagrant `private_network`, with an instance-configured private IPv4 address | Provider-specific isolated virtual NIC, VPC subnet, or virtual network with equivalent learner reachability |
| Learner access | Not provisioned yet; credentials/access delivery must be deliberately scoped to the assigned Windows guest | Restricted approved connection endpoint, optionally through a dedicated access broker |
| NAT egress | Permitted **only during trusted bootstrap as required**; removal/disconnection and offline repeatability must be tested | Denied/restricted by security groups/firewalls/routes unless explicitly required and approved |

**Never treat NAT alone as an isolated training network.** In particular, `vmnet8` may be shared with unrelated VMs and permit outbound networking. A deliberately vulnerable machine must not be trusted merely because it has a private IP. The operator must also prevent guest-to-host and guest-to-hypervisor management access through firewall, routing and interface controls.

## Current operator host collision preflight (read-only)

The source-level portability tests have passed on the operator's development machine (6/6). That proves the recipe does not pin specific VMware vmnet names; it **does not** prove a proposed range is safe in the live VMware environment.

`scripts/wslpe-check-host-network.py` is a **Linux/VMware-only read-only checker**, independent of NORTH's hardcoded VMware configuration scripts. It inspects JSON IPv4 interface addresses, **all routing tables** (including routes installed by VPNs), and the host's actual `/etc/vmware/networking` subnet/netmask definitions. It fails closed if the VMware metadata is unreadable or if a candidate network overlaps the observed routes, interfaces or configured vmnets.

```bash
cd "$HOME/kingdoms-lpe-standalone"
python3 -m unittest discover -s tests -p 'test_wslpe_host_network.py' -v
python3 scripts/wslpe-check-host-network.py --ip-range 172.28.231
```

The prefix above is **only a candidate observed to be outside the previously shared address list**, not a universal default. This checker never installs/configures a vmnet or VM and reports `[NOT VERIFIED]` for the actual future guest adapter, other VMs' static IP assignments, NAT/firewall policy and learner isolation. A `[PASS]` does **not** authorize installation. The WSLPE installer remains locked pending the remaining network and guest runtime gates.

A future Windows VMware host or VPS/cloud provider needs an equivalent **provider-specific** network preflight, not `/etc/vmware/networking`.

## Fresh VMware host acceptance

The same WSLPE recipe should be portable to a compatible clean VMware workstation/bare-metal host **without NORTH**, subject to an explicit preflight:

1. Prove that VMware Workstation, the compatible Vagrant provider/plugin, Windows guest box/version and WinRM management path are available.
2. Enumerate **all** host IPv4 routes/addresses, VPNs and VMware vmnets; reject overlapping address spaces. Do not silently reuse NORTH's vmnet10 or the existing operator's private subnet.
3. Choose an available private /24 and render the native WSLPE instance using the existing Kingdoms `LabInstance` preview. A preview PASS is only source validation, never authorization to create a VM.
4. Inspect the actual Vagrant/VMware adapter mapping once instantiated. Verify the management and exercise adapters are correctly separated, and the latter never joins an existing NORTH or unrelated VM segment.
5. Verify WinRM remains operator-only, learner account is local/non-admin, and no domain join or external target dependency exists.
6. When provisioning completes, test that learner-side LPE exercises work with management NAT disconnected and cannot reach the operator control plane or other learners' VMs.
7. Fail closed if a requested network cannot be isolated, even if an alternative NAT interface is present.

These runtime checks are **not yet implemented as a complete pre-install automated gate**. WSLPE installation remains locked until they are validated.

## Future VPS or AWS installation

**Do not carry VMware vmnet identifiers into cloud metadata, AMIs, VPCs, or instance provisioning.** WSLPE's reusable assets are its Windows image/OS contract, local-account foundation and shared `windows_lpe` Ansible role. Deployment adapters implement the actual VM and networking.

There are two materially different hosting models:

- **Nested hypervisor on a VPS or dedicated host:** Requires confirmed hardware-assisted virtualization/nested virtualization, sufficient resources, a supported Linux/Windows hypervisor/guest configuration and licensing. Many ordinary VPS products do not offer these capabilities; VMware Workstation on the existing Kali desktop is not a drop-in VPS deployment recipe.
- **Direct Windows cloud instance (e.g. AWS EC2):** Use a provider-specific Windows image/AMI pipeline and isolated VPC subnet/security groups. Vagrant's VMware `private_network` and `vmnet8` are not applicable. Confirm Windows image import/build options, license rights, appropriate instance hardware, learner assignment and restricted access delivery.

The present `WSLPE` recipe has **only a VMware provider definition**. A future AWS/VPS adapter must be separately implemented and accepted; source portability does **not** claim cloud deployment is already supported. It must not call any NORTH router, domain controller or VMware network setup script.

## Regression gates and source ownership

- `WSLPE`'s recipe must never hard-code `vmnet8`, `vmnet10` or a particular development-machine IP prefix.
- Provider defaults must remain provider-specific. Do **not** modify NORTH's provider networking in the name of WSLPE portability.
- The shared `windows_lpe` role must remain free of VMware/vmnet/cloud provider assumptions.
- The WSLPE operator console must keep `install` disabled until the native provider/network isolation gates are proven.
- A later clean-host test must demonstrate installation **without NORTH**. A separate cloud-provider test is mandatory before calling WSLPE portable to AWS/VPS.

See [WSLPE core integration plan](WSLPE_CORE_INTEGRATION_PLAN.md).
