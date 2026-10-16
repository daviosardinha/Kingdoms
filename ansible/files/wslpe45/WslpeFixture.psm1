# Standalone WSLPE advanced/expert fixture ownership library.
# Deliberately contains no top-level actions: import does not touch Windows.
# Designed for exact WSLPE-WS01 workgroup machine only.
Set-StrictMode -Version Latest

function Assert-Wslpe45Identity {
    [CmdletBinding()]
    param()
    $ErrorActionPreference = 'Stop'
    $machine = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop

    if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or [bool]$machine.PartOfDomain) {
        throw 'WSLPE fixture refuses unexpected hostname or domain-joined machine'
    }
    if ([string]$os.Caption -notmatch 'Windows 10' -or [int]$os.ProductType -ne 1) {
        throw 'WSLPE fixture requires standalone Windows 10 workstation'
    }
    $learner = Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
    if (-not $learner.Enabled) {
        throw 'WSLPE fixture refuses disabled local learner'
    }
    $administrators = Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
    $members = @(Get-LocalGroupMember -Group $administrators.Name -ErrorAction Stop)
    foreach ($member in $members) {
        if ($member.SID.Value -eq $learner.SID.Value) {
            throw 'WSLPE learner must remain non-administrator'
        }
    }
    return [pscustomobject]@{
        Machine = 'WSLPE-WS01'
        LearnerSid = $learner.SID.Value
        DomainJoined = $false
        Platform = 'Windows 10'
    }
}

function Get-Wslpe45FixturePath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][ValidatePattern('^[a-z_]+$')][string]$Id
    )
    if ($Id -in @('north', 'goad', 'ws01', 'domain', 'system32')) {
        throw 'Reserved WSLPE fixture name'
    }
    # Fixed trusted parent; never take arbitrary user-supplied absolute paths.
    return [System.IO.Path]::GetFullPath(
        [System.IO.Path]::Combine('C:\ProgramData\KingdomsWSLPE45', 'fixtures', $Id)
    )
}

function Assert-Wslpe45NoReparsePoints {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$Path)

    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $root = [System.IO.Path]::GetFullPath('C:\ProgramData\KingdomsWSLPE45\fixtures').TrimEnd('\')
    if (-not $full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'WSLPE fixture path escapes the dedicated fixtures root'
    }

    $cursor = $full
    while ($cursor -and $cursor.Length -ge 3) {
        if (Test-Path -LiteralPath $cursor) {
            $attrs = [System.IO.File]::GetAttributes($cursor)
            if (($attrs -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'WSLPE fixture path includes a reparse point'
            }
        }
        $cursor = Split-Path -Path $cursor -Parent
    }
    if (Test-Path -LiteralPath $full -PathType Container) {
        foreach ($entry in (Get-ChildItem -LiteralPath $full -Recurse -Force -ErrorAction Stop)) {
            if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'WSLPE fixture contains a reparse point; refusing recursive cleanup'
            }
        }
    }
}

function New-Wslpe45OwnedFixture {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateRange(21,45)][int]$Number,
        [Parameter(Mandatory=$true)][ValidatePattern('^[a-z_]+$')][string]$Id
    )
    $identity = Assert-Wslpe45Identity
    $root = Get-Wslpe45FixturePath -Id $Id
    Assert-Wslpe45NoReparsePoints -Path $root
    if (Test-Path -LiteralPath $root) {
        throw 'Fixture already exists; never silently overwrite or adopt pre-existing objects'
    }
    $fixturesRoot = Split-Path -Path $root -Parent
    New-Item -ItemType Directory -Path $fixturesRoot -Force -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
    $metadata = [ordered]@{
        schema = 'kingdoms.wslpe.fixture-owner.v1'
        machine = $identity.Machine
        number = $Number
        id = $Id
        learner_sid = $identity.LearnerSid
        created_utc = [DateTime]::UtcNow.ToString('o')
    }
    $metadata | ConvertTo-Json -Compress -Depth 4 |
        Set-Content -LiteralPath (Join-Path $root '.kingdoms-owned.json') -Encoding UTF8 -ErrorAction Stop
    return $root
}

function Assert-Wslpe45OwnedFixture {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateRange(21,45)][int]$Number,
        [Parameter(Mandatory=$true)][ValidatePattern('^[a-z_]+$')][string]$Id
    )
    $identity = Assert-Wslpe45Identity
    $root = Get-Wslpe45FixturePath -Id $Id
    Assert-Wslpe45NoReparsePoints -Path $root
    $marker = Join-Path $root '.kingdoms-owned.json'
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
        throw 'Missing fixture ownership marker'
    }
    $owner = Get-Content -LiteralPath $marker -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    if ($owner.schema -cne 'kingdoms.wslpe.fixture-owner.v1' -or
        $owner.machine -cne 'WSLPE-WS01' -or
        [int]$owner.number -ne $Number -or
        $owner.id -cne $Id -or
        $owner.learner_sid -cne $identity.LearnerSid) {
        throw 'Fixture ownership does not match exact standalone guest'
    }
    return $root
}

function Remove-Wslpe45OwnedFixture {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateRange(21,45)][int]$Number,
        [Parameter(Mandatory=$true)][ValidatePattern('^[a-z_]+$')][string]$Id
    )
    # Caller is responsible for deleting only its explicitly named service,
    # task, COM registration, or other dedicated external resources *first*.
    # This method deliberately never removes an arbitrary path or Windows object.
    $root = Assert-Wslpe45OwnedFixture -Number $Number -Id $Id
    Assert-Wslpe45NoReparsePoints -Path $root
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction Stop
    if (Test-Path -LiteralPath $root) { throw 'Fixture directory still exists after reset' }
}

Export-ModuleMember -Function @(
    'Assert-Wslpe45Identity',
    'Get-Wslpe45FixturePath',
    'Assert-Wslpe45NoReparsePoints',
    'New-Wslpe45OwnedFixture',
    'Assert-Wslpe45OwnedFixture',
    'Remove-Wslpe45OwnedFixture'
)
