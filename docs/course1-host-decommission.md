# Host decommission — discarded NORTH + previously installed full Kingdoms

User-approved target is a **clean Kali VMware host for Course 1**: remove the
disposable NORTH lab AND the currently installed reference/full Kingdoms lab,
including their guest disks, Vagrant workspace state, custom vmnets, routes,
host-address helpers, relevant units/timers, headless exercise processes and
other verified host leftovers. Delete the abandoned NORTH GitHub feature
branch once its old installation has been destroyed. Preserve the original
`main` source and fresh `rebuild/course1-from-kingdoms` source branch.

## Safety boundary

The approval is for the **installed labs and their owned host integrations**,
not for VMware Workstation, Vagrant, Ansible, base Vagrant boxes, the user's
personal files, unrelated VMs, other local web/agent services, or the new
Course 1 source. Do not delete the entire `~/.vmware`, `~/.goad`,
`/etc/vmware`, `/etc/systemd/system`, or source checkout. The global
`~/.vmware/inventory.vmls` includes unrelated VMs and must not be removed
or truncated. VMware default vmnet1/vmnet8 must be retained.

## Discovery phase (no changes)

```bash
cd "$HOME/kingdoms-course1-src"
git fetch origin
git switch rebuild/course1-from-kingdoms ||
  git switch --track origin/rebuild/course1-from-kingdoms
git pull --ff-only
python3 -m unittest tests.test_course1_cleanup_audit
sudo -v
python3 scripts/course1-cleanup-audit.py \
  --checkout "$HOME/Documents/GOAD_NOMAD" \
  --output "$HOME/kingdoms-cleanup-audit-$(date -u +%Y%m%dT%H%M%SZ).json"
```

The report is read-only. It prints a summary and saves a new JSON evidence
file containing potentially private host paths, IP ranges and configuration
metadata. Do not publish the raw evidence. If running under a sudo-inherited
root HOME, use the real user instead; sudo is needed only for privileged
read-only firewall inspection via `sudo -n`.

Review the results to enumerate **both** exact workspace IDs, Vagrant
machine IDs and VMX absolute paths, VMware powered-on process inventory,
Workstation powered-off user registry, `vagrant global-status`, and vmnet
address/routing/service ownership. A filename or GOAD-sounding process alone
is NOT enough to authorize deletion.

## Expected cleanup categories (not an automatic deletion list)

| Category | Candidate identities | Pre-deletion proof |
| --- | --- | --- |
| NORTH guests | 4 Windows + GOAD-ROUTER in `6ca91b-north-vmware` | exact Vagrant IDs and VMX realpaths |
| Full Kingdoms guests | 6 Windows + GOAD-ROUTER in the installed reference workspace | exact full instance ID and VMX realpaths |
| NORTH VMware custom vmnets | vmnet11 / vmnet12 / vmnet13 | exact configured subnets and absence of foreign VMX attachments |
| Original VMware custom vmnets | vmnet10 / vmnet20 / vmnet30 / vmnet99 | exact configured subnets and absence of foreign VMX attachments |
| Host routes/addresses | original `10.4.*` and disposable NORTH `10.41.*` routes | exact prefix/gateway/dev tuple, no foreign owner |
| System services/timers | `goad-nomad-vmnet-hostaddrs.*`, `kingdoms-north-vmnet-hostaddrs.*` | exact systemd FragmentPath/ExecStart and source |
| Lab exercise services | `kingdoms-phase03-rickon.service`, `kingdoms-rdp-bot.service` and discoverable user units | exact unit provenance and process ownership |
| Host helper files | `/usr/local/sbin/goad-nomad-vmnet-hostaddrs`, `kingdoms-north-vmnet-hostaddrs` | contents/provenance and service reference |
| Stateful files/backups | old workspaces, installer logs and explicit GOAD_NOMAD backups | contents classified; preserve backups until final validation |
| Legacy Git branch | `feature/course1-reduced-profile-source` | local checkout switched to rebuild branch first |

