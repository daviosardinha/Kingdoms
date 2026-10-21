# WSLPE41 — Native Stage 1 partial-guest recovery

**Scope:** One existing, partially materialized standalone KINGDOMS WSLPE
instance. **Never** a fresh instance creation command or a GOAD/NORTH recovery.

## Why this exists

The WSLPE VMware base may return a failed initial `vagrant up` after Windows
boots, even when NAT-side WinRM remains accessible. The guest can have a working
NAT IP but a missing VMware Tools core service and an APIPA exercise NIC.

On the first verified fresh WSLPE41 attempt (2026-10-21), instance
`bf5369-wslpe-vmware` used `172.28.232.0/24`, booted Windows, and authenticated
WinRM over the private NAT port. Vagrant could not complete guest networking.
The VMware Tools MSI then returned 1603 during
`VM_SecureVGAuthDirs`; `vminst.log` reported a sharing violation
(`0x80070020`) on the VGAuth log file. The failing custom action is proven;
whether stopping VGAuth is sufficient to resolve the MSI issue requires a live
guest test.

## Reused KINGDOMS implementation

- `goad/provider/vagrant/vmware.py`: existing provider-owned ISO mounting,
  forwarded WinRM health, Tools installation/reboot and process readiness.
  Only the WSLPE setup script now stops and restores the pre-existing
  `VGAuthService` around MSI setup to address the observed file lock.
  The shared KINGDOMS provider additionally treats authenticated WSLPE WinRM
  with a running VMTools core as more authoritative than VMware host-IP
  telemetry, following its existing GOAD design. GOAD/NORTH's installer
  setup script and segmented lifecycle are unchanged.
- `kingdoms/wslpe_stage1_repair.py`: checks an existing **CREATED**
  local VMware/WSLPE instance, its **running** registered VMX, canonical source
  Vagrantfile, exact workgroup Windows name, enabled NAT default-route adapter
  with the **same MAC as its registered VMX**, and authenticated forwarded WinRM.
  It then calls the existing provider's Tools repair, verifies Tools state,
  runs exactly **one** native bounded `vagrant up WSLPE-WS01 --provision`,
  and verifies Windows, Tools and the instance's expected `<prefix>.31`
  exercise address. That Vagrantfile invokes the existing
  `vagrant/fix_ip.ps1`. A failed step leaves the instance **CREATED**
  and the VM preserved for investigation.
- `goad_nomad.py`: private operator console exposes `load` scoped to existing
  native WSLPE instances and `repair_stage1` with an exact confirmation.
  No LPE fixture, learner, TLS handoff, vmnet allocation, NAT removal or NORTH
  lifecycle runs as part of this operation.

## Operator procedure for the preserved VM

Use a **clean, updated** `feature/wslpe41-fresh-full-installer` checkout.
Run the current read-only registration/VMware checks before recovery. Do not
use `install` or attempt to create the VM again.

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git status --short
git pull --ff-only
./goad.sh -c windows-lpe
```

Inside the KINGDOMS operator console, if the instance is not already loaded:

```text
load bf5369-wslpe-vmware
```

Check `course` to verify the loaded instance's `CREATED` state. Then issue:

```text
repair_stage1
```

Only after checking the scope and understanding that a **Windows-only**
Tools installation/reboot and **one** Vagrant provisioning pass may occur,
confirm `REPAIR WSLPE STAGE1` when prompted. Do **not** automatically retry
the command if it fails. Preserve the Vagrant/WinRM/MSI logs and inspect the
specific failure. The original WSLPE VM and NORTH must remain unchanged.

**Success means only Stage 1** and `PROVIDED`. The 41-scenario installation,
new operator account, validated HTTPS/TLS, independent JEA #30 activation and
the final release acceptance are separate gates. The full `--execute`
entry point remains disabled until these are validated.

## Test scope

Mock-only tests exercise the exact existing provider script selector, the
VGAuth scoped MSI workaround, the existing native `vagrant --provision` call,
registered Windows NAT MAC evidence and first-failure blocking. Source CI
success is not evidence that the live VM has been repaired.
