# KINGDOMS — One Root, One Console, Independent Lab Instances

**Status:** Deferred engineering / next multi-lab integration update. **Not implemented.**

**Requested:** 2026-10-27, after the PURPLE v1 rollout and NORTH resume.

## Objective

Operate all independently developed KINGDOMS labs from **one canonical source root**
and **one** `./goad.sh` command. A learner/operator must not have to enter
a separate NORTH checkout or PURPLE checkout just to select an installed lab.

The finished management console should discover installed instances regardless
of which lab created them and should allow selecting NORTH, PURPLE, full
KINGDOMS (GOAD scenario) and WSLPE without silently creating, moving, or
reprovisioning their Windows or Linux virtual machines.

The existing repository source root should remain the canonical Git checkout;
the migration must not require a new or nested repository.

### Current observed behavior (source-confirmed)

- `goad/goadpath.py`: `GoadPath.get_workspace_path()` is
  `<current-repository-root>/workspace`.
- `goad/instances.py`: `LabInstances._init_instances()` scans **only that
  checkout's** `workspace/*/instance.json` and reconstructs the
  installed-instance table from its local disk paths.
- `goad.py`: the console lists the loaded workspace and loads the locally
  defined default instance.
- Therefore `~/labs/purple-team/Kingdoms/./goad.sh` shows installed
  `ef5c0b-purple-vmware`, whereas
  `~/kingdoms-north-fresh-test/./goad.sh` shows
  `0da0a9-north-vmware`. **These are two source checkouts, not two
  separate control planes that should remain permanent.**
- The current `main` contains `ad/NORTH`, `ad/PURPLE`, and
  `ad/GOAD`/other existing scenarios, but **does not yet have
  `ad/WSLPE`**. The standalone WSLPE development must be integrated
  as a separate, properly tested lab before claiming it is selectable
  in the unified console.

### Target operator experience

One root, e.g. `~/Kingdoms` (final physical path selected once):

```text
~/Kingdoms/
  goad.sh
  ad/                       # All merged scenario definitions
  ansible/                   # Shared provisioners
  goad/                      # One lab-management CLI
  scripts/
  workspace/                 # Registered per-instance runtime metadata
    0da0a9-north-vmware/
    ef5c0b-purple-vmware/
    <kingdoms-instance-id>/
    <wslpe-instance-id>/
```

```bash
cd ~/Kingdoms
./goad.sh
```

Example console (illustrative only; not currently implemented):

```text
Instance ID               Lab       Provider  Network
0da0a9-north-vmware       NORTH     vmware    10.4.0.0/16
ef5c0b-purple-vmware      PURPLE    vmware    172.28.233.0/24
...                       KINGDOMS  vmware    own topology
...                       WSLPE     vmware    own topology
```

Switching to an instance must preserve its identity, MACs, Vagrant state,
VMware guest files, domain state, and existing installed applications. The
single console is a **management consolidation**, not a full lab rebuild.

## Engineering contract

1. **Inventory first, read only:** enumerate every existing checkout,
   `instance.json`, generated provider folder, `.vagrant` state,
   referenced `.vmx` paths, registered VMware guests, and actual lab
   networks. Verify instance IDs are unique. Do not infer that Git branch
   name represents an instance identity.
2. **Choose a canonical root once:** a user-owned KINGDOMS checkout from
   a known, clean Git commit on `main`, not a symlink chain or implicit
   per-branch source directory. In-flight NORTH and WSLPE engineering stays
   on its own review branches until merged; do not replace their
   installation-critical code with older `main` behavior.
3. **Agree on a runtime registry:** either a single versioned workspace
   inventory or a tested shared registry mechanism with explicit
   per-instance paths. Retain the supported behavior of
   `GoadPath.get_instance_path()`, generation of inventories, Vagrant
   identities, and safe deletion. Registry migration must be transactional:
   plan -> validate -> back up -> apply -> verify -> rollback on failure.
4. **Preserve VM identities:** do not copy or move running `.vmx` or VM
   disks, regenerate MAC addresses, `vagrant destroy`, or recreate
   Vagrant VM mappings merely to change the workspace listing. Handle
   absolute paths in `.vagrant/machines/*/vmware_desktop/id` and any
   VMware inventory/provider paths explicitly. Detect and refuse stale
   paths; never silently point at a different VM.
5. **Maintain independence:** NORTH keeps its existing segmented
   vmnet10/vmnet20/vmnet99 ownership and policies; PURPLE keeps isolated
   vmnet4 (172.28.233.0/24); other labs get documented non-conflicting
   networks. Starting, stopping, resetting or deleting one instance must
   never mutate an unrelated lab or host network.
6. **One console, many instances:** enumerate all registered instances,
   choose an instance explicitly, show each instance's real state and
   defaults, and apply `start/stop/status` only to the selected instance.
   Avoid ambiguous global-default operations across multiple labs.
7. **Avoid accidental bootstrap:** opening the console must not start
   provisioning, create VMware networks, switch Git branches or edit
   VMware host settings. Implement a `--dry-run`/read-only migration
   report and explicit opt-in for any state change.
8. **Preserve historical projects:** do not remove old checkouts or
   their workspace data until the canonical console is proven to control
   the **same VMs**, with snapshots and a tested rollback. Old source
   folders can be retired only in a separate confirmed cleanup step.
9. **Documentation:** replace scattered per-checkout launch instructions
   with one canonical launch path. Clearly distinguish lab definitions
   (`ad/`), installed instances (`workspace/`) and original VMware
   machine storage.
10. **Rollout order:** prove two existing labs (NORTH + PURPLE) first;
    integrate WSLPE after its independent scenario and lifecycle have
    passed acceptance; add the full KINGDOMS environment when existing
    state is discovered and compatible. Never assume an undeployed lab
    already exists on the host.

## Acceptance gates

- [ ] Read-only inventory correctly discovers both existing installed
      instance IDs without rebuilding or modifying their guests.
- [ ] A dry run identifies each required metadata change with zero host
      writes.
- [ ] Automated tests cover path translation, multiple defaults, missing
      VMX, duplicate identity, interrupted migration, and safe rollback.
- [ ] Launching **one** `./goad.sh` lists both the deployed PURPLE and
      NORTH instances.
- [ ] `status/start/stop` operate only on the chosen lab; both labs may
      run simultaneously on disjoint networks when the host has resources.
- [ ] Verification proves the same VMware VM IDs, files, MACs, IPs and
      AD/Wazuh state before/after console consolidation.
- [ ] Existing NORTH lifecycle / safety preflights and PURPLE VMware
      network guard still pass.
- [ ] WSLPE is listed only after its separate lab integration is merged
      and validated; full KINGDOMS is listed only if an actual instance
      has been registered.
- [ ] An explicit rollback restores the original working per-checkout
      management paths without changing guest disks.
- [ ] Canonical operator documentation and a source-gated regression
      run are complete before the feature is merged into `main`.

## Separate follow-up: actual guest hostname standardization

Independently align the operating-system hostnames with the displayed
VM names (`PURPLE-DC01`, `PURPLE-WS01`, `PURPLE-LX01`,
`PURPLE-WAZUH`). Existing PURPLE Windows hostnames, DNS/AD references,
Wazuh agent enrollment, scripts and certificates must be audited first.
Do **not** change a promoted domain controller's computer name as part
of a workspace/console migration.

**Current rule:** no shell command here migrates anything. This is a
planning/acceptance contract to be implemented on a separate branch,
with snapshots, tests, and an operator-approved cutover.
