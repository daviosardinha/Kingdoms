# Six lab-only IPC/file-link/plugin trust candidates, no external guest impact.
Set-StrictMode -Version Latest

function Remove-Wslpe45OwnedLinkJunction {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$FixtureRoot,
        [Parameter(Mandatory=$true)][string]$LearnerSid
    )
    # The generic fixture ownership guard intentionally rejects ALL reparse
    # points. Only #34 may present its exact lab-owned inbox/link junction.
    # Validate the protected owner metadata and immediate ancestors before
    # unlinking; never traverse or recursively delete the link target.
    foreach($parent in @($FixtureRoot,(Join-Path $FixtureRoot 'inbox'))) {
        $info=Get-Item -LiteralPath $parent -Force -ErrorAction Stop
        if(-not $info.PSIsContainer -or
           ($info.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'NTFS junction recovery refuses altered fixture ancestors'
        }
    }
    $ownerFile=Join-Path $FixtureRoot '.kingdoms-owned.json'
    $owner=Get-Content -LiteralPath $ownerFile -Raw -ErrorAction Stop |
        ConvertFrom-Json -ErrorAction Stop
    if($owner.schema -cne 'kingdoms.wslpe.fixture-owner.v1' -or
       $owner.machine -cne 'WSLPE-WS01' -or
       [int]$owner.number -ne 34 -or
       $owner.id -cne 'ntfs_link_redirection' -or
       $owner.learner_sid -cne $LearnerSid) {
        throw 'Refusing NTFS junction recovery without exact fixture ownership'
    }
    $link=Join-Path (Join-Path $FixtureRoot 'inbox') 'link'
    $item=Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue
    if($null -eq $item) { return }
    if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
        # Ordinary files or directories can be checked by the generic guard.
        return
    }
    if($item.LinkType -cne 'Junction') {
        throw 'Refusing to remove unexpected NTFS reparse-point type'
    }
    $target=[string]$item.Target
    $expected=[IO.Path]::GetFullPath((Join-Path $FixtureRoot 'protected')).TrimEnd([char]92)
    if([string]::IsNullOrWhiteSpace($target) -or
       -not $target.TrimEnd([char]92).Equals($expected,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'NTFS junction target differs from owned protected directory'
    }
    # Windows PowerShell 5.1 recursive Remove-Item must NOT be used against
    # directory junctions. CMD RMDIR without /S unlinks the junction itself.
    $cmd=('rmdir "{0}"' -f $link)
    $result=(& (Join-Path $env:WINDIR 'System32\cmd.exe') /d /c $cmd 2>&1 | Out-String)
    if($LASTEXITCODE -ne 0 -or (Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue)) {
        throw ('Dedicated NTFS junction unlink failed: '+$result)
    }
}

