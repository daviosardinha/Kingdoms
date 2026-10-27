# Offline WinRS loader contract: no network, credentials or VM changes.
# This proves the gzip/EncodedCommand wrapper reports a safe class/stage on
# failure, instead of hiding the exception and returning exit_code=1 only.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\..\ansible\files\north-parent-winrs.ps1"

function Invoke-LocalEncodedParentFixture([string]$Script) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Script)
    $memory = [IO.MemoryStream]::new()
    $gzip = [IO.Compression.GzipStream]::new(
        $memory, [IO.Compression.CompressionMode]::Compress, $true)
    $gzip.Write($bytes, 0, $bytes.Length)
    $gzip.Dispose()
    $packed = [Convert]::ToBase64String($memory.ToArray())
    $memory.Dispose()
    $loader = New-NorthParentWinRSLoader $packed
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($loader))
    if ($encoded.Length -gt 6500) { throw 'Offline fixture unexpectedly exceeds command limit' }
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $psi.Arguments = "-NoProfile -NonInteractive -EncodedCommand $encoded"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $p = [Diagnostics.Process]::Start($psi)
    try {
        $stdout = $p.StandardOutput.ReadToEnd()
        $stderr = $p.StandardError.ReadToEnd()
        if (-not $p.WaitForExit(10000)) {
            $p.Kill()
            throw 'Offline loader fixture timed out'
        }
        return [pscustomobject]@{
            ExitCode = [int]$p.ExitCode
            Stdout = $stdout
            StderrBytes = [Text.Encoding]::UTF8.GetByteCount($stderr)
        }
    } finally {
        $p.Dispose()
    }
}
$good = Invoke-LocalEncodedParentFixture "Write-Output 'NORTH_PARENT_DC_AD_HEALTH=PASS host=KINGSLANDING'"
$accepted = Get-NorthParentHealthProofStatus $good
if (-not $accepted.Accepted -or $accepted.ExitCode -ne 0) {
    throw ('Read-only fixture unexpected result: exit={0} count={1} bytes={2} stdout={3}' -f $good.ExitCode, $accepted.MarkerCount, $accepted.StdoutBytes, ($good.Stdout.Trim() -replace '[^A-Za-z0-9_:=|\-]', '_'))
}
$bad = Invoke-LocalEncodedParentFixture @'
Write-Output 'NORTH_PARENT_HEALTH_STAGE=identity'
throw 'Synthetic failure only, no remote access'
'@
$rejected = Get-NorthParentHealthProofStatus $bad
if ($rejected.Accepted -or $rejected.ExitCode -ne 1 -or
    $rejected.LastStage -ne 'identity' -or
    $rejected.RemoteType -ne 'RuntimeException' -or
    $rejected.RemoteCategory -ne 'OperationStopped') {
    throw ('Offline failure classification incorrect; code={0} stage={1} type={2} category={3}' -f
        $rejected.ExitCode, $rejected.LastStage, $rejected.RemoteType, $rejected.RemoteCategory)
}
Write-Output 'NORTH_PARENT_WINRS_LOADER_TESTS=2 PASS'
