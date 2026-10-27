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
    $loader = "`$ErrorActionPreference='Stop';try{`$m=[IO.MemoryStream]::new(,[Convert]::FromBase64String('$packed'));`$g=[IO.Compression.GzipStream]::new(`$m,[IO.Compression.CompressionMode]::Decompress);`$r=[IO.StreamReader]::new(`$g);& ([scriptblock]::Create(`$r.ReadToEnd()))}catch{exit 1}"
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
        $parentWinrsShellGuid = $created.SelectSingleNode("//*[local-name()='ShellId']").InnerText
        if ([string]::IsNullOrWhiteSpace($parentWinrsShellGuid)) {
            throw 'KINGSLANDING returned no WinRS shell identifier'
        }
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
