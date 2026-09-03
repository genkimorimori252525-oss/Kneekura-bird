Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Join-Path ([IO.Path]::GetTempPath()) ('JollySupervisorDiag-' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Force -Path $root | Out-Null

    $runnerRoot = Join-Path $root 'runner-fixture'
    New-Item -ItemType Directory -Force -Path $runnerRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $runnerRoot 'run.cmd') -Value '@echo off' -Encoding ASCII
    [ordered]@{
        agentName = 'runner-fixture'
        gitHubUrl = 'https://github.com/example/diag-runner'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runnerRoot '.runner') -Encoding UTF8

    [ordered]@{
        version = 1
        profiles = @(
            [ordered]@{
                id = 'diag-runner'
                name = 'Diagnostic Runner'
                repoUrl = 'https://github.com/example/diag-runner'
                runnerRoot = $runnerRoot
            }
        )
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root 'profiles.json') -Encoding UTF8

    $offsetStamp = [DateTimeOffset]::UtcNow.AddSeconds(-8).ToOffset([TimeSpan]::FromHours(-7)).ToString('o')
    [ordered]@{
        schema = 'jolly.managed-supervisor'
        version = 1
        processId = 4321
        updatedAt = $offsetStamp
        profiles = @()
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root 'supervisor-status.json') -Encoding UTF8

    $dispatchRoot = Join-Path $root 'dispatch'
    New-Item -ItemType Directory -Force -Path $dispatchRoot | Out-Null
    [ordered]@{
        schema = 'jolly.dispatch-probe'
        version = 1
        repository = 'example/diag-runner'
        apiOk = $false
        error = 'gh exit=4: authentication failed for github_pat_TEST_SECRET_123456789'
        probedAt = ([DateTimeOffset]::UtcNow.AddSeconds(-4).ToString('o'))
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $dispatchRoot 'dispatch-diag-runner.json') -Encoding UTF8

    $events = @(
        ([ordered]@{timestamp=([DateTimeOffset]::UtcNow.AddSeconds(-3).ToString('o'));profileId='runner-a';action='start';result='issued';reason='fixture'} | ConvertTo-Json -Compress),
        ([ordered]@{timestamp=([DateTimeOffset]::UtcNow.AddSeconds(-2).ToString('o'));profileId='';action='cycle';result='ok';reason='fixture-global'} | ConvertTo-Json -Compress)
    )
    Set-Content -LiteralPath (Join-Path $root 'managed-supervisor.jsonl') -Value $events -Encoding UTF8

    $inspect = Join-Path $PSScriptRoot 'Inspect-ManagedSupervisorStatus.ps1'
    $output = @(& $inspect -AppRoot $root)
    $line = @($output | Where-Object { [string]$_ -like 'SUPERVISOR_DIAG=*' } | Select-Object -Last 1)
    if ($line.Count -ne 1) { throw 'Supervisor diagnostic output marker was not emitted exactly once.' }
    $diag = ([string]$line[0]).Substring('SUPERVISOR_DIAG='.Length) | ConvertFrom-Json

    if ([string]$diag.schema -ne 'jolly.managed-supervisor-diagnostic' -or [int]$diag.version -ne 3) {
        throw 'Supervisor diagnostic schema/version mismatch.'
    }
    if ([int]$diag.supervisorProcessId -ne 4321) { throw 'Supervisor diagnostic process id mismatch.' }
    if ($null -eq $diag.statusAgeSeconds -or [int]$diag.statusAgeSeconds -lt 0 -or [int]$diag.statusAgeSeconds -gt 30) {
        throw ('Offset-aware heartbeat age was not bounded: ' + [string]$diag.statusAgeSeconds)
    }
    if (@($diag.recentEvents).Count -ne 2) { throw 'Generic recent event projection mismatch.' }
    if ([string]$diag.recentEvents[0].profileId -ne 'runner-a') { throw 'Profile event was not preserved.' }
    if ($null -ne $diag.PSObject.Properties['recentKneekuraEvents']) { throw 'Project-specific diagnostic event field must not return.' }

    $profile = @($diag.profiles | Where-Object { [string]$_.id -eq 'diag-runner' }) | Select-Object -First 1
    if ($null -eq $profile) { throw 'Configured diagnostic profile was not projected.' }
    if ([string]$profile.binding -ne 'configured') { throw 'Configured diagnostic profile binding mismatch.' }
    if ([string]$profile.configuredRootLeaf -ne 'runner-fixture' -or [string]$profile.effectiveRootLeaf -ne 'runner-fixture') {
        throw 'Diagnostic profile root leaf projection mismatch.'
    }
    if ([bool]$profile.dispatchProbePresent -ne $true -or [bool]$profile.dispatchProbeApiOk -ne $false) {
        throw 'Dispatch probe health projection mismatch.'
    }
    if ([string]$profile.dispatchProbeError -notmatch '<redacted-token>' -or [string]$profile.dispatchProbeError -match 'TEST_SECRET') {
        throw 'Dispatch probe diagnostic did not redact token-like content.'
    }
    if ($null -eq $profile.dispatchProbeAgeSeconds -or [int]$profile.dispatchProbeAgeSeconds -gt 30) {
        throw 'Dispatch probe age projection mismatch.'
    }

    $candidate = @($diag.candidates | Where-Object { [string]$_.repository -eq 'example/diag-runner' }) | Select-Object -First 1
    if ($null -eq $candidate -or [string]$candidate.rootLeaf -ne 'runner-fixture') {
        throw 'Diagnostic candidate root leaf projection mismatch.'
    }

    [ordered]@{
        schema = 'jolly.managed-supervisor'
        version = 1
        processId = 4321
        updatedAt = 'not-a-time'
        profiles = @()
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root 'supervisor-status.json') -Encoding UTF8

    $output = @(& $inspect -AppRoot $root)
    $line = @($output | Where-Object { [string]$_ -like 'SUPERVISOR_DIAG=*' } | Select-Object -Last 1)
    if ($line.Count -ne 1) { throw 'Supervisor diagnostic output marker was not emitted on malformed timestamp case.' }
    $diag = ([string]$line[0]).Substring('SUPERVISOR_DIAG='.Length) | ConvertFrom-Json
    if ($null -ne $diag.statusAgeSeconds) { throw 'Malformed heartbeat timestamp must produce null age.' }

    Write-Host 'managed supervisor diagnostic tests: ok'
}
finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
