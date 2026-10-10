# NORTH installation-readiness — single operator command

The source of truth is the patched Kingdoms GitHub feature branch; this is
NOT upstream GOAD and it does not use a separate installation engine.

Run from the Kingdoms feature checkout:

```bash
bash scripts/course1/check-install-readiness.sh
```

To sync when GitHub has a newer commit first:

```bash
cd "$HOME/kingdoms-course1-src" && git pull --ff-only && bash scripts/course1/check-install-readiness.sh
```

The command verifies clean source, offline contracts and syntax, registered
VMX inventory and actual NORTH VMware networks/host addresses, reference
address integrity, current native deployment guards, and basic RAM/disk
advisories. The full existing `validate-course1.sh --survey-host` runs only
once for each clean commit; later checks reuse that passing **offline**
regression and still perform a fresh full read-only host/network survey. Use
`--refresh` to run the full suite again.

The console shows a short PASS/BLOCKED/FAIL table instead of dumping hundreds
of repetitive test lines. Full logs are stored under
`~/.local/state/kingdoms/course1/` with private user-only permissions.
Source cache is invalidated automatically for changed Git HEAD or a dirty
checkout. It is not a substitute for live VMware validation.

**Exit codes:** `0` is reserved for a future, fully verified installable
NORTH state and is not returned today; `1` means a failed/inconsistent
check; `2` means current source/host checks passed but installation is
**BLOCKED** because essential provisioning/lifecycle/runtime acceptance
has not been completed. This exit code is intentional; don't override it
or remove the guard. User won't need to run a separate manual checklist.

**What cannot be validated yet:** native four-guest VMware install/start/stop
integration, authenticated Windows/AD lifecycle and WinRM, NAT provisioning
to exercise-mode isolation, first disposable end-to-end NORTH installation,
and subsequent MSSQL / Phase 03 live evidence. The one command reports
these as BLOCKED rather than pretending they were tested.

This tool is **read-only relative to hosts, VMs and lab state**; the only
writes are local restricted diagnostic logs/cache. It never starts/stops VMs,
does not allocate VMnets, change routing, switch nftables, or install AD.
