Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-JollyEphemeralBasePath {
    param([string]$BasePath)

    if ([string]::IsNullOrWhiteSpace($BasePath)) {
        $BasePath = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub\ephemeral'
    }
    return [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($BasePath))
}

function Assert-JollyChildPath {
    param(
        [Parameter(Mandatory=$true)][string]$Parent,
        [Parameter(Mandatory=$true)][string]$Child
    )

    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd('\')
    $childFull = [IO.Path]::GetFullPath($Child)
    $prefix = $parentFull + [IO.Path]::DirectorySeparatorChar
    if (-not $childFull.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside ephemeral base: $childFull"
    }
    return $childFull
}

function New-JollyEphemeralRunnerPlan {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidatePattern('^[^/\s]+/[^/\s]+$')][string]$Repository,
        [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9._-]+$')][string[]]$Labels,
        [Parameter(Mandatory=$true)][string]$SourceRunnerRoot,
        [ValidateRange(5,1440)][int]$TtlMinutes = 60,
        [string]$BasePath,
        [ValidatePattern('^[A-Za-z0-9-]{8,64}$')][string]$InstanceId,
        [long]$ExpectedRunId = 0
    )

    if (@($Labels).Count -eq 0) { throw 'At least one custom label is required.' }
    $labelsNormalized = @($Labels | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -Unique)
    if ($labelsNormalized.Count -eq 0) { throw 'At least one custom label is required.' }

    $sourceFull = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($SourceRunnerRoot))
    if (-not (Test-Path -LiteralPath (Join-Path $sourceFull 'config.cmd')) -or
        -not (Test-Path -LiteralPath (Join-Path $sourceFull 'run.cmd'))) {
        throw "Source runner root is not a configured actions-runner distribution: $sourceFull"
    }

    $baseFull = Get-JollyEphemeralBasePath -BasePath $BasePath
    if ([string]::IsNullOrWhiteSpace($InstanceId)) {
        $InstanceId = [Guid]::NewGuid().ToString('N')
    }
    $instanceRoot = Assert-JollyChildPath -Parent $baseFull -Child (Join-Path $baseFull $InstanceId)
    $runnerRoot = Assert-JollyChildPath -Parent $instanceRoot -Child (Join-Path $instanceRoot 'runner')
    $safeRepo = ($Repository -replace '[^A-Za-z0-9_.-]','-')
    $runnerName = "Jolly-$safeRepo-$($InstanceId.Substring(0,8))"
    $createdAt = [DateTimeOffset]::UtcNow

    return [pscustomobject]@{
        version = 1
        id = $InstanceId
        repository = $Repository
        runnerName = $runnerName
        labels = $labelsNormalized
        sourceRunnerRoot = $sourceFull
        instanceRoot = $instanceRoot
        runnerRoot = $runnerRoot
        statePath = (Join-Path $instanceRoot 'state.json')
        logPath = (Join-Path $instanceRoot 'watchdog.log')
        stdoutLogPath = (Join-Path $instanceRoot 'runner.stdout.log')
        stderrLogPath = (Join-Path $instanceRoot 'runner.stderr.log')
        createdAt = $createdAt.ToString('o')
        expiresAt = $createdAt.AddMinutes($TtlMinutes).ToString('o')
        expectedRunId = $ExpectedRunId
    }
}

function Write-JollyEphemeralRunnerState {
    param([Parameter(Mandatory=$true)]$State)

    $statePath = [IO.Path]::GetFullPath([string]$State.statePath)
    $instanceRoot = [IO.Path]::GetFullPath([string]$State.instanceRoot)
    [void](Assert-JollyChildPath -Parent (Split-Path -Parent $instanceRoot) -Child $statePath)
    New-Item -ItemType Directory -Path $instanceRoot -Force | Out-Null
    $temporaryPath = "$statePath.$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryPath -Encoding UTF8
        Move-Item -LiteralPath $temporaryPath -Destination $statePath -Force
    }
    finally {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
}

function Read-JollyEphemeralRunnerState {
    param([Parameter(Mandatory=$true)][string]$StatePath)

    if (-not (Test-Path -LiteralPath $StatePath)) { throw "Runner state does not exist: $StatePath" }
    return Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Invoke-JollyGhJson {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & gh @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) { throw "gh command failed with exit code $exitCode`: $($output -join [Environment]::NewLine)" }
    return ($output -join [Environment]::NewLine)
}

function Get-JollyGitHubRunner {
    param(
        [Parameter(Mandatory=$true)][string]$Repository,
        [Parameter(Mandatory=$true)][string]$RunnerName
    )

    $payload = Invoke-JollyGhJson -Arguments @('api','--method','GET',"repos/$Repository/actions/runners",'-f','per_page=100') | ConvertFrom-Json
    return @($payload.runners | Where-Object { [string]$_.name -eq $RunnerName } | Select-Object -First 1)
}

function Remove-JollyGitHubRunnerRegistration {
    param($State)

    $runner = Get-JollyGitHubRunner -Repository ([string]$State.repository) -RunnerName ([string]$State.runnerName)
    if ($runner.Count -eq 0) { return }
    [void](Invoke-JollyGhJson -Arguments @('api','--method','DELETE',"repos/$($State.repository)/actions/runners/$($runner[0].id)"))
}