function Invoke-Wslpe45Boundary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet('named_pipe_authorization','privileged_loopback_http_authz','privileged_file_toctou','privileged_backup_restore_api','ntfs_link_redirection','elevated_plugin_signature_bypass')]
        [string]$Id,
        [Parameter(Mandatory=$true)]
        [ValidateSet('apply','validate','reset')][string]$Action,
        [Parameter(Mandatory=$true)]
        [ValidateSet('apply','vulnerable','reset','clean','reapply','revulnerable')][string]$Stage
    )
    $ErrorActionPreference='Stop'
    Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeFixture.psm1' -Force -ErrorAction Stop
    $who=Assert-Wslpe45Identity
    $map=@{
        ntfs_link_redirection=@{number=34;service='Kingdom45LinkSvc'}
        elevated_plugin_signature_bypass=@{number=43;service='Kingdom45PluginSvc'}
        named_pipe_authorization=@{number=29;service='Kingdom45PipeSvc'}
        privileged_loopback_http_authz=@{number=39;service='Kingdom45HttpSvc'}
        privileged_file_toctou=@{number=44;service='Kingdom45RaceSvc'}
        privileged_backup_restore_api=@{number=45;service='Kingdom45RestoreSvc'}
    }
    $contract=$map[$Id]
    if($null -eq $contract){throw 'Unknown isolated privileged API fixture'}
    $number=[int]$contract.number
    $name=[string]$contract.service
    $root=Get-Wslpe45FixturePath -Id $Id
    $input=Join-Path $root 'inbox'
    $protected=Join-Path $root 'protected'
    $binary=Join-Path $root 'KingdomBoundaryService.exe'
    $template='C:\ProgramData\KingdomsWSLPE45\lib\KingdomBoundaryService.cs'
    $service=Get-CimInstance -ClassName Win32_Service -Filter "Name='$name'" -ErrorAction Stop

    if($Action -eq 'apply'){
        if($service){throw 'Refusing collision with existing Windows service'}
        if(-not (Test-Path -LiteralPath $template -PathType Leaf)){
            throw 'Owned standalone boundary-service source missing'
        }
        $root=New-Wslpe45OwnedFixture -Number $number -Id $Id
        New-Item -ItemType Directory -Path $input -ErrorAction Stop | Out-Null
        New-Item -ItemType Directory -Path $protected -ErrorAction Stop | Out-Null
        $acl=Get-Acl -LiteralPath $input -ErrorAction Stop
        $flags=[Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
        $prop=[Security.AccessControl.PropagationFlags]::None
        $allow=[Security.AccessControl.AccessControlType]::Allow
        $sid=[Security.Principal.SecurityIdentifier]::new($who.LearnerSid)
        $rule=[Security.AccessControl.FileSystemAccessRule]::new(
            $sid,[Security.AccessControl.FileSystemRights]::Modify,$flags,$prop,$allow)
        $acl.AddAccessRule($rule) | Out-Null
        Set-Acl -LiteralPath $input -AclObject $acl -ErrorAction Stop
        if($Id -eq 'elevated_plugin_signature_bypass'){
            $pluginSource='C:\ProgramData\KingdomsWSLPE45\lib\Kingdom45Plugin.cs'
            if(-not (Test-Path -LiteralPath $pluginSource -PathType Leaf)){throw 'Fixed benign plugin source missing'}
            $plugin=Join-Path $input 'Kingdom45Plugin.dll'
            Add-Type -TypeDefinition (Get-Content -LiteralPath $pluginSource -Raw -ErrorAction Stop) -Language CSharp -OutputAssembly $plugin -OutputType Library -ErrorAction Stop
            Set-Content -LiteralPath (Join-Path $input 'manifest.txt') -Value 'trusted=false' -Encoding Ascii -ErrorAction Stop
        }
        if($Id -eq 'ntfs_link_redirection'){
            Set-Content -LiteralPath (Join-Path $protected 'proof.txt') -Value 'BASELINE' -Encoding Ascii -ErrorAction Stop
        }
        if($Id -eq 'privileged_file_toctou'){
            Set-Content -LiteralPath (Join-Path $input 'request.txt') -Value 'IDLE' -Encoding Ascii
        }
        if($Id -eq 'privileged_backup_restore_api'){
            Set-Content -LiteralPath (Join-Path $input 'restore.request') -Value 'IDLE' -Encoding Ascii
            Set-Content -LiteralPath (Join-Path $input 'backup.txt') -Value 'BASELINE' -Encoding Ascii
        }
        $source=Get-Content -LiteralPath $template -Raw -ErrorAction Stop
        $source=$source.Replace('__MODE__',$Id).Replace('__SERVICE__',$name).Replace('__ROOT__',$root)
        Add-Type -TypeDefinition $source -Language CSharp -ReferencedAssemblies @('System.ServiceProcess.dll','System.Core.dll') -OutputAssembly $binary -OutputType WindowsApplication -ErrorAction Stop
        New-Service -Name $name -BinaryPathName ('"{0}"' -f $binary) -DisplayName ('Kingdoms WSLPE boundary '+$Id) -StartupType Manual -ErrorAction Stop | Out-Null
        $status=& sc.exe sdset $name "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;LCRPWP;;;$($who.LearnerSid))" 2>&1
        if($LASTEXITCODE -ne 0){throw "Could not set dedicated service start-right: $status"}
        Start-Service -Name $name -ErrorAction Stop
        $service=Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction Stop
        if(-not $service -or $service.State -ne 'Running' -or $service.StartName -ne 'LocalSystem'){
            throw 'Isolated privileged boundary consumer did not start as SYSTEM'
        }
        Write-Output ('WSLPE45_BOUNDARY_APPLIED='+$Id)
    }
    elseif($Action -eq 'reset'){
        if($Id -eq 'ntfs_link_redirection'){
            # A valid learner-created junction is expected in this fixture;
            # detach ONLY its exact owned link before generic reparse checks.
            Remove-Wslpe45OwnedLinkJunction -FixtureRoot $root -LearnerSid $who.LearnerSid
        }
        $root=Assert-Wslpe45OwnedFixture -Number $number -Id $Id
        $service=Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction Stop
        if(-not $service -or -not ([string]$service.PathName).Trim('"').Equals(
            $binary,[StringComparison]::OrdinalIgnoreCase)){
            throw 'Refusing to remove service without exact fixture ownership'
        }
        if($service.State -eq 'Running'){Stop-Service -Name $name -Force -ErrorAction Stop}
        $result=& sc.exe delete $name 2>&1
        if($LASTEXITCODE -ne 0){throw "Owned WSLPE service delete failed: $result"}
        for($i=0;$i -lt 25;$i++){
            if(-not (Get-Service -Name $name -ErrorAction SilentlyContinue)){break}
            Start-Sleep -Milliseconds 400
        }
        if(Get-Service -Name $name -ErrorAction SilentlyContinue){
            throw 'Service still registered after removal; manual recovery required'
        }
        Remove-Wslpe45OwnedFixture -Number $number -Id $Id
        Write-Output ('WSLPE45_BOUNDARY_RESET='+$Id)
    }
    elseif($Stage -eq 'clean'){
        if($service -or (Test-Path -LiteralPath $root)){
            throw 'Standalone boundary fixture has not been cleaned'
        }
        Write-Output ('WSLPE45_BOUNDARY_CLEAN='+$Id)
    }
    else{
        $root=Assert-Wslpe45OwnedFixture -Number $number -Id $Id
        if(-not $service -or $service.StartName -ne 'LocalSystem' -or
           $service.State -ne 'Running' -or $service.ProcessId -le 0){
            throw 'Expected running SYSTEM service missing'
        }
        if(-not ([string]$service.PathName).Trim('"').Equals(
           $binary,[StringComparison]::OrdinalIgnoreCase)){
            throw 'Unexpected privileged service binary'
        }
        if(-not (Test-Path -LiteralPath $binary -PathType Leaf) -or
           -not (Test-Path -LiteralPath $input -PathType Container) -or
           -not (Test-Path -LiteralPath $protected -PathType Container)){
            throw 'Missing owned input, protected sink or consumer binary'
        }
        $acl=(Get-Acl -LiteralPath $input -ErrorAction Stop).Access
        $canWrite=$false
        foreach($ace in $acl){
            $aceSid=$null
            try{$aceSid=$ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value}catch{}
            if($aceSid -eq $who.LearnerSid -and
                $ace.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
                ($ace.FileSystemRights -band [Security.AccessControl.FileSystemRights]::WriteData)){
                $canWrite=$true
            }
        }
        if(-not $canWrite){throw 'Local learner cannot modify request objects'}
        $dacl=(& sc.exe sdshow $name 2>&1 | Out-String)
        if($LASTEXITCODE -ne 0 -or -not $dacl.Contains($who.LearnerSid)){
            throw 'Dedicated SYSTEM service trigger access missing'
        }
        Write-Output ('WSLPE45_BOUNDARY_VULNERABLE_CONFIGURATION='+$Id)
    }
    Write-Output ('WSLPE45_BATCH_STAGE='+$Id+':'+$Stage+':PASS')
}
Export-ModuleMember -Function 'Invoke-Wslpe45Boundary'
