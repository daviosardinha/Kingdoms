"""Bounded, authenticated NT5DS recovery for installed KINGDOMS members.

The existing lab-mode controller has the same recovery stages, but installed
VMware cold starts use direct WinRM and must not invoke Vagrant's mode logic.
No Linux distro-specific tools, trust reset, manual NTP peer or NAT fallback.
"""

TIME_PENDING = "KINGDOMS_INSTALLED_MEMBER_TIME_PENDING|"
TIME_REPAIRED = "KINGDOMS_INSTALLED_MEMBER_TIME_REPAIRED|"
TIME_REPAIR_FAILED = "KINGDOMS_INSTALLED_MEMBER_TIME_REPAIR_FAILED|"

# Values are not drawn from user input. Keep exact domain/DC allowlisting here.
DOMAINS = {
    ("north.sevenkingdoms.local", "winterfell.north.sevenkingdoms.local"),
    ("essos.local", "meereen.essos.local"),
}

# Keep this script compact: pywinrm sends it via a UTF-16LE Base64
# powershell.exe -EncodedCommand argument, subject to Windows cmdline limits.
# Long explanatory comments belong in Python, never inside this payload.
_SCRIPT = r"""
$ErrorActionPreference='Continue'
$domain='__DOMAIN__'
$dc='__DC__'
$timer=[Diagnostics.Stopwatch]::StartNew()
$budget=__BUDGET__
function Fail-Time([string]$stage) {
  Write-Output "KINGDOMS_INSTALLED_MEMBER_TIME_REPAIR_FAILED|stage=$stage|source=$source|resync_rc=$resyncRc"
  exit 0
}
try {
  Resolve-DnsName $dc -ErrorAction Stop|Out-Null
  if(-not (Test-ComputerSecureChannel -Server $dc -ErrorAction Stop)){Fail-Time 'secure_channel'}
} catch {Fail-Time 'identity'}
& nltest.exe "/sc_query:$domain"|Out-Null
if($LASTEXITCODE){Fail-Time 'netlogon_session'}
& nltest.exe "/dsgetdc:$domain" /timeserv /force|Out-Null
if($LASTEXITCODE){Fail-Time 'timeserv_locator'}
& w32tm.exe /stripchart "/computer:$dc" /samples:2 /dataonly|Out-Null
if($LASTEXITCODE){Fail-Time 'ntp_path'}
if($timer.Elapsed.TotalSeconds -ge $budget){Fail-Time 'budget'}
& w32tm.exe /config /syncfromflags:domhier /update|Out-Null
if($LASTEXITCODE){Fail-Time 'config'}
try {
  Restart-Service W32Time -Force -ErrorAction Stop
  (Get-Service W32Time -ErrorAction Stop).WaitForStatus(
    [System.ServiceProcess.ServiceControllerStatus]::Running,
    [TimeSpan]::FromSeconds(10))
} catch {Fail-Time 'service'}
for($attempt=1;$attempt -le 12;$attempt++){
  if($timer.Elapsed.TotalSeconds -ge $budget){Fail-Time 'budget'}
  if($attempt -eq 1 -or (($attempt-1)%3) -eq 0){
    & nltest.exe "/sc_query:$domain"|Out-Null
    if($LASTEXITCODE){Fail-Time 'netlogon_session_lost'}
    & nltest.exe "/dsgetdc:$domain" /timeserv /force|Out-Null
    if($LASTEXITCODE){Fail-Time 'timeserv_locator_lost'}
    & w32tm.exe /resync /rediscover /nowait|Out-Null
    $resyncRc=$LASTEXITCODE
  }
  $remaining=[int]($budget-$timer.Elapsed.TotalSeconds)
  if($remaining -le 0){Fail-Time 'budget'}
  Start-Sleep -Seconds ([Math]::Min(5,$remaining))
  $source=(& w32tm.exe /query /source 2>$null|Out-String).Trim().TrimEnd('.')
  if($LASTEXITCODE -ne 0 -or $source -ine $dc){continue}
  $status=(& w32tm.exe /query /status /verbose 2>&1|Out-String)
  if($LASTEXITCODE -ne 0){continue}
  if($status -match 'SignatureAuthenticated' -and
     $status -match 'Last Sync Error:\s*0\s*\(' -and
     $status -match 'Leap Indicator:\s*0\s*\('){
    Write-Output "KINGDOMS_INSTALLED_MEMBER_TIME_REPAIRED|source=$source|attempt=$attempt|authenticated=true"
    exit 0
  }
}
Fail-Time 'rediscover'
"""


def build_time_recovery_script(domain: str, dc: str, budget: int = 90) -> str:
    """Return the bounded PowerShell script for one known installed member."""
    if (domain, dc) not in DOMAINS:
        raise ValueError("Unknown installed member time hierarchy")
    if type(budget) is not int or not 30 <= budget <= 90:
        raise ValueError("Recovery budget must be between 30 and 90 seconds")
    script = (_SCRIPT.replace("__DOMAIN__", domain)
                     .replace("__DC__", dc)
                     .replace("__BUDGET__", str(budget)))
    # powershell -EncodedCommand uses Base64 of UTF-16LE. Windows' command
    # launcher rejects commands around 8191 chars. Leave ample headroom for
    # the pywinrm command prefix and defend against a future bloated script.
    import base64
    encoded_size = len(base64.b64encode(script.encode("utf-16le")))
    if encoded_size > 6500:
        raise ValueError(f"WinRM recovery command exceeds safe size: {encoded_size}")
    return script


def is_time_only_pending(status_code: int, output: bytes,
                         expected_dc: str) -> bool:
    """Accept a dedicated time-only marker, never a general WinRM failure."""
    if status_code != 0:
        return False
    return any(
        line.strip() == TIME_PENDING + "expected=" + expected_dc
        for line in output.decode(errors="replace").splitlines()
    )


def is_authenticated_repair(status_code: int, output: bytes,
                            expected_dc: str) -> bool:
    """Require the exact successful signed-source terminal marker."""
    if status_code != 0:
        return False
    return any(
        line.strip().startswith(TIME_REPAIRED + "source=" + expected_dc + "|")
        and line.strip().endswith("|authenticated=true")
        for line in output.decode(errors="replace").splitlines()
    )