function Start-JollyEphemeralRunner {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidatePattern('^[^/\s]+/[^/\s]+$')][string]$Repository,
        [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9._-]+$')][string[]]$Labels,
        [Parameter(Mandatory=$true)][string]$SourceRunnerRoot,
        [ValidateRange(5,1440)][int]$TtlMinutes = 60,
        [string]$BasePath,
        [long]$ExpectedRunId = 0,
        [string]$WatchdogPath = (Join-Path $PSScriptRoot 'EphemeralRunnerWatchdog.ps1')
    )

    $mutex = New-Object Threading.Mutex($false,'Local\JollyRunnerHub-EphemeralLifecycle')
    if (-not $mutex.WaitOne([TimeSpan]::FromSeconds(30))) { throw 'Timed out waiting for the ephemeral runner lifecycle lock.' }
    $plan = $null
    try {
        $plan = New-JollyEphemeralRunnerPlan -Repository $Repository -Labels $Labels `
            -SourceRunnerRoot $SourceRunnerRoot -TtlMinutes $TtlMinutes -BasePath $BasePath `
            -ExpectedRunId $ExpectedRunId
        if (Test-Path -LiteralPath $plan.instanceRoot) { throw "Ephemeral instance already exists: $($plan.id)" }
        if (-not (Test-Path -LiteralPath $WatchdogPath)) { throw "Watchdog script is missing: $WatchdogPath" }

        New-Item -ItemType Directory -Path $plan.runnerRoot -Force | Out-Null
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & robocopy $plan.sourceRunnerRoot $plan.runnerRoot /E /XD _work _diag /XF .runner .credentials .credentials_rsaparams .service | Out-Null
            $copyExit = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $previousPreference }
        if ($copyExit -gt 7) { throw "Runner copy failed with robocopy exit code $copyExit" }

        $token = (Invoke-JollyGhJson -Arguments @('api','--method','POST',"repos/$Repository/actions/runners/registration-token",'--jq','.token')).Trim()
        if ([string]::IsNullOrWhiteSpace($token)) { throw 'GitHub returned an empty runner registration token.' }
        $previousToken = $env:ACTIONS_RUNNER_INPUT_TOKEN
        $env:ACTIONS_RUNNER_INPUT_TOKEN = $token
        try {
            Push-Location $plan.runnerRoot
            try {
                & .\config.cmd --unattended --url "https://github.com/$Repository" `
                    --name $plan.runnerName --labels ($plan.labels -join ',') `
                    --work _work --ephemeral --disableupdate
                if ($LASTEXITCODE -ne 0) { throw "config.cmd failed with exit code $LASTEXITCODE" }
            }
            finally { Pop-Location }
        }
        finally {
            $token = $null
            $env:ACTIONS_RUNNER_INPUT_TOKEN = $previousToken
        }

        $state = [ordered]@{}
        foreach ($property in $plan.PSObject.Properties) { $state[$property.Name] = $property.Value }
        $state.status = 'starting'
        $state.watchdogPid = $null
        $state.runnerPid = $null
        $state.githubRunnerId = $null
        $state.githubStatus = 'pending'
        $state.busy = $false
        $state.updatedAt = [DateTimeOffset]::UtcNow.ToString('o')
        $stateObject = [pscustomobject]$state
        Write-JollyEphemeralRunnerState -State $stateObject

        $previousTracking = $env:RUNNER_TRACKING_ID
        $env:RUNNER_TRACKING_ID = ''
        try {
            $argumentLine = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -StatePath "{1}"' -f `
                ([IO.Path]::GetFullPath($WatchdogPath)),([IO.Path]::GetFullPath($plan.statePath))
            $watchdog = Start-Process powershell.exe -ArgumentList $argumentLine -WindowStyle Hidden -PassThru
        }
        finally { $env:RUNNER_TRACKING_ID = $previousTracking }
        $stateObject.watchdogPid = $watchdog.Id
        $stateObject.updatedAt = [DateTimeOffset]::UtcNow.ToString('o')
        Write-JollyEphemeralRunnerState -State $stateObject
        return $stateObject
    }
    catch {
        if ($null -ne $plan -and (Test-Path -LiteralPath $plan.instanceRoot)) {
            $safeRoot = Assert-JollyChildPath -Parent (Get-JollyEphemeralBasePath -BasePath $BasePath) -Child $plan.instanceRoot
            Remove-Item -LiteralPath $safeRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
        throw
    }
    finally {
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }
}

