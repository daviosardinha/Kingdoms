$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'KINGSLANDING') {
    throw "Unexpected remote DC identity $env:COMPUTERNAME"
}

$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if (-not $computer.PartOfDomain -or
    $computer.Domain -ine 'sevenkingdoms.local' -or
    $computer.DomainRole -ne 5) {
    throw 'KINGSLANDING root PDC domain identity unhealthy'
}

foreach ($name in @('NTDS','DNS','ADWS','Netlogon','Kdc','W32Time')) {
    if ((Get-Service -Name $name -ErrorAction Stop).Status -ne 'Running') {
        throw "KINGSLANDING service $name not running"
    }
}

foreach ($name in @('SYSVOL','NETLOGON')) {
    if (-not (Get-SmbShare -Name $name -ErrorAction SilentlyContinue)) {
        throw "KINGSLANDING missing $name share"
    }
}

$records = @(Resolve-DnsName '_ldap._tcp.dc._msdcs.sevenkingdoms.local' -Type SRV -Server 127.0.0.1 -ErrorAction Stop |
    Where-Object { $_.NameTarget.TrimEnd('.') -ieq 'kingslanding.sevenkingdoms.local' })
if ($records.Count -lt 1) {
    throw 'KINGSLANDING root-domain LDAP SRV advertisement missing'
}

$locator = @(& nltest.exe '/dsgetdc:sevenkingdoms.local' /timeserv /force 2>&1)
if ($LASTEXITCODE -ne 0 -or ($locator -join ' ') -notmatch '10\.4\.20\.10') {
    throw 'KINGSLANDING local TIMESERV discovery failed'
}

$source = (& w32tm.exe /query /source 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $source) {
    throw 'KINGSLANDING W32Time source unavailable'
}
$status = (& w32tm.exe /query /status 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or -not $status.Trim()) {
    throw 'KINGSLANDING W32Time status unavailable'
}

# Root PDC may use a local source; it must advertise time,
# not follow its child controller's time hierarchy.
Write-Output 'NORTH_PARENT_DC_AD_HEALTH=PASS host=KINGSLANDING'
