# NORTH Topic 12 | Fixed SYSTEM command proof via missing DLL

Status: PR #107 implementation pilot. Windows runtime has not been tested yet. This is internal code documentation, not student-facing Notion content.

## The vulnerability

Rickon can create a missing native DLL at C:\Kingdom LPE\DLL Hijack\KingdomHelper.dll but cannot alter the protected KingdomDllSvc executable or start that SYSTEM service directly. The separate Workstation Component Health task starts it under LocalSystem every minute.

The service loads the DLL at the explicit path, finds its KingdomDllProof export, and executes that function under its SYSTEM token. Unlike the previous on-screen popup and file log implementations, the new prepared DLL runs two fixed, read-only Windows commands: C:\Windows\System32\whoami.exe and C:\Windows\System32\whoami.exe /priv. Both are hardcoded in the DLL. No input is accepted.

The DLL checks host WS01 and token SID S-1-5-18. Its real command stdout is transmitted over the local write-only named pipe \\.\pipe\KingdomsTopic12Proof into a separately launched, read-only PowerShell viewer running as Rickon. The viewer displays actual command results directly in his terminal. There is no unrestricted SYSTEM CMD, reverse shell, file-based proof, message popup, network listener or persistent command input.

## Source of truth

- Native source: ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.c
- Precompiled DLL: ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.dll.gz.b64
- Read-only PowerShell viewer: ansible/roles/windows_lpe/files/dll_hijack/KingdomDllProofViewer.ps1
- Build script: scripts/build-north-topic12-dll-proof.sh
- Expected DLL SHA256: 3a68f77286498a365fece9e53cda32417eb7294c63ef031be27a00ccb036b9d1

The binary was cross-compiled as a native x64 PE DLL. Its import table includes CreateProcessW, its export is KingdomDllProof, and its contents were hashed. The Windows runtime outcome still needs actual WS01 evidence.

## Selective NORTH application

Use only the disposable NORTH WS01 and the existing exact-technique script. From Kali:
ROOT="$HOME/kingdoms-north-fresh-test"; git -C "$ROOT" fetch origin && git -C "$ROOT" switch feature/north-topic12-dll-hijack-execution-pilot && git -C "$ROOT" pull --ff-only && python3 -m pytest -q "$ROOT/tests/test_north_topic12_dll_hijacking_source.py" && export GOAD_PROVIDER_DIR="$ROOT/workspace/0da0a9-north-vmware/provider" && bash "$ROOT/scripts/apply-windows-lpe-candidates.sh" service_dll_hijacking

## Actual learner test

Open two non-elevated PowerShell windows in Rickon's active NORTH RDP desktop.

First window, start the read-only command-output viewer:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Public\Documents\KingdomDllProofViewer.ps1"

Second window, confirm the DLL destination is absent and copy the prepared file:
Test-Path -LiteralPath 'C:\Kingdom LPE\DLL Hijack\KingdomHelper.dll' -PathType Leaf
Get-FileHash -LiteralPath 'C:\Users\Public\Documents\KingdomHelper.dll' -Algorithm SHA256
Copy-Item -LiteralPath 'C:\Users\Public\Documents\KingdomHelper.dll' -Destination 'C:\Kingdom LPE\DLL Hijack\KingdomHelper.dll' -ErrorAction Stop

The viewer waits for the next scheduled service cycle (up to 150 seconds). If successful, it displays actual stdout from the two fixed Windows commands as SYSTEM. The viewer remains Rickon's own account. This is bounded, real privileged command execution, not an interactive privileged shell.

Cleanup removes only the planted DLL:
Remove-Item -LiteralPath 'C:\Kingdom LPE\DLL Hijack\KingdomHelper.dll' -ErrorAction Stop

Verify that the DLL is absent and service config is unchanged. The selected reset action must delete only Topic 12 fixtures and keep Topics 07–11 intact.

## Release gates

- [x] Cross-compiled PE64 DLL with reviewed import/export table.
- [x] Local-only output path and no arbitrary command input.
- [ ] Local source pytest passes for final branch commit.
- [ ] Selective NORTH WS01 apply validates.
- [ ] SYSTEM whoami output and privilege list arrive in Rickon's terminal.
- [ ] Cleanup and reset/reapply are independently verified.

Keep PR #107 unmerged until real WS01 evidence confirms these outcomes.
