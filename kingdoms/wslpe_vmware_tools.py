"""VMware Tools MSI repair for the native, isolated WSLPE workgroup guest.

Reuses KINGDOMS VmwareProvider's ISO mounting, forwarded WinRM transport,
readiness polling and reboot handling. This supplies only a narrow WSLPE
PowerShell setup procedure for the VGAuth file-sharing conflict observed in
fresh Windows 10 installs. It never touches VMware networks, vagrant state,
NORTH, or any LPE fixture.
"""

WSLPE_VMTOOLS_SETUP = r"""
$ErrorActionPreference = 'Stop'
$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $computer.PartOfDomain) {
    throw 'WSLPE_VMTOOLS_WRONG_GUEST'
}
$svc = Get-Service -Name VMTools -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') {
    Write-Output 'GOAD_VMTOOLS_INSTALL_EXIT=0'
    return
}
# Use whichever genuine VMware Tools ISO drive was mounted by the
# existing provider. Do not assume drive D: or download a new installer.
$deadline = (Get-Date).AddSeconds(90)
$setup = $null
while ((Get-Date) -lt $deadline -and -not $setup) {
    $setup = Get-CimInstance Win32_LogicalDisk |
        Where-Object { $_.DriveType -eq 5 -and $_.VolumeName -eq 'VMware Tools' } |
        ForEach-Object {
            $candidate = "$($_.DeviceID)\setup.exe"
            if (Test-Path $candidate) { $candidate }
        } | Select-Object -First 1
    if (-not $setup) { Start-Sleep -Seconds 2 }
}
if (-not $setup) { throw 'WSLPE_VMTOOLS_ISO_NOT_FOUND' }

# A fresh guest may retain VGAuthService while its VMTools core service is
# missing. The MSI VM_SecureVGAuthDirs custom action must scrub an alias/log
# directory; an in-use VGAuth logfile caused 0x80070020 -> MSI 1603.
# Stop only the existing VGAuth service and always attempt to restore it.
$vg = Get-Service -Name VGAuthService -ErrorAction SilentlyContinue
$wasRunning = $null -ne $vg -and $vg.Status -eq 'Running'
try {
    if ($wasRunning) {
        Stop-Service -Name VGAuthService -ErrorAction Stop
        (Get-Service VGAuthService -ErrorAction Stop).WaitForStatus(
            'Stopped', [TimeSpan]::FromSeconds(30)
        )
    }
    $p = Start-Process -FilePath $setup -ArgumentList '/S','/v"/qn REBOOT=ReallySuppress"' -Wait -PassThru
    Write-Output "GOAD_VMTOOLS_INSTALL_EXIT=$($p.ExitCode)"
    if ($p.ExitCode -notin @(0, 3010)) {
        throw "WSLPE_VMTOOLS_INSTALL_FAILED=$($p.ExitCode)"
    }
}
finally {
    if ($wasRunning) {
        $current = Get-Service -Name VGAuthService -ErrorAction SilentlyContinue
        if ($current -and $current.Status -ne 'Running') {
            Start-Service -Name VGAuthService -ErrorAction Stop
            (Get-Service VGAuthService -ErrorAction Stop).WaitForStatus(
                'Running', [TimeSpan]::FromSeconds(30)
            )
        }
    }
}
"""