Other observed items (including phase03 listeners, cron entries, headless
RDP, port forwards, firewall rules, static leases, abandoned VM disk
directories or VMware Workstation library entries) must be classified by
specific path, port, rule handle and origin before removal.

## Decommission order after ownership has been reviewed

1. Verify exact two workspace IDs and ALL VMX files; stop dedicated
   Kingdoms systemd/user timers and headless activities identified by audit
   (not unrelated processes). Avoid touching unrelated always-on projects.
2. Destroy guests from each exact Vagrant provider folder; verify only the
   intended VMX identities are gone from VMware running inventory,
   Workstation registry, Vagrant global-status and their disk directories.
   Never use global `vagrant destroy` from the wrong checkout.
3. Remove only verified residual workspace/disk folders; never delete a
   parent folder whose realpath or contents diverges from the audit.
4. Remove scoped host routes/addresses; first prove ownership and no
   collisions. Disable/remove only source-proven Kingdoms units, helpers and
   cron rules.
5. Back up `/etc/vmware/networking` and `netmap.conf`. Strip ONLY the
   approved custom VNET keys for 10/11/12/13/20/30/99, with before/after
   diff and collision proof. Never touch vmnet1/vmnet8. Restart global
   VMware networking ONLY when **every** VMware guest, including unrelated
   instances, is stopped and a rollback is available.
6. Verify routes, firewall rules, host addresses, stale VM disks, units,
   Vagrant index and Workstation registry no longer reference either
   installed lab. Preserve the cleanup report/backup until confirmation.
7. Delete the abandoned remote feature branch using an exact branch-name
   Git push only after the source checkout is on the new rebuild branch:
   `git push origin --delete feature/course1-reduced-profile-source`.
   Do not delete `main` or `rebuild/course1-from-kingdoms`.

**Do not run destructive phases merely from this document.** Produce the
manifest from the actual Kali host inventory first. This prevents deleting
unrelated VMs or leaving VMware unable to operate.

## Clean-state acceptance

No remaining GOAD/NORTH Vagrant instances or VMX registrations; no target
guest disks, vmnet10/11/12/13/20/30/99 configuration, routes, addresses,
dedicated services/timers, orphan headless sessions, DNS redirections or
firewall rules. VMware still works with its normal defaults; unrelated
VMs/services stay unchanged; the new source branch is clean, and a fresh
Course 1 can use 10.4.0.0/16 without conflicts.

## Actual host incident: original source checkout deleted before audit (2026-10-11)

The operator used `rm -rf` on `~/Documents/GOAD_NOMAD`. The separate
`~/kingdoms-course1-src` is a **linked Git worktree**, whose
`.git` pointer refers to
`~/Documents/GOAD_NOMAD/.git/worktrees/kingdoms-course1-src`. As a
result Git commands there now fail with `fatal: not a git repository`.
**No claim that installed VMware guests, Vagrant IDs, disks, routes, services
or vmnets were deleted by that command.** The old reference workspace's
Vagrant ID files may have been lost, making Workstation's powered-off
`~/.vmware/inventory.vmls` and Vagrant's global index particularly
important for ownership reconstruction.

Do NOT run `git fetch/switch` from the broken linked checkout, delete its
`workspace`, or overwrite that checkout to 'repair' it. Recover the source
into a **fresh non-worktree clone** at a new path, preserving the broken
worktree and whatever guest metadata it still holds:

```bash
# git clone refuses to overwrite an existing nonempty destination.
git clone --branch rebuild/course1-from-kingdoms --single-branch \
  https://github.com/daviosardinha/Kingdoms.git \
  "$HOME/kingdoms-rebuild"
cd "$HOME/kingdoms-rebuild"
python3 -m unittest tests.test_course1_cleanup_audit
python3 scripts/course1-cleanup-audit.py \
  --checkout "$HOME/kingdoms-course1-src" \
  --checkout "$HOME/Documents/GOAD_NOMAD" \
  --output "$HOME/kingdoms-cleanup-audit-$(date -u +%Y%m%dT%H%M%SZ).json"
```

