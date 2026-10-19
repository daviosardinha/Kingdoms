# Windows-native CLR COM registration and dedicated SYSTEM client.
# No import-time changes. All names, CLSIDs and paths are exercise-owned.
Set-StrictMode -Version Latest

function Invoke-Wslpe45RegAsmProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$RegAsm,
        [Parameter(Mandatory=$true)][string]$Assembly,
        [Parameter(Mandatory=$true)][ValidateSet('/codebase','/unregister')][string]$Operation
    )
    # Read native streams directly: PS5.1 turns 2>&1 stderr into ErrorRecords.
    foreach($path in @($RegAsm,$Assembly)) {
        if($path.IndexOfAny([char[]]@('"',[char]13,[char]10)) -ge 0 -or
           -not [IO.Path]::IsPathRooted($path) -or
           -not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'RegAsm requires existing absolute literal file paths'
        }
    }
    $start=[Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$RegAsm
    $start.Arguments=('"'+$Assembly+'" '+$Operation+' /nologo')
    $start.UseShellExecute=$false
    $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true
    $start.RedirectStandardError=$true
    $process=[Diagnostics.Process]::new()
    $process.StartInfo=$start
    try {
        if(-not $process.Start()) { throw 'RegAsm did not start' }
        $stdout=$process.StandardOutput.ReadToEndAsync()
        $stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit(120000)) {
            throw ('RegAsm timeout; preserve partial state and inspect process '+$process.Id)
        }
        $output=$stdout.GetAwaiter().GetResult()
        $errors=$stderr.GetAwaiter().GetResult()
        $code=$process.ExitCode
        if($code -ne 0) { throw ('RegAsm exit '+$code+': '+$output+[Environment]::NewLine+$errors) }
        return [pscustomobject]@{ExitCode=$code;StdOut=$output;StdErr=$errors}
    } finally { $process.Dispose() }
}

function Assert-Wslpe45OwnedComCodeBase {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$CodeBase,
        [Parameter(Mandatory=$true)][string]$Assembly
    )
    # RegAsm writes a file URI, not a Windows path. It also canonicalizes
    # the extension to .DLL on this Windows/.NET Framework guest. Compare
    # *complete local paths* case-insensitively; never compare URI text to
    # backslash paths or accept a matching suffix from another directory.
    $uri=$null
    if(-not [Uri]::TryCreate($CodeBase,[UriKind]::Absolute,[ref]$uri) -or
       -not $uri.IsFile -or $uri.IsUnc -or
       -not [string]::IsNullOrEmpty($uri.Query) -or
       -not [string]::IsNullOrEmpty($uri.Fragment)) {
        throw 'COM CodeBase must be a local absolute file URI'
    }
    $actual=[IO.Path]::GetFullPath($uri.LocalPath)
    $expected=[IO.Path]::GetFullPath($Assembly)
    if(-not [string]::Equals($actual,$expected,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'COM registered CodeBase does not match owned assembly'
    }
}

