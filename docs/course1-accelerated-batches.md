# Kingdoms Course 1 — accelerated engineering batches

Current operational proof: 161/161 tests passed at commit 8787696; complete
VMware observational snapshot and no *observed* collision with the synthetic
three-segment proposal. This is not a deployment authorization.

## What changed in this batch

The same consolidated gate now validates a **single isolated source artifact
set** with eight files: four-Windows-VM Vagrant definition, rendered outer
Vagrantfile, deny-forward three-NIC Linux router bootstrap, source manifest,
four-host Ansible provisioning inventory, four-host post-Vagrant WinRM
inventory, VMware provider inventory and the parent/NORTH AD fixture config.

The new Ansible inventory renderer only translates exact known addresses from
the established six-VM reference to the proposed Course 1 addresses. It
preserves fixture passwords without printing them. Native
`ansible-inventory --list` verifies all three generated inventories,
four host addresses and WINRM credential equivalence on the NORTH hosts.

The new **read-only dependency audit** examines source files in
`scripts/`, `goad/`, `ansible/` and `ad/GOAD/` for legacy addresses,
vmnets, ESSOS domains or six-VM assumptions. It prints filenames and counts
but never fixture passwords or full matching lines. P0 runtime source
dependencies receive priority: installer path/binding, VMware provider,
router SSH and lab-mode transitions. A match is a migration lead, not
automatic proof of a defect; the six-VM reference source *must* retain its
original addresses.

## Single operator invocation

```bash
cd "$HOME/kingdoms-course1-src"
git pull --ff-only
bash scripts/course1/validate-course1.sh --survey-host
```

This checks Python contracts, Ruby, router Bash syntax, native Ansible
inventories, ephemeral private source outputs, host observations and legacy
dependency counts in one shot. No hypervisor/VM modification or network
allocation; private generated artifacts are deleted after the run.

## Batch to implement after audit

1. Isolated profile-aware install source + immutable instance binding,
   including correct script paths (never point Vagrant at the current preview).
2. Three-segment VMware vmnet allocation and proven local/manual MAC support,
   router PCI/NIC/SSH, safe NAT provisioning/rollback and host routes.
3. Runtime lifecycle and lab-mode guest roster transitions.
4. KINGDOMS2, Phase 03, parent/NORTH AD and all Course 1 release tests.

Do not activate Course 1, merge draft PR #30, or modify the validated
reference Kingdoms deployment until disposable runtime acceptance is green.
