# Run ONLY inside the isolated, disposable Windows CI VM, elevated PowerShell.
# This never belongs on a NORTH, PURPLE, KINGDOMS or WSLPE guest.
# It configures the CI fixture; it does not claim native WinRS readiness.
[CmdletBinding()]
param([switch]$ConfirmDisposableRunner)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $ConfirmDisposableRunner) {
    throw 'Explicit -ConfirmDisposableRunner required'
}
if ($env:COMPUTERNAME -cne 'NK-WINRS-CI' -or
    $env:COMPUTERNAME -in @('WINTERFELL','KINGSLANDING','CASTELBLACK','WS01','WSLPE-WS01')) {
    throw 'Refusing to configure a non-CI or training guest'
}
$computer = Get-CimInstance Win32_ComputerSystem
if ($computer.PartOfDomain) { throw 'Disposable CI runner must not be domain joined' }
$principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Elevated PowerShell required on disposable CI guest'
}
if ($PSVersionTable.PSVersion.Major -ne 5) {
    throw 'Use Windows PowerShell 5.1, not PowerShell Core'
}

$svc = Get-Service WinRM
if ($svc.Status -ne 'Running') { Start-Service WinRM -ErrorAction Stop }

$listeners = @(Get-ChildItem WSMan:\localhost\Listener | Where-Object {
    $_.Keys -contains 'Transport=HTTPS'
})
if ($listeners.Count -gt 1) { throw 'Ambiguous HTTPS WinRM listeners; no changes applied' }
if ($listeners.Count -eq 1 -and
    (Get-Item ($listeners[0].PSPath + '\Port')).Value -ne '5986') {
    throw 'Existing HTTPS WinRM listener uses unexpected port'
}

# This short-lived certificate is scoped ONLY to the disposable CI VM.
# Do not weaken certificate-expiry or WinRS authentication checks.
$cert = New-SelfSignedCertificate -DnsName 'localhost' `
    -CertStoreLocation Cert:\LocalMachine\My `
    -NotAfter ((Get-Date).AddDays(7)) -ErrorAction Stop
$selector = @{Address='*';Transport='HTTPS'}
$newValues = @{Hostname='localhost';CertificateThumbprint=$cert.Thumbprint}
if ($listeners.Count -eq 0) {
    $null = New-WSManInstance winrm/config/Listener `
        -SelectorSet $selector -ValueSet $newValues -ErrorAction Stop
} else {
    $null = Set-WSManInstance winrm/config/Listener `
        -SelectorSet $selector -ValueSet $newValues -ErrorAction Stop
}
Restart-Service WinRM -Force -ErrorAction Stop

$active = @(Get-ChildItem WSMan:\localhost\Listener | Where-Object {
    $_.Keys -contains 'Transport=HTTPS'
})
if ($active.Count -ne 1) { throw 'HTTPS listener postcheck failed' }
$thumb = [string](Get-Item ($active[0].PSPath + '\CertificateThumbprint')).Value
if ($thumb -cne $cert.Thumbprint) { throw 'HTTPS listener certificate binding mismatch' }
if (-not (Test-NetConnection 127.0.0.1 -Port 5986 -InformationLevel Quiet)) {
    throw 'Prepared HTTPS port is not reachable on loopback'
}
Write-Output 'NORTH_PRIVATE_WINRS_RUNNER_TLS_PREPARED=PASS'
Write-Output 'This is only TLS/listener preflight, NOT a native WinRS shell acceptance.'
