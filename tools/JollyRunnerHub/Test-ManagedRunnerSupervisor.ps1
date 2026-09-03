Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ManagedRunnerSupervisorCore.ps1')

function Assert-Decision([string]$Expected,$Decision,[string]$Message) {
    if ([string]$Decision.Action -ne $Expected) { throw "$Message expected=$Expected actual=$($Decision.Action) reason=$($Decision.Reason)" }
}

Assert-Decision 'none' (Get-JollyManagedSupervisorDecision -Configured $false -DesiredState running -ProcessRunning $false -LocalCode stopped -DispatchCode probe_pending -DispatchCanRecover $false -RunnerBusy $false -ConsecutiveRecoverableProbes 0 -MinutesSinceLastAttempt 999 -AttemptsInWindow 0) 'unconfigured runner'
Assert-Decision 'none' (Get-JollyManagedSupervisorDecision -Configured $true -DesiredState stopped -ProcessRunning $false -LocalCode stopped -DispatchCode github_offline -DispatchCanRecover $false -RunnerBusy $false -ConsecutiveRecoverableProbes 0 -MinutesSinceLastAttempt 999 -AttemptsInWindow 0) 'manual stop'
Assert-Decision 'start' (Get-JollyManagedSupervisorDecision -Configured $true -DesiredState running -ProcessRunning $false -LocalCode stopped -DispatchCode github_offline -DispatchCanRecover $false -RunnerBusy $false -ConsecutiveRecoverableProbes 0 -MinutesSinceLastAttempt 999 -AttemptsInWindow 0) 'missing listener'
Assert-Decision 'none' (Get-JollyManagedSupervisorDecision -Configured $true -DesiredState running -ProcessRunning $true -LocalCode running_job -DispatchCode dispatch_stalled -DispatchCanRecover $true -RunnerBusy $true -ConsecutiveRecoverableProbes 9 -MinutesSinceLastAttempt 999 -AttemptsInWindow 0) 'busy runner'
Assert-Decision 'none' (Get-JollyManagedSupervisorDecision -Configured $true -DesiredState running -ProcessRunning $true -LocalCode listening -DispatchCode dispatch_stalled -DispatchCanRecover $true -RunnerBusy $false -ConsecutiveRecoverableProbes 1 -MinutesSinceLastAttempt 999 -AttemptsInWindow 0) 'single bad probe'
Assert-Decision 'reconnect' (Get-JollyManagedSupervisorDecision -Configured $true -DesiredState running -ProcessRunning $true -LocalCode listening -DispatchCode dispatch_stalled -DispatchCanRecover $true -RunnerBusy $false -ConsecutiveRecoverableProbes 2 -MinutesSinceLastAttempt 11 -AttemptsInWindow 0) 'stalled route'
Assert-Decision 'none' (Get-JollyManagedSupervisorDecision -Configured $true -DesiredState running -ProcessRunning $true -LocalCode listening -DispatchCode dispatch_stalled -DispatchCanRecover $true -RunnerBusy $false -ConsecutiveRecoverableProbes 2 -MinutesSinceLastAttempt 2 -AttemptsInWindow 0) 'cooldown'
Assert-Decision 'none' (Get-JollyManagedSupervisorDecision -Configured $true -DesiredState running -ProcessRunning $true -LocalCode listening -DispatchCode dispatch_stalled -DispatchCanRecover $true -RunnerBusy $false -ConsecutiveRecoverableProbes 2 -MinutesSinceLastAttempt 999 -AttemptsInWindow 2) 'hourly cap'
Write-Host 'managed runner supervisor core tests: ok'
