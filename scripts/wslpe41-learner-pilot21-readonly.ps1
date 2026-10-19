# WSLPE41 learner acceptance, scenario #21 — read-only preconditions only.
# Execute from an ordinary PowerShell console signed in as .\lpe.trainee
# on the independently verified, offline disposable VMware clone.
# This DOES NOT reconfigure, run or modify any scheduled task.
$ErrorActionPreference = 'Stop'
$taskName = 'Kingdom45DefinitionTask'
$root = 'C:\ProgramData\KingdomsWSLPE45\fixtures\scheduled_task_definition_acl'
$expectedApp = Join-Path $root 'Kingdom45Task21.exe'
$stage = 'LEARNER_BOUNDARY'

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $learner = Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
    $machine = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $adapters = @(Get-NetAdapter -ErrorAction Stop | Where-Object { $_.Status -eq 'Up' })
    if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain -or
        $os.Caption -notmatch 'Windows 10' -or [int]$os.ProductType -ne 1 -or
        $identity.User.Value -cne $learner.SID.Value -or -not $learner.Enabled -or
        $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or
        $adapters.Count -ne 0) {
        throw 'Learner, guest or disconnected network boundary mismatch'
    }
    Write-Output 'WSLPE41_21_LEARNER_BOUNDARY=PASS'

    # The owned marker and binary deliberately live inside an Administrators/
    # SYSTEM-only fixture directory. A learner must NOT be granted file access
    # just to satisfy the acceptance preflight. Ownership was checked with
    # privileged deployment evidence and needs a separate operator audit
    # on this clone; the learner only observes the dedicated task object.
    Write-Output 'WSLPE41_21_FIXTURE_OWNERSHIP=OPERATOR_CHECK_REQUIRED'

    $stage = 'SYSTEM_TASK'
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    if ($task.TaskPath -cne '\' -or
        $task.Principal.UserId -notin @('SYSTEM','S-1-5-18') -or
        @($task.Actions).Count -ne 1 -or
        -not [string]::Equals([string]$task.Actions[0].Execute,
            $expectedApp,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Dedicated SYSTEM task action or identity differs'
    }
    Write-Output 'WSLPE41_21_SYSTEM_TASK=PASS'

    $stage = 'LEARNER_TASK_ACL'
    $scheduler = New-Object -ComObject 'Schedule.Service'
    $scheduler.Connect()
    $registered = $scheduler.GetFolder('\').GetTask($taskName)
    $sddl = [string]$registered.GetSecurityDescriptor(4)
    if ([string]::IsNullOrWhiteSpace($sddl)) {
        throw 'Learner cannot read exact task security descriptor'
    }
    $security = [Security.AccessControl.RawSecurityDescriptor]::new($sddl)
    $found = $false
    foreach ($ace in $security.DiscretionaryAcl) {
        if ($ace.SecurityIdentifier.Value -ceq $identity.User.Value -and
            $ace.AceType -eq [Security.AccessControl.AceType]::AccessAllowed -and
            ($ace.AccessMask -band 0x001f01ff) -eq 0x001f01ff) {
            $found = $true
        }
    }
    if (-not $found) {
        throw 'Expected scoped learner task-object DACL permission absent'
    }
    Write-Output 'WSLPE41_21_LEARNER_TASK_ACL=PASS'
    Write-Output 'WSLPE41_21_LEARNER_TASK_PREFLIGHT=PASS'
    Write-Output 'WSLPE41_21_READONLY_PREFLIGHT=PASS'
    Write-Output 'WSLPE41_21_LEARNER_EXPLOITATION=NOT_TESTED'
}
catch {
    Write-Output 'WSLPE41_21_READONLY_PREFLIGHT=BLOCKED'
    Write-Output ('WSLPE41_21_FAILED_STAGE=' + $stage)
    # Report the error category only; never emit credentials, task descriptors, or tokens.
    Write-Output ('WSLPE41_21_FAILURE_TYPE=' + $_.Exception.GetType().Name)
    Write-Output 'WSLPE41_21_LEARNER_EXPLOITATION=NOT_TESTED'
    # Throw instead of 'exit': an interactive learner console must stay open.
    # Noninteractive callers still receive a failure outcome, not a false PASS.
    throw ('WSLPE41_21_READONLY_PREFLIGHT=BLOCKED at ' + $stage)
}
