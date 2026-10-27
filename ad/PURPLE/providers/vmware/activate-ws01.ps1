# PURPLE WS01 uses the same Windows 10 Enterprise Evaluation grace-period
# maintenance as KINGDOMS/NORTH (ansible/roles/settings/eval_rearm).
# No product key is required, stored, or passed.
param([switch]$Verify)
$ErrorActionPreference = 'Stop'

$license = Get-CimInstance SoftwareLicensingProduct -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like 'Windows*' -and
        $_.PartialProductKey -and
        $_.Description -match 'TIMEBASED_EVAL'
    } |
    Select-Object -First 1

if (-not $license) {
    Write-Output 'PURPLE_WS01_EVAL=NOT_TIMEBASED_EVAL'
    return
}

$minutes = [int64]$license.GracePeriodRemaining
Write-Output "PURPLE_WS01_EVAL_GRACE_MINUTES=$minutes"

if ($Verify) {
    if ($minutes -le 0) {
        throw "PURPLE WS01 Windows evaluation is still expired after reboot (status=$($license.LicenseStatus))"
    }
    Write-Output 'PURPLE_WS01_EVAL_READY=PASS'
    return
}

if ($minutes -gt 0) {
    Write-Output 'PURPLE_WS01_EVAL=READY'
    return
}

# Same conditional rearm used by the existing KINGDOMS/NORTH Ansible role.
$stdout = Join-Path $env:TEMP 'purple-ws01-slmgr-rearm.out'
$stderr = Join-Path $env:TEMP 'purple-ws01-slmgr-rearm.err'
Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
$process = Start-Process -FilePath "$env:SystemRoot\System32\cscript.exe" `
    -ArgumentList @('//NoLogo', "$env:SystemRoot\System32\slmgr.vbs", '/rearm') `
    -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

$out = if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout -Raw } else { '' }
$err = if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Raw } else { '' }
if ($process.ExitCode -ne 0) {
    throw "PURPLE WS01 evaluation rearm failed with exit code $($process.ExitCode): $out $err"
}
if (($out + $err) -notmatch '(?i)success|restart|rearm') {
    throw "PURPLE WS01 evaluation rearm returned unexpected output: $out $err"
}
Write-Output 'PURPLE_WS01_EVAL=REARMED'
# Vagrant's reboot: true waits for Windows/WinRM to return before continuing.
