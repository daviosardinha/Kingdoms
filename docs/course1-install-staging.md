# Kingdoms Course 1 — verified pre-install staging plan

**Status: source staging only. No installer activation.**

Operator validated 177/177 tests at `e17572d` with the VMware host survey.
The reference six-Windows-VM Kingdoms lab was not changed.

The next artifact gate prepares a known layout for an eventual **separate**
Course 1 instance. This is deliberately different from registering an
installed Vagrant instance in the existing `workspace/` directory.

The source-rendered Course 1 candidate now has an explicit first-line Ruby
`raise` in `instance-preview/Vagrantfile`. Directly loading that Vagrantfile
will halt, rather than attempting to create a machine before the remaining
deployment safety checks. Ruby syntax checking still works.

`goad.course1_install_stage` re-renders all 11 candidate files from the
trusted source and compares each private file byte-for-byte, checks directory
and file permissions, rejects symlinks/unexpected files and any installed
Vagrant/workspace markers, and confirms exactly four Windows guests plus
the router. The generated manifest remains
`PREVIEW_ONLY_NOT_INSTALLABLE`; the instance profile is never inferred
from a branch or filename.

### Planned installation layout

Only the mapping is emitted. Neither an instance directory nor an
`instance.json` is created.

| Candidate file | Intended future instance location |
|---|---|
| `instance-preview/Vagrantfile` | `provider/Vagrantfile` |
| `providers/vmware/inventory` | `inventory` |
| `data/inventory_disable_vagrant` | `inventory_disable_vagrant` |
| `data/inventory` | `data/inventory` |
| `data/config.json` | `data/config.json` |
| `router/provision.sh` | `router/provision.sh` |
| `vagrant/*.ps1` (three scripts) | `vagrant/*.ps1` |

This is a **planning map**, not a copy/install operation and not a guarantee
that the GOAD-inherited provisioner will use every file from those locations
without adapting it. The separate source recipe
`providers/vmware/Vagrantfile` remains an upstream build ingredient.

The existing consolidated acceptance command invokes the integrity gate
against the ephemeral candidate with a deterministic **test-only** instance
ID. The gate prints `guest_lifecycle_authorized=false` and
`deployment_authorized=false` and never writes instance state.

Remaining hard blockers: host vmnet allocation and dormant VM collision
inventory, actual VMware static MAC acceptance, router three-NIC PCI and
SSH proof, provider and Ansible path translation, per-instance lifecycle
binding, rollback/reset, KINGDOMS2 SQL, and Phase 03 live parity. No reference
lab network or VMs should be mutated as part of this milestone.

Operator command:

```bash
cd "$HOME/kingdoms-course1-src" && git pull --ff-only && bash scripts/course1/validate-course1.sh --survey-host
```


## Registered/powered-off VMware inventory gate

The same Course 1 validation command now inspects read-only Workstation
library registrations (`~/.vmware/inventory.vmls`) as well as `vmrun` running
VMX files. The planned Course 1 vmnet and manual MAC IDs must not overlap
either source. An unreadable listed VMX is a failed collision gate, not
evidence that the identifier is available. Missing library is called out as
insufficient registered guest visibility; unrelated unregistered VMs remain
outside coverage. No host/guest/network changes are attempted.
