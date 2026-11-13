# NORTH Topic 10 interactive SYSTEM pilot

## Objective

Make the Registry key ACL weakness of `KingdomRegistrySvc` produce a separate interactive SYSTEM CMD on WS01 without giving Rickon permission to change the service DACL or start the service manually.

This is a pilot and remains unvalidated until the Windows apply, registry write, reboot, interactive process, reset and reapply gates pass. Do not merge as a completed exercise before that evidence exists.

## What changes in the fixture

The existing service remains `LocalSystem`. Its service object ACL is not widened. `BUILTIN\Users` retains only the deliberately weak Registry `SetValue` access that this lesson investigates.

The service is now configured with automatic startup. When a student changes `ImagePath`, a controlled reboot allows the Service Control Manager to reload that configuration and launch the registered program.

The role stages `C:\Users\Public\Documents\KingdomRegistryShell.exe`. This is a service-aware helper with a hard-coded `KingdomRegistrySvc` registration. It checks the machine is WS01 and the executing account is SYSTEM. It listens for Rickon's active NORTH RDP session and attempts to create a separate CMD in that session. It has no network listener.

The role resets the service and deletes its staged helper during the normal per-technique reset action.

## Host-side deployment gate

Use the normal KINGDOMS checkout and confirmed `GOAD_PROVIDER_DIR`. On the pilot branch, apply only the affected scenario, not the full Windows LPE profile.

```bash
bash scripts/verify-test-source.sh
bash scripts/apply-windows-lpe-candidates.sh weak_service_registry_permissions
```

Before proceeding, verify on WS01 that `sc.exe qc KingdomRegistrySvc` reports `AUTO_START`, that the account is `LocalSystem`, and that the helper exists. Recheck the service Registry ACL to confirm `BUILTIN\Users` has `SetValue`. A service DACL granting Rickon direct change or start rights would invalidate this exercise.

## Student preflight from Rickon's unelevated PowerShell

```powershell
whoami
sc.exe qc KingdomRegistrySvc
sc.exe sdshow KingdomRegistrySvc
reg.exe query "HKLM\SYSTEM\CurrentControlSet\Services\KingdomRegistrySvc" /v ImagePath
Test-Path -LiteralPath "C:\Users\Public\Documents\KingdomRegistryShell.exe"
```

Ensure the original `ImagePath` is `"C:\Kingdom LPE\Weak Service Registry\KingdomRegistry.exe"` with the `REG_EXPAND_SZ` type. Capture an export of the service key and retain the original value before making any changes.

## Redirect the service command

Rickon must use only the existing Registry `SetValue` right. The .NET open call explicitly requests this permission rather than FullControl.

```powershell
$subkey = 'SYSTEM\CurrentControlSet\Services\KingdomRegistrySvc'
$rk = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($subkey, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, [System.Security.AccessControl.RegistryRights]::SetValue)
if ($null -eq $rk) { throw 'Registry SetValue access was not granted' }
try {
    $rk.SetValue('ImagePath', '"C:\Users\Public\Documents\KingdomRegistryShell.exe"', [Microsoft.Win32.RegistryValueKind]::ExpandString)
} finally {
    $rk.Close()
}
reg.exe query "HKLM\SYSTEM\CurrentControlSet\Services\KingdomRegistrySvc" /v ImagePath
sc.exe qc KingdomRegistrySvc
```

A successful Registry change does not imply the running SCM has accepted the change. Do not claim execution before rebooting and verifying the resulting process.

## Controlled reboot and execution evidence

Reboot WS01 through its normal user-accessible restart mechanism or VMware interface. Reconnect with Rickon's RDP account when the workstation is ready. The SCM should now start the redirected program as LocalSystem. The service-aware helper waits for Rickon's session.

Inside the new `NORTH_KINGDOM_SYSTEM_SHELL` CMD window, verify `whoami` and `whoami /all`. The identity must be `nt authority\system`. In Rickon's original PowerShell session, `whoami` must still identify `north\rickon.stark`.

Capture the new shell and the two separate identities. A service in `RUNNING` state without a verified new SYSTEM process is not a successful interactive escalation.

If the helper fails to launch, collect `sc.exe query`, `sc.exe qc`, the System Service Control Manager events, and the active RDP session before changing the fixture. Do not grant additional rights or disable security controls to force the demonstration.

## Restore the original configuration

After capturing the result, restore the service command using Rickon's same Registry permission. The PowerShell variables that existed before the reboot will have been lost, so use the saved original Registry value and type. Do not assume the original session is still open.

```powershell
$subkey = 'SYSTEM\CurrentControlSet\Services\KingdomRegistrySvc'
$rk = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($subkey, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, [System.Security.AccessControl.RegistryRights]::SetValue)
if ($null -eq $rk) { throw 'Registry SetValue access was not granted for restoration' }
try {
    $rk.SetValue('ImagePath', '"C:\Kingdom LPE\Weak Service Registry\KingdomRegistry.exe"', [Microsoft.Win32.RegistryValueKind]::ExpandString)
} finally {
    $rk.Close()
}
reg.exe query "HKLM\SYSTEM\CurrentControlSet\Services\KingdomRegistrySvc" /v ImagePath
```

Reboot WS01 again so the SCM returns to the restored original command. Confirm that `sc.exe qc` and the Registry `ImagePath` agree, the type remains `REG_EXPAND_SZ`, and the service is again configured for automatic startup. The lab role's reset and apply actions can restore the fixture if a manual rollback fails.

## Acceptance gate

1. Apply on WS01 succeeds and the service remains LocalSystem.
2. The ACL remains Registry `SetValue` for Users without direct service start or configuration permissions.
3. Rickon can edit only the Registry value, with the correct `REG_EXPAND_SZ` type.
4. A normal restart reloads the service's executable command.
5. The service-aware program produces an interactive SYSTEM CMD in Rickon's RDP session without altering his original token.
6. Restoring the original path and rebooting returns the complete baseline.
7. Role reset, clean validation, apply and vulnerable validation all pass.

Source-level tests are in `tests/test_north_topic10_registry_shell_source.py`. They do not prove runtime behavior.
