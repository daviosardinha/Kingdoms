# Native WSLPE 45 — consolidated read-only feasibility sweep

This development-phase command checks native Windows prerequisites for **all 25 new techniques #21–45 in one invocation**. It is not installation, exploit success, or lifecycle acceptance; the 25 novel fixtures have **not been implemented**. The original 20 are preserved without modification. There is no NORTH guest, inventory, domain or Windows machine interaction.

## Reuse the existing exact WSLPE target

The runner imports `scripts/wslpe-fast-track-20.py` safety checks and independently checks the exact registered standalone VMware VMX, inventory, WSLPE management WinRM, local `lpe.trainee`, computer hostname, Windows 10 and absence of domain membership. Any mismatch blocks before the guest code. All results are read-only, including Task Scheduler COM `GetSecurityDescriptor(4)`, SCM descriptor reading, registry key inspection and Windows API presence checks. Native API availability **does not prove an LPE primitive is exploitable**.

## Run once on Kali (no NORTH contact)

```bash
if (
  cd "$HOME/kingdoms-lpe-standalone" &&
  git fetch origin feature/windows-lpe-45-batch &&
  git switch feature/windows-lpe-45-batch &&
  git pull --ff-only &&
  "$HOME/.goad/.venv/bin/python" -m unittest -v \
    tests.test_wslpe_advanced_catalog \
    tests.test_wslpe_batch_catalog \
    tests.test_wslpe_batch_feasibility &&
  "$HOME/.goad/.venv/bin/python" scripts/wslpe-45-feasibility.py --execute
); then
  echo "[PASS] One-shot WSLPE 25-native-API feasibility returned"
else
  echo "[BLOCKED] Standalone read-only feasibility did not finish"
fi
```

If the checkout does not yet have a local `feature/windows-lpe-45-batch` branch, create a tracking branch via `git switch --track origin/feature/windows-lpe-45-batch` first. Check for a clean working tree before switching. Do not manually construct inventories or override the expected guest IP to bypass the guard.

A generated report lives under `~/.local/state/kingdoms-wslpe-feasibility`, owner-only. Share the summarized `native_api_available` / `native_api_blocked` results, **not raw Ansible logs, secrets or inventory hostvars**. Native API failures should inform the **single coordinated fixture implementation**; they do not justify weaker global Windows security settings.

## What this gate means

All 25 rows are accounted for and independently checked for available Windows platform features, but all remain `not_implemented` and `not_tested` for exploitation. The next engineering milestone is actual standalone-only fixtures, reversible apply/validate/reset, their six-step lifecycle qualification and true local-user privilege escalation evidence. This read-only command never returns an all-45 implementation success marker.
