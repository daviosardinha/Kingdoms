# NORTH: actual Kingdoms instance-bound lifecycle planning

The **existing** `goad.course1_bound_lifecycle.plan_bound_instance` now
accepts `lab_name="NORTH"` in addition to the historical `GOAD`. It verifies
the exact native files generated under a disposable Kingdoms workspace,
using `inspect_north_instance_assets`, and returns a four-Windows-guest
dependency plan with the isolated `10.41.x` endpoints from
`north_binding().roster`. An environment variable or a profile name
**alone** is never sufficient: the concrete provider/Vagrantfile, IPs, MACs,
VMware networks and native Windows/router/Ansible files must match the
committed patched Kingdoms recipe.

`./goad.sh` continues to use `LabInstance` and the same
`ProfiledGoadKingdomsVmwareProvider`. The existing hardened provider
consumes bound plans and now keeps start/stop/per-VM operations on the
hardened Kingdoms path for NORTH rather than falling back to stock Vagrant.

The `plan_bound_instance` CLI remains **source-only and read-only** and never grants execution authority:
`execution=BLOCKED_STATIC_PLAN_ONLY`, `activation=NOT_AUTHORIZED_BY_THIS_CHECK`.
By default, NORTH stays PREVIEW: instance creation, provider, and mode
operations are denied. For the first disposable VMware deployment, the
source-controlled NORTH manifest now contains an exact pilot identity.
An operator must also opt in using the exact
`KINGDOMS_NORTH_FIRST_INSTALL_PILOT` value. Without BOTH approvals the
preview restrictions remain intact. The pilot is **not** a general Course 1
release; the original six-machine reference planner remains unchanged.

Remaining work before opening a controlled first installation: make the
runtime provider identity concrete, protect collision/power-on paths from
reference VMX overlap, provide a recoverable NORTH mode controller that uses
the same authenticated AD readiness with the child/parent only, validate
Windows Vagrant NAT/WinRM and the three NIC router in a disposable live
instance, and prove reference isolation end to end.

## Controlled first-install pilot — operator runbook

1. Pull a clean, upstream-matched `feature/course1-reduced-profile-source`.
   Run `bash scripts/course1/check-install-readiness.sh --refresh` with
   no pilot environment set. All source regressions, VMware inventory,
   vmnet11/12/13, .254 addresses and reference collision protections must
   pass. The dashboard intentionally still exits 2 and displays
   `NOT INSTALLABLE YET` because the course is not generally released.
2. Confirm no existing NORTH disposable installation is registered on those
   vmnets. Do not stop or modify the six-guest reference to make this work.
   Have enough RAM/disk in the actual VMware VM storage volume, not just the
   repository checkout.
3. Start the **interactive** native console with:
   `KINGDOMS_NORTH_FIRST_INSTALL_PILOT=NORTH_VMWARE_DISPOSABLE_FIRST_INSTALL_20261010 ./goad.sh`
   Then explicitly `unload` any reference instance, `set_lab NORTH`,
   inspect `settings` (must show FIRST-INSTALL-PILOT, vmware, local), and
   issue `install`. Never use default/implicit GOAD lab selection.
4. The pilot requires the four-guest native Vagrantfile and inventories,
   instance-local WinRM/router assets, static 10.41.10 instance range,
   and registered/running VMX collision survey BEFORE any provider VM/host
   mutation. It stages the router first, validates vmnet11/13 host addresses
   and authenticated management SSH, and enables only NORTH's temporary
   parent route before Windows startup. A failed Windows first boot attempts
   exact-route and router-policy rollback. A failed install is NOT a ready lab.
5. Inspect Vagrant/WinRM/Ansible output and saved install timing. Verify the
   parent and child AD domains, WinRM, SQL, and Phase 03 in sequence. Run
   provisioning-to-exercise isolation checks and reference regression before
   considering promotion from the pilot.

**Safety:** This pilot is a deliberate operator acceptance test, not a guarantee
of success. Never force `vagrant up` directly, replace a VMX path, merge the
pilot into main, or disable binding/collision protections to proceed. Pilot
authorization does not grant `ws01`, `create_empty`, or other independent
course console shortcuts; use the native full `install` lifecycle only.

## Post-install readiness survey (existing NORTH instance)

After the disposable first provider bring-up, the default pre-allocation host
collision survey remains intentionally strict: it cannot distinguish newly
created NORTH guest MACs from an unauthorized foreign guest on vmnet11/12/13.
Do **not** delete, unregister, or stop guests to satisfy that pre-install gate.

For an actual instance, scope the same read-only readiness command to its
existing **absolute** `provider` directory (no pilot environment required):

```bash
bash scripts/course1/check-install-readiness.sh --refresh \
  --instance-provider "$HOME/kingdoms-course1-src/workspace/6ca91b-north-vmware/provider"
```

The scoped survey first validates the canonical NORTH instance assets and
reuses the full registered/running VMX collision preflight. Only VMX identities
proven owned by this instance using canonical Vagrant IDs and matching reserved
MACs are removed from the *comparison copy* of the host snapshot. The
specific temporary `10.41.20.0/24 via 10.41.10.1 dev vmnet11` route may also
be normalized. Other routes, foreign VMX guests, subnets, or changed vmnets
still fail closed. The survey does not modify the instance or authorize general
installation. Keep the already provisioned router/Windows guests intact.
