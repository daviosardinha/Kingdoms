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
test ! -e "$HOME/kingdoms-rebuild" || { echo 'Destination exists'; exit 1; }
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
