[CmdletBinding()]
param(
    [string]$AppRoot = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'),
    [ValidateRange(5,300)][int]$IntervalSeconds = 10,
    [string]$MutexName = 'Local\JollyRunnerHub-ManagedSupervisor-v1',
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
$RootResolverPath = Join-Path $AppRoot 'RunnerRootResolver.ps1'
$MaintenancePath = Join-Path $AppRoot 'RunnerMaintenance.ps1'

foreach ($required in @($ConfigModulePath,$ControlStatePath,$DispatchWatchPath,$DispatchProbePath,$ConnectionStatePath,$SupervisorCorePath,$RootResolverPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Supervisor dependency missing: $required" }
}
. $ConfigModulePath
. $ControlStatePath
. $DispatchWatchPath
. $ConnectionStatePath
. $SupervisorCorePath
. $RootResolverPath

New-Item -ItemType Directory -Force -Path $AppRoot,$DispatchRoot | Out-Null
$mutex = New-Object Threading.Mutex($false,$MutexName)
if (-not $mutex.WaitOne([TimeSpan]::FromSeconds(2))) { exit 0 }

$script:Recovery = @{}
$script:ProbeProcesses = @{}
$script:MaintenanceProcess = $null
$script:LastMaintenance = [datetime]::MinValue
$script:ProcessInventory = @()

function Write-SupervisorEvent {
    param([string]$ProfileId,[string]$Action,[string]$Result,[string]$Reason)
    try {
        if (Test-Path -LiteralPath $EventLogPath) {
            $file = Get-Item -LiteralPath $EventLogPath -ErrorAction SilentlyContinue
            if ($null -ne $file -and $file.Length -gt 10485760) {
                Move-Item -LiteralPath $EventLogPath -Destination ($EventLogPath + '.1') -Force -ErrorAction SilentlyContinue
            }
        }
        [ordered]@{timestamp=([datetime]::UtcNow).ToString('o');profileId=$ProfileId;action=$Action;result=$Result;reason=$Reason} | ConvertTo-Json -Compress | Add-Content -LiteralPath $EventLogPath -Encoding UTF8
    } catch {}
}

function Format-SupervisorError {
    param([Parameter(Mandatory=$true)]$ErrorRecord)
    $parts = New-Object System.Collections.Generic.List[string]
    [void]$parts.Add(('type=' + [string]$ErrorRecord.Exception.GetType().FullName))
    [void]$parts.Add(('message=' + [string]$ErrorRecord.Exception.Message))
    if ($null -ne $ErrorRecord.InvocationInfo -and [int]$ErrorRecord.InvocationInfo.ScriptLineNumber -gt 0) {
        [void]$parts.Add(('line=' + [string]$ErrorRecord.InvocationInfo.ScriptLineNumber))
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$ErrorRecord.ScriptStackTrace)) {
        $stack = ([string]$ErrorRecord.ScriptStackTrace) -replace '[\r\n]+',' <- '
        [void]$parts.Add(('stack=' + $stack))
    }
    $text = $parts -join '; '
    if ($text.Length -gt 1800) { $text = $text.Substring(0,1800) }
    return $text
}

function Refresh-SupervisorProcessInventory {
    try {
        $script:ProcessInventory = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { [string]$_.Name -in @('Runner.Listener.exe','cmd.exe') })
    } catch {
        $script:ProcessInventory = @()
    }
}

function Get-SupervisorRunnerProcesses {
    param($Profile)
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot).TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($root)) { return @() }
    $escapedRoot = [regex]::Escape($root)
    $pattern = '^' + $escapedRoot + '(?:\\|["\s]|$)'
    return @($script:ProcessInventory | Where-Object {
        ([string]$_.ExecutablePath -match $pattern) -or ([string]$_.CommandLine -match $escapedRoot)
    })
}

