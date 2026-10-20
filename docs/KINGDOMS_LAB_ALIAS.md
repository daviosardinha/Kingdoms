# Public KINGDOMS lab alias

The full seven-VM Kingdoms topology is selected publicly as `KINGDOMS`.
The command-line and interactive entry point remains `./goad.sh`.

```bash
./goad.sh -t install -l KINGDOMS -p vmware
./goad.sh
# In the interactive console:
# set_lab KINGDOMS
```

The existing `GOAD` name is a supported backwards-compatible alias:

```bash
./goad.sh -t install -l GOAD -p vmware
```

## What changes

- The argument parser resolves `KINGDOMS` to internal `GOAD` **before**
  settings, provider selection and instance creation.
- Interactive `set_lab KINGDOMS` resolves to internal `GOAD`.
- The interactive lab table, current settings and console prompt display
  `KINGDOMS`. Tab completion offers both public and legacy spellings.
- Existing `GOAD` selections continue to use the exact same VMware provider.

## What intentionally does not change

- `ad/GOAD`, Vagrant configuration and machine identifiers such as
  `GOAD-WS01`, `GOAD-DC01` and `GOAD-ROUTER`.
- VMware registrations, virtual disks, VMX paths and snapshots.
- Domain names, router policy, vmnet10/vmnet20/vmnet30/vmnet99, IPs or MACs.
- Stored lab instance identity and directory layout.
- Provider installation, start/stop, restore and reset implementations.
- The separate NORTH or standalone Windows LPE lab definitions.

This is a **naming-layer change**, not a lab conversion or migration.
Do not rename an installed instance's internal lab field or the GOAD folder.

## Source verification

The following test needs Python 3 and does not access VMware or Windows:

```bash
python3 -m unittest tests.test_kingdoms_lab_alias -v
```

Other lifecycle tests should remain passing. A fresh VM installation is not
required for the alias change because the original provider implementation
is unchanged. This is *not* a claim that a new installation was performed.

For operators working on NORTH, do not run full KINGDOMS alongside NORTH
on the same overlapping VMware network profile. The existing provider
collision and ownership gates remain authoritative.

## Rollout

1. Review the feature-branch diff and run source checks.
2. Confirm `KINGDOMS` and `GOAD` resolve to the same internal lab.
3. Merge only after review. Existing installations and their snapshots
   are left untouched.
