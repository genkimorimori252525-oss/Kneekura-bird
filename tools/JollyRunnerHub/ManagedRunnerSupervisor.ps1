[CmdletBinding()]
param(
    [string]$AppRoot = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'),
    [ValidateRange(5,300)][int]$IntervalSeconds = 10,
    [switch]$Once
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:RUNNER_TRACKING_ID = ''

$ConfigPath = Join-Path $AppRoot 'profiles.json'
$DefaultConfigPath = Join-Path $AppRoot 'profiles.default.json'
$StatusPath = Join-Path $AppRoot 'supervisor-status.json'
$EventLogPath = Join-Path $AppRoot 'managed-supervisor.jsonl'
$DispatchRoot = Join-Path $AppRoot 'dispatch'
$ConfigModulePath = Join-Path $AppRoot 'RunnerConfig.ps1'
$ControlStatePath = Join-Path $AppRoot 'RunnerControlState.ps1'
$DispatchWatchPath = Join-Path $AppRoot 'RunnerDispatchWatch.ps1'
$DispatchProbePath = Join-Path $AppRoot 'RunnerDispatchProbe.ps1'
$ConnectionStatePath = Join-Path $AppRoot 'RunnerConnectionState.ps1'
$SupervisorCorePath = Join-Path $AppRoot 'ManagedRunnerSupervisorCore.ps1'
$MaintenancePath = Join-Path $AppRoot 'RunnerMaintenance.ps1'

foreach ($required in @($ConfigModulePath,$ControlStatePath,$DispatchWatchPath,$DispatchProbePath,$ConnectionStatePath,$SupervisorCorePath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Supervisor dependency missing: $required" }
}
. $ConfigModulePath
. $ControlStatePath
. $DispatchWatchPath
. $ConnectionStatePath
. $SupervisorCorePath

New-Item -ItemType Directory -Force -Path $AppRoot,$DispatchRoot | Out-Null
$mutex = New-Object Threading.Mutex($false,'Local\JollyRunnerHub-ManagedSupervisor-v1')
if (-not $mutex.WaitOne([TimeSpan]::FromSeconds(2))) { exit 0 }

$script:Recovery = @{}
$script:LastProbeLaunch = @{}
$script:MaintenanceProcess = $null
$script:LastMaintenance = [datetime]::MinValue

function Write-SupervisorEvent {
    param([string]$ProfileId,[string]$Action,[string]$Result,[string]$Reason)
    try {
        if (Test-Path -LiteralPath $EventLogPath) {
            $file = Get-Item -LiteralPath $EventLogPath -ErrorAction SilentlyContinue
            if ($null -ne $file -and $file.Length -gt 10485760) {
                Move-Item -LiteralPath $EventLogPath -Destination ($EventLogPath + '.1') -Force -ErrorAction SilentlyContinue
            }
        }
        [ordered]@{
            timestamp=([datetime]::UtcNow).ToString('o')
            profileId=$ProfileId
            action=$Action
            result=$Result
            reason=$Reason
        } | ConvertTo-Json -Compress | Add-Content -LiteralPath $EventLogPath -Encoding UTF8
    } catch {}
}

function Get-SupervisorRunnerProcesses {
    param($Profile)
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot).TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($root)) { return @() }
    $pattern = '^' + [regex]::Escape($root) + '(?:\\|["\s]|$)'
    try {
        return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            [string]$_.Name -in @('Runner.Listener.exe','cmd.exe') -and (
                ([string]$_.ExecutablePath -match $pattern) -or
                ([string]$_.CommandLine -match [regex]::Escape($root))
            )
        })
    } catch { return @() }
}

function Test-SupervisorRunnerConfigured {
    param($Profile)
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    return (Test-Path -LiteralPath (Join-Path $root 'run.cmd') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $root '.runner') -PathType Leaf)
}

