# Three distinct standalone service-consumer LPE source candidates.
# No import-time effects; only an exact scoped action mutates WSLPE-WS01.
Set-StrictMode -Version Latest

function Invoke-Wslpe45ServiceConsumer {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet('privileged_service_config_injection','privileged_updater_hijack','privileged_argument_injection')]
        [string]$Id,
        [Parameter(Mandatory=$true)]
        [ValidateSet('apply','reset','validate')]
        [string]$Action,
        [Parameter(Mandatory=$true)]
        [ValidateSet('apply','vulnerable','reset','clean','reapply','revulnerable')]
        [string]$Stage
    )
    $ErrorActionPreference='Stop'
    Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeFixture.psm1' -Force -ErrorAction Stop
    $who=Assert-Wslpe45Identity
    $number=@{
        privileged_service_config_injection=23
        privileged_updater_hijack=24
        privileged_argument_injection=41
    }[$Id]
    if($number -notin @(23,24,41)) { throw 'Unexpected service consumer identity' }
    $root=Get-Wslpe45FixturePath -Id $Id
    $inbox=Join-Path $root 'inbox'
    $request=Join-Path $inbox 'request.txt'
    $binary=Join-Path $root 'Kingdom45Consumer.exe'
    $serviceName=if($number -eq 23){'Kingdom45ConfigSvc'}elseif($number -eq 24){'Kingdom45UpdateSvc'}else{'Kingdom45ArgsSvc'}
    $template='C:\ProgramData\KingdomsWSLPE45\lib\KingdomServiceConsumer.cs'
    $existing=Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction Stop

    if($Action -eq 'apply') {
        if($existing) { throw 'Refusing service collision; dedicated WSLPE name already exists' }
        if(-not (Test-Path -LiteralPath $template -PathType Leaf)) {
            throw 'Dedicated service CSharp source missing'
        }
        $root=New-Wslpe45OwnedFixture -Number $number -Id $Id
        New-Item -ItemType Directory -Path $inbox -ErrorAction Stop | Out-Null
        Set-Content -LiteralPath $request -Value 'baseline' -Encoding Ascii -ErrorAction Stop
        $learner=[Security.Principal.SecurityIdentifier]::new($who.LearnerSid)
        $acl=Get-Acl -LiteralPath $inbox -ErrorAction Stop
        $rights=[Security.AccessControl.FileSystemRights]::Modify
        $inherit=[Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
        $prop=[Security.AccessControl.PropagationFlags]::None
        $allow=[Security.AccessControl.AccessControlType]::Allow
        $rule=[Security.AccessControl.FileSystemAccessRule]::new(
            $learner,$rights,$inherit,$prop,$allow
        )
        $acl.AddAccessRule($rule) | Out-Null
        Set-Acl -LiteralPath $inbox -AclObject $acl -ErrorAction Stop

        $source=(Get-Content -LiteralPath $template -Raw -ErrorAction Stop)
        foreach($pair in @(
            @('__MODE__',$Id),@('__ROOT__',$root),@('__SERVICE__',$serviceName)
        )) {
            $source=$source.Replace($pair[0],$pair[1])
        }
        Add-Type -TypeDefinition $source -Language CSharp -ReferencedAssemblies 'System.ServiceProcess.dll' -OutputAssembly $binary -OutputType WindowsApplication -ErrorAction Stop
        New-Service -Name $serviceName -DisplayName ('Standalone WSLPE ' + $Id) -BinaryPathName ('"{0}"' -f $binary) -StartupType Manual -ErrorAction Stop | Out-Null
        # Learner may query/start/stop this one custom consumer, never change
        # service configuration or affect the SCM security descriptor.
        $sd="D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;LCRPWP;;;$($who.LearnerSid))"
        $response=& sc.exe sdset $serviceName $sd 2>&1
        if($LASTEXITCODE -ne 0) { throw "Could not configure bounded consumer service DACL: $response" }
        Write-Output ('WSLPE45_SERVICE_CONSUMER_APPLIED=' + $Id)
    }
    elseif($Action -eq 'reset') {
        $root=Assert-Wslpe45OwnedFixture -Number $number -Id $Id
        $existing=Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction Stop
        if(-not $existing) { throw 'Owned service missing before reset' }
        if(-not ([string]$existing.PathName).Trim('"').Equals($binary,[StringComparison]::OrdinalIgnoreCase)) {
            throw 'Refusing to stop or remove an unowned service'
        }
        if($existing.State -eq 'Running') {
            Stop-Service -Name $serviceName -Force -ErrorAction Stop
        }
        $response=& sc.exe delete $serviceName 2>&1
        if($LASTEXITCODE -ne 0) { throw "Dedicated consumer service deletion failed: $response" }
        for($attempt=0;$attempt -lt 20;$attempt++) {
            if(-not (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Milliseconds 500
        }
        if(Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
            throw 'SCM has not removed our consumer service yet'
        }
        Remove-Wslpe45OwnedFixture -Number $number -Id $Id
        Write-Output ('WSLPE45_SERVICE_CONSUMER_RESET=' + $Id)
    }
    elseif($Stage -eq 'clean') {
        if($existing -or (Test-Path -LiteralPath $root)) { throw 'Fixture not clean after reset' }
        Write-Output ('WSLPE45_SERVICE_CONSUMER_CLEAN=' + $Id)
    }
    else {
        $root=Assert-Wslpe45OwnedFixture -Number $number -Id $Id
        $existing=Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction Stop
        if(-not $existing -or $existing.StartName -ne 'LocalSystem') {
            throw 'Dedicated privileged consumer is absent or not SYSTEM'
        }
        if(-not ([string]$existing.PathName).Trim('"').Equals($binary,[StringComparison]::OrdinalIgnoreCase)) {
            throw 'Unexpected service binary ownership'
        }
        if(-not (Test-Path -LiteralPath $binary -PathType Leaf) -or
           -not (Test-Path -LiteralPath $request -PathType Leaf)) {
            throw 'Consumer executable or learner-controlled request is missing'
        }
        $access=@((Get-Acl -LiteralPath $inbox -ErrorAction Stop).Access)
        $learnerMayModify=$false
        foreach($ace in $access) {
            $aceSid=$null
            try{$aceSid=$ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value}catch{}
            if($aceSid -eq $who.LearnerSid -and
               $ace.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
               ($ace.FileSystemRights -band [Security.AccessControl.FileSystemRights]::WriteData)) {
                $learnerMayModify=$true
            }
        }
        if(-not $learnerMayModify) { throw 'Learner cannot edit service request input' }
        $sd=(& sc.exe sdshow $serviceName 2>&1 | Out-String)
        if($LASTEXITCODE -ne 0 -or -not $sd.Contains($who.LearnerSid)) {
            throw 'Learner cannot trigger custom privileged service'
        }
        Write-Output ('WSLPE45_SERVICE_CONSUMER=VULNERABLE_CONFIGURATION:' + $Id)
    }
    Write-Output ('WSLPE45_BATCH_STAGE='+$Id+':'+$Stage+':PASS')
}

Export-ModuleMember -Function 'Invoke-Wslpe45ServiceConsumer'
