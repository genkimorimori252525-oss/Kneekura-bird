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
        [Parameter(Mandatory=$true)][double]$MinutesSinceLastAttempt,
        [Parameter(Mandatory=$true)][int]$AttemptsInWindow
    )

    if (-not $Configured) {
        return [pscustomobject]@{Action='none';Reason='runner not configured'}
    }
    if ($DesiredState -eq 'stopped') {
        return [pscustomobject]@{Action='none';Reason='manual desired state is stopped'}
    }
    if (-not $ProcessRunning) {
        return [pscustomobject]@{Action='start';Reason='desired running but listener is absent'}
    }
    if ($RunnerBusy -or $LocalCode -eq 'running_job') {
        return [pscustomobject]@{Action='none';Reason='runner is busy'}
    }
    if ($DispatchCanRecover -and
        $ConsecutiveRecoverableProbes -ge 2 -and
        $MinutesSinceLastAttempt -ge 10 -and
        $AttemptsInWindow -lt 2) {
        return [pscustomobject]@{Action='reconnect';Reason=('recoverable dispatch state: ' + $DispatchCode)}
    }
    return [pscustomobject]@{Action='none';Reason='no recovery action required'}
}
