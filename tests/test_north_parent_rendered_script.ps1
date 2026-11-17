# Compile the full NORTH parent-DC Ansible win_powershell script *after*
# rendering both file lookups with Jinja's indent(10) semantics. This catches
# PowerShell 5.1 here-string delimiters broken by embedding/indentation.
# No WinRM, guest credentials, domain calls, or VM changes.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$book = [IO.File]::ReadAllText((Join-Path $root 'ansible/north-exercise-health-readonly.yml'))
$lines = $book -split '\r?\n'
$secondPlay = -1
for ($index=0; $index -lt $lines.Length; $index++) {
    if ($lines[$index] -eq '- name: Verify KINGSLANDING directly through the permitted inter-DC path') {
        $secondPlay = $index
        break
    }
}
if ($secondPlay -lt 0) { throw 'Cannot find authenticated parent proof play' }
$start = -1
$end = -1
for ($index=$secondPlay; $index -lt $lines.Length; $index++) {
    if ($lines[$index] -eq '        script: |') { $start = $index + 1; continue }
    if ($start -ge 0 -and $lines[$index] -eq '        sensitive_parameters:') { $end = $index; break }
}
if ($start -lt 0 -or $end -le $start) { throw 'Cannot find parent win_powershell script block' }
$sourceLines = [Collections.Generic.List[string]]::new()
for ($index=$start; $index -lt $end; $index++) {
    $line = $lines[$index]
    if ($line.StartsWith('          ')) { $sourceLines.Add($line.Substring(10)); continue }
    if (-not $line.Trim()) { $sourceLines.Add(''); continue }
    throw 'Unexpected YAML indentation within parent PowerShell script'
}
$script = [string]::Join("`n", $sourceLines)
function Get-IndentedJinjaFile([string]$filename) {
    $raw = [IO.File]::ReadAllText((Join-Path $root ('ansible/files/' + $filename)))
    $split = $raw -split '\r?\n'
    $result = [Collections.Generic.List[string]]::new()
    for ($i=0; $i -lt $split.Length; $i++) {
        if ($i -eq 0 -or -not $split[$i]) { $result.Add($split[$i]) }
        else { $result.Add((' ' * 10) + $split[$i]) }
    }
    return [string]::Join("`n", $result)
}
foreach ($filename in @('north-parent-winrs.ps1', 'north-parent-dc-health.ps1')) {
    $token = "{{ lookup('ansible.builtin.file', 'files/$filename') | indent(10) }}"
    if (-not $script.Contains($token)) { throw ('Template is missing lookup for ' + $filename) }
    $script = $script.Replace($token, (Get-IndentedJinjaFile $filename))
}
if ($script.Contains('{{')) { throw 'Unresolved Jinja template remains in parent script' }
$tokens = $null
$errors = $null
$null = [Management.Automation.Language.Parser]::ParseInput($script,[ref]$tokens,[ref]$errors)
if ($errors.Count -gt 0) {
    foreach ($err in $errors) {
        Write-Output ('NORTH_PARENT_RENDER_PARSE_ERROR={0} line={1}' -f
            $err.ErrorId, $err.Extent.StartLineNumber)
    }
    throw ('Rendered parent win_powershell parser failed with ' + $errors.Count + ' errors')
}
if ($script -notmatch 'function Invoke-NorthParentWinRS' -or
    $script -notmatch 'function New-NorthParentWinRSLoader' -or
    $script -notmatch 'NORTH_PARENT_DC_AD_HEALTH=PASS') {
    throw 'Rendered parent script is missing required strict health proof functions'
}
Write-Output ('NORTH_PARENT_RENDERED_POWERSHELL_PARSE=PASS lines={0}' -f ($script -split '\n').Length)
