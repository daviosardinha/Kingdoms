# PURPLE-WS01: activate Windows during first Vagrant provisioning.
# The product key is supplied by the operator at runtime, never committed.
$ErrorActionPreference = 'Stop'

$key = $env:PURPLE_WS01_PRODUCT_KEY
if ([string]::IsNullOrWhiteSpace($key)) {
    throw 'PURPLE-WS01 activation requires PURPLE_WS01_PRODUCT_KEY before installation. No license is stored in Git.'
}
$key = $key.Trim().ToUpperInvariant()
if ($key -notmatch '^[A-Z0-9]{5}(-[A-Z0-9]{5}){4}$') {
    throw 'PURPLE-WS01 product key format is invalid (expected five groups of five characters).'
}

$slmgr = Join-Path $env:SystemRoot 'System32\slmgr.vbs'
function Invoke-Slmgr([string]$operation, [string]$productKey = '') {
    if ($productKey) {
        # Never write the key or slmgr output to the provisioner log.
        $null = & cscript.exe //nologo $slmgr $operation $productKey 2>&1
    } else {
        $null = & cscript.exe //nologo $slmgr $operation 2>&1
    }
    if ($LASTEXITCODE -ne 0) {
        throw "PURPLE-WS01 Windows activation step $operation failed. Check edition and license compatibility inside the guest."
    }
}
try {
    Invoke-Slmgr '/ipk' $key
} finally {
    Remove-Item Env:\PURPLE_WS01_PRODUCT_KEY -ErrorAction SilentlyContinue
    $key = $null
}
Invoke-Slmgr '/ato'

# slmgr may return before the Windows licensing service reports the result.
$deadline = (Get-Date).AddSeconds(90)
$activated = $false
while ((Get-Date) -lt $deadline) {
    $windows = Get-CimInstance SoftwareLicensingProduct -Filter "ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f'" |
        Where-Object { $_.PartialProductKey -and $_.LicenseStatus -eq 1 }
    if ($windows) {
        $activated = $true
        break
    }
    Start-Sleep -Seconds 5
}
if (-not $activated) {
    throw 'PURPLE-WS01 Windows activation was not confirmed. Check that the product key matches the installed edition and the activation service is reachable.'
}
Write-Output 'PURPLE_WS01_ACTIVATION_CONFIRMED'
# Vagrant shell provisioner handles the subsequent reboot and communicator wait.
