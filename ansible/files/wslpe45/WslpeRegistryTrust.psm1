# WSLPE standalone registry-consumer exercise contracts for #26 and #28.
# This module is never loaded on NORTH and has no import-time side effects.
Set-StrictMode -Version Latest

function Invoke-Wslpe45RegistryTrust {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet('ifeo_debugger_acl_hijack','app_paths_registry_hijack')]
        [string]$Id,
        [Parameter(Mandatory=$true)]
        [ValidateSet('apply','reset','validate')]
        [string]$Action,
        [Parameter(Mandatory=$true)]
        [ValidateSet('apply','reset','vulnerable','clean','reapply','revulnerable')]
        [string]$Stage
    )
    $ErrorActionPreference='Stop'
    Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeFixture.psm1' -Force -ErrorAction Stop
    $identity = Assert-Wslpe45Identity
    $number = if($Id -eq 'ifeo_debugger_acl_hijack'){26}else{28}
    $serviceName = if($number -eq 26){'Kingdom45IfeoProbe.exe'}else{'Kingdom45AppPathsProbe.exe'}
    $taskName = if($number -eq 26){'Kingdom45IfeoConsumer'}else{'Kingdom45AppPathsConsumer'}
    $keySub = if($number -eq 26) {
        'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\Kingdom45IfeoProbe.exe'
    } else {
        'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Kingdom45AppPathsProbe.exe'
    }
    $root = Get-Wslpe45FixturePath -Id $Id
    $bin = Join-Path $root 'bin'
    $benignExe = Join-Path $bin $serviceName
    $consumerExe = if($number -eq 26){$benignExe}else{Join-Path $bin 'Kingdom45AppPathsLauncher.exe'}
    $payloadExe = Join-Path $bin 'Kingdom45Proof.exe'
    $protected = Join-Path $root 'protected'
    $proof = Join-Path $protected 'proof.txt'
    $kernel = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::LocalMachine,
        [Microsoft.Win32.RegistryView]::Registry64
    )
    try {
        $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($Action -eq 'apply') {
            if ($existingTask) { throw 'Standalone task collision; refusing to adopt it' }
            $existingRegistry = $kernel.OpenSubKey($keySub)
            if ($existingRegistry) { $existingRegistry.Close(); throw 'Registry key collision; no overwrite' }
            $root = New-Wslpe45OwnedFixture -Number $number -Id $Id
            New-Item -ItemType Directory -Path $bin -ErrorAction Stop | Out-Null
            New-Item -ItemType Directory -Path $protected -ErrorAction Stop | Out-Null
            # A writable proof directory would invalidate this LPE scenario.
            # Only SYSTEM/Administrators can create its evidence file.
            $protectedAcl = Get-Acl -LiteralPath $protected -ErrorAction Stop
            $protectedAcl.SetAccessRuleProtection($true, $false)
            $inherit = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
            $prop = [Security.AccessControl.PropagationFlags]::None
            $allow = [Security.AccessControl.AccessControlType]::Allow
            foreach ($targetSid in @('S-1-5-18','S-1-5-32-544')) {
                $principal = [Security.Principal.SecurityIdentifier]::new($targetSid)
                $rule = [Security.AccessControl.FileSystemAccessRule]::new(
                    $principal, [Security.AccessControl.FileSystemRights]::FullControl,
                    $inherit, $prop, $allow
                )
                $protectedAcl.AddAccessRule($rule) | Out-Null
            }
            Set-Acl -LiteralPath $protected -AclObject $protectedAcl -ErrorAction Stop

            # Both executables are restricted to our lab tree. The benign one
            # does not elevate or write a proof; only the alternate one does.
            $benign = @'
using System;
public static class Kingdom45Benign { public static void Main() {} }
'@
            Add-Type -TypeDefinition $benign -Language CSharp -OutputAssembly $benignExe -OutputType ConsoleApplication -ErrorAction Stop
            $proofCode = @"
using System;
using System.IO;
using System.Security.Principal;
public static class Kingdom45Proof {
    public static void Main(){
        string path = @"$proof";
        if (!String.Equals(Path.GetFullPath(path), @"$proof", StringComparison.OrdinalIgnoreCase)) return;
        File.WriteAllText(path, "WSLPE45_REGISTRY_PROOF=" + WindowsIdentity.GetCurrent().Name);
    }
}
"@
            Add-Type -TypeDefinition $proofCode -Language CSharp -OutputAssembly $payloadExe -OutputType ConsoleApplication -ErrorAction Stop

            if ($number -eq 28) {
                $launcherCode = @'
using System;
using System.Diagnostics;
public static class Kingdom45AppPathLauncher {
    public static void Main() {
        var start = new ProcessStartInfo();
        start.FileName = "Kingdom45AppPathsProbe.exe";
        start.UseShellExecute = true;
        start.CreateNoWindow = true;
        Process.Start(start);
    }
}
'@
                Add-Type -TypeDefinition $launcherCode -Language CSharp -OutputAssembly $consumerExe -OutputType ConsoleApplication -ErrorAction Stop
            }

            # Custom exercise-only key. No Windows-owned IFEO or App Path touched.
            $key = $kernel.CreateSubKey($keySub, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree)
            if (-not $key) { throw 'Could not create unique registry fixture key' }
            try {
                if ($number -eq 28) {
                    $key.SetValue('', $benignExe, [Microsoft.Win32.RegistryValueKind]::String)
                }
                $acl = $key.GetAccessControl()
                $sid = [Security.Principal.SecurityIdentifier]::new($identity.LearnerSid)
                $rule = [Security.AccessControl.RegistryAccessRule]::new(
                    $sid, [Security.AccessControl.RegistryRights]::SetValue,
                    [Security.AccessControl.InheritanceFlags]::None,
                    [Security.AccessControl.PropagationFlags]::None,
                    [Security.AccessControl.AccessControlType]::Allow
                )
                $acl.AddAccessRule($rule) | Out-Null
                $key.SetAccessControl($acl)
            }
            finally { $key.Close() }

            $trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 365)
            $actionTask = New-ScheduledTaskAction -Execute $consumerExe
            Register-ScheduledTask -TaskName $taskName -Action $actionTask -Trigger $trigger -User 'SYSTEM' -RunLevel Highest -ErrorAction Stop | Out-Null
            # No attacker-controlled task definition or service DACL.
            Write-Output ('WSLPE45_REGISTRY_TRUST_APPLIED=' + $Id)
        }
        elseif ($Action -eq 'reset') {
            $root = Assert-Wslpe45OwnedFixture -Number $number -Id $Id
            if ($existingTask) {
                $command = [string]$existingTask.Actions[0].Execute
                if ($existingTask.Actions.Count -ne 1 -or
                    -not $command.Equals($consumerExe, [StringComparison]::OrdinalIgnoreCase)) {
                    throw 'Refusing to delete non-owned scheduled task'
                }
                Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
            }
            $key = $kernel.OpenSubKey($keySub)
            if (-not $key) { throw 'Registry fixture missing before reset' }
            $key.Close()
            $split = $keySub.LastIndexOf('\')
            $parentName = $keySub.Substring(0,$split)
            $leaf = $keySub.Substring($split+1)
            $parent=$kernel.OpenSubKey($parentName, $true)
            if (-not $parent) { throw 'Registry fixture parent missing' }
            try { $parent.DeleteSubKeyTree($leaf, $false) }
            finally { $parent.Close() }
            Remove-Wslpe45OwnedFixture -Number $number -Id $Id
            Write-Output ('WSLPE45_REGISTRY_TRUST_RESET=' + $Id)
        }
        elseif ($Stage -eq 'clean') {
            if ($existingTask -or $kernel.OpenSubKey($keySub) -or (Test-Path -LiteralPath $root)) {
                throw 'Fixture is not clean'
            }
            Write-Output ('WSLPE45_REGISTRY_TRUST_CLEAN=' + $Id)
        }
        else {
            $root = Assert-Wslpe45OwnedFixture -Number $number -Id $Id
            if (-not $existingTask -or [string]$existingTask.Principal.UserId -notin @('SYSTEM','S-1-5-18')) {
                throw 'Expected unique SYSTEM scheduler consumer missing'
            }
            if (-not [string]$existingTask.Actions[0].Execute -or
                -not ([string]$existingTask.Actions[0].Execute).Equals($consumerExe,[StringComparison]::OrdinalIgnoreCase)) {
                throw 'Unexpected privileged executable; no vulnerability proof'
            }
            $key = $kernel.OpenSubKey($keySub)
            if (-not $key) { throw 'Deliberately delegated registry key is missing' }
            try {
                $acl = $key.GetAccessControl()
                $rules = $acl.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier])
                $allowed = $false
                foreach($ace in $rules) {
                    if($ace.IdentityReference.Value -eq $identity.LearnerSid -and
                       $ace.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
                       ($ace.RegistryRights -band [Security.AccessControl.RegistryRights]::SetValue) -ne 0) {
                        $allowed = $true
                    }
                }
                if(-not $allowed) { throw 'Learner cannot modify intended registry entry' }
            } finally { $key.Close() }
            if (-not (Test-Path -LiteralPath $benignExe -PathType Leaf) -or
                -not (Test-Path -LiteralPath $payloadExe -PathType Leaf) -or
                -not (Test-Path -LiteralPath $protected -PathType Container)) {
                throw 'Unique lab binaries or protected directory missing'
            }
            $protectedDacl = (Get-Acl -LiteralPath $protected).Access
            foreach ($entry in $protectedDacl) {
                $sid = $null
                try { $sid = $entry.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch {}
                if ($sid -eq $identity.LearnerSid -and
                    $entry.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
                    ($entry.FileSystemRights -band [Security.AccessControl.FileSystemRights]::WriteData)) {
                    throw 'Learner can write protected evidence without escalation'
                }
            }
            Write-Output ('WSLPE45_REGISTRY_TRUST_VULNERABLE_CONFIGURATION=' + $Id)
        }
        Write-Output ('WSLPE45_BATCH_STAGE=' + $Id + ':' + $Stage + ':PASS')
    }
    finally { $kernel.Close() }
}

Export-ModuleMember -Function 'Invoke-Wslpe45RegistryTrust'
