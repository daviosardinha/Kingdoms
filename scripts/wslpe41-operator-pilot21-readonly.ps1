# WSLPE41 scenario #21: privileged, read-only fixture ownership verification.
# Run ONLY on the disconnected, disposable learner clone in elevated PowerShell.
# This script never changes NTFS ACLs, scheduled tasks or fixture contents.
$ErrorActionPreference='Stop'
$stage='OPERATOR_BOUNDARY'
try {
    $who=[Security.Principal.WindowsIdentity]::GetCurrent()
    $principal=[Security.Principal.WindowsPrincipal]::new($who)
    $machine=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $os=Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $learner=Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
    $admins=Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
    $members=@(Get-LocalGroupMember -Group $admins.Name -ErrorAction Stop)
    $adapters=@(Get-NetAdapter -ErrorAction Stop | Where-Object {$_.Status -eq 'Up'})
    if($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain -or
       [int]$os.ProductType -ne 1 -or $os.Caption -notmatch 'Windows 10' -or
       -not $learner.Enabled -or $adapters.Count -ne 0 -or
       -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or
       @($members | Where-Object {$_.SID.Value -ceq $learner.SID.Value}).Count -ne 0) {
       throw 'Wrong offline operator context, guest or learner boundary'
    }
    Write-Output 'WSLPE41_21_OPERATOR_BOUNDARY=PASS'

    $stage='OWNED_MARKER'
    $root='C:\ProgramData\KingdomsWSLPE45\fixtures\scheduled_task_definition_acl'
    $marker=Join-Path $root '.kingdoms-owned.json'
    $binary=Join-Path $root 'Kingdom45Task21.exe'
    foreach($path in @('C:\ProgramData\KingdomsWSLPE45',
                       'C:\ProgramData\KingdomsWSLPE45\fixtures',
                       $root,$marker,$binary)) {
        $item=Get-Item -LiteralPath $path -Force -ErrorAction Stop
        if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Unexpected reparse point inside scoped fixture'
        }
    }
    $owned=Get-Content -LiteralPath $marker -Raw -ErrorAction Stop |
        ConvertFrom-Json -ErrorAction Stop
    if($owned.schema -cne 'kingdoms.wslpe.fixture-owner.v1' -or
       $owned.machine -cne 'WSLPE-WS01' -or
       [int]$owned.number -ne 21 -or
       $owned.id -cne 'scheduled_task_definition_acl' -or
       $owned.learner_sid -cne $learner.SID.Value) {
        throw 'Protected #21 marker does not match dedicated fixture'
    }
    if(-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
        throw 'Dedicated task binary missing'
    }
    Write-Output 'WSLPE41_21_OWNED_MARKER=PASS'

    $stage='FIXTURE_NTFS'
    $acl=Get-Acl -LiteralPath $root -ErrorAction Stop
    $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
    $allowed=@('S-1-5-18','S-1-5-32-544')
    if(-not $acl.AreAccessRulesProtected) {
        throw 'Dedicated fixture root unexpectedly inherits NTFS ACLs'
    }
    foreach($rule in $rules) {
        if($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
           $rule.IdentityReference.Value -notin $allowed) {
            throw 'Unexpected nonprivileged allow ACE on dedicated fixture root'
        }
    }
    foreach($sid in $allowed) {
        if(@($rules | Where-Object {
            $_.IdentityReference.Value -ceq $sid -and
            $_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
            ($_.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq
              [Security.AccessControl.FileSystemRights]::FullControl
        }).Count -lt 1) {
            throw 'Expected Administrators/SYSTEM full-control ACE missing'
        }
    }
    Write-Output 'WSLPE41_21_PROTECTED_NTFS=PASS'
    Write-Output 'WSLPE41_21_PRIVILEGED_READONLY_AUDIT=PASS'
    Write-Output 'WSLPE41_21_LEARNER_EXPLOITATION=NOT_TESTED'
}
catch {
    Write-Output 'WSLPE41_21_PRIVILEGED_READONLY_AUDIT=BLOCKED'
    Write-Output ('WSLPE41_21_FAILED_STAGE=' + $stage)
    Write-Output ('WSLPE41_21_FAILURE_TYPE=' + $_.Exception.GetType().Name)
    Write-Output 'WSLPE41_21_LEARNER_EXPLOITATION=NOT_TESTED'
    throw ('WSLPE41_21_PRIVILEGED_READONLY_AUDIT=BLOCKED at ' + $stage)
}
