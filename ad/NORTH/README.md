# NORTH — Course 1: Fall of the North

Native Kingdoms lab namespace: `ad/NORTH`. The interactive `./goad.sh`
command discovers the lab automatically through `ad/NORTH/providers/vmware`.
The course title and runtime profile are defined in `course.json`.

**Current status: NATIVE RECIPE PRESENT / NOT INSTALLABLE**. The source tree
now contains the real four-Windows-VM Vagrant machine recipe, pruned two-domain
AD config, translated NORTH inventories and three-NIC router provision script.
The VMware provider deliberately remains fail-closed until those files are
wired into the existing patched Kingdoms instance creation, router mode,
Windows/WinRM and Ansible lifecycle. There is no separate installer. See
`docs/course1-network-candidate.md`.

The Git feature checkout has no installed instance. Once NORTH is verified
and merged, the operator uses the same `./goad.sh` in the primary Kingdoms
project folder, `labs`, `set_lab NORTH`, then `install`, `start`,
`stop`, `status` and `validate` as supported by the released provider.

Adding future courses means adding another `ad/<COURSE_LAB>/course.json`,
the `providers/<provider>` recipe, and a validated provider implementation.
A console entry alone **must never** activate an incomplete lab.

## Inheritance requirement

**NORTH inherits the patched Kingdoms engineering foundation, not stock
GOAD.** The legacy \`ad/GOAD\` folder still supplies some source data
only because it is the tested, *Kingdoms-modified reference recipe*. New
NORTH output must first pass \`goad.kingdoms_foundation\` verification,
and its course manifest must bind to \`kingdoms-foundation-v1\`.
When the reusable Kingdoms base is extracted into a course-neutral home,
the reference source linkage must be removed without losing any validated
VMware, WinRM, AD, router, networking, isolation, logging or recovery fixes.
See \`docs/kingdoms-foundation.md\`.
