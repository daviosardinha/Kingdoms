# Same WinRM remote-shell resource used by Ansible/pywinrm. PSRP's separate
# Microsoft.PowerShell endpoint/ACL is not an installation prerequisite.
function Get-NorthParentCredential([PSCredential]$Credential) {
    $name = $Credential.UserName
    if ($name -notmatch '[@\\]') { $name = 'SEVENKINGDOMS\' + $name }
    if ($name -notmatch '^(?i)(SEVENKINGDOMS|sevenkingdoms\.local)\\[^\\@]+$' -and
        $name -notmatch '^[^\\@]+@(?i)sevenkingdoms\.local$') {
        throw 'DC01 requires its own root-domain inventory account'
    }
    return [PSCredential]::new($name, $Credential.Password)
}

function Assert-NorthParentPath {
    if ($env:COMPUTERNAME -cne 'WINTERFELL') { throw 'Expected NORTH child DC' }
    $resolved = @(Resolve-DnsName 'kingslanding.sevenkingdoms.local' -Type A -ErrorAction Stop |
        Where-Object { $_.Type -eq 'A' })
    if ($resolved.Count -ne 1 -or $resolved[0].IPAddress -cne '10.4.20.10') {
        throw 'Parent DC DNS identity is not uniquely 10.4.20.10'
    }
    $discovery = @(& nltest.exe '/dsgetdc:sevenkingdoms.local' /timeserv /force 2>&1)
    if ($LASTEXITCODE -ne 0 -or ($discovery -join ' ') -notmatch '10\.4\.20\.10') {
        throw 'Parent DC TIMESERV discovery failed'
    }
}

# Session.Create returns a WS-Addressing endpoint reference.
# ShellId is in wsman:Selector Name="ShellId", NOT an XML element.
function Get-NorthParentWinRSShellGuid([xml]$CreateResponse) {
    $selector = $CreateResponse.SelectSingleNode(
        "//*[local-name()='Selector' and translate(@Name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='shellid']")
    if ($null -eq $selector) { throw 'KINGSLANDING Create response missing ShellId selector' }
    $identifier = ([string]$selector.InnerText).Trim()
    $rawGuid = $identifier -replace '^uuid:', ''
    $parsedGuid = [guid]::Empty
    if (-not [guid]::TryParse($rawGuid, [ref]$parsedGuid)) {
        throw 'KINGSLANDING Create response contains invalid ShellId GUID'
    }
    return $identifier
}

# PowerShell may put a #< CLIXML progress block immediately before stdout
# without a newline. Require one exact proof marker either at the beginning of
# a line or immediately following a closing CLIXML document.
function Get-NorthParentHealthProofStatus($Result) {
    $expected = 'NORTH_PARENT_DC_AD_HEALTH=PASS host=KINGSLANDING'
    $text = [string]$Result.Stdout
    $pattern = '(?:^|</Objs>)' + [regex]::Escape($expected) + '(?=\r?$)'
    $matchesFound = [regex]::Matches(
        $text, $pattern,
        [Text.RegularExpressions.RegexOptions]::Multiline)
    $stageMatches = [regex]::Matches($text,
        'NORTH_PARENT_HEALTH_STAGE=(identity|services|shares|dns_srv|locator_timeserv|w32tm_source|w32tm_status)',
        [Text.RegularExpressions.RegexOptions]::Multiline)
    $lastStage = 'none'
    if ($stageMatches.Count -gt 0) {
        $lastStage = $stageMatches[$stageMatches.Count - 1].Groups[1].Value
    }
    $remote = [regex]::Match($text,
        'NORTH_PARENT_REMOTE_ERROR\|type=([A-Za-z0-9_]+)\|category=([A-Za-z0-9_]+)\|line=([0-9]+)')
    $remoteType = if ($remote.Success) { $remote.Groups[1].Value } else { 'none' }
    $remoteCategory = if ($remote.Success) { $remote.Groups[2].Value } else { 'none' }
    $remoteLine = if ($remote.Success) { [int]$remote.Groups[3].Value } else { 0 }
    $exitCode = [int]$Result.ExitCode
    return [pscustomobject]@{
        Accepted = ($exitCode -eq 0 -and $matchesFound.Count -eq 1)
        ExitCode = $exitCode
        MarkerCount = [int]$matchesFound.Count
        StdoutBytes = [Text.Encoding]::UTF8.GetByteCount($text)
        StderrBytes = [int]$Result.StderrBytes
        LastStage = $lastStage
        RemoteType = $remoteType
        RemoteCategory = $remoteCategory
        RemoteLine = $remoteLine
    }
}

# Preserve remote WinRS error classification without exposing exception text.
function New-NorthParentWinRSLoader([string]$PackedScript) {
    if ($PackedScript -notmatch '^[A-Za-z0-9+/]+={0,2}$') {
        throw 'Invalid compressed parent proof encoding'
    }
    # Construct source from literals; Jinja's indent filter would otherwise
    # indent the closing delimiter of a PowerShell 5.1 here-string.
    $template = @(
        '$ErrorActionPreference = ''Stop''',
        'try {',
        '    $decoded = [Convert]::FromBase64String(''__NORTH_PACKED__'')',
        '    $m = [IO.MemoryStream]::new($decoded)',
        '    $g = [IO.Compression.GzipStream]::new($m,[IO.Compression.CompressionMode]::Decompress)',
        '    $r = [IO.StreamReader]::new($g)',
        '    & ([scriptblock]::Create($r.ReadToEnd()))',
        '} catch {',
        '    $kind = ([string]$_.Exception.GetType().Name) -replace ''[^A-Za-z0-9_]'', ''''',
        '    $category = ([string]$_.CategoryInfo.Category) -replace ''[^A-Za-z0-9_]'', ''''',
        '    $line = if ($_.InvocationInfo) { [int]$_.InvocationInfo.ScriptLineNumber } else { 0 }',
        '    [Console]::Out.WriteLine("NORTH_PARENT_REMOTE_ERROR|type=$kind|category=$category|line=$line")',
        '    exit 1',
        '}'
    ) -join [Environment]::NewLine
    return $template.Replace('__NORTH_PACKED__', $PackedScript)
}

function Invoke-NorthParentWinRS {
    param([PSCredential]$Credential, [string]$Script,
          [string]$Endpoint = 'https://kingslanding.sevenkingdoms.local:5986/wsman')
    # Alternate endpoint is restricted to a disposable hosted Windows CI fixture.
    if ($Endpoint -cne 'https://kingslanding.sevenkingdoms.local:5986/wsman' -and
        -not ($env:GITHUB_ACTIONS -eq 'true' -and $env:RUNNER_ENVIRONMENT -eq 'github-hosted' -and
              $env:KINGDOMS_TEST_NORTH_WINRS -eq '1' -and
              $Endpoint -ceq 'https://localhost:5986/wsman' -and
              $env:COMPUTERNAME -notin @('WINTERFELL','KINGSLANDING'))) {
        throw 'Unexpected parent WinRM endpoint'
    }
    $ErrorActionPreference = 'Stop'
    $memory = [IO.MemoryStream]::new()
    $gzip = [IO.Compression.GzipStream]::new($memory, [IO.Compression.CompressionMode]::Compress, $true)
    $bytes = [Text.Encoding]::UTF8.GetBytes($Script)
    $gzip.Write($bytes, 0, $bytes.Length); $gzip.Dispose()
    $packed = [Convert]::ToBase64String($memory.ToArray()); $memory.Dispose()
    $loader = New-NorthParentWinRSLoader $packed
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($loader))
    if ($encoded.Length -gt 6500) { throw 'Parent health command exceeds safe WinRM command length' }

    $automation = New-Object -ComObject WSMan.Automation
    $options = $automation.CreateConnectionOptions()
    $options.UserName = $Credential.UserName
    $options.Password = $Credential.GetNetworkCredential().Password
    # Preserve the established isolated-lab HTTPS/Negotiate certificate policy.
    # Never enable Basic, CredSSP, delegation, plaintext or broader endpoint ACLs.
    $flags = $automation.SessionFlagCredUsernamePassword() -bor $automation.SessionFlagUseNegotiate() -bor
        $automation.SessionFlagSkipCACheck() -bor $automation.SessionFlagSkipCNCheck() -bor 0x2000000 -bor 0x8000000
    $session = $automation.CreateSession($Endpoint, $flags, $options)
    $session.Timeout = 15000
    $ns = 'http://schemas.microsoft.com/wbem/wsman/1/windows/shell'
    $resource = $ns + '/cmd'
    $locator = $null
    $stage = 'create shell'
    try {
        $created = [xml]$session.Create($resource,
            "<rsp:Shell xmlns:rsp='$ns'><rsp:InputStreams>stdin</rsp:InputStreams><rsp:OutputStreams>stdout stderr</rsp:OutputStreams></rsp:Shell>", 0)
        # $ShellId is a built-in read-only PowerShell automatic variable.
        # Keep the remote WSMan shell GUID in a distinct writable variable.
        $parentWinrsShellGuid = Get-NorthParentWinRSShellGuid $created
        $locator = $automation.CreateResourceLocator($resource)
        $locator.AddSelector('ShellId', $parentWinrsShellGuid)
        $stage = 'start command'
        $command = [xml]$session.Invoke($ns + '/Command', $locator,
            "<rsp:CommandLine xmlns:rsp='$ns'><rsp:Command>powershell.exe</rsp:Command><rsp:Arguments>-NoLogo -NoProfile -NonInteractive -EncodedCommand $encoded</rsp:Arguments></rsp:CommandLine>", 0)
        $commandId = $command.SelectSingleNode("//*[local-name()='CommandId']").InnerText
        $output = @{stdout=[IO.MemoryStream]::new(); stderr=[IO.MemoryStream]::new()}
        $timer = [Diagnostics.Stopwatch]::StartNew()
        $stage = 'receive proof'
        try {
            while ($timer.Elapsed.TotalSeconds -lt 60) {
                try {
                    $received = [xml]$session.Invoke($ns + '/Receive', $locator,
                        "<rsp:Receive xmlns:rsp='$ns'><rsp:DesiredStream CommandId='$commandId'>stdout stderr</rsp:DesiredStream></rsp:Receive>", 0)
                } catch {
                    # WSMan operation timeout means the same command is still
                    # running. Receive again; never restart the command.
                    if ($session.Error -match 'Code="2150858793"') { continue }
                    throw
                }
                foreach ($stream in $received.SelectNodes("//*[local-name()='Stream']")) {
                    $data = [Convert]::FromBase64String($stream.InnerText)
                    $name = $stream.GetAttribute('Name')
                    if (-not $output.ContainsKey($name)) { throw 'Unexpected WinRS stream' }
                    $output[$name].Write($data, 0, $data.Length)
                    if ($output[$name].Length -gt 65536) { throw 'Parent proof output exceeds limit' }
                }
                $state = $received.SelectSingleNode("//*[local-name()='CommandState']")
                if ($state -and $state.State -eq ($ns + '/CommandState/Done')) {
                    return [pscustomobject]@{
                        ExitCode=[int]$state.ExitCode
                        Stdout=[Text.Encoding]::UTF8.GetString($output.stdout.ToArray())
                        StderrBytes=[int]$output.stderr.Length
                    }
                }
            }
            throw 'Parent proof deadline expired'
        } finally { $output.stdout.Dispose(); $output.stderr.Dispose() }
    } catch {
        # Avoid dumping remoting objects/credentials into Ansible failure output.
        $code = 'unavailable'
        if ($session.Error -match 'Code="([0-9]+)"') { $code = $Matches[1] }
        if ($env:GITHUB_ACTIONS -eq 'true' -and $env:RUNNER_ENVIRONMENT -eq 'github-hosted' -and
            $env:KINGDOMS_TEST_NORTH_WINRS -eq '1') {
            # Disposable fixture diagnostics; never print the connection object.
            Write-Warning ($session.Error.Replace($Credential.GetNetworkCredential().Password, '[redacted]'))
        }
        throw "KINGSLANDING WinRS $stage failed (WSMan code $code); inspect DC01 inventory authentication and existing WinRM authorization"
    } finally {
        if ($locator) { $null = $session.Delete($locator, 0) }
        $options.Password = ''
    }
}