function Invoke-Wslpe45ComRegistration {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateSet('apply','validate','reset')][string]$Action,
        [Parameter(Mandatory=$true)]
        [ValidateSet('apply','vulnerable','reset','clean','reapply','revulnerable')][string]$Stage
    )
    $ErrorActionPreference='Stop'
    Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeFixture.psm1' -Force -ErrorAction Stop
    $who=Assert-Wslpe45Identity
    $id='com_clsid_registration_hijack'
    $clsid='{7E86DE4C-10F9-414B-82B5-07CB20264527}'
    $progid='Kingdoms45.ComServer'
    $taskName='Kingdom45ComClient'
    $root=Get-Wslpe45FixturePath -Id $id
    $inbox=Join-Path $root 'inbox'
    $library='C:\ProgramData\KingdomsWSLPE45\lib\Kingdom45ComServer.cs'
    $assembly=Join-Path $root 'Kingdom45ComServer.dll'
    $alternate=Join-Path $inbox 'Kingdom45ComServer.dll'
    $client=Join-Path $root 'consumer.ps1'
    $regasm=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe'
    $registry=[Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::LocalMachine,
        [Microsoft.Win32.RegistryView]::Registry64)
    $regSub='SOFTWARE\Classes\CLSID\'+$clsid
    $existingTask=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    try {
        $key=$registry.OpenSubKey($regSub)
        if($key){$key.Close()}
        if($Action -eq 'apply') {
            if($existingTask -or $key){throw 'Existing COM registration or task collision'}
            if(-not (Test-Path -LiteralPath $regasm -PathType Leaf)){throw '64-bit .NET Framework RegAsm missing'}
            if(-not (Test-Path -LiteralPath $library -PathType Leaf)){throw 'Dedicated COM server source missing'}
            $root=New-Wslpe45OwnedFixture -Number 27 -Id $id
            New-Item -ItemType Directory -Path $inbox -ErrorAction Stop | Out-Null
            $source=Get-Content -LiteralPath $library -Raw -ErrorAction Stop
            Add-Type -TypeDefinition $source -Language CSharp -OutputAssembly $assembly -OutputType Library -ErrorAction Stop
            $altSource=$source.Replace('WSLPE45_COM_BASELINE','WSLPE45_COM_SUBSTITUTE')
            Add-Type -TypeDefinition $altSource -Language CSharp -OutputAssembly $alternate -OutputType Library -ErrorAction Stop
            $sid=[Security.Principal.SecurityIdentifier]::new($who.LearnerSid)
            $fileAcl=Get-Acl -LiteralPath $inbox -ErrorAction Stop
            $fileAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
                $sid,[Security.AccessControl.FileSystemRights]::Modify,
                [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit',
                [Security.AccessControl.PropagationFlags]::None,
                [Security.AccessControl.AccessControlType]::Allow)) | Out-Null
            Set-Acl -LiteralPath $inbox -AclObject $fileAcl -ErrorAction Stop

            $result=Invoke-Wslpe45RegAsmProcess -RegAsm $regasm -Assembly $assembly -Operation '/codebase'
            Write-Output ('WSLPE45_REGASM_EXIT='+$result.ExitCode)
            if($result.StdOut){Write-Output $result.StdOut}
            if($result.StdErr){Write-Warning $result.StdErr}
            $clsidKey=$registry.OpenSubKey($regSub)
            if(-not $clsidKey){throw 'COM class registration absent after RegAsm'}
            $clsidKey.Close()
            # PowerShell run as SYSTEM instantiates this exact CLSID. Its
            # CodeBase can be redirected by the learner via scoped registry
            # SetValue, while the baseline assembly remains protected.
            $script=@'
$ErrorActionPreference='Stop'
$instance=New-Object -ComObject Kingdoms45.ComServer -ErrorAction Stop
$instance.Proof()
'@
            Set-Content -LiteralPath $client -Value $script -Encoding UTF8 -ErrorAction Stop
            $powershell=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
            $taskAction=New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -NonInteractive -File "{0}"' -f $client)
            $trigger=New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 365)
            Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -User 'SYSTEM' -RunLevel Highest -ErrorAction Stop | Out-Null

            $classInproc=$registry.OpenSubKey($regSub+'\InprocServer32')
            if(-not $classInproc){throw 'COM InprocServer32 missing'}
            try{
                $versions=@($classInproc.GetSubKeyNames())
                if($versions.Count -ne 1){throw 'COM version registration count not uniquely owned'}
                $version=$classInproc.OpenSubKey($versions[0], $true)
                if(-not $version){throw 'COM version registration missing'}
                try{
                    Assert-Wslpe45OwnedComCodeBase -CodeBase ([string]$version.GetValue('CodeBase')) -Assembly $assembly
                    $security=$version.GetAccessControl()
                    $rule=[Security.AccessControl.RegistryAccessRule]::new(
                        $sid,[Security.AccessControl.RegistryRights]::SetValue,
                        [Security.AccessControl.InheritanceFlags]::None,
                        [Security.AccessControl.PropagationFlags]::None,
                        [Security.AccessControl.AccessControlType]::Allow)
                    $security.AddAccessRule($rule) | Out-Null
                    $version.SetAccessControl($security)
                } finally {$version.Close()}
            } finally {$classInproc.Close()}
            Write-Output 'WSLPE45_COM_REGISTERED'
        }
        elseif($Action -eq 'reset'){
            $root=Assert-Wslpe45OwnedFixture -Number 27 -Id $id
            $task=Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
            if(-not $task -or $task.Principal.UserId -notin @('SYSTEM','S-1-5-18')){throw 'Refusing unexpected COM consumer task'}
            $argument=[string]$task.Actions[0].Arguments
            if(-not $argument.Contains($client)){throw 'Refusing foreign task action'}
            if(-not $key){throw 'Owned CLSID missing'}
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
            $result=Invoke-Wslpe45RegAsmProcess -RegAsm $regasm -Assembly $assembly -Operation '/unregister'
            Write-Output ('WSLPE45_REGASM_EXIT='+$result.ExitCode)
            if($result.StdOut){Write-Output $result.StdOut}
            if($result.StdErr){Write-Warning $result.StdErr}
            $left=$registry.OpenSubKey($regSub)
            if($left){$left.Close();throw 'Dedicated COM CLSID not cleaned by RegAsm'}
            Remove-Wslpe45OwnedFixture -Number 27 -Id $id
            Write-Output 'WSLPE45_COM_UNREGISTERED'
        }
        elseif($Stage -eq 'clean'){
            if($existingTask -or $key -or (Test-Path -LiteralPath $root)){throw 'COM fixture not clean'}
            Write-Output 'WSLPE45_COM_CLEAN'
        }
        else{
            $root=Assert-Wslpe45OwnedFixture -Number 27 -Id $id
            if(-not $existingTask -or $existingTask.Principal.UserId -notin @('SYSTEM','S-1-5-18')){
                throw 'Privileged COM consumer task missing'
            }
            if(-not $key -or -not (Test-Path -LiteralPath $assembly -PathType Leaf) -or
               -not (Test-Path -LiteralPath $alternate -PathType Leaf)){
                throw 'Dedicated COM class and binaries missing'
            }
            $child=$registry.OpenSubKey($regSub+'\InprocServer32')
            if(-not $child){throw 'Registered COM InprocServer32 missing'}
            try{
                $versions=@($child.GetSubKeyNames())
                if($versions.Count -ne 1){throw 'Unexpected COM versions'}
                $v=$child.OpenSubKey($versions[0])
                if(-not $v){throw 'Expected COM version missing'}
                try{
                    Assert-Wslpe45OwnedComCodeBase -CodeBase ([string]$v.GetValue('CodeBase')) -Assembly $assembly
                    $sids=$v.GetAccessControl().GetAccessRules($true,$false,[Security.Principal.SecurityIdentifier])
                    $found=$false
                    foreach($ace in $sids){
                        if($ace.IdentityReference.Value -eq $who.LearnerSid -and $ace.AccessControlType -eq 'Allow' -and
                           ($ace.RegistryRights -band [Security.AccessControl.RegistryRights]::SetValue)){$found=$true}
                    }
                    if(-not $found){throw 'Learner cannot edit isolated COM registration value'}
                } finally {$v.Close()}
            } finally {$child.Close()}
            Write-Output 'WSLPE45_COM_CONFIGURATION_PRESENT_NOT_EXPLOIT_PROVEN'
        }
        Write-Output ('WSLPE45_BATCH_STAGE='+$id+':'+$Stage+':PASS')
    }
    finally {$registry.Close()}
}
Export-ModuleMember -Function Invoke-Wslpe45ComRegistration, Assert-Wslpe45OwnedComCodeBase
