# NORTH Topic 12 - read-only terminal viewer for fixed SYSTEM identity commands.
# Run as NORTH\rickon.stark in a non-elevated PowerShell window BEFORE planting
# the prepared DLL. Only SYSTEM can send data into the local named pipe.
# This viewer cannot send commands, spawn privileged processes or modify the lab.
$ErrorActionPreference = 'Stop'
$pipeName = 'KingdomsTopic12Proof'
$pipe = $null
try {
    $rules = [System.IO.Pipes.PipeSecurity]::new()
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $systemSid = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    $rules.AddAccessRule([System.IO.Pipes.PipeAccessRule]::new(
        $currentUser, [System.IO.Pipes.PipeAccessRights]::ReadWrite, $allow
    ))
    $rules.AddAccessRule([System.IO.Pipes.PipeAccessRule]::new(
        $systemSid, [System.IO.Pipes.PipeAccessRights]::Write, $allow
    ))
    $pipe = [System.IO.Pipes.NamedPipeServerStream]::new(
        $pipeName, [System.IO.Pipes.PipeDirection]::In, 1,
        [System.IO.Pipes.PipeTransmissionMode]::Byte,
        [System.IO.Pipes.PipeOptions]::Asynchronous,
        4096, 4096, $rules
    )

    Write-Host '[NORTH Topic 12] Read-only viewer running as:' -ForegroundColor Cyan
    whoami
    Write-Host 'Waiting for KingdomDllSvc to execute fixed identity checks as SYSTEM...'
    Write-Host 'Leave this PowerShell window open and plant KingdomHelper.dll from the other Rickon window.'

    $pending = $pipe.BeginWaitForConnection($null, $null)
    if (-not $pending.AsyncWaitHandle.WaitOne(150000)) {
        throw 'The scheduled service did not connect within 150 seconds. No SYSTEM command execution has been verified.'
    }
    $pipe.EndWaitForConnection($pending)
    $reader = [System.IO.StreamReader]::new($pipe, [System.Text.Encoding]::Default)
    $received = $reader.ReadToEnd()
    if (-not $received.Contains('=== End of SYSTEM command proof ===')) {
        throw 'The SYSTEM command proof was interrupted or incomplete.'
    }
    Write-Host ''
    Write-Host $received -ForegroundColor Green
    Write-Host 'The output above came from fixed commands launched by the DLL under the service token.' -ForegroundColor Cyan
    Write-Host 'This window is still Rickon, not a new interactive SYSTEM shell.'
}
finally {
    if ($pipe) { $pipe.Dispose() }
}
