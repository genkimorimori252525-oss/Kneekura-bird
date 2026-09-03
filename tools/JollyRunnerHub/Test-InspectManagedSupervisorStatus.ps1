Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Join-Path ([IO.Path]::GetTempPath()) ('JollySupervisorDiag-' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Force -Path $root | Out-Null

    [ordered]@{
        version = 1
        profiles = @()
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root 'profiles.json') -Encoding UTF8

    $offsetStamp = [DateTimeOffset]::UtcNow.AddSeconds(-8).ToOffset([TimeSpan]::FromHours(-7)).ToString('o')
    [ordered]@{
        schema = 'jolly.managed-supervisor'
        version = 1
        processId = 4321
        updatedAt = $offsetStamp
        profiles = @()
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root 'supervisor-status.json') -Encoding UTF8

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

    if ([string]$diag.schema -ne 'jolly.managed-supervisor-diagnostic' -or [int]$diag.version -ne 2) {
        throw 'Supervisor diagnostic schema/version mismatch.'
    }
    if ([int]$diag.supervisorProcessId -ne 4321) { throw 'Supervisor diagnostic process id mismatch.' }
    if ($null -eq $diag.statusAgeSeconds -or [int]$diag.statusAgeSeconds -lt 0 -or [int]$diag.statusAgeSeconds -gt 30) {
        throw ('Offset-aware heartbeat age was not bounded: ' + [string]$diag.statusAgeSeconds)
    }
    if (@($diag.recentEvents).Count -ne 2) { throw 'Generic recent event projection mismatch.' }
    if ([string]$diag.recentEvents[0].profileId -ne 'runner-a') { throw 'Profile event was not preserved.' }
    if ($null -ne $diag.PSObject.Properties['recentKneekuraEvents']) { throw 'Project-specific diagnostic event field must not return.' }

    [ordered]@{
        schema = 'jolly.managed-supervisor'
        version = 1
        processId = 4321
        updatedAt = 'not-a-time'
        profiles = @()
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root 'supervisor-status.json') -Encoding UTF8

    $output = @(& $inspect -AppRoot $root)
    $line = @($output | Where-Object { [string]$_ -like 'SUPERVISOR_DIAG=*' } | Select-Object -Last 1)
    $diag = ([string]$line[0]).Substring('SUPERVISOR_DIAG='.Length) | ConvertFrom-Json
    if ($null -ne $diag.statusAgeSeconds) { throw 'Malformed heartbeat timestamp must produce null age.' }

    Write-Host 'managed supervisor diagnostic tests: ok'
}
finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
