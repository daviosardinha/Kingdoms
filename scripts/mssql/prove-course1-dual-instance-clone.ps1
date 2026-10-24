#Requires -RunAsAdministrator
# Kingdoms: run ONLY inside an isolated, disposable full clone of CASTELBLACK.
[CmdletBinding()]
param([switch]$CloneConfirmed)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if (-not $CloneConfirmed) {throw 'Pass -CloneConfirmed only inside a disposable clone.'}
if ($env:COMPUTERNAME -ne 'CASTELBLACK') {throw 'Not a CASTELBLACK clone.'}
if (@(Get-NetAdapter | Where-Object {$_.Status -eq 'Up'}).Count -gt 0) {
    throw 'ABORT: active NIC detected. Disconnect ALL clone adapters in VMware.'
}
$setup='C:\setup\mssql\media\SQLEXPRADV_2019\setup.exe'
if (-not (Test-Path $setup)) {throw 'Offline SQL Server 2019 setup missing.'}
if (-not (Get-Command sqlcmd.exe -ErrorAction SilentlyContinue)) {throw 'sqlcmd missing.'}
if ((Get-Service -Name 'MSSQL$SQLEXPRESS').Status -ne 'Running') {throw 'Original SQLEXPRESS service not running on clone.'}
$disk=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
if ($disk.FreeSpace -lt 8GB) {throw 'Clone needs at least 8 GB free C:.'}
if ((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory -lt 5GB) {throw 'Clone RAM less than expected 6 GB profile.'}
Write-Host '[PASS] Clone-only preflight: disconnected NICs, SQL media, original instance, resources.'

$work=Join-Path $env:ProgramData 'Kingdoms\sql-clone-test'
New-Item -ItemType Directory -Path $work -Force | Out-Null
& icacls.exe $work '/inheritance:r' '/grant:r' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) {throw 'Could not restrict temp directory ACL.'}
function Run-Sql {
    param([string]$server,[string]$query,[string]$login='',[string]$password='')
    $tmp=Join-Path $work ('query-'+[guid]::NewGuid().ToString('N')+'.sql')
    try {
        [IO.File]::WriteAllText($tmp,$query)
        if ($login) {
            $env:SQLCMDPASSWORD=$password
            $result=@(& sqlcmd.exe -S $server -U $login -b -W -h -1 -l 15 -i $tmp 2>&1)
        } else {
            $result=@(& sqlcmd.exe -S $server -E -b -W -h -1 -l 15 -i $tmp 2>&1)
        }
        if ($LASTEXITCODE -ne 0) {throw "SQL query failed on $server (SQLCMD status $LASTEXITCODE)."}
        return ($result | ForEach-Object {[string]$_})
    } finally {
        Remove-Item Env:\SQLCMDPASSWORD -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}
function Random-Password {
    $buf=New-Object byte[] 24
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try {$rng.GetBytes($buf)} finally {$rng.Dispose()}
    return ('K1!'+[Convert]::ToBase64String($buf))
}
$before=(Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'").FreeSpace
$svc=Get-Service -Name 'MSSQL$KINGDOMS2' -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Host '[INFO] Installing KINGDOMS2 on DISPOSABLE CLONE only; do not interrupt setup.'
    $args=@('/Q','/ACTION=Install','/FEATURES=SQLENGINE','/INSTANCENAME=KINGDOMS2','/INSTANCEID=KINGDOMS2','/SQLSYSADMINACCOUNTS=BUILTIN\Administrators','/TCPENABLED=1','/NPENABLED=0','/UpdateEnabled=False','/IACCEPTSQLSERVERLICENSETERMS')
    $p=Start-Process -FilePath $setup -ArgumentList $args -PassThru -Wait
    if ($p.ExitCode -eq 3010) {throw 'Setup needs a reboot; reboot isolated CLONE and rerun.'}
    if ($p.ExitCode -ne 0) {throw "Setup returned $($p.ExitCode). Inspect SQL Setup Bootstrap Log on clone."}
}
$svc=Get-Service -Name 'MSSQL$KINGDOMS2'
if ($svc.Status -ne 'Running') {Start-Service -Name 'MSSQL$KINGDOMS2'}
$root='HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\MSSQL15.KINGDOMS2\MSSQLServer'
if (-not (Test-Path $root)) {throw 'KINGDOMS2 registry ID missing.'}
Set-ItemProperty -Path $root -Name LoginMode -Value 2
$tcp=Join-Path $root 'SuperSocketNetLib\Tcp'
foreach($ip in @(Get-ChildItem -Path $tcp | Where-Object {$_.PSChildName -like 'IP*'})) {
    Set-ItemProperty -LiteralPath $ip.PSPath -Name TcpDynamicPorts -Value ''
    Set-ItemProperty -LiteralPath $ip.PSPath -Name TcpPort -Value '1444'
}
Restart-Service -Name 'MSSQL$KINGDOMS2' -ErrorAction Stop
$up=$false
for($i=0;$i -lt 24;$i++){
    Start-Sleep -Seconds 5
    if(@(Get-NetTCPConnection -State Listen -LocalPort 1444 -ErrorAction SilentlyContinue).Count -gt 0){$up=$true;break}
}
if (-not $up){throw 'KINGDOMS2 did not listen on TCP 1444.'}
Write-Host '[PASS] Both SQL services available, second instance listening on TCP 1444.'
$a='tcp:127.0.0.1,1433'
$b='tcp:127.0.0.1,1444'
$beforeA=@(Run-Sql $a "SELECT @@SERVERNAME AS ServerName;")
$beforeB=@(Run-Sql $b "SELECT @@SERVERNAME AS ServerName;")
Write-Host ('[INFO] Source: '+($beforeA -join ' '))
Write-Host ('[INFO] Target: '+($beforeB -join ' '))

$lowPass=Random-Password
$highPass=Random-Password
$low='COURSE1_LOW'
$high='COURSE1_LINK_ADMIN'
$qA=@"
IF NOT EXISTS(SELECT 1 FROM sys.sql_logins WHERE name=N'$low') CREATE LOGIN [$low] WITH PASSWORD=N'$lowPass',CHECK_POLICY=OFF;
ELSE ALTER LOGIN [$low] WITH PASSWORD=N'$lowPass';
"@
$qB=@"
IF NOT EXISTS(SELECT 1 FROM sys.sql_logins WHERE name=N'$high') CREATE LOGIN [$high] WITH PASSWORD=N'$highPass',CHECK_POLICY=OFF;
ELSE ALTER LOGIN [$high] WITH PASSWORD=N'$highPass';
IF IS_SRVROLEMEMBER('sysadmin','$high')=0 ALTER SERVER ROLE sysadmin ADD MEMBER [$high];
"@
Run-Sql $a $qA | Out-Null
Run-Sql $b $qB | Out-Null
$qLink=@"
IF EXISTS(SELECT 1 FROM sys.servers WHERE name=N'KINGDOMS2' AND data_source <> N'127.0.0.1,1444') THROW 51000, 'Existing link points elsewhere',1;
IF NOT EXISTS(SELECT 1 FROM sys.servers WHERE name=N'KINGDOMS2') EXEC master.dbo.sp_addlinkedserver @server=N'KINGDOMS2',@srvproduct=N'',@provider=N'SQLNCLI',@datasrc=N'127.0.0.1,1444';
IF EXISTS(SELECT 1 FROM sys.linked_logins WHERE server_id=(SELECT server_id FROM sys.servers WHERE name=N'KINGDOMS2') AND local_principal_id=0) EXEC master.dbo.sp_droplinkedsrvlogin @rmtsrvname=N'KINGDOMS2',@locallogin=NULL;
IF EXISTS(SELECT 1 FROM sys.linked_logins WHERE server_id=(SELECT server_id FROM sys.servers WHERE name=N'KINGDOMS2') AND local_principal_id=SUSER_ID(N'$low')) EXEC master.dbo.sp_droplinkedsrvlogin @rmtsrvname=N'KINGDOMS2',@locallogin=N'$low';
EXEC master.dbo.sp_addlinkedsrvlogin @rmtsrvname=N'KINGDOMS2',@useself=N'False',@locallogin=N'$low',@rmtuser=N'$high',@rmtpassword=N'$highPass';
EXEC master.dbo.sp_serveroption @server=N'KINGDOMS2',@optname=N'data access',@optvalue=N'true';
"@
Run-Sql $a $qLink | Out-Null
$fromA=@(Run-Sql $a "SELECT 'KINGDOMS_LOW',SYSTEM_USER,IS_SRVROLEMEMBER('sysadmin');" $low $lowPass)
$fromLink=@(Run-Sql $a "SELECT * FROM OPENQUERY([KINGDOMS2], 'SELECT ''KINGDOMS_LINKED'' AS Marker,SYSTEM_USER AS RemoteLogin,IS_SRVROLEMEMBER(''sysadmin'') AS RemoteSysadmin');" $low $lowPass)
Write-Host ('[PROOF] Source: '+($fromA -join ' | '))
Write-Host ('[PROOF] Linked: '+($fromLink -join ' | '))
if (-not (($fromA -join ' ') -match 'KINGDOMS_LOW\s+COURSE1_LOW\s+0')) {throw 'Source low-privilege check failed.'}
if (-not (($fromLink -join ' ') -match 'KINGDOMS_LINKED\s+COURSE1_LINK_ADMIN\s+1')) {throw 'Remote sysadmin proof failed.'}
Write-Host '[PASS] SQL low-privilege source -> elevated linked instance PROVEN.'
foreach($p in @(Get-Process sqlservr -ErrorAction Stop)) {
    Write-Host ('[RESOURCE] PID='+$p.Id+' WorkingSetMB='+[math]::Round($p.WorkingSet64/1MB,1)+' PrivateMB='+[math]::Round($p.PrivateMemorySize64/1MB,1))
}
$after=(Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'").FreeSpace
Write-Host ('[RESOURCE] Disk used by experiment GB='+[math]::Round(($before-$after)/1GB,2))
Write-Host '[INFO] Reboot this isolated CLONE and rerun to validate persistence.'
