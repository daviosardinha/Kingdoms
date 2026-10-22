# Exact fresh WSLPE management repair. No account/password, NIC, IP or scenario changes.
[CmdletBinding()]
param(
    [ValidateSet('Inspect','Prepare','ConsoleCheck','Harden','Verify','Rollback')]
    [string] $Mode = 'Inspect',
    [string] $Nonce = '',
    [string] $SourceBase64 = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Instance = 'bf5369-wslpe-vmware'
$Folder = 'C:\ProgramData\Kingdoms\OperatorManagement-bf5369'
$StatePath = Join-Path $Folder 'state.clixml'
$ScriptPath = Join-Path $Folder 'management.ps1'
$Group = 'Kingdoms WSLPE41 operator bf5369'
$Prefix = 'Kingdoms-WSLPE41-bf5369-'
$Policy = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'

function Get-WSBool([string] $Path) {
    # WSMan provider values can be strings. [bool]'false' is TRUE in PowerShell.
    return [Convert]::ToBoolean([string](Get-Item -LiteralPath $Path).Value)
}

function Assert-Guest {
    $machine = Get-CimInstance Win32_ComputerSystem
    if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain) {
        throw 'Wrong standalone guest'
    }
    $principal = New-Object Security.Principal.WindowsPrincipal(
        [Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'An elevated local administrator token is required'
    }
    if ((Get-ItemPropertyValue $Policy EnableLUA) -ne 1) { throw 'UAC must remain enabled' }
    if (@(Get-NetFirewallProfile -PolicyStore ActiveStore |
        Where-Object { [string]$_.Enabled -ne 'True' }).Count) {
        throw 'All Windows Firewall profiles must already be enabled'
    }
    $adapters = @(Get-NetAdapter -Physical)
    $expected = @('000C292FD75B','000C292FD765','000C292FD76F')
    if ($adapters.Count -ne 3) { throw 'Expected exactly the three existing VMware NICs' }
    $mapped = @{}
    foreach ($mac in $expected) {
        $found = @($adapters | Where-Object {
            ($_.MacAddress -replace '[^0-9A-Fa-f]', '').ToUpperInvariant() -ceq $mac
        })
        if ($found.Count -ne 1 -or [string]$found[0].Status -ne 'Up') {
            throw 'Expected active VMware MAC missing'
        }
        $mapped[$mac] = $found[0]
    }
    $mgmt = $mapped['000C292FD76F']
    $ips = @(Get-NetIPAddress -InterfaceIndex $mgmt.ifIndex -AddressFamily IPv4)
    if (@($ips | Where-Object { $_.IPAddress -eq '172.28.233.31' -and
        $_.PrefixLength -eq 24 -and [string]$_.AddressState -eq 'Preferred' }).Count -ne 1 -or
        @($ips | Where-Object { $_.IPAddress -ne '172.28.233.31' -and
            $_.IPAddress -notlike '169.254.*' }).Count) { throw 'Management IPv4 changed' }
    if (@(Get-NetRoute -InterfaceIndex $mgmt.ifIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue).Count) {
        throw 'Management has a default gateway'
    }
    $bootstrap = Get-LocalUser -Name vagrant
    $learner = Get-LocalUser -Name lpe.trainee
    $admins = Get-LocalGroup -SID 'S-1-5-32-544'
    $members = @(Get-LocalGroupMember -Group $admins.Name | ForEach-Object { $_.SID.Value })
    if (-not $bootstrap.Enabled -or $members -notcontains $bootstrap.SID.Value -or
        -not $learner.Enabled -or $members -contains $learner.SID.Value) {
        throw 'Existing bootstrap/standard learner foundation is not intact'
    }
    return $mapped
}

function Get-Certificate {
    $listeners = @(Get-ChildItem WSMan:\localhost\Listener | Where-Object {
        @($_.Keys) -contains 'Transport=HTTPS'
    })
    if ($listeners.Count -ne 1) { throw 'Expected one existing HTTPS listener' }
    $thumb = [string](Get-Item ($listeners[0].PSPath + '\CertificateThumbprint')).Value
    $cert = Get-Item ('Cert:\LocalMachine\My\' + $thumb)
    if (-not $cert.HasPrivateKey -or $cert.NotBefore -gt (Get-Date) -or
        $cert.NotAfter -lt (Get-Date).AddDays(1)) { throw 'Existing HTTPS certificate is not usable' }
    return $cert
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { throw 'Recovery state missing' }
    $state = Import-Clixml -LiteralPath $StatePath
    if ($state.Instance -cne $Instance -or $state.Certificate -cne (Get-Certificate).Thumbprint) {
        throw 'Recovery state identity/certificate mismatch'
    }
    return $state
}

function Protect-Folder {
    # Refuse filesystem redirection before touching privileged recovery files.
    foreach ($path in @('C:\ProgramData\Kingdoms', $Folder, $StatePath, $ScriptPath)) {
        if ((Test-Path -LiteralPath $path) -and
            ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Recovery path must not contain reparse points'
        }
    }
    if (-not (Test-Path -LiteralPath $Folder)) {
        $null = New-Item -ItemType Directory -Path $Folder -Force
    }
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @('S-1-5-18','S-1-5-32-544')) {
        $identity = New-Object Security.Principal.SecurityIdentifier($sid)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    Set-Acl -LiteralPath $Folder -AclObject $acl
}

function Rule-Specs($Nics) {
    $mgmt = [string]$Nics['000C292FD76F'].Name
    # Explicit blocks override the image's broad allow rules. No existing rule is deleted.
    return @(
        @{ Suffix='HTTPS-Allow'; Action='Allow'; LocalPort=@('5986');
           InterfaceAlias=@($mgmt); LocalAddress=@('172.28.233.31'); RemoteAddress=@('172.28.233.254') },
        @{ Suffix='HTTP-Block'; Action='Block'; LocalPort=@('5985');
           InterfaceAlias=@('Any'); LocalAddress=@('Any'); RemoteAddress=@('Any') },
        @{ Suffix='HTTPS-OtherNIC-Block'; Action='Block'; LocalPort=@('5986');
           InterfaceAlias=@([string]$Nics['000C292FD75B'].Name, [string]$Nics['000C292FD765'].Name);
           LocalAddress=@('Any'); RemoteAddress=@('Any') },
        @{ Suffix='HTTPS-OtherSource-Block'; Action='Block'; LocalPort=@('5986');
           InterfaceAlias=@($mgmt); LocalAddress=@('Any');
           RemoteAddress=@('0.0.0.0-172.28.233.253','172.28.233.255-255.255.255.255','::/0') },
        @{ Suffix='HTTPS-OtherAddress-Block'; Action='Block'; LocalPort=@('5986');
           InterfaceAlias=@($mgmt); RemoteAddress=@('Any');
           LocalAddress=@('0.0.0.0-172.28.233.30','172.28.233.32-255.255.255.255','::/0') }
    )
}

function Normalize-Values($Values) {
    return (@($Values | ForEach-Object { ([string]$_) -replace '/32$', '' -replace '/128$', '' } |
        Sort-Object) -join ',')
}

function Assert-Rule($Spec) {
    $rule = @(Get-NetFirewallRule -PolicyStore ActiveStore -Name ($Prefix + $Spec.Suffix))
    if ($rule.Count -ne 1 -or [string]$rule[0].Enabled -ne 'True' -or
        [string]$rule[0].Direction -ne 'Inbound' -or [string]$rule[0].Action -ne $Spec.Action -or
        [string]$rule[0].Profile -ne 'Any' -or $rule[0].Group -cne $Group) {
        throw ('Firewall rule not effective: ' + $Spec.Suffix)
    }
    $ports = $rule[0] | Get-NetFirewallPortFilter
    $addresses = $rule[0] | Get-NetFirewallAddressFilter
    $interfaces = $rule[0] | Get-NetFirewallInterfaceFilter
    $application = $rule[0] | Get-NetFirewallApplicationFilter
    $service = $rule[0] | Get-NetFirewallServiceFilter
    if ([string]$ports.Protocol -notin @('TCP','6') -or
        [string]$ports.RemotePort -ne 'Any' -or
        [string]$application.Program -ne 'Any' -or [string]$service.Service -ne 'Any' -or
        (Normalize-Values $ports.LocalPort) -cne (Normalize-Values $Spec.LocalPort) -or
        (Normalize-Values $addresses.LocalAddress) -cne (Normalize-Values $Spec.LocalAddress) -or
        (Normalize-Values $addresses.RemoteAddress) -cne (Normalize-Values $Spec.RemoteAddress) -or
        (Normalize-Values $interfaces.InterfaceAlias) -cne (Normalize-Values $Spec.InterfaceAlias)) {
        throw ('Firewall filter mismatch: ' + $Spec.Suffix)
    }
}

function Ensure-Rule($Spec) {
    $name = $Prefix + $Spec.Suffix
    if (-not (Get-NetFirewallRule -PolicyStore PersistentStore -Name $name -ErrorAction SilentlyContinue)) {
        $params = @{}
        foreach ($key in $Spec.Keys) { if ($key -ne 'Suffix') { $params[$key] = $Spec[$key] } }
        $null = New-NetFirewallRule @params -Name $name -DisplayName $name -Group $Group `
            -Enabled True -Direction Inbound -Protocol TCP -Profile Any -PolicyStore PersistentStore
    }
    Assert-Rule $Spec
}

# Rollback deliberately does NOT depend on current NIC state, UAC, WinRM,
# firewall profiles or the active certificate. It must work in a local console.
if ($Mode -eq 'Rollback') {
    $machine = Get-CimInstance Win32_ComputerSystem
    if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain) { throw 'Wrong recovery guest' }
    $state = Import-Clixml -LiteralPath $StatePath
    if ($state.Instance -cne $Instance) { throw 'Wrong recovery state' }
    foreach ($suffix in @('HTTPS-Allow','HTTP-Block','HTTPS-OtherNIC-Block',
        'HTTPS-OtherSource-Block','HTTPS-OtherAddress-Block','Console-Canary')) {
        $rule = Get-NetFirewallRule -Name ($Prefix + $suffix) -ErrorAction SilentlyContinue
        if ($rule) {
            if ($rule.Group -cne $Group) { throw 'Unowned recovery rule' }
            $rule | Remove-NetFirewallRule
        }
    }
    # NTLM message encryption preserves native bootstrap recovery without
    # re-enabling insecure authentication, even if the base image allowed it.
    Set-Item WSMan:\localhost\Service\Auth\Basic -Value $false
    Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $false
    if ($state.TokenPolicyPresent) {
        Set-ItemProperty $Policy LocalAccountTokenFilterPolicy -Value $state.TokenPolicy
    } else {
        Remove-ItemProperty $Policy LocalAccountTokenFilterPolicy -ErrorAction SilentlyContinue
    }
    $state.ConsoleNonce = ''
    $state.Phase = 'rolled-back'
    $state | Export-Clixml -LiteralPath $StatePath
    Write-Output 'WSLPE_OPERATOR_ROLLBACK=PASS'
    return
}

$Nics = Assert-Guest
$Certificate = Get-Certificate
if ($Mode -eq 'Inspect') {
    $operator = Get-LocalUser -Name kingdom.operator -ErrorAction SilentlyContinue
    $nat = @(Get-NetIPAddress -InterfaceIndex $Nics['000C292FD75B'].ifIndex -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike '169.254.*' })
    if ($nat.Count -ne 1) { throw 'NAT IPv4 ambiguous' }
    $info = @{
        Instance=$Instance; Certificate=[Convert]::ToBase64String($Certificate.RawData)
        Thumbprint=$Certificate.Thumbprint; OperatorExists=($null -ne $operator)
        NatAddress=$nat[0].IPAddress; Identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    }
    Write-Output ('WSLPE_OPERATOR_JSON=' + ($info | ConvertTo-Json -Compress))
    return
}

if ($Mode -eq 'Prepare') {
    if ($Nonce -cnotmatch '^[a-f0-9]{32}$' -or -not $SourceBase64) { throw 'Missing recovery binding' }
    Protect-Folder
    if (-not (Test-Path -LiteralPath $StatePath)) {
        if (@(Get-NetFirewallRule -Name ($Prefix + '*') -ErrorAction SilentlyContinue).Count) {
            throw 'Unjournaled management rules already exist'
        }
        $policyItem = Get-ItemProperty -Path $Policy
        $tokenProperty = $policyItem.PSObject.Properties['LocalAccountTokenFilterPolicy']
        $state = [pscustomobject]@{
            Instance=$Instance; Certificate=$Certificate.Thumbprint; Phase='prepared'; Nonce=$Nonce
            ConsoleNonce=''; Basic=(Get-WSBool 'WSMan:\localhost\Service\Auth\Basic')
            AllowUnencrypted=(Get-WSBool 'WSMan:\localhost\Service\AllowUnencrypted')
            TokenPolicyPresent=($null -ne $tokenProperty)
            TokenPolicy=$(if ($tokenProperty) { [int]$tokenProperty.Value } else { 0 })
        }
        $state | Export-Clixml -LiteralPath $StatePath
        [IO.File]::WriteAllBytes($ScriptPath, [Convert]::FromBase64String($SourceBase64))
    }
    $state = Read-State
    if ($state.Nonce -cne $Nonce -or
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($ScriptPath)) -cne $SourceBase64) {
        throw 'Existing recovery transaction differs; preserve it and inspect'
    }
    if (-not (Get-WSBool 'WSMan:\localhost\Service\Auth\Negotiate')) {
        throw 'Existing NTLM/Negotiate bootstrap is not enabled'
    }
    # Documented requirement for an administrative workgroup WinRM account.
    # EnableLUA stays 1. Basic and plaintext are never enabled by this repair.
    Set-ItemProperty $Policy LocalAccountTokenFilterPolicy -Type DWord -Value 1
    Set-Item WSMan:\localhost\Service\Auth\Basic -Value $false
    Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $false
    Ensure-Rule (Rule-Specs $Nics)[0]
    Write-Output 'WSLPE_OPERATOR_PREPARED=PASS'
    return
}

$state = Read-State
if ($Nonce -cne $state.Nonce -or $Nonce -cnotmatch '^[a-f0-9]{32}$') { throw 'Recovery nonce mismatch' }
if ($Mode -eq 'ConsoleCheck') {
    if ((Get-Process -Id $PID).SessionId -eq 0 -or (Test-Path Variable:PSSenderInfo)) {
        throw 'Run this in elevated PowerShell in the VMware console, independently of WinRM'
    }
    if (-not (Test-Path -LiteralPath $ScriptPath)) { throw 'Local rollback script missing' }
    # Exercise the same firewall write/delete capability rollback needs, without
    # removing any active protection or disrupting a working management path.
    $name = $Prefix + 'Console-Canary'
    if (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue) { throw 'Unexpected recovery canary' }
    try {
        $null = New-NetFirewallRule -Name $name -DisplayName $name -Group $Group `
            -Direction Inbound -Action Block -Protocol TCP -LocalPort 9 -Enabled False
        Get-NetFirewallRule -Name $name | Remove-NetFirewallRule
        if (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue) { throw 'Console recovery check failed' }
    } finally {
        Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
    $state.ConsoleNonce = $Nonce
    $state | Export-Clixml -LiteralPath $StatePath
    Write-Output 'WSLPE_OPERATOR_CONSOLE=PASS'
    return
}

if ([Security.Principal.WindowsIdentity]::GetCurrent().Name -ine 'WSLPE-WS01\kingdom.operator') {
    throw 'Handoff must run through a newly authenticated kingdom.operator session'
}
if ($state.ConsoleNonce -cne $Nonce) { throw 'Independent console recovery check is pending' }
if ($Mode -eq 'Harden') {
    foreach ($spec in (Rule-Specs $Nics)) { Ensure-Rule $spec }
    $state.Phase = 'hardened'
    $state | Export-Clixml -LiteralPath $StatePath
}
foreach ($spec in (Rule-Specs $Nics)) { Assert-Rule $spec }
if ((Get-WSBool 'WSMan:\localhost\Service\Auth\Basic') -or
    (Get-WSBool 'WSMan:\localhost\Service\AllowUnencrypted')) { throw 'Insecure WinRM authentication enabled' }
Write-Output 'WSLPE_OPERATOR_POLICY=PASS'
