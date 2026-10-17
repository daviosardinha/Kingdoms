# Five standalone-only IPC/application/file-race/NTFS-link attack fixtures.
Set-StrictMode -Version Latest

function Invoke-Wslpe45Boundary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet('named_pipe_authorization','privileged_loopback_http_authz','privileged_file_toctou','privileged_backup_restore_api','ntfs_link_redirection')]
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