This command is NONDESTRUCTIVE. Review the output before preparing the
explicit teardown manifest. Do not use `rm -rf ~/.vmware`,
`rm -rf ~/.vagrant.d`, a blanket `vagrant global-status --prune`, or
deletion of `~/vmware`; those directories could contain surviving
guest registration state, unrelated VMs, and other projects.

## 2026-10-11 cleanup checkpoint — NORTH destroyed; original VMware guests survive

Operator successfully disabled both host-address persistence timers and ran
`vagrant destroy -f` from the exact disposable NORTH Vagrant provider
folder `~/kingdoms-course1-src/workspace/6ca91b-north-vmware/provider`.
All five disposable VMs (GOAD-DC01, DC02, SRV02, WS01, ROUTER)
were stopped/deleted by Vagrant. The subsequent `vmrun -T ws list` did
not include those five paths. Workspace residue, Vagrant cache and
network state **not yet fully audited/deleted**.

The same post-destroy `vmrun -T ws list` shows **seven running
original-reference VMs**, all under the previously deleted
`~/Documents/GOAD_NOMAD/workspace/6fdd5a-goad-vmware/provider/.vagrant/machines`:
GOAD-DC01, GOAD-DC02, GOAD-DC03, GOAD-SRV02, GOAD-SRV03, GOAD-WS01,
GOAD-ROUTER. This proves deleting the original repository folder via
`rm -rf` did not shut down these VMware processes. It does not prove
their VMX and disk files still exist at their old paths.

`vagrant global-status` ALSO includes seven entries for a different
workspace, `~/Documents/GOAD_NOMAD_fresh/workspace/22a3c5-goad-vmware/provider`.
Two are cached as `running` there but **none** appear in `vmrun list`;
do not trust cached Vagrant state to establish live VMware existence.
The user's Workstation registry additionally contains
`~/vmware/KINGDOMS-SQL-CLONE/KINGDOMS-SQL-CLONE.vmx`, an independent
clone whose ownership must be established explicitly before deletion.

The live host still lists vmnet10, vmnet11, vmnet13 and vmnet99 addresses;
their present host addresses show `.1`, not the project's historic
`.254`. Do NOT change global VMware vmnets while the seven original
guests are running. Other custom vmnets 12/20/30 exist as VMware
configuration entries even if they lack a host-visible IP interface.

### Next non-destructive evidence request

From the NEW `~/kingdoms-rebuild` checkout on Kali (do not use the
deleted original checkout or broken linked worktree), examine:
- physical existence and ownership of each of seven original VMX paths
  from `vmrun list`, plus whether `~/Documents/GOAD_NOMAD` was truly removed;
- existence and provider directory state for the distinct
  `GOAD_NOMAD_fresh` workspace and its Vagrant IDs;
- status of `KINGDOMS-SQL-CLONE` as a separate VM and its disk files;
- current running VMware processes and names, **without** global
  `killall`, `pkill`, `vagrant global-status --prune`, or network resets.

After ownership evidence, stop/delete only exact identified VMware
guests; if a VMX was unlinked while still running, normal `vmrun stop`
may fail. Handle that explicitly, never by killing all VMware processes.
The separate SQL clone may be useful as a course fixture and must not
be silently treated as one of the seven original VMs.

No machine cleanup beyond the five disposable NORTH VMs and disabling
the two timers is proved yet.

## 2026-10-11 original Kingdoms orphan process identification

The operator verified **all seven** original GOAD_NOMAD guests have no
corresponding VMX on disk but remain in `vmrun -T ws list`, and mapped
every one to a live `vmware-vmx` process by inspecting `/proc/PID/cmdline`.
Every process points into the **exact**
`~/Documents/GOAD_NOMAD/workspace/6fdd5a-goad-vmware/provider/.vagrant/machines`
tree; this is not the new `~/kingdoms-rebuild` checkout:

- GOAD-ROUTER PID 3305649
- GOAD-DC01 PID 3309414
- GOAD-DC02 PID 3320884
- GOAD-DC03 PID 3332796
- GOAD-SRV02 PID 3342712
- GOAD-WS01 PID 3396827
- GOAD-SRV03 PID 3404884

