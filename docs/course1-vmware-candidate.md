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
- `instance-preview/Vagrantfile`: outer Vagrant template with the three
  Windows provisioning paths rebased into the self-contained private bundle.
  This is still NOT a deployable instance; VMware runtime is unverified.
- `vagrant/fix_ip.ps1`, `vagrant/Install-WMF3Hotfix.ps1` and
  `vagrant/ConfigureRemotingForAnsible.ps1`: privately staged Windows helpers.
  The candidate-only fix_ip.ps1 installs `10.41.0.0/16` through the course
  router, replacing the reference script's `10.4.0.0/16` persistent route.
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

Do **not** execute `vagrant up` against either preview. The proposal
now uses VMware-format `00:50:56:3A/3B:XX:XX` manual MACs, which pass a
static syntax/range check; actual VMware provider and runtime behavior are
still unproven.
`vmnet11`, `vmnet12` and `vmnet13` are unallocated example names.
No host availability check proves that dormant/unregistered VMs are absent.

### Engineering release gates

Still required before activation: VMware adapter/MAC/PCI compatibility proof,
dedicated host vmnet allocation/route selection without disturbing reference,
profile-specific Ansible/AD/DNS/WinRM settings, router management/SSH,
transactional lab-mode + NAT rollback, KINGDOMS2 SQL and all Phase 03 and
Course 1 attack regressions. This commit is *not* a deployment.

## VMware static-MAC compatibility correction

The example candidate now uses VMware Workstation's documented manual
static Ethernet range `00:50:56:00..3F:YY:ZZ` instead of the unsupported
`02:44` test MACs. It also proposes unallocated vmnet11/12/13 rather than
vmnet41/42/49, for conventional Workstation naming. These identifiers are
not reserved; dormant guests and host VMware configuration require separate
collision/compatibility validation before deployment.

VMware reference: https://knowledge.broadcom.com/external/article?legacyId=507
