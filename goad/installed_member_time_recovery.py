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

_SCRIPT = r"""
$ErrorActionPreference = 'Continue'
$domain = '__DOMAIN__'
$dc = '__DC__'
$deadline = [Diagnostics.Stopwatch]::StartNew()
$budget = __BUDGET__

function Fail-Time([string]$stage, [string]$detail) {
    $safe = (($detail -replace '[|\r\n]', ' ').Trim())
    Write-Output ("KINGDOMS_INSTALLED_MEMBER_TIME_REPAIR_FAILED|stage={0}|detail={1}" -f $stage,$safe)
    exit 0
}

# A readiness probe has already passed DNS, machine trust and the Netlogon
# secure session. Recheck them immediately; do not touch time otherwise.
try {
    Resolve-DnsName $dc -ErrorAction Stop | Out-Null
    if (-not (Test-ComputerSecureChannel -Server $dc -ErrorAction Stop)) {
        Fail-Time 'secure_channel' 'unhealthy'
    }
} catch {
    Fail-Time 'identity' $_.Exception.Message
}
& nltest.exe ("/sc_query:" + $domain) | Out-Null
if ($LASTEXITCODE -ne 0) { Fail-Time 'netlogon_session' "$LASTEXITCODE" }

& nltest.exe ("/dsgetdc:" + $domain) /timeserv /force | Out-Null
if ($LASTEXITCODE -ne 0) { Fail-Time 'timeserv_locator' "$LASTEXITCODE" }

# A positive unauthenticated UDP test establishes the path but cannot be
# treated as success. The final source must be domain-authenticated NT5DS.
$strip = @(& w32tm.exe /stripchart ("/computer:" + $dc) /samples:2 /dataonly 2>&1)
if ($LASTEXITCODE -ne 0) {
    Fail-Time 'ntp_path' (($strip | Out-String).Trim())
}
if ($deadline.Elapsed.TotalSeconds -ge $budget) {
    Fail-Time 'budget' 'expired during preflight'
}

& w32tm.exe /config /syncfromflags:domhier /update | Out-Null
if ($LASTEXITCODE -ne 0) { Fail-Time 'config' "$LASTEXITCODE" }

try {
    Restart-Service W32Time -Force -ErrorAction Stop
    (Get-Service W32Time -ErrorAction Stop).WaitForStatus(
        [System.ServiceProcess.ServiceControllerStatus]::Running,
        [TimeSpan]::FromSeconds(10)
    )
} catch {
    Fail-Time 'service' $_.Exception.Message
}

# The controller permits one recovery attempt per member/start. Inside it,
# re-prime the domain session and request bounded rediscovery as in lab-mode.sh.
for ($attempt = 1; $attempt -le 12; $attempt++) {
    if ($deadline.Elapsed.TotalSeconds -ge $budget) {
        Fail-Time 'budget' 'expired during rediscovery'
    }
    if ($attempt -eq 1 -or (($attempt - 1) % 3) -eq 0) {
        & nltest.exe ("/sc_query:" + $domain) | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Fail-Time 'netlogon_session_lost' "$LASTEXITCODE"
        }
        & nltest.exe ("/dsgetdc:" + $domain) /timeserv /force | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Fail-Time 'timeserv_locator_lost' "$LASTEXITCODE"
        }
        & w32tm.exe /resync /rediscover /nowait | Out-Null
        # A nonzero nowait result isn't a successful sync. Observe verified
        # source and signed time status below before accepting anything.
    }

    $remaining = [Math]::Floor($budget - $deadline.Elapsed.TotalSeconds)
    if ($remaining -le 0) { Fail-Time 'budget' 'expired before time probe' }
    Start-Sleep -Seconds ([Math]::Min(5, $remaining))

    $source = (& w32tm.exe /query /source 2>$null | Out-String).Trim().TrimEnd('.')
    $sourceRc = $LASTEXITCODE
    if ($sourceRc -ne 0 -or $source -ine $dc) { continue }

    $status = (& w32tm.exe /query /status /verbose 2>&1 | Out-String)
    $statusRc = $LASTEXITCODE
    if ($statusRc -ne 0) { continue }
    if ($status -notmatch 'SignatureAuthenticated' -or
        $status -notmatch 'Last Sync Error:\s*0\s*\(' -or
        $status -notmatch 'Leap Indicator:\s*0\s*\(') {
        continue
    }
    Write-Output ("KINGDOMS_INSTALLED_MEMBER_TIME_REPAIRED|source={0}|attempt={1}|authenticated=true" -f $source,$attempt)
    exit 0
}
Fail-Time 'rediscover' 'authenticated domain time did not converge'
"""


def build_time_recovery_script(domain: str, dc: str, budget: int = 90) -> str:
    """Return the bounded PowerShell script for one known installed member."""
    if (domain, dc) not in DOMAINS:
        raise ValueError("Unknown installed member time hierarchy")
    if type(budget) is not int or not 30 <= budget <= 90:
        raise ValueError("Recovery budget must be between 30 and 90 seconds")
    return (_SCRIPT.replace("__DOMAIN__", domain)
                   .replace("__DC__", dc)
                   .replace("__BUDGET__", str(budget)))


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
