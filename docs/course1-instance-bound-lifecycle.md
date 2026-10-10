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

This is **source-only and read-only** until runtime acceptance:
`execution=BLOCKED_STATIC_PLAN_ONLY`, `activation=NOT_AUTHORIZED_BY_THIS_CHECK`.
The `NORTH` course manifest, instance creation, provider and mode operations
remain blocked. No VMware VM or host route is modified by these checks, and
the reference six-machine planner remains unchanged.

Remaining work before opening a controlled first installation: make the
runtime provider identity concrete, protect collision/power-on paths from
reference VMX overlap, provide a recoverable NORTH mode controller that uses
the same authenticated AD readiness with the child/parent only, validate
Windows Vagrant NAT/WinRM and the three NIC router in a disposable live
instance, and prove reference isolation end to end.
