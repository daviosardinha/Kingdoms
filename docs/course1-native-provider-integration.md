# NORTH VMware source and runtime release boundary

**The installation engine is the existing patched Kingdoms `LabInstance` and
`ProfiledGoadKingdomsVmwareProvider`.** No upstream GOAD installer and no new
standalone Vagrant workflow.

During normal Kingdoms instance creation, NORTH's Vagrantfile is rendered
from `ad/NORTH/providers/vmware/Vagrantfile`, the existing template applies
Kingdoms' VMware reliability fixes, and the existing instance builder stages
NORTH's own router and Windows remoting/IP scripts under that instance folder.

The new `goad.north_native_instance.inspect_north_instance_assets` proves,
without writing or contacting VMware, that a concrete instance has exactly
GOAD-DC01, GOAD-DC02, GOAD-SRV02, GOAD-WS01 and GOAD-ROUTER; matching
vmnet11/12/13, MACs, addresses, provisioning scripts and both source
inventories. Reference `GOAD` inventory/Vagrantfile migration is intentionally
never run on a NORTH provider. Source acceptance is **not** VM runtime
permission or AD readiness.

The existing patched VMware provider has NORTH-specific dispatch for host
address checks and router host-address recovery; its first install preflight
performs the exact instance-source gate before privileged/guest changes.
Direct provider calls refuse unreleased NORTH operations—even if a caller
tries to circumvent the preview console.

**NOT YET INSTALLABLE:** NORTH remains registered as
`PREVIEW_ONLY_NOT_INSTALLABLE`; the runtime binding has
`segmented_install_enabled=False`, so no VM, network route or router policy
mutation is authorized. The P0 remainder is verified native per-instance
runtime authorization, four-guest startup/AD dependency acceptance, parent
route coexistence on a deployed guest library, and exercise-mode NAT isolation
acceptance. Live MSSQL/Phase 03 validation comes after first install.

Always run the single operator checker:
`bash scripts/course1/check-install-readiness.sh`.
Its normal return code is 2 (all source/host checks pass but installation
remains blocked). Do not manually bypass it with Vagrant.