function Start-SupervisorRunner {
    param($Profile)
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    if (-not (Test-SupervisorRunnerConfigured $Profile)) { throw "Runner not configured: $root" }
    if (@(Get-SupervisorRunnerProcesses $Profile).Count -gt 0) { return }
    $logRoot = Join-Path $AppRoot 'logs'
    New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
    $id = ([string]$Profile.id -replace '[^A-Za-z0-9_.-]','_')
    $log = Join-Path $logRoot ("runner-$id.log")
    $cmd = Join-Path $root 'run.cmd'
    $line = '""{0}" >> "{1}" 2>&1"' -f $cmd,$log
    $previousTracking = $env:RUNNER_TRACKING_ID
    $env:RUNNER_TRACKING_ID = ''
    try {
        Start-Process cmd.exe -ArgumentList '/d','/s','/c',$line -WorkingDirectory $root -WindowStyle Hidden | Out-Null
    } finally {
        $env:RUNNER_TRACKING_ID = $previousTracking
    }
}

function Stop-SupervisorRunner {
    param($Profile)
    $processes = @(Get-SupervisorRunnerProcesses $Profile)
    $ids = @($processes | ForEach-Object { [int]$_.ProcessId } | Where-Object { $_ -gt 0 } | Select-Object -Unique)
    foreach ($processId in $ids) {
        Start-Process taskkill.exe -ArgumentList '/PID',[string]$processId,'/T','/F' -Wait -WindowStyle Hidden | Out-Null
    }
}

function Get-SupervisorRawLocalState {
    param($Profile)
    $running = @(Get-SupervisorRunnerProcesses $Profile).Count -gt 0
    if (-not $running) { return Get-JollyRunnerConnectionStateLegacy -ProcessRunning $false -LogLines @() }
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    $diagRoot = Join-Path $root '_diag'
    $lines = @()
    if (Test-Path -LiteralPath $diagRoot -PathType Container) {
        $latest = Get-ChildItem -LiteralPath $diagRoot -Filter 'Runner_*.log' -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($null -ne $latest) {
            try { $lines = @(Get-Content -LiteralPath $latest.FullName -Tail 300 -Encoding UTF8 -ErrorAction Stop) } catch {}
        }
    }
    return Get-JollyRunnerConnectionStateLegacy -ProcessRunning $true -LogLines $lines
}

function Get-SupervisorDispatchPath {
    param($Profile)
    $id = ([string]$Profile.id -replace '[^A-Za-z0-9_.-]','_')
    return Join-Path $DispatchRoot ("dispatch-$id.json")
}

function Read-SupervisorDispatchProbe {
    param($Profile)
    $path = Get-SupervisorDispatchPath $Profile
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try {
        $probe = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        $at = [datetime]::MinValue
        if (-not [datetime]::TryParse([string]$probe.probedAt,[ref]$at)) { return $null }
        $age = [math]::Max(0,[int]([datetime]::UtcNow-$at.ToUniversalTime()).TotalSeconds)
        Add-Member -InputObject $probe -NotePropertyName SnapshotAgeSeconds -NotePropertyValue $age -Force
        return $probe
    } catch { return $null }
}

function Invoke-SupervisorDispatchProbe {
    param($Profile)
    $repository = ([string]$Profile.repoUrl).TrimEnd('/') -replace '^https://github.com/',''
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    $output = Get-SupervisorDispatchPath $Profile
    $routingCsv = (Get-JollyDispatchRoutingLabels $Profile) -join ','
    $args = @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',('"{0}"' -f $DispatchProbePath),'-Repository',$repository,'-RunnerRoot',('"{0}"' -f $root),'-OutputPath',('"{0}"' -f $output),'-RoutingLabelsCsv',$routingCsv,'-TimeoutSeconds','4')
    $process = Start-Process powershell.exe -ArgumentList $args -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(45000)) {
        try { Start-Process taskkill.exe -ArgumentList '/PID',[string]$process.Id,'/T','/F' -Wait -WindowStyle Hidden | Out-Null } catch {}
        Write-SupervisorEvent ([string]$Profile.id) 'dispatch-probe' 'timeout' 'probe exceeded 45 seconds'
    }
}

