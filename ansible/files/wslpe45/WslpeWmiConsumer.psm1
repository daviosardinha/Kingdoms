# Native WMI permanent event-consumer script trust exercise, WSLPE only.
# Windows root\subscription ACLs are NEVER relaxed. The intentionally weak
# permission is on the dedicated lab consumer script, not the WMI namespace.
Set-StrictMode -Version Latest

function Invoke-Wslpe45WmiConsumer {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateSet('apply','validate','reset')][string]$Action,
        [Parameter(Mandatory=$true)][ValidateSet('apply','vulnerable','reset','clean','reapply','revulnerable')][string]$Stage
    )
    $ErrorActionPreference='Stop'
    Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeFixture.psm1' -Force -ErrorAction Stop
    $who=Assert-Wslpe45Identity
    $id='wmi_permanent_consumer_hijack'
    $root=Get-Wslpe45FixturePath -Id $id
    $inbox=Join-Path $root 'inbox'
    $script=Join-Path $inbox 'consumer.ps1'
    $wake=Join-Path $root 'Kingdom45WmiWake.exe'
    $source='C:\ProgramData\KingdomsWSLPE45\lib\Kingdom45WmiWake.cs'
    $namespace='root\subscription'
    $filterName='Kingdom45WmiFilter37'
    $consumerName='Kingdom45WmiConsumer37'
    $filter=Get-WmiObject -Namespace $namespace -Class '__EventFilter' -Filter "Name='$filterName'" -ErrorAction Stop
    $consumer=Get-WmiObject -Namespace $namespace -Class 'CommandLineEventConsumer' -Filter "Name='$consumerName'" -ErrorAction Stop
    $binding=@(Get-WmiObject -Namespace $namespace -Class '__FilterToConsumerBinding' -ErrorAction Stop | Where-Object {
        $_.Filter -match $filterName -or $_.Consumer -match $consumerName
    })
    if($Action -eq 'apply'){
        if($filter -or $consumer -or $binding.Count -gt 0){
            throw 'WMI permanent subscription collision; refusing adoption'
        }
        if(-not (Test-Path -LiteralPath $source -PathType Leaf)){throw 'Dedicated WMI wake source missing'}
        $root=New-Wslpe45OwnedFixture -Number 37 -Id $id
        New-Item -ItemType Directory -Path $inbox -ErrorAction Stop | Out-Null
        $code=Get-Content -LiteralPath $source -Raw -ErrorAction Stop
        Add-Type -TypeDefinition $code -Language CSharp -OutputAssembly $wake -OutputType ConsoleApplication -ErrorAction Stop
        $userSid=[Security.Principal.SecurityIdentifier]::new($who.LearnerSid)
        $acl=Get-Acl -LiteralPath $inbox -ErrorAction Stop
        $rule=[Security.AccessControl.FileSystemAccessRule]::new(
            $userSid,[Security.AccessControl.FileSystemRights]::Modify,
            [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit',
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule) | Out-Null
        Set-Acl -LiteralPath $inbox -AclObject $acl -ErrorAction Stop
        $wakeAcl=Get-Acl -LiteralPath $wake -ErrorAction Stop
        $wakeRule=[Security.AccessControl.FileSystemAccessRule]::new(
            $userSid,[Security.AccessControl.FileSystemRights]::ReadAndExecute,
            [Security.AccessControl.AccessControlType]::Allow)
        $wakeAcl.AddAccessRule($wakeRule) | Out-Null
        Set-Acl -LiteralPath $wake -AclObject $wakeAcl -ErrorAction Stop
        $payload=@'
$ErrorActionPreference = 'Stop'
$destination = 'C:\ProgramData\KingdomsWSLPE45\fixtures\wmi_permanent_consumer_hijack\proof.txt'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
[IO.File]::WriteAllText($destination, 'WSLPE45_WMI_CONSUMER_PROOF=' + $identity)
'@
        Set-Content -LiteralPath $script -Value $payload -Encoding UTF8 -ErrorAction Stop
        $powershell=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $cmd=('"{0}" -NoProfile -NonInteractive -File "{1}"' -f $powershell,$script)
        # Narrow namespace objects, all created by the same privileged owner
        # so CreatorSID satisfies WMI subscription security requirements.
        $filter=Set-WmiInstance -Namespace $namespace -Class '__EventFilter' -Arguments @{
            Name=$filterName
            QueryLanguage='WQL'
            Query="SELECT * FROM Win32_ProcessStartTrace WHERE ProcessName='Kingdom45WmiWake.exe'"
            EventNamespace='root\cimv2'
        } -ErrorAction Stop
        $consumer=Set-WmiInstance -Namespace $namespace -Class 'CommandLineEventConsumer' -Arguments @{
            Name=$consumerName
            CommandLineTemplate=$cmd
        } -ErrorAction Stop
        $bind=Set-WmiInstance -Namespace $namespace -Class '__FilterToConsumerBinding' -Arguments @{
            Filter=$filter
            Consumer=$consumer
        } -ErrorAction Stop
        if(-not $bind){throw 'Dedicated WMI event binding creation failed'}
        Write-Output 'WSLPE45_WMI_PERMANENT_CONSUMER_APPLIED'
    }
    elseif($Action -eq 'reset'){
        $root=Assert-Wslpe45OwnedFixture -Number 37 -Id $id
        if(-not $filter -or -not $consumer -or $binding.Count -ne 1){
            throw 'WMI permanent subscription changed unexpectedly; manual recovery'
        }
        $expected=$consumer.CommandLineTemplate
        if(-not ([string]$expected).Contains($script)){
            throw 'Refusing deletion of foreign WMI event consumer'
        }
        $binding[0].Delete() | Out-Null
        $filter.Delete() | Out-Null
        $consumer.Delete() | Out-Null
        $check=Get-WmiObject -Namespace $namespace -Class 'CommandLineEventConsumer' -Filter "Name='$consumerName'" -ErrorAction Stop
        if($check){throw 'WMI consumer still exists after targeted cleanup'}
        Remove-Wslpe45OwnedFixture -Number 37 -Id $id
        Write-Output 'WSLPE45_WMI_PERMANENT_CONSUMER_RESET'
    }
    elseif($Stage -eq 'clean'){
        if($filter -or $consumer -or $binding.Count -gt 0 -or (Test-Path -LiteralPath $root)){
            throw 'Dedicated WMI subscription or owned fixture remains'
        }
        Write-Output 'WSLPE45_WMI_CONSUMER_CLEAN'
    }
    else{
        $root=Assert-Wslpe45OwnedFixture -Number 37 -Id $id
        if(-not $filter -or -not $consumer -or $binding.Count -ne 1){
            throw 'WMI permanent subscription missing'
        }
        if(-not ([string]$consumer.CommandLineTemplate).Contains($script)){
            throw 'WMI consumer command no longer points at dedicated input'
        }
        if(-not (Test-Path -LiteralPath $script -PathType Leaf) -or
           -not (Test-Path -LiteralPath $wake -PathType Leaf)){
            throw 'Learner-controlled WMI script and trigger executable missing'
        }
        $acl=(Get-Acl -LiteralPath $inbox -ErrorAction Stop).Access
        $writable=$false
        foreach($ace in $acl){
            $sid=$null
            try{$sid=$ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value}catch{}
            if($sid -eq $who.LearnerSid -and $ace.AccessControlType -eq 'Allow' -and
               ($ace.FileSystemRights -band [Security.AccessControl.FileSystemRights]::WriteData)){
                $writable=$true
            }
        }
        if(-not $writable){throw 'Dedicated script directory not learner-writable'}
        Write-Output 'WSLPE45_WMI_SUBSCRIPTION_CONFIGURED_NOT_EXPLOIT_PROVEN'
    }
    Write-Output ('WSLPE45_BATCH_STAGE='+$id+':'+$Stage+':PASS')
}
Export-ModuleMember -Function 'Invoke-Wslpe45WmiConsumer'
