# Offline contract for the private WinRS native transport gate.
# It is never run by untrusted PR code on a public self-hosted runner.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\..\ansible\files\north-parent-winrs.ps1"

$names = @('GITHUB_ACTIONS','RUNNER_ENVIRONMENT','GITHUB_REPOSITORY',
           'KINGDOMS_TEST_NORTH_WINRS','KINGDOMS_NORTH_PRIVATE_WINRS_RUNNER',
           'COMPUTERNAME')
$old = @{}
foreach ($name in $names) {
    $old[$name] = [Environment]::GetEnvironmentVariable($name,'Process')
}
try {
    $env:GITHUB_ACTIONS = 'true'
    $env:RUNNER_ENVIRONMENT = 'self-hosted'
    $env:GITHUB_REPOSITORY = 'daviosardinha/Kingdoms-WinRS-CI'
    $env:KINGDOMS_TEST_NORTH_WINRS = '1'
    $env:KINGDOMS_NORTH_PRIVATE_WINRS_RUNNER = '1'
    $env:COMPUTERNAME = 'NK-WINRS-CI'
    if (-not (Test-NorthParentWinRSCiFixture)) {
        throw 'Explicit private fixture should be accepted'
    }

    foreach ($invalid in @(
        @{ GITHUB_REPOSITORY='daviosardinha/Kingdoms' },
        @{ COMPUTERNAME='WINTERFELL' },
        @{ COMPUTERNAME='KINGSLANDING' },
        @{ COMPUTERNAME='NK-OTHER-CI' },
        @{ KINGDOMS_NORTH_PRIVATE_WINRS_RUNNER='0' },
        @{ RUNNER_ENVIRONMENT='untrusted' }
    )) {
        $changed = @()
        foreach ($key in $invalid.Keys) {
            $changed += @($key, [Environment]::GetEnvironmentVariable($key,'Process'))
            [Environment]::SetEnvironmentVariable($key,$invalid[$key],'Process')
        }
        try {
            if (Test-NorthParentWinRSCiFixture) {
                throw 'Unexpected fixture eligibility granted'
            }
        } finally {
            for ($i=0; $i -lt $changed.Count; $i+=2) {
                [Environment]::SetEnvironmentVariable($changed[$i],$changed[$i+1],'Process')
            }
        }
    }

    $env:RUNNER_ENVIRONMENT = 'github-hosted'
    $env:GITHUB_REPOSITORY = 'daviosardinha/Kingdoms'
    $env:COMPUTERNAME = 'WINTERFELL'
    if (Test-NorthParentWinRSCiFixture) {
        throw 'A training guest must never qualify as a CI runner'
    }
    $env:COMPUTERNAME = 'github-ci'
    if (-not (Test-NorthParentWinRSCiFixture)) {
        throw 'Original hosted disposable fixture allowance must be preserved'
    }
    Write-Output 'NORTH_PRIVATE_WINRS_FIXTURE_GATE=PASS'
} finally {
    foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name,$old[$name],'Process')
    }
}