function Test-SupervisorRunnerConfigured {
    param($Profile)
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    return (Test-Path -LiteralPath (Join-Path $root 'run.cmd') -PathType Leaf) -and (Test-Path -LiteralPath (Join-Path $root '.runner') -PathType Leaf)
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
    $ids = @(Get-SupervisorRunnerProcesses $Profile | ForEach-Object { [int]$_.ProcessId } | Where-Object { $_ -gt 0 } | Sort-Object -Descending -Unique)
    foreach ($processId in $ids) {
        try { Start-Process taskkill.exe -ArgumentList '/PID',[string]$processId,'/T','/F' -Wait -WindowStyle Hidden | Out-Null } catch {}
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
        $latest = Get-ChildItem -LiteralPath $diagRoot -Filter 'Runner_*.log' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
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

function Cleanup-SupervisorProbeProcesses {
    foreach ($profileId in @($script:ProbeProcesses.Keys)) {
        $entry = $script:ProbeProcesses[$profileId]
        if ($null -eq $entry -or $null -eq $entry.Process) {
            $script:ProbeProcesses.Remove($profileId)
            continue
        }
        if ($entry.Process.HasExited) {
            $script:ProbeProcesses.Remove($profileId)
            continue
        }
        if (([datetime]::UtcNow-[datetime]$entry.StartedAt).TotalSeconds -gt 30) {
            try { Start-Process taskkill.exe -ArgumentList '/PID',[string]$entry.Process.Id,'/T','/F' -Wait -WindowStyle Hidden | Out-Null } catch {}
            Write-SupervisorEvent $profileId 'dispatch-probe' 'timeout' 'background probe exceeded 30 seconds'
            $script:ProbeProcesses.Remove($profileId)
        }
    }
}

function Start-SupervisorDispatchProbe {
    param($Profile)
    $profileId = [string]$Profile.id
    if ($script:ProbeProcesses.ContainsKey($profileId)) { return $false }
    $repository = ([string]$Profile.repoUrl).TrimEnd('/') -replace '^https://github.com/',''
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    $output = Get-SupervisorDispatchPath $Profile
    $routingCsv = (Get-JollyDispatchRoutingLabels $Profile) -join ','
    $args = @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',('"{0}"' -f $DispatchProbePath),'-Repository',$repository,'-RunnerRoot',('"{0}"' -f $root),'-OutputPath',('"{0}"' -f $output),'-RoutingLabelsCsv',$routingCsv,'-TimeoutSeconds','4')
    $previousTracking = $env:RUNNER_TRACKING_ID
    $env:RUNNER_TRACKING_ID = ''
    try {
        $process = Start-Process powershell.exe -ArgumentList $args -WindowStyle Hidden -PassThru
        $script:ProbeProcesses[$profileId] = [pscustomobject]@{Process=$process;StartedAt=[datetime]::UtcNow}
        return $true
    } finally {
        $env:RUNNER_TRACKING_ID = $previousTracking
    }
}

function Get-SupervisorRecoveryState {
    param($Profile)
    $id = [string]$Profile.id
    if (-not $script:Recovery.ContainsKey($id)) {
        $script:Recovery[$id] = [pscustomobject]@{
            Consecutive=0
            LastProbeAt=''
            LastRecoveryAttempt=[datetime]::MinValue
            RecoveryWindowStart=[datetime]::UtcNow
            RecoveryAttemptsInWindow=0
            LastStartAttempt=[datetime]::MinValue
            StartFailureCount=0
        }
    }
    return $script:Recovery[$id]
}

function Write-SupervisorStatus {
    param($Profiles)
    $payload = [ordered]@{
        schema='jolly.managed-supervisor'
        version=2
        processId=$PID
        updatedAt=([datetime]::UtcNow).ToString('o')
        intervalSeconds=$IntervalSeconds
        activeDispatchProbes=@($script:ProbeProcesses.Keys).Count
        maintenanceRunning=($null -ne $script:MaintenanceProcess -and -not $script:MaintenanceProcess.HasExited)
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
            Cleanup-SupervisorProbeProcesses
            Refresh-SupervisorProcessInventory
            $config = Read-JollyRunnerConfig -ConfigPath $ConfigPath -DefaultConfigPath $DefaultConfigPath
            $configuredRoots = @($config.profiles | ForEach-Object { [string]$_.runnerRoot } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
            $candidateRoots = @(Get-JollyRunnerRootCandidates -AdditionalRoots $configuredRoots)
            $probeBudget = 1
            foreach ($profile in @($config.profiles)) {
                $profileId = [string]$profile.id
                $binding = Resolve-JollyRunnerRootBinding -Profile $profile -CandidateRoots $candidateRoots
                $effectiveProfile = if (-not [string]::IsNullOrWhiteSpace([string]$binding.Root)) {
                    New-JollyProfileWithRunnerRoot -Profile $profile -RunnerRoot ([string]$binding.Root)
                } else {
                    $profile
                }
                $configured = ([string]$binding.Status -in @('configured','fallback')) -and (Test-SupervisorRunnerConfigured $effectiveProfile)
                $desired = Get-JollyDesiredRunnerState -AppRoot $AppRoot -Profile $profile -Config $config
                $processRunning = @(Get-SupervisorRunnerProcesses $effectiveProfile).Count -gt 0
                $local = Get-SupervisorRawLocalState $effectiveProfile

                $probe = Read-SupervisorDispatchProbe $effectiveProfile
                $probeMaxAge = Get-JollyDispatchProbeMaxAgeSeconds $effectiveProfile
                if ($configured -and $probeBudget -gt 0 -and -not $script:ProbeProcesses.ContainsKey($profileId) -and ($null -eq $probe -or [int]$probe.SnapshotAgeSeconds -ge $probeMaxAge)) {
                    try {
                        if (Start-SupervisorDispatchProbe $effectiveProfile) { $probeBudget-- }
                    } catch {
                        Write-SupervisorEvent $profileId 'dispatch-probe' 'failed' $_.Exception.Message
                    }
                }

                $dispatch = if ($configured) {
                    $age = if ($null -ne $probe) { [int]$probe.SnapshotAgeSeconds } else { 0 }
                    Get-JollyDispatchClassification -LocalCode ([string]$local.Code) -Probe $probe -WarnSeconds (Get-JollyDispatchWarnSeconds $effectiveProfile) -RecoverSeconds (Get-JollyDispatchRecoverSeconds $effectiveProfile) -ProbeAgeSeconds $age
                } else {
                    [pscustomobject]@{Code='unregistered';Text='unregistered';Tone='bad';CanRecover=$false;Evidence='runner not configured'}
                }

                $recovery = Get-SupervisorRecoveryState $profile
                if ($processRunning) { $recovery.StartFailureCount = 0 }
                $probeAt = if ($null -ne $probe) { [string]$probe.probedAt } else { '' }
                if ($probeAt -and $probeAt -ne [string]$recovery.LastProbeAt) {
                    $recovery.LastProbeAt = $probeAt
                    if ([bool]$dispatch.CanRecover) { $recovery.Consecutive=[int]$recovery.Consecutive+1 } else { $recovery.Consecutive=0 }
                }
                if (([datetime]::UtcNow-[datetime]$recovery.RecoveryWindowStart).TotalHours -ge 1) {
                    $recovery.RecoveryWindowStart=[datetime]::UtcNow
                    $recovery.RecoveryAttemptsInWindow=0
                }

                $busy = if ($null -ne $probe) { [bool]$probe.runnerBusy } else { $false }
                $decision = Get-JollyManagedSupervisorDecision -Configured $configured -DesiredState $desired -ProcessRunning $processRunning -LocalCode ([string]$local.Code) -DispatchCode ([string]$dispatch.Code) -DispatchCanRecover ([bool]$dispatch.CanRecover) -RunnerBusy $busy -ConsecutiveRecoverableProbes ([int]$recovery.Consecutive) -MinutesSinceLastRecoveryAttempt (([datetime]::UtcNow-[datetime]$recovery.LastRecoveryAttempt).TotalMinutes) -RecoveryAttemptsInWindow ([int]$recovery.RecoveryAttemptsInWindow) -SecondsSinceLastStartAttempt (([datetime]::UtcNow-[datetime]$recovery.LastStartAttempt).TotalSeconds) -StartFailureCount ([int]$recovery.StartFailureCount)

                $actionResult = 'none'
                if ([string]$decision.Action -eq 'stop') {
                    try {
                        Stop-SupervisorRunner $effectiveProfile
                        $actionResult='stopped'
                        Write-SupervisorEvent $profileId 'stop' 'success' ([string]$decision.Reason)
                        Refresh-SupervisorProcessInventory
                    } catch {
                        $actionResult='stop-failed'
                        Write-SupervisorEvent $profileId 'stop' 'failed' $_.Exception.Message
                    }
                }
                elseif ([string]$decision.Action -eq 'start') {
                    $recovery.LastStartAttempt=[datetime]::UtcNow
                    $recovery.StartFailureCount=[math]::Min(5,[int]$recovery.StartFailureCount+1)
                    try {
                        Start-SupervisorRunner $effectiveProfile
                        $actionResult='start-issued'
                        Write-SupervisorEvent $profileId 'start' 'issued' ([string]$decision.Reason)
                    } catch {
                        $actionResult='start-failed'
                        Write-SupervisorEvent $profileId 'start' 'failed' $_.Exception.Message
                    }
                }
                elseif ([string]$decision.Action -eq 'reconnect') {
                    try {
                        Stop-SupervisorRunner $profile
                        Start-Sleep -Milliseconds 600
                        Refresh-SupervisorProcessInventory
                        Start-SupervisorRunner $profile
                        $recovery.LastRecoveryAttempt=[datetime]::UtcNow
                        $recovery.RecoveryAttemptsInWindow=[int]$recovery.RecoveryAttemptsInWindow+1
                        $recovery.Consecutive=0
                        $actionResult='reconnect-issued'
                        Write-SupervisorEvent $profileId 'reconnect' 'issued' ([string]$decision.Reason)
                    } catch {
                        $actionResult='reconnect-failed'
                        Write-SupervisorEvent $profileId 'reconnect' 'failed' $_.Exception.Message
                    }
                }

                $cycleProfiles += [pscustomobject]@{
                    id=$profileId
                    desiredState=$desired
                    configured=[bool]$configured
                    rootBinding=[string]$binding.Status
                    configuredRoot=[string]$binding.ConfiguredRoot
                    effectiveRoot=[string]$binding.Root
                    processRunning=[bool]$processRunning
                    localCode=[string]$local.Code
                    dispatchCode=[string]$dispatch.Code
                    dispatchTone=[string]$dispatch.Tone
                    runnerBusy=[bool]$busy
                    eligibleQueuedCount=if ($null -ne $probe) {[int]$probe.eligibleQueuedCount} else {0}
                    oldestQueuedSeconds=if ($null -ne $probe) {[int]$probe.oldestQueuedSeconds} else {0}
                    recoveryConsecutive=[int]$recovery.Consecutive
                    startFailureCount=[int]$recovery.StartFailureCount
                    action=$actionResult
                    decisionReason=[string]$decision.Reason
                }
            }
            Start-MaintenanceIfDue
            Write-SupervisorStatus $cycleProfiles
        } catch {
            $cycleError = Format-SupervisorError $_
            Write-SupervisorEvent '' 'cycle' 'failed' $cycleError
            Write-SupervisorStatus @([pscustomobject]@{id='supervisor';action='cycle-failed';error=$cycleError})
        }
        if (-not $Once) { Start-Sleep -Seconds $IntervalSeconds }
    } while (-not $Once)
} finally {
    foreach ($profileId in @($script:ProbeProcesses.Keys)) {
        $entry = $script:ProbeProcesses[$profileId]
        try { if ($null -ne $entry -and $null -ne $entry.Process -and -not $entry.Process.HasExited) { $entry.Process.Kill() } } catch {}
    }
    try { $mutex.ReleaseMutex() } catch {}
    $mutex.Dispose()
}
