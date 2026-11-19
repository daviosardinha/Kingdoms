# NORTH Topic 12 | DLL Hijacking execution pilot

**Source of truth for lab implementation:** `ansible/roles/windows_lpe/tasks/techniques/service_dll_hijacking.yml`

This document is for lab maintenance and validation, not the student walkthrough. The Notion course should contain only enumeration, explanation, commands, output, and interpretation.

## Objective

Fix the existing Topic 12 scenario without changing other NORTH techniques, KINGDOMS, or WSLPE. The lab intentionally models an absolute-path native DLL load by a service running as LocalSystem:

- `KingdomDllSvc` stays `DEMAND_START`, runs under `LocalSystem`, and retains the protected, quoted `KingdomDllHost.exe` service executable.
- The missing target is `C:\Kingdom LPE\DLL Hijack\KingdomHelper.dll`.
- BUILTIN\\Users may create a file in the target directory. That right is scoped to **the parent directory only**, not inherited by the protected `Service` subdirectory.
- Ordinary users cannot start the service directly. Its existing service DACL is not changed to grant `SERVICE_START`.
- The separate, visible Task Scheduler task `Workstation Component Health` runs under SYSTEM every minute and cycles **only** `KingdomDllSvc`. BUILTIN\\Users may read its definition, but cannot modify or start it on demand. This does not modify Topic 07's `Workstation Service Health` task.
- A native x64 proof DLL is available at `C:\Users\Public\Documents\KingdomHelper.dll`. Copying it into the missing target location supplies an exported function, `KingdomDllProof`, returning a fixed marker.
- On the next authorized maintenance start, the service calls the DLL's exported function. The DLL checks the WS01/SYSTEM identity and uses WTSSendMessageW to display a visible notification in the active NORTH Rickon RDP session. No text proof file is created.
- The native DLL contains no reverse shell, network activity, process creation or `DllMain` side effects. It is not the earlier executable `KingdomProof.exe` renamed to `.dll`.

## Deterministic proof artifact

Source: `ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.c`

Reproducible compressed artifact: `ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.dll.gz.b64`

Expected native DLL SHA-256:

`cc3b582f9afd96e741a3110be556a8c4209afb48299963deb985f628f4215ba7`

On a developer machine with `clang-cl`, `lld-link`, and Python 3, rebuild the compressed artifact with:

```bash
bash scripts/build-north-topic12-dll-proof.sh
python3 -m pytest -q tests/test_north_topic12_dll_hijacking_source.py
```

These are **source checks**, not Windows runtime validation.

## Selective NORTH deployment

Use only the already-created NORTH provider. From any Kali directory:

```bash
ROOT="$HOME/kingdoms-north-fresh-test"; git -C "$ROOT" switch main && git -C "$ROOT" pull --ff-only && export GOAD_PROVIDER_DIR="$ROOT/workspace/0da0a9-north-vmware/provider" && test -f "$GOAD_PROVIDER_DIR/.vagrant/machines/GOAD-WS01/vmware_desktop/id" && bash "$ROOT/scripts/apply-windows-lpe-candidates.sh" service_dll_hijacking
```

The script is technique-selective. Do not use it for the full KINGDOMS or WSLPE provider.

## Evidence from NORTH\\rickon.stark on WS01

Start from Rickon's non-elevated PowerShell. First verify the service, task and candidate file:

```powershell
whoami
sc.exe qc KingdomDllSvc
sc.exe sdshow KingdomDllSvc
schtasks.exe /query /tn "Workstation Component Health" /v /fo LIST
Get-ScheduledTask -TaskName 'Workstation Component Health' | Select-Object -ExpandProperty Actions
icacls "C:\Kingdom LPE\DLL Hijack"
icacls "C:\Kingdom LPE\DLL Hijack\Service"
Test-Path -LiteralPath 'C:\Kingdom LPE\DLL Hijack\KingdomHelper.dll' -PathType Leaf
Get-FileHash -LiteralPath 'C:\Users\Public\Documents\KingdomHelper.dll' -Algorithm SHA256
```

Expected: service LocalSystem/Manual, no ordinary-user SERVICE_START, a visible read-only SYSTEM task whose action starts and stops this service on a one-minute repetition, native DLL fixture with the documented hash, writable target parent, protected service subdirectory, target DLL **absent** before the experiment.

For a controlled proof, copy the prepared native DLL into the missing location. Do not replace the service executable or alter the task/service ACL:

```powershell
$src = 'C:\Users\Public\Documents\KingdomHelper.dll'
$dst = 'C:\Kingdom LPE\DLL Hijack\KingdomHelper.dll'
if (Test-Path -LiteralPath $dst) { throw 'Target DLL already exists. Do not overwrite.' }
Copy-Item -LiteralPath $src -Destination $dst -ErrorAction Stop
Get-FileHash -LiteralPath $dst -Algorithm SHA256
```

Allow the normal scheduled maintenance cycle to execute. In Rickon's active NORTH RDP desktop, inspect the on-screen notification titled NORTH | DLL Hijacking proof. Its text should confirm that KingdomDllSvc loaded the DLL while running as NT AUTHORITY\SYSTEM. The DLL returns the success marker only if Windows accepts the notification. A copied DLL alone, or a successful task-start message, is not execution proof. This is a visible SYSTEM identity demonstration, not an interactive SYSTEM CMD.

## Rollback

After obtaining proof, remove only the DLL planted at the previously missing path:

```powershell
Remove-Item -LiteralPath 'C:\Kingdom LPE\DLL Hijack\KingdomHelper.dll' -ErrorAction Stop
Test-Path -LiteralPath 'C:\Kingdom LPE\DLL Hijack\KingdomHelper.dll' -PathType Leaf
sc.exe query KingdomDllSvc
```

Expected `Test-Path=False`. The maintenance task may temporarily change service state during its next cycle. Preserve the notification screenshot as evidence; no protected text log is generated.

For complete reset/reapply testing, use the repository's exact-technique Windows LPE reset and validation workflow on a disposable NORTH instance. Reset must delete only `Workstation Component Health`, `KingdomDllSvc`, the Topic 12 directory and its native proof DLL fixture. It must leave Topic 07 and all other exercises unchanged.

## Release acceptance

- [ ] Source checks pass with the deterministic packaged DLL hash.
- [ ] Selective apply completes with `WINDOWS_LPE_SERVICE_DLL_HIJACKING=VULNERABLE` and `WINDOWS_LPE_TOPIC12_TRIGGER_READY`.
- [ ] Standard-user enumeration can inspect the Task Scheduler trigger without manually executing it.
- [ ] Protected service directory rejects a standard-user file write, while the target parent permits DLL creation.
- [ ] The SYSTEM maintenance cycle loads the planted DLL and the active Rickon RDP session receives a fresh on-screen identity notification.
- [ ] Removing the planted DLL restores the missing-DLL baseline.
- [ ] Reset/reapply is idempotent and does not affect Topic 07 or any other NORTH scenario.

Do not mark runtime verification complete until the notification has been observed on NORTH WS01 and the DLL has been removed. The distinct requirement for an interactive SYSTEM CMD is not fulfilled by this proof and remains open.
