Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Join-Path ([IO.Path]::GetTempPath()) ('JollySupervisorRuntime-' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    foreach ($name in @(
        'RunnerConfig.ps1','RunnerControlState.ps1','RunnerDispatchWatch.ps1','RunnerDispatchProbe.ps1',
        'RunnerConnectionState.ps1','ManagedRunnerSupervisorCore.ps1','RunnerRootResolver.ps1','RunnerMaintenance.ps1'
    )) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $root $name) -Force
    }

    $config = [ordered]@{
        version=7
        autoConnect=$false
        profiles=@(
            [ordered]@{
                id='runtime-test-a'
                name='Runtime Test A'
                repoUrl='https://github.com/example/example-a'
                runnerRoot=(Join-Path $root 'missing-runner-a')
                dispatchWatchEnabled=$true
                dispatchAutoRecover=$true
                dispatchWarnSeconds=45
                dispatchRecoverSeconds=180
                dispatchProbeMaxAgeSeconds=45
                routingLabels=@('self-hosted','Windows','X64','runtime-test-a')
            },
            [ordered]@{
                id='runtime-test-b'
                name='Runtime Test B'
                repoUrl='https://github.com/example/example-b'
                runnerRoot=(Join-Path $root 'missing-runner-b')
                dispatchWatchEnabled=$true
                dispatchAutoRecover=$true
                dispatchWarnSeconds=45
                dispatchRecoverSeconds=180
                dispatchProbeMaxAgeSeconds=45
                routingLabels=@('self-hosted','Windows','X64','runtime-test-b')
            }
        )
    }
    $json = $config | ConvertTo-Json -Depth 10
    $json | Set-Content -LiteralPath (Join-Path $root 'profiles.default.json') -Encoding UTF8
    $json | Set-Content -LiteralPath (Join-Path $root 'profiles.json') -Encoding UTF8

    $supervisor = Join-Path $PSScriptRoot 'ManagedRunnerSupervisor.ps1'
    $supervisorSource = Get-Content -LiteralPath $supervisor -Raw -Encoding UTF8
    $reconnectMarker = "elseif ([string]`$decision.Action -eq 'reconnect') {"
    $cycleMarker = '$cycleProfiles += [pscustomobject]@{'
    $reconnectStart = $supervisorSource.IndexOf($reconnectMarker,[StringComparison]::Ordinal)
    if ($reconnectStart -lt 0) { throw 'Supervisor reconnect branch start marker was not found.' }
    $reconnectEnd = $supervisorSource.IndexOf($cycleMarker,$reconnectStart,[StringComparison]::Ordinal)
    if ($reconnectEnd -lt 0) { throw 'Supervisor reconnect branch end marker was not found.' }
    $reconnectBody = $supervisorSource.Substring($reconnectStart,$reconnectEnd-$reconnectStart)
    if ($reconnectBody -notmatch 'Stop-SupervisorRunner\s+\$effectiveProfile') { throw 'Reconnect must stop the resolved effective profile.' }
    if ($reconnectBody -notmatch 'Start-SupervisorRunner\s+\$effectiveProfile') { throw 'Reconnect must start the resolved effective profile.' }
    if ($reconnectBody -match '(Stop|Start)-SupervisorRunner\s+\$profile(?:\s|$)') { throw 'Reconnect must never target the stale configured profile root.' }

    $process = Start-Process powershell.exe -ArgumentList @(
        '-NoProfile','-ExecutionPolicy','Bypass','-File',('"{0}"' -f $supervisor),
        '-AppRoot',('"{0}"' -f $root),'-IntervalSeconds','5',
        '-MutexName',('Local\JollyRunnerHub-Test-' + [guid]::NewGuid().ToString('N')),'-Once'
    ) -PassThru -Wait -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "Supervisor runtime test exit=$($process.ExitCode)" }

    $statusPath = Join-Path $root 'supervisor-status.json'
    if (-not (Test-Path -LiteralPath $statusPath -PathType Leaf)) { throw 'Supervisor status was not written.' }
    $status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$status.schema -ne 'jolly.managed-supervisor') { throw 'Supervisor status schema mismatch.' }
    if ([int]$status.version -ne 2) { throw 'Supervisor status version mismatch.' }
    if (@($status.profiles).Count -ne 2) { throw 'Supervisor runtime profile count mismatch.' }
    $profiles = @($status.profiles)
    if (($profiles.id -join ',') -ne 'runtime-test-a,runtime-test-b') { throw 'Supervisor runtime profile ids mismatch.' }
    foreach ($profile in $profiles) {
        if ([string]$profile.desiredState -ne 'stopped') { throw 'autoConnect=false must default desired state to stopped.' }
        if ([bool]$profile.configured) { throw 'Missing fixture runner must remain unconfigured.' }
        if ([string]$profile.action -ne 'none') { throw 'Unconfigured fixture must not trigger a process action.' }
    }
    Write-Host 'managed runner supervisor runtime tests: ok'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