function Get-JollyEphemeralRunnerStatus {
    param(
        [Parameter(Mandatory=$true)][string]$InstanceId,
        [string]$BasePath,
        [switch]$RefreshGitHub
    )

    $baseFull = Get-JollyEphemeralBasePath -BasePath $BasePath
    $instanceRoot = Assert-JollyChildPath -Parent $baseFull -Child (Join-Path $baseFull $InstanceId)
    $state = Read-JollyEphemeralRunnerState -StatePath (Join-Path $instanceRoot 'state.json')
    if ($RefreshGitHub) {
        $runner = Get-JollyGitHubRunner -Repository ([string]$state.repository) -RunnerName ([string]$state.runnerName)
        if ($runner.Count -eq 0) {
            $state.githubStatus = 'not_registered'
            $state.busy = $false
        }
        else {
            $state.githubRunnerId = $runner[0].id
            $state.githubStatus = [string]$runner[0].status
            $state.busy = [bool]$runner[0].busy
        }
        $state.updatedAt = [DateTimeOffset]::UtcNow.ToString('o')
        Write-JollyEphemeralRunnerState -State $state
    }
    return $state
}

function Wait-JollyEphemeralRunnerOnline {
    param(
        [Parameter(Mandatory=$true)][string]$InstanceId,
        [string]$BasePath,
        [ValidateRange(10,300)][int]$TimeoutSeconds = 90
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $state = Get-JollyEphemeralRunnerStatus -InstanceId $InstanceId -BasePath $BasePath -RefreshGitHub
        if ([string]$state.githubStatus -eq 'online') {
            $state.status = $(if ([bool]$state.busy) { 'assigned' } else { 'online' })
            $state.updatedAt = [DateTimeOffset]::UtcNow.ToString('o')
            Write-JollyEphemeralRunnerState -State $state
            return $state
        }
        Start-Sleep -Seconds 2
    } while ([DateTimeOffset]::UtcNow -lt $deadline)

    [void](Stop-JollyEphemeralRunner -InstanceId $InstanceId -BasePath $BasePath -Reason 'online-timeout')
    throw "Ephemeral runner $InstanceId did not become online within $TimeoutSeconds seconds."
}

function Stop-JollyEphemeralRunner {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$InstanceId,
        [string]$BasePath,
        [string]$Reason = 'requested'
    )

    $baseFull = Get-JollyEphemeralBasePath -BasePath $BasePath
    $instanceRoot = Assert-JollyChildPath -Parent $baseFull -Child (Join-Path $baseFull $InstanceId)
    $state = Read-JollyEphemeralRunnerState -StatePath (Join-Path $instanceRoot 'state.json')
    foreach ($processId in @($state.runnerPid,$state.watchdogPid)) {
        if ($null -ne $processId -and [int]$processId -gt 0) {
            & taskkill.exe /PID ([string]$processId) /T /F 2>$null | Out-Null
        }
    }
    Remove-JollyGitHubRunnerRegistration -State $state
    $runnerRoot = Assert-JollyChildPath -Parent $instanceRoot -Child ([string]$state.runnerRoot)
    if (Test-Path -LiteralPath $runnerRoot) { Remove-Item -LiteralPath $runnerRoot -Recurse -Force }
    $state.status = 'stopped'
    $state.stopReason = $Reason
    $state.updatedAt = [DateTimeOffset]::UtcNow.ToString('o')
    Write-JollyEphemeralRunnerState -State $state
    return $state
}

function Invoke-JollyEphemeralRunnerGc {
    [CmdletBinding(SupportsShouldProcess=$true)]
    param(
        [string]$BasePath,
        [ValidateRange(1,365)][int]$RetentionDays = 7
    )

    $baseFull = Get-JollyEphemeralBasePath -BasePath $BasePath
    if (-not (Test-Path -LiteralPath $baseFull)) { return @() }
    $cutoff = [DateTimeOffset]::UtcNow.AddDays(-$RetentionDays)
    $removed = New-Object Collections.Generic.List[string]
    foreach ($directory in @(Get-ChildItem -LiteralPath $baseFull -Directory)) {
        $statePath = Join-Path $directory.FullName 'state.json'
        if (-not (Test-Path -LiteralPath $statePath)) { continue }
        try { $state = Read-JollyEphemeralRunnerState -StatePath $statePath } catch { continue }
        $terminal = @('completed','expired','failed','stopped') -contains [string]$state.status
        $updatedAt = [DateTimeOffset]::Parse([string]$state.updatedAt)
        if ($terminal -and $updatedAt -lt $cutoff) {
            $safeRoot = Assert-JollyChildPath -Parent $baseFull -Child $directory.FullName
            if ($PSCmdlet.ShouldProcess($safeRoot,'Remove retained ephemeral runner evidence')) {
                Remove-Item -LiteralPath $safeRoot -Recurse -Force
            }
            [void]$removed.Add([string]$state.id)
        }
    }
    return @($removed)
}

Export-ModuleMember -Function @(
    'Get-JollyEphemeralBasePath',
    'Assert-JollyChildPath',
    'New-JollyEphemeralRunnerPlan',
    'Write-JollyEphemeralRunnerState',
    'Read-JollyEphemeralRunnerState',
    'Get-JollyGitHubRunner',
    'Remove-JollyGitHubRunnerRegistration',
    'Start-JollyEphemeralRunner',
    'Get-JollyEphemeralRunnerStatus',
    'Wait-JollyEphemeralRunnerOnline',
    'Stop-JollyEphemeralRunner',
    'Invoke-JollyEphemeralRunnerGc'
)
