param([Parameter(Mandatory=$true)][string]$StatePath)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$modulePath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'EphemeralRunnerController.psm1'
Import-Module $modulePath -Force
$state = Read-JollyEphemeralRunnerState -StatePath $StatePath

function Save-State([string]$Status) {
    $state.status = $Status
    $state.updatedAt = [DateTimeOffset]::UtcNow.ToString('o')
    Write-JollyEphemeralRunnerState -State $state
}

try {
    $previousTracking = $env:RUNNER_TRACKING_ID
    $env:RUNNER_TRACKING_ID = ''
    try {
        $runner = Start-Process -FilePath (Join-Path ([string]$state.runnerRoot) 'run.cmd') `
            -WorkingDirectory ([string]$state.runnerRoot) -WindowStyle Hidden -PassThru
    }
    finally { $env:RUNNER_TRACKING_ID = $previousTracking }

    $state.runnerPid = $runner.Id
    Save-State -Status 'running'
    $expiresAt = [DateTimeOffset]::Parse([string]$state.expiresAt)
    while (-not $runner.HasExited -and [DateTimeOffset]::UtcNow -lt $expiresAt) {
        Start-Sleep -Seconds 5
        $runner.Refresh()
    }

    if (-not $runner.HasExited) {
        & taskkill.exe /PID ([string]$runner.Id) /T /F 2>$null | Out-Null
        Save-State -Status 'expired'
    }
    else {
        $state.runnerExitCode = $runner.ExitCode
        Save-State -Status $(if ($runner.ExitCode -eq 0) { 'completed' } else { 'failed' })
    }
}
catch {
    $state.error = $_.Exception.Message
    Save-State -Status 'failed'
}
finally {
    try { Remove-JollyGitHubRunnerRegistration -State $state } catch {
        $state.cleanupError = $_.Exception.Message
        Save-State -Status ([string]$state.status)
    }
    $runnerRoot = Assert-JollyChildPath -Parent ([string]$state.instanceRoot) -Child ([string]$state.runnerRoot)
    if (Test-Path -LiteralPath $runnerRoot) {
        Remove-Item -LiteralPath $runnerRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