function Get-SupervisorRecoveryState {
    param($Profile)
    $id = [string]$Profile.id
    if (-not $script:Recovery.ContainsKey($id)) {
        $script:Recovery[$id] = [pscustomobject]@{
            Consecutive=0
            LastProbeAt=''
            LastAttempt=[datetime]::MinValue
            WindowStart=[datetime]::UtcNow
            AttemptsInWindow=0
        }
    }
    return $script:Recovery[$id]
}

function Write-SupervisorStatus {
    param($Profiles)
    $payload = [ordered]@{
        schema='jolly.managed-supervisor'
        version=1
        processId=$PID
        updatedAt=([datetime]::UtcNow).ToString('o')
        intervalSeconds=$IntervalSeconds
        profiles=$Profiles
    }
    $temp = $StatusPath + '.tmp-' + [guid]::NewGuid().ToString('N')
    try {
        $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temp -Encoding UTF8
        Move-Item -LiteralPath $temp -Destination $StatusPath -Force
    } finally {
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
}

function Start-MaintenanceIfDue {
    if (-not (Test-Path -LiteralPath $MaintenancePath -PathType Leaf)) { return }
    if ($null -ne $script:MaintenanceProcess -and -not $script:MaintenanceProcess.HasExited) { return }
    if (([datetime]::UtcNow-$script:LastMaintenance).TotalSeconds -lt 120) { return }
    $previousTracking = $env:RUNNER_TRACKING_ID
    $env:RUNNER_TRACKING_ID = ''
    try {
        $script:MaintenanceProcess = Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',('"{0}"' -f $MaintenancePath),'-AppRoot',('"{0}"' -f $AppRoot)) -WindowStyle Hidden -PassThru
        $script:LastMaintenance = [datetime]::UtcNow
    } catch {
        Write-SupervisorEvent '' 'maintenance' 'failed' $_.Exception.Message
    } finally {
        $env:RUNNER_TRACKING_ID = $previousTracking
    }
}

try {
    do {
        $cycleProfiles = @()
        try {
            $config = Read-JollyRunnerConfig -ConfigPath $ConfigPath -DefaultConfigPath $DefaultConfigPath
            $probeBudget = 1
            foreach ($profile in @($config.profiles)) {
                $profileId = [string]$profile.id
                $configured = Test-SupervisorRunnerConfigured $profile
                $desired = Get-JollyDesiredRunnerState -AppRoot $AppRoot -Profile $profile -Config $config
                $processRunning = @(Get-SupervisorRunnerProcesses $profile).Count -gt 0
                $local = Get-SupervisorRawLocalState $profile

                $probe = Read-SupervisorDispatchProbe $profile
                $probeMaxAge = Get-JollyDispatchProbeMaxAgeSeconds $profile
                if ($configured -and $probeBudget -gt 0 -and ($null -eq $probe -or [int]$probe.SnapshotAgeSeconds -ge $probeMaxAge)) {
                    try {
                        Invoke-SupervisorDispatchProbe $profile
                        $script:LastProbeLaunch[$profileId] = [datetime]::UtcNow
                    } catch {
                        Write-SupervisorEvent $profileId 'dispatch-probe' 'failed' $_.Exception.Message
                    }
                    $probeBudget--
                    $probe = Read-SupervisorDispatchProbe $profile
                }

                $dispatch = if ($configured) {
                    $age = if ($null -ne $probe) { [int]$probe.SnapshotAgeSeconds } else { 0 }
                    Get-JollyDispatchClassification -LocalCode ([string]$local.Code) -Probe $probe -WarnSeconds (Get-JollyDispatchWarnSeconds $profile) -RecoverSeconds (Get-JollyDispatchRecoverSeconds $profile) -ProbeAgeSeconds $age
                } else {
                    [pscustomobject]@{Code='unregistered';Text='unregistered';Tone='bad';CanRecover=$false;Evidence='runner not configured'}
                }

                $recovery = Get-SupervisorRecoveryState $profile
                $probeAt = if ($null -ne $probe) { [string]$probe.probedAt } else { '' }
                if ($probeAt -and $probeAt -ne [string]$recovery.LastProbeAt) {
                    $recovery.LastProbeAt = $probeAt
                    if ([bool]$dispatch.CanRecover) { $recovery.Consecutive=[int]$recovery.Consecutive+1 } else { $recovery.Consecutive=0 }
                }
                if (([datetime]::UtcNow-[datetime]$recovery.WindowStart).TotalHours -ge 1) {
                    $recovery.WindowStart=[datetime]::UtcNow
                    $recovery.AttemptsInWindow=0
                }
                $busy = $false
                if ($null -ne $probe) { $busy = [bool]$probe.runnerBusy }
                $minutesSinceAttempt = ([datetime]::UtcNow-[datetime]$recovery.LastAttempt).TotalMinutes
                $decision = Get-JollyManagedSupervisorDecision -Configured $configured -DesiredState $desired -ProcessRunning $processRunning -LocalCode ([string]$local.Code) -DispatchCode ([string]$dispatch.Code) -DispatchCanRecover ([bool]$dispatch.CanRecover) -RunnerBusy $busy -ConsecutiveRecoverableProbes ([int]$recovery.Consecutive) -MinutesSinceLastAttempt $minutesSinceAttempt -AttemptsInWindow ([int]$recovery.AttemptsInWindow)

                $actionResult = 'none'
                if ([string]$decision.Action -eq 'start') {
                    try {
                        Start-SupervisorRunner $profile
                        $recovery.LastAttempt=[datetime]::UtcNow
                        $actionResult='started'
                        Write-SupervisorEvent $profileId 'start' 'success' ([string]$decision.Reason)
                    } catch {
                        $actionResult='start-failed'
                        Write-SupervisorEvent $profileId 'start' 'failed' $_.Exception.Message
                    }
                }
                elseif ([string]$decision.Action -eq 'reconnect') {
                    try {
                        Stop-SupervisorRunner $profile
                        Start-Sleep -Milliseconds 600
                        Start-SupervisorRunner $profile
                        $recovery.LastAttempt=[datetime]::UtcNow
                        $recovery.AttemptsInWindow=[int]$recovery.AttemptsInWindow+1
                        $recovery.Consecutive=0
                        $actionResult='reconnected'
                        Write-SupervisorEvent $profileId 'reconnect' 'success' ([string]$decision.Reason)
                    } catch {
                        $actionResult='reconnect-failed'
                        Write-SupervisorEvent $profileId 'reconnect' 'failed' $_.Exception.Message
                    }
                }

                $cycleProfiles += [pscustomobject]@{
                    id=$profileId
                    desiredState=$desired
                    configured=[bool]$configured
                    processRunning=[bool](@(Get-SupervisorRunnerProcesses $profile).Count -gt 0)
                    localCode=[string]$local.Code
                    dispatchCode=[string]$dispatch.Code
                    dispatchTone=[string]$dispatch.Tone
                    runnerBusy=$busy
                    eligibleQueuedCount=if ($null -ne $probe) {[int]$probe.eligibleQueuedCount} else {0}
                    oldestQueuedSeconds=if ($null -ne $probe) {[int]$probe.oldestQueuedSeconds} else {0}
                    recoveryConsecutive=[int]$recovery.Consecutive
                    action=$actionResult
                }
            }
            Start-MaintenanceIfDue
            Write-SupervisorStatus $cycleProfiles
        } catch {
            Write-SupervisorEvent '' 'cycle' 'failed' $_.Exception.Message
            Write-SupervisorStatus @([pscustomobject]@{id='supervisor';action='cycle-failed';error=$_.Exception.Message})
        }
        if (-not $Once) { Start-Sleep -Seconds $IntervalSeconds }
    } while (-not $Once)
} finally {
    try { $mutex.ReleaseMutex() } catch {}
    $mutex.Dispose()
}