PIDs are **observational, not permanent identities**: revalidate both
`/proc/<pid>/cmdline` and expected missing VMX, ensure exactly seven
expected and no foreign VM, then signal those specific processes.
Prefer TERM first, wait boundedly, and use KILL only for processes still
verified as those exact original-orphan identities. Never `killall
vmware-vmx`, `pkill vmware`, or stop `vmware.service` globally.

The SQL clone at `~/vmware/KINGDOMS-SQL-CLONE/` is a separately
registered VM and is **not** one of these seven orphan PIDs. The previous
`GOAD_NOMAD_fresh` Vagrant registry references have no surviving
provider directory. After confirming orphan shutdown, separately audit
VMware registry and Vagrant index, dedicated host services/timers,
vmnet10/11/12/13/20/30/99, firewall rules, and user-owned leftovers.

## 2026-10-11 — original seven orphan VM processes successfully terminated

Operator ran the verified Bash process-identity teardown (after avoiding Zsh
history expansion of Bash associative-array syntax). All seven exact
GOAD_NOMAD instance/process identities passed verification. Each received
a TERM signal; the subsequent remaining-orphan check found nothing to
force-kill. The final VMware output explicitly reads:

```text
===== FINAL VMWARE STATE =====
Total running VMs: 0
```

NORTH's five disposable Vagrant VMs were explicitly destroyed, and
the original seven orphan VMware processes were terminated. Thus,
**all twelve are no longer running**, but
original Vagrant metadata and Workstation registrations remain to be
removed. Original guest disk/VMX files were already deleted by the
operator's prior checkout-folder removal.

**Do not claim the host clean yet.** Proceed with ownership-aware removal
of stale Workstation registrations, Vagrant cache, discarded linked
worktree and workspace, dedicated Kingdoms units/helpers, exact
vmnet10/11/12/13/20/30/99 configurations, and owned routes.
Before VMware global networking reset, inspect the separately registered
`~/vmware/KINGDOMS-SQL-CLONE/KINGDOMS-SQL-CLONE.vmx` for references
to any target vmnets; do not break a foreign guest or remove unrelated
VMware inventory entries. Re-run clean-state validation after each stage.

## 2026-10-11 — VMware network and separate SQL clone blocker

The operator's latest live read-only audit shows:

- `vmrun -T ws list`: **Total running VMs: 0**; no VMX processes.
- `~/vmware/KINGDOMS-SQL-CLONE/KINGDOMS-SQL-CLONE.vmx` exists, and its
  configuration explicitly includes `ethernet1.connectionType = "custom"`
  and **`ethernet1.vnet = "vmnet10"`**. This standalone clone therefore
  depends on a network slated for removal. Ethernet0 is also present but
  no vnet name was visible for it in the displayed filtered output.
- `/etc/vmware/networking` retains VNET records for **10, 11, 12, 13,
  20, 30, 99**, with 10.4 and 10.41 segment assignments. VMware host
  IPv4 connected routes currently exist for vmnet10 (10.4.10.0/24),
  vmnet99 (10.4.99.0/24), vmnet11 (10.41.10.0/24), and vmnet13
  (10.41.99.0/24). Host addresses appear as `.1`, not the original
  intended host-side `.254`.
- Both `goad-nomad-vmnet-hostaddrs.timer` and
  `kingdoms-north-vmnet-hostaddrs.timer` are disabled, but the
  corresponding service/timer **unit files remain installed**.
- The abandoned linked checkout and `6ca91b-north-vmware` workspace
  folders still exist. These are residual files after successful VM
  destruction; do not confuse folder existence with a live Vagrant VM.

**Mandatory next decision:** whether the user explicitly includes the
separately registered `KINGDOMS-SQL-CLONE` in permanent lab removal.
Do NOT delete or reconfigure vmnet10 while preserving a VM that uses it.
If user elects clone deletion, confirm its VMX/disk/snapshot chain and
any reference by other VMs before targeted deletion. If user elects
preservation, vmnet10 remains out of scope for cleanup and the result
cannot be described as a completely empty custom-vmnet host.

