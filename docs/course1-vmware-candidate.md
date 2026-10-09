# Kingdoms Course 1 — isolated VMware Vagrant and router source candidate

**Status: source-only, NOT installable.** This generator is separate from the
legacy six-Windows-VM reference source and does not modify any installed VMware
instance, host network, VMware adapter, route, guest, or Ansible configuration.

`goad/course1_vmware_candidate.py` consumes
`docs/course1-network-candidate.example.json` (strict three-zone
`PROPOSED_NOT_DEPLOYABLE` input), derives the four original Windows box
definitions from the validated reduced preview, replaces per-guest IP, gateway,
NIC vmnet and MAC identities, and constructs a NEW three-adapter Linux router.

The distinct candidate artifacts are:

- `providers/vmware/Vagrantfile`: four original Windows guest definitions
  with proposed NORTH/parent addresses, plus GOAD-ROUTER with exactly
  three explicit non-NAT lab adapters.
- `instance-preview/Vagrantfile`: outer Vagrant template syntax. **Not**
  complete: the current relative Windows provisioning script paths still
  assume the reference workspace source layout.
- `router/provision.sh`: a new router bootstrap adapted from the original
  reference script, with NORTH, SEVENKINGDOMS and MANAGEMENT only. No ESSOS
  NIC, address, MAC or bootstrap printout. The custom NICs use proposed
  PCI slots 224, 256 and 1184; their VMware/udev mapping is UNVERIFIED.
  Forwarding defaults to **DROP** (not reference provisioning allow-forward)
  until a proper transactional Course 1 lifecycle controller exists.
- `manifest.json`: source hash, exact course roster and explicit outstanding
  blockers with `deployment_authorized=false`.

The existing six-Windows-VM reference Vagrantfile, router bootstrap, snapshots,
network mode and routes remain untouched.

### One-command acceptance

```bash
cd "$HOME/kingdoms-course1-src"
git pull --ff-only
bash scripts/course1/validate-course1.sh --survey-host
```

The consolidated runner now tests the Python generator, renders the new
candidate into its own private ephemeral directory, checks `ruby -c`,
`bash -n`, and absence of ESSOS/legacy reference network identities.
It still verifies the OLD reduced recipe is blocked from startup, and deletes
the generated private candidate on normal exit/failure.

Do **not** execute `vagrant up` against either preview. On VMware
Workstation the proposed locally administered `02:44:...` MAC syntax has not
yet been proven compatible with the provider's manual MAC requirements.
`vmnet41`, `vmnet42` and `vmnet49` are unallocated example names.
No host availability check proves that dormant/unregistered VMs are absent.

### Engineering release gates

Still required before activation: VMware adapter/MAC/PCI compatibility proof,
dedicated host vmnet allocation/route selection without disturbing reference,
profile-specific Ansible/AD/DNS/WinRM settings, router management/SSH,
transactional lab-mode + NAT rollback, KINGDOMS2 SQL and all Phase 03 and
Course 1 attack regressions. This commit is *not* a deployment.
