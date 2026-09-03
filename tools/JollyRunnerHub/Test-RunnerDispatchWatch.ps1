Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RunnerDispatchWatch.ps1')
. (Join-Path $PSScriptRoot 'RunnerConnectionState.ps1')

function Assert-True([bool]$Condition,[string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Assert-Equal($Expected,$Actual,[string]$Message) {
    if ([string]$Expected -ne [string]$Actual) {
        throw "$Message expected=$Expected actual=$Actual"
    }
}

Assert-True (Test-JollyDispatchLabelsEligible -RequiredLabels @('self-hosted','Windows','X64','kneekura') -RunnerLabels @('X64','kneekura','Windows','self-hosted')) 'label subset should be case-insensitive/order-independent'
Assert-True (-not (Test-JollyDispatchLabelsEligible -RequiredLabels @('self-hosted','Windows','X64','kneekura') -RunnerLabels @('self-hosted','Windows','X64'))) 'missing custom label must reject routing'

$readyProbe = [pscustomobject]@{apiOk=$true;error='';routeCandidateCount=1;runnerFound=$true;runnerStatus='online';runnerBusy=$false;eligibleQueuedCount=0;assignedQueuedCount=0;oldestQueuedSeconds=0}
$ready = Get-JollyDispatchClassification -LocalCode listening -Probe $readyProbe -WarnSeconds 45 -RecoverSeconds 180
Assert-Equal 'ready' $ready.Code 'ready classification'

$slowProbe = [pscustomobject]@{apiOk=$true;error='';routeCandidateCount=1;runnerFound=$true;runnerStatus='online';runnerBusy=$false;eligibleQueuedCount=2;assignedQueuedCount=0;oldestQueuedSeconds=80}
$slow = Get-JollyDispatchClassification -LocalCode listening -Probe $slowProbe -WarnSeconds 45 -RecoverSeconds 180
Assert-Equal 'dispatch_slow' $slow.Code 'slow classification'
Assert-True (-not $slow.CanRecover) 'slow queue must not auto-recover yet'

$stalledProbe = [pscustomobject]@{apiOk=$true;error='';routeCandidateCount=1;runnerFound=$true;runnerStatus='online';runnerBusy=$false;eligibleQueuedCount=5;assignedQueuedCount=0;oldestQueuedSeconds=240}
$stalled = Get-JollyDispatchClassification -LocalCode listening -Probe $stalledProbe -WarnSeconds 45 -RecoverSeconds 180
Assert-Equal 'dispatch_stalled' $stalled.Code 'stalled classification'
Assert-True $stalled.CanRecover 'stalled eligible queue should allow safe reconnect'

$busyProbe = [pscustomobject]@{apiOk=$true;error='';routeCandidateCount=1;runnerFound=$true;runnerStatus='online';runnerBusy=$true;eligibleQueuedCount=4;assignedQueuedCount=0;oldestQueuedSeconds=500}
$busy = Get-JollyDispatchClassification -LocalCode listening -Probe $busyProbe -WarnSeconds 45 -RecoverSeconds 180
Assert-Equal 'running' $busy.Code 'busy runner must win over stale queue'
Assert-True (-not $busy.CanRecover) 'busy runner must never be restarted'

$ghost = Get-JollyDispatchClassification -LocalCode reconnecting -Probe $stalledProbe -WarnSeconds 45 -RecoverSeconds 180
Assert-Equal 'ghost_online' $ghost.Code 'fresh online API with broken local listener should be ghost-online'
Assert-True $ghost.CanRecover 'fresh ghost online with old eligible queue should be recoverable'

# Live regression: a reconnect marker from an old _diag file must not remain a
# permanent ghost-online signal just because Runner.Listener is still alive.
$now = [datetime]::UtcNow
$staleLocal = Get-JollyRunnerConnectionState -ProcessRunning $true -LogLines @('runner connect error fixture') `
    -LogUpdatedAtUtc $now.AddSeconds(-300) -NowUtc $now -GitHubStatus unknown -StaleAfterSeconds 120
Assert-Equal 'stale_diagnostics' $staleLocal.Code 'old reconnect marker must age into stale diagnostics'
$freshLocal = Get-JollyRunnerConnectionState -ProcessRunning $true -LogLines @('runner connect error fixture') `
    -LogUpdatedAtUtc $now.AddSeconds(-30) -NowUtc $now -GitHubStatus unknown -StaleAfterSeconds 120
Assert-Equal 'reconnecting' $freshLocal.Code 'fresh reconnect marker must remain reconnecting'

$staleReady = Get-JollyDispatchClassification -LocalCode stale_diagnostics -Probe $readyProbe -WarnSeconds 45 -RecoverSeconds 180
Assert-Equal 'ready' $staleReady.Code 'stale local reconnect evidence must not create ghost-online with healthy API and empty queue'
Assert-True (-not $staleReady.CanRecover) 'stale diagnostics alone must never trigger reconnect'
Assert-True ([string]$staleReady.Evidence -match 'stale local diagnostics ignored') 'ready evidence must disclose stale local diagnostics'

$staleStalled = Get-JollyDispatchClassification -LocalCode stale_diagnostics -Probe $stalledProbe -WarnSeconds 45 -RecoverSeconds 180
Assert-Equal 'dispatch_stalled' $staleStalled.Code 'real old eligible queue must remain recoverable even when local diagnostics are stale'
Assert-True $staleStalled.CanRecover 'stale diagnostics must not disable genuine guarded dispatch recovery'

$duplicateProbe = [pscustomobject]@{apiOk=$true;error='';routeCandidateCount=2;runnerFound=$true;runnerStatus='online';runnerBusy=$false;eligibleQueuedCount=0;assignedQueuedCount=0;oldestQueuedSeconds=0}
$duplicate = Get-JollyDispatchClassification -LocalCode listening -Probe $duplicateProbe -WarnSeconds 45 -RecoverSeconds 180
Assert-Equal 'route_duplicate' $duplicate.Code 'duplicate route classification'
Assert-True (-not $duplicate.CanRecover) 'duplicate route is not fixed by listener restart'

$missingProbe = [pscustomobject]@{apiOk=$true;error='';routeCandidateCount=0;runnerFound=$false;runnerStatus='unknown';runnerBusy=$false;eligibleQueuedCount=1;assignedQueuedCount=0;oldestQueuedSeconds=300}
$missing = Get-JollyDispatchClassification -LocalCode listening -Probe $missingProbe -WarnSeconds 45 -RecoverSeconds 180
Assert-Equal 'registration_missing' $missing.Code 'missing registration classification'

# Regression for the two Windows PowerShell process-adapter failures seen live:
# 1) empty redirected stderr can become $null under Get-Content -Raw;
# 2) Start-Process may expose no usable ExitCode even after the process exits.
# A valid JSON response must still be accepted when ExitCode is unavailable.
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('JollyDispatchProbeTest-' + [guid]::NewGuid().ToString('N'))
$oldPath = $env:PATH
try {
    $bin = Join-Path $tempRoot 'bin'
    $runnerRoot = Join-Path $tempRoot 'runner'
    $successOutput = Join-Path $tempRoot 'probe-success.json'
    $failureOutput = Join-Path $tempRoot 'probe-failure.json'
    New-Item -ItemType Directory -Force -Path $bin,$runnerRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $runnerRoot 'run.cmd') -Value '@echo off' -Encoding ASCII
    [ordered]@{agentName='dispatch-fixture';gitHubUrl='https://github.com/example/fixture'} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runnerRoot '.runner') -Encoding UTF8

    # Keep only the fake gh plus Windows system tools; this prevents a globally
    # installed gh.exe from winning Get-Command gh.exe during the child probe.
    $env:PATH = $bin + [IO.Path]::PathSeparator + (Join-Path $env:WINDIR 'System32') + [IO.Path]::PathSeparator + $env:WINDIR
    $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $probeScript = Join-Path $PSScriptRoot 'RunnerDispatchProbe.ps1'

    # gh.cmd is intentionally a shell-associated command because that is one of
    # the cases where PowerShell 5.1 can leave Process.ExitCode unavailable.
    Set-Content -LiteralPath (Join-Path $bin 'gh.cmd') -Value @(
        '@echo off',
        'echo %* | findstr /L /C:"actions/runners" >nul',
        'if %errorlevel%==0 (',
        '  echo {"runners":[]}',
        '  exit /b 0',
        ')',
        'echo %* | findstr /L /C:"actions/runs?status=queued" >nul',
        'if %errorlevel%==0 (',
        '  echo {"workflow_runs":[]}',
        '  exit /b 0',
        ')',
        'echo {"jobs":[]}',
        'exit /b 0'
    ) -Encoding ASCII

    & $powershell -NoProfile -ExecutionPolicy Bypass -File $probeScript `
        -Repository 'example/fixture' -RunnerRoot $runnerRoot -OutputPath $successOutput -TimeoutSeconds 2
    Assert-Equal 0 $LASTEXITCODE 'valid JSON gh probe should complete without crashing'
    Assert-True (Test-Path -LiteralPath $successOutput -PathType Leaf) 'valid JSON gh probe must write output JSON'
    $successResult = Get-Content -LiteralPath $successOutput -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True ([bool]$successResult.apiOk) 'valid gh JSON must be accepted even when Process.ExitCode is unavailable'
    Assert-True ([string]::IsNullOrWhiteSpace([string]$successResult.error)) 'successful fake gh probe must not retain an adapter error'

    Set-Content -LiteralPath (Join-Path $bin 'gh.cmd') -Value @('@echo off','exit /b 1') -Encoding ASCII
    & $powershell -NoProfile -ExecutionPolicy Bypass -File $probeScript `
        -Repository 'example/fixture' -RunnerRoot $runnerRoot -OutputPath $failureOutput -TimeoutSeconds 2
    Assert-Equal 0 $LASTEXITCODE 'failed gh probe should still publish diagnostic JSON without crashing'
    Assert-True (Test-Path -LiteralPath $failureOutput -PathType Leaf) 'failed gh probe must write output JSON'
    $failureResult = Get-Content -LiteralPath $failureOutput -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True (-not [bool]$failureResult.apiOk) 'fake gh failure must remain apiOk=false'
    Assert-True ([string]$failureResult.error -match '^gh (?:exit=1|exit unavailable): no stderr$') 'empty stderr must normalize to a bounded gh failure diagnostic'
    Assert-True ([string]$failureResult.error -notmatch 'Length') 'empty stderr must never produce the StrictMode Length exception'
}
finally {
    $env:PATH = $oldPath
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host 'runner dispatch watch tests: ok'