Do not run `vmware-networks --stop`, remove VNET keys, flush routes or
delete systemd helpers merely because all VMware processes are stopped.
First enumerate all VMX registrations and possible foreign attachments,
back up the current `/etc/vmware/networking` and `netmap.conf`,
then use an exact-number VNET delta with rollback and post-reset
verification preserving vmnet1/vmnet8 and unrelated VMs.

## 2026-10-11 — user removed ~/vmware; host networking staged

The operator reports manually deleting `~/vmware` (previously containing
`KINGDOMS-SQL-CLONE`). This does not automatically delete its stale
Workstation library registration, which may still refer to a missing VMX.
No running guests remain per the immediately prior `vmrun list`.

A strictly scoped network-removal helper has been added:
`scripts/course1-decommission-vmnets.py`. It offers a read-only
`plan` mode and an explicit `apply --confirm --backup-root` mode.
The latter requires a root process, zero running VMware VMs/processes,
and no **existing**, registered VMX that attaches to any of
vmnet10/11/12/13/20/30/99. It creates a unique backup of
`/etc/vmware/networking` and `netmap.conf`, edits only the seven
exact VNET record families and per-vmnet description comments, restarts
`vmware-networks` and rolls back the networking file if restart
or subsequent configuration checks fail. Default vmnet1/vmnet8 remain.

**Acceptance status:** The helper is a new source implementation,
NOT YET syntax-tested or live-tested on Kali. Do not execute apply until
the operator has run `python3 -m py_compile
scripts/course1-decommission-vmnets.py`,
`python3 scripts/course1-decommission-vmnets.py plan`,
and confirmed the proposal and any remaining registered VMX attachments.
Afterwards, hostaddr unit files, stale Workstation entries, Vagrant
machine-index metadata, discarded worktrees, and old Git branch
remain separate explicit cleanup steps.

## 2026-10-11 — VMware network cleanup passed live

Kali ran the newly committed six-test `tests.test_course1_decommission_vmnets`
suite: **6/6 PASS**. The exact non-mutating cleanup `plan` reported
vmnet10, vmnet11, vmnet12, vmnet13, vmnet20, vmnet30, vmnet99
and 13 remaining configuration lines. The confirmed `apply` then
printed:

```text
[BACKUP] /etc/vmware/kingdoms-cleanup-20261011T121537Z
[PASS] VMware network definitions removed; defaults preserved
```

Post-apply verification showed only **vmnet1 and vmnet8** in
`ip -br link show`, no obsolete VNET configuration keys, and
`vmrun -T ws list`: **Total running VMs: 0**.

**Do not restore old host address helpers/timers**: they refer to vmnets
that no longer exist. Next manually verify exact `FragmentPath` and
`ExecStart` provenance for:
`goad-nomad-vmnet-hostaddrs.service/.timer` and
`kingdoms-north-vmnet-hostaddrs.service/.timer`. Once those are
proven and inactive, remove only those four unit files and the
`/usr/local/sbin/goad-nomad-vmnet-hostaddrs` and
`/usr/local/sbin/kingdoms-north-vmnet-hostaddrs` helpers, followed by
`systemctl daemon-reload`. Never touch vmware.service, VMware default
networking, or other host service units.

After service cleanup, separately review the stale
`~/.vmware/inventory.vmls`, Vagrant global index, broken linked
`~/kingdoms-course1-src` worktree and residual
`6ca91b-north-vmware` folder, and the old remote Git feature branch.
These have not yet been cleaned or verified.

## 2026-10-11 — retired host-address services removed

The user successfully ran the exact ownership-verified cleanup for:
`goad-nomad-vmnet-hostaddrs.{service,timer}`,
`kingdoms-north-vmnet-hostaddrs.{service,timer}`, and the matching
`/usr/local/sbin` helper executables. Both prefixes verified as owned;
the two timers were disabled; six files were moved into
`/etc/vmware/kingdoms-cleanup-20261011T121537Z/hostaddr-units`.
`systemctl daemon-reload` completed. The final output confirmed
`[PASS] Obsolete host-address services removed`.

