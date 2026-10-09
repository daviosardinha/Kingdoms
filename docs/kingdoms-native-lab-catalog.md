# Kingdoms — native interactive course selection

The public operator interface is **one `./goad.sh`** from the primary
Kingdoms checkout. No extra Course 1 launcher, no separate permanent
`kingdoms-course1-src` operating environment. A separate Git checkout is
allowed for feature development and read-only validation, not for running
the production lab.

The native lab registration structure is:

```text
Kingdoms/
├── goad.sh                         # single console
├── ad/
│   ├── GOAD/                       # unchanged six-Windows reference recipe
│   ├── NORTH/                      # Kingdoms Course 1
│   │   ├── course.json             # name, title, runtime profile, release state
│   │   ├── data/                   # course-specific Ansible recipe (pending)
│   │   └── providers/
│   │       └── vmware/             # preview provider, install blocked
│   └── <FUTURE_LAB>/               # future course, not defined yet
└── workspace/                      # independently bound installed instances
```

The normal interactive console `labs` command discovers folders from
`ad/`. NORTH is now a native lab that can be selected with
`set_lab NORTH` and appears as `preview` under VMware. The provider
is a **non-mutating placeholder** with all lifecycle actions blocked.
Furthermore, direct `LabManager.create_instance`,
`LabInstance.create_instance_folder`, and interactive/non-interactive
install and provisioning entrypoints reject unreleased course profiles
*before* creating a workspace directory.

Example operator flow **after this branch passes tests and is merged**:

```text
./goad.sh
unload                      # only if an existing GOAD instance is loaded
labs
set_lab NORTH
config
install                     # currently explicitly BLOCKED; no new VM
```

This is deliberate: registering NORTH in a menu does **not** prove that
its isolated Vagrant provisioning, AD/WinRM, SQL KINGDOMS2, three-NIC
router, Phase 03 relay attack paths or lifecycle are ready. After
release it will use the same `install`, `list`, `load`,
`start`, `stop`, `status`, `validate` command family as GOAD,
but on its **own** instance and provider adapter.

The current live reference installation in
`~/Documents/GOAD_NOMAD` on `main` is not edited by this Git branch.
The console in the feature checkout has no installed instance because
`workspace/` is per-checkout; this is expected, not a missing
deployment. Never copy/symlink feature workspace into main.

For each future course, create a new native `ad/<NAME>/course.json`
with its own topology/runtime profile and provider(s), then validate
that provider before marking it installable. Keep course identity
independent of VMware/Ludus, ensuring one course can have multiple
validated provider backends.

## Materialized native source (2026-10-09)

The NORTH directory now contains an actual five-guest VMware machine recipe,
real AD configuration and Ansible inventories. This is the **source input**
for the existing Kingdoms `LabInstance` and provider pipeline. The next
engineering step is binding the validated Kingdoms lifecycle to this profile,
not building another installer. Native source files alone **do not** authorize
VM provisioning; the existing fail-closed NORTH provider remains active until
profile-specific runtime acceptance.
