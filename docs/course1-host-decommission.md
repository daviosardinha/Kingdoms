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

This establishes that the eleven? **No**: NORTH's five disposable Vagrant
VMs were explicitly destroyed, and the original seven orphan VMware
processes were terminated; **all twelve are no longer running**, but
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