Remaining work: inspect/prune only stale Workstation library records,
Vagrant machine-index references to the missing original/fresh workspaces,
the discarded NORTH checkout/workspace, and the abandoned feature branch.
The separate fresh rebuild checkout `~/kingdoms-rebuild`, `main`, and
unrelated VMware/Vagrant state must not be removed. Further host-owned
Kingdoms artifacts require verified path-by-path classification.

## 2026-10-11 — old hostaddr files gone; only stale VM indexes remain

The operator verified hostaddr unit/helper removal with:
`[VERIFIED] goad-nomad-vmnet-hostaddrs`,
`[VERIFIED] kingdoms-north-vmnet-hostaddrs`, and
`[PASS] Obsolete host-address services removed`.

Latest VM/library/home snapshot:

- `~/.vmware/inventory.vmls`: seven `vmlist4.config` through
  `vmlist10.config` entries point to the deleted
  `~/Documents/GOAD_NOMAD/workspace/6fdd5a-goad-vmware` instance.
  One `vmlist11.config` entry points to now-deleted
  `~/vmware/KINGDOMS-SQL-CLONE/KINGDOMS-SQL-CLONE.vmx`.
  Other empty slots should be preserved; edit only those eight proven
  owned-and-missing VMX registrations, including any properties under
  those eight exact vmlist slot numbers, backing up the whole registry.
  Do not remove `~/.vmware` or rewrite non-owned registered entries.
- `vagrant global-status` lists fourteen obsolete machine-index entries:
  seven from `GOAD_NOMAD/workspace/6fdd5a-goad-vmware` and
  seven from `GOAD_NOMAD_fresh/workspace/22a3c5-goad-vmware`.
  Both provider directories were verified MISSING. A controlled
  `vagrant global-status --prune` may remove those stale index
  entries; it is **not** a VM destroy. Check remaining global-status.
- `~/kingdoms-course1-src`, `~/Documents/GOAD_NOMAD`,
  `~/Documents/GOAD_NOMAD_fresh`, and `~/vmware` are already missing;
  no folder deletion is needed. The new `~/kingdoms-rebuild` Git
  checkout remains clean.
- At home top level, a Kerberos `.ccache` file with NORTH principal
  and `~/.goad` remain. The `.ccache` is a likely lab-secret artifact
  to inspect and securely retire; `~/.goad` may contain reusable
  installer dependencies, so do NOT bulk-delete it.

Once stale registry cleanup is completed and VMware remains usable,
repeat the global host audit for systemd/cron/routing/firewall leftovers
and delete the abandoned GitHub feature branch. The initial registry
cleanup is **not yet executed**.

## 2026-10-11 — VMware Workstation GUI closed; stale library cleanup prepared

After encountering a safety block (the running VMware GUI used executable
`/usr/lib/vmware/bin/appLoader`, not the literal `vmware` path), the
operator verified PID `2233180` owned by `stark`, VM count zero,
and closed that precise process with TERM. Final operator evidence:
no `vmware` or `vmware-vmx` process, `vmrun -T ws list`
**Total running VMs: 0**.

A dedicated two-stage inventory file tool is committed at
`scripts/course1-cleanup-vmware-library.py` with four source regression
cases under `tests/test_course1_cleanup_vmware_library.py`. It matches
exactly GOAD original hosts and the deleted SQL clone, and only slots
`vmlist4` through `vmlist11`; refuses existing VMX files, mismatching
slots, any VMware GUI/guest process or active VMs. It backs up
`~/.vmware/inventory.vmls` before an atomic replacement, preserving
all other VMware inventory properties/entries.

**Status:** The live Kali execution of these four tests, `plan`, and
`apply --confirm` is PENDING. Do not claim VMware registry clean yet.
Run the plan and confirm the eight explicit registrations before apply.
The Vagrant registry already reports no active environments after prune.

