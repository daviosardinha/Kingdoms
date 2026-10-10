# Kingdoms Course 1 — VMware maintenance apply and rollback

**Status: maintenance code committed for regression, not yet validated on Kali.
It is NOT executed by the standard Course 1 test suite.**

The operator approved **temporarily shutting down all six running reference
VMware guests** during a controlled window. This is not authorization to
delete guests or to bypass backups/readiness gates. The initial read-only
maintenance plan at 6495651 passed 213/213 regression tests and reports
MAINTENANCE_WINDOW_REQUIRED while six guests run.

## Operating boundary

The dedicated command \`scripts/course1/maintain-vmware-networks.sh\` has
three separate operations. All require clean pinned Kingdoms Git source:

- \`plan\`: fresh read-only snapshot, registered powered-off VM inventory,
  exact additive config plan, and actual running-VM count. Never requires sudo.
- \`apply --confirm-maintenance\`: user must **first** perform an orderly
  shutdown using the existing reference Kingdoms stop/lifecycle workflow;
  the script never powers off guests. Requires **zero** running
  \`vmware-vmx\` processes, a fresh zero-running Workstation snapshot, all
  registered VMX readable and a collision-free candidate. Only then does it
  invoke its separate privileged Python transaction through sudo.
- \`rollback BACKUP_ID --confirm-maintenance\`: requires zero running
  VMware guests; recovers the backed-up networking file and any existing
  \`netmap.conf\`, restarts VMware networking, and rechecks reference
  network keys. Refuses invalid backup IDs and unexpected configuration
  changes. Recovery from a failed apply can be marked \`RECOVERY_NEEDED\`.

**DO NOT run** the existing \`scripts/setup-vmware-networks.sh\` to add
Course 1 networks: that file owns the validated reference vmnet10/20/30/99.

## Transaction design

The privileged \`goad.course1_vmnet_transaction\` module:

1. Verifies root privileges, no running VMware VMs (regardless of profile),
   complete registered inventory, exact host network collision fit, and the
   three-zone additive-only maintenance plan.
2. Stores private backups under
   \`/etc/vmware/kingdoms-course1-backups/c1-TIMESTAMP-NONCE/\` (0700), with
   original \`networking\` and any existing \`netmap.conf\` plus a file hash
   manifest (files mode 0600). Never overwrites a previous backup.
3. Stops VMware virtual networking **once**, atomically appends just
   vmnet11/12/13 definitions, and restarts networking.
4. Verifies the reference VMware VNET settings still match the backup,
   new vmnet11/12/13 definitions remain correct, and all three VMware
   \`/dev/vmnetN\` network devices exist.
5. On any stop/write/restart/verification failure, attempts to restore the
   original VMware file and restart networking. If rollback itself fails,
   reports \`RECOVERY_NEEDED\` and the exact backup ID for manual recovery.

Workstation may remove host-address metadata when networking restarts;
the reference Kingdoms host-address timer remains untouched, and this
transaction explicitly does not claim that Course 1's new NORTH or MANAGEMENT
host \`.254\` interface addresses are persistent.

## Workflow (operator-controlled; NOT automatic)

Before a maintenance run, have recovery/backups ready and confirm the
reference lab has no active exercise or unsaved Windows work.

Read-only status:

\`\`\`bash
cd "$HOME/kingdoms-course1-src"
bash scripts/course1/maintain-vmware-networks.sh plan
\`\`\`

At the agreed maintenance window, **first** use the validated reference
Kingdoms shutdown workflow to stop the six Windows guests **and** router.
Prove there is no remaining \`vmware-vmx\` process. Then, after reviewing
this procedure and the current source:

\`\`\`bash
bash scripts/course1/maintain-vmware-networks.sh apply --confirm-maintenance
\`\`\`

The command prints a backup ID. Record it before any further host change.
It does **not** start the Course 1 lab or activate its installer.

For an explicitly requested rollback, with all VMware guests stopped:

\`\`\`bash
bash scripts/course1/maintain-vmware-networks.sh rollback BACKUP_ID --confirm-maintenance
\`\`\`

After a successful network transaction, verify existing reference vmnets and
restore/restart the reference Kingdoms lab using the previously validated
lifecycle. Recheck DC parent/child readiness before installing any Course 1
machine. Restore original VMware networking from the saved backup if any
reference recovery gate fails.

## Remaining release gates

- New vmnet11 and vmnet13 Linux host addresses \`.254\` and persistence;
- router three-NIC PCI/udev mapping and management SSH after disposable boot;
- isolated VMware guest provisioning, WinRM and AD readiness;
- course-scoped instance binding/start/stop/reset;
- KINGDOMS2 and Phase 03 attack-path parity.

Course 1 install/start/reset remains blocked, and PR #30 remains draft.
