# NORTH — Course 1: Fall of the North

Native Kingdoms lab namespace: `ad/NORTH`. The interactive `./goad.sh`
command discovers the lab automatically through `ad/NORTH/providers/vmware`.
The course title and runtime profile are defined in `course.json`.

**Current status: PREVIEW ONLY / NOT INSTALLABLE**. The VMware provider for
NORTH is deliberately a fail-closed placeholder, not a copy of the existing
six-Windows-VM GOAD provider. NORTH uses four Windows VMs plus a three-NIC
router, and later will use its own provisioner, lifecycle and per-instance
networks. See `docs/course1-network-candidate.md`.

The Git feature checkout has no installed instance. Once NORTH is verified
and merged, the operator uses the same `./goad.sh` in the primary Kingdoms
project folder, `labs`, `set_lab NORTH`, then `install`, `start`,
`stop`, `status` and `validate` as supported by the released provider.

Adding future courses means adding another `ad/<COURSE_LAB>/course.json`,
the `providers/<provider>` recipe, and a validated provider implementation.
A console entry alone **must never** activate an incomplete lab.
