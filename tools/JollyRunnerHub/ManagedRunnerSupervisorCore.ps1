Set-StrictMode -Version Latest

function Get-JollyManagedSupervisorDecision {
    param(
        [Parameter(Mandatory=$true)][bool]$Configured,
        [Parameter(Mandatory=$true)][ValidateSet('running','stopped')][string]$DesiredState,
        [Parameter(Mandatory=$true)][bool]$ProcessRunning,
        [Parameter(Mandatory=$true)][string]$LocalCode,
        [Parameter(Mandatory=$true)][string]$DispatchCode,
        [Parameter(Mandatory=$true)][bool]$DispatchCanRecover,
        [Parameter(Mandatory=$true)][bool]$RunnerBusy,
        [Parameter(Mandatory=$true)][int]$ConsecutiveRecoverableProbes,
        [Parameter(Mandatory=$true)][double]$MinutesSinceLastRecoveryAttempt,
        [Parameter(Mandatory=$true)][int]$RecoveryAttemptsInWindow,
        [Parameter(Mandatory=$true)][double]$SecondsSinceLastStartAttempt,
        [Parameter(Mandatory=$true)][int]$StartFailureCount
    )

    if (-not $Configured) {
        return [pscustomobject]@{Action='none';Reason='runner not configured'}
    }

    if ($DesiredState -eq 'stopped') {
        if ($ProcessRunning) {
            return [pscustomobject]@{Action='stop';Reason='manual desired state is stopped'}
        }
        return [pscustomobject]@{Action='none';Reason='manual desired state is stopped'}
    }

    if (-not $ProcessRunning) {
        $boundedFailures = [math]::Min(5,[math]::Max(0,$StartFailureCount))
        $requiredDelay = [math]::Min(60,[math]::Pow(2,$boundedFailures) * 2)
        if ($SecondsSinceLastStartAttempt -ge $requiredDelay) {
            return [pscustomobject]@{Action='start';Reason=('desired running but listener is absent; backoff=' + [string]$requiredDelay + 's')}
        }
        return [pscustomobject]@{Action='none';Reason=('start backoff active; wait=' + [string]$requiredDelay + 's')}
    }

    if ($RunnerBusy -or $LocalCode -eq 'running_job') {
        return [pscustomobject]@{Action='none';Reason='runner is busy'}
    }

    if ($DispatchCanRecover -and
        $ConsecutiveRecoverableProbes -ge 2 -and
        $MinutesSinceLastRecoveryAttempt -ge 10 -and
        $RecoveryAttemptsInWindow -lt 2) {
        return [pscustomobject]@{Action='reconnect';Reason=('recoverable dispatch state: ' + $DispatchCode)}
    }

    return [pscustomobject]@{Action='none';Reason='no recovery action required'}
}