## 2026-10-11 — stale VMware library and Vagrant index removed

Operator ran the dedicated `tests.test_course1_cleanup_vmware_library`
suite (4/4 PASS), reviewed `scripts/course1-cleanup-vmware-library.py plan`,
and successfully executed `apply --confirm`. Exactly eight entries
(`vmlist4` through `vmlist11`) were removed: the seven missing original
GOAD guest VMX registrations and the deleted `KINGDOMS-SQL-CLONE`.
Backup file created:
`/home/stark/.vmware/inventory.vmls.backup-20261011T163541602406Z`.

Afterward `vmrun -T ws list` showed `Total running VMs: 0`,
`vagrant global-status` showed no active entries, and the only
`inventory.vmls` config entries were the three pre-existing empty
slots `vmlist1.config = ""`, `vmlist2.config = ""` and
`vmlist3.config = ""`. Keep these harmless empty slots.

**Core virtualization cleanup complete**, not yet final host hygiene.
Outstanding acceptance: read-only post-removal scan of remaining
Kingdoms/GOAD timers, processes, routes, nft/iptables rules, crontabs,
credential cache files, legacy backups and stray helper scripts; classify
findings with exact ownership evidence. Verify the abandoned
`feature/course1-reduced-profile-source` branch is no longer needed and
delete only that named remote branch; preserve `main` and
`rebuild/course1-from-kingdoms`. Do not purge reusable `~/.goad`
tooling, unrelated caches or any other project resources without review.

## 2026-10-11 final host scan: orphan user RDP units and ticket caches

Post-cleanup `scripts/course1-cleanup-audit.py` read-only summary showed
no installed Kingdoms workspace and `VMNET SETTINGS: none observed`.
The separately performed `systemctl` scans found TWO enabled **user**
service units: `kingdoms-phase03-rickon.service` and
`kingdoms-rdp-bot.service`. Both source unit definitions from the retired
NORTH branch launch Bash scripts under the deleted
`%h/Documents/GOAD_NOMAD/scripts/`: respectively
`phase03/rickon-headless.sh` and `rdp-bot-headless.sh`. As the original
checkout has been removed, both are obsolete and potentially restart
forever after login. Their actual user FragmentPath/ExecStart must be
verified on Kali before removing them.

Top-level home listing contains
`Administrator@cifs_ws01.north.sevenkingdoms.local@NORTH.SEVENKINGDOMS.LOCAL.ccache`
and `PHASE03RBCD$.ccache`: sensitive Kerberos ticket caches from the
retired lab; user-approved hygiene should remove only those exact
artifacts after verifying they are regular files and are not in use.
`~/.goad` remains and may contain the Ansible/Python provisioning
environment: preserve pending a dependency review. Keep
`~/kingdoms-rebuild` and final audit JSON.

Future acceptance: confirm user services disabled/unloaded, caches retired,
zero custom vmnet/IP routes, no GOAD/NORTH running services/processes, empty
VMware/Vagrant registries, and delete only the explicitly abandoned
`feature/course1-reduced-profile-source` remote branch. This is the
final host hygiene stage before the minimal Course 1 rebuild.

## 2026-10-11 — user RDP services removed and backed up

Operator successfully ran the exact file/ExecStart ownership verification
for `kingdoms-phase03-rickon.service` and `kingdoms-rdp-bot.service`.
Both passed verification. `systemctl --user disable --now` removed their
`default.target.wants` links; the installed unit files were removed and
systemd user daemon reloaded. Output confirmed
`[PASS] Old Kingdoms RDP units removed`.

Backup directory: `/home/stark/kingdoms-cleanup-user-units-20261011T164927Z`.

**Still outstanding:** safely retire exactly the two legacy Kerberos
ticket caches from the user's home directory, delete only the abandoned
`feature/course1-reduced-profile-source` remote branch, and repeat final
read-only host checks. Preserve `main`, `rebuild/course1-from-kingdoms`,
`~/kingdoms-rebuild`, shared VMware/Vagrant tooling, and cleanup backups.
