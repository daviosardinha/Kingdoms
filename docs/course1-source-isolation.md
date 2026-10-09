# Kingdoms Course 1 — private source isolation gate

Status: **preview-only**. This does not create a Kingdoms instance, copy
anything into `workspace/`, configure Ansible, change GOAD compatibility
paths, or permit Vagrant/VMware operations.

## Why this gate exists

The established Kingdoms installer currently resolves source recipes through
`GoadPath.get_lab_path("GOAD")` and registers live instances under
`workspace/<instance>/`. Repointing either path at a four-guest preview would
silently mix two different deployment contracts. We must instead require an
explicit, separately staged, **non-operational** Course 1 source candidate.

This gate reads a preview produced by `scripts/course1/generate-profile.py`,
requires that its root be outside Git and every `workspace` directory, refuses
symlinks, verifies private file/directory permissions, and compares **all seven
artifacts byte-for-byte** with the current canonical generator's output.
Unknown or changed files, stale source, forged activation markers and mismatched
rosters fail closed. Failure diagnostics do not print credentials.

## Operator procedure

```bash
# Preview is private because it contains existing lab fixture credentials.
python3 scripts/course1/generate-profile.py \
  --output "$HOME/Kingdoms-course1-preview" \
  --acknowledge-lab-credentials

python3 -m goad.course1_source_gate \
  --check-preview "$HOME/Kingdoms-course1-preview"

python3 -m unittest tests.test_course1_source_gate
```

Do not create the preview if an older path already exists: the generator refuses
overwrite. It is safe to continue using the source-only test suite before
creating a private preview.

**A passing result is NOT an installation approval.** The gate returns only
nonsecret profile metadata plus `deployment_authorized=false`.
The production instance manager, VMware controller and network-mode scripts
still do not consume this stage. The separate release requirements remain:
profile-aware installation/Ansible selection, isolated networking and MACs,
runtime reset, KINGDOMS2 SQL, fresh NORTH/parent AD, and Phase 03/00–09 parity.
