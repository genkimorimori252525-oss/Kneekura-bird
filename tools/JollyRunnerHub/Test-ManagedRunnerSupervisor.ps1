Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ManagedRunnerSupervisorCore.ps1')

function Decide {
    param(
        [bool]$Configured=$true,[string]$DesiredState='running',[bool]$ProcessRunning=$true,
        [string]$LocalCode='listening',[string]$DispatchCode='ready',[bool]$DispatchCanRecover=$false,
        [bool]$RunnerBusy=$false,[int]$Consecutive=0,[double]$RecoveryMinutes=999,
        [int]$RecoveryAttempts=0,[double]$StartSeconds=999,[int]$StartFailures=0
    )
    return Get-JollyManagedSupervisorDecision -Configured $Configured -DesiredState $DesiredState -ProcessRunning $ProcessRunning -LocalCode $LocalCode -DispatchCode $DispatchCode -DispatchCanRecover $DispatchCanRecover -RunnerBusy $RunnerBusy -ConsecutiveRecoverableProbes $Consecutive -MinutesSinceLastRecoveryAttempt $RecoveryMinutes -RecoveryAttemptsInWindow $RecoveryAttempts -SecondsSinceLastStartAttempt $StartSeconds -StartFailureCount $StartFailures
}
function Assert-Decision([string]$Expected,$Decision,[string]$Message) {
    if ([string]$Decision.Action -ne $Expected) {
        throw "$Message expected=$Expected actual=$($Decision.Action) reason=$($Decision.Reason)"
    }
}

Assert-Decision 'none' (Decide -Configured $false -ProcessRunning $false) 'unconfigured runner'
Assert-Decision 'none' (Decide -DesiredState stopped -ProcessRunning $false) 'manual stop already stopped'
Assert-Decision 'stop' (Decide -DesiredState stopped -ProcessRunning $true -RunnerBusy $true) 'manual stop is authoritative'
Assert-Decision 'start' (Decide -ProcessRunning $false -StartSeconds 999 -StartFailures 0) 'missing listener'
Assert-Decision 'none' (Decide -ProcessRunning $false -StartSeconds 1 -StartFailures 0) 'initial start backoff'
Assert-Decision 'none' (Decide -ProcessRunning $false -StartSeconds 31 -StartFailures 4) 'exponential start backoff'
Assert-Decision 'start' (Decide -ProcessRunning $false -StartSeconds 33 -StartFailures 4) 'backoff elapsed'
Assert-Decision 'none' (Decide -LocalCode running_job -DispatchCode dispatch_stalled -DispatchCanRecover $true -RunnerBusy $true -Consecutive 9) 'busy runner'
Assert-Decision 'none' (Decide -DispatchCode dispatch_stalled -DispatchCanRecover $true -Consecutive 1) 'single bad probe'
Assert-Decision 'reconnect' (Decide -DispatchCode dispatch_stalled -DispatchCanRecover $true -Consecutive 2 -RecoveryMinutes 11) 'stalled route'
Assert-Decision 'none' (Decide -DispatchCode dispatch_stalled -DispatchCanRecover $true -Consecutive 2 -RecoveryMinutes 2) 'recovery cooldown'
Assert-Decision 'none' (Decide -DispatchCode dispatch_stalled -DispatchCanRecover $true -Consecutive 2 -RecoveryAttempts 2) 'hourly recovery cap'
Write-Host 'managed runner supervisor core tests: ok'
