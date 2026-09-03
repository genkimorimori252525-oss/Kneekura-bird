[CmdletBinding()]
param(
    [string]$AppRoot = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'),
    [string]$StartupDirectory = '',
    [switch]$NoStart,
    [switch]$RestartExisting
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$supervisor = Join-Path $AppRoot 'ManagedRunnerSupervisor.ps1'
$statusPath = Join-Path $AppRoot 'supervisor-status.json'
if (-not (Test-Path -LiteralPath $supervisor -PathType Leaf)) { throw "Supervisor not found: $supervisor" }

function Get-SupervisorProcessIds {
    param([Parameter(Mandatory=$true)][string]$ScriptPath)
    $ids = @()
    try {
        $escaped = [regex]::Escape($ScriptPath)
        foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue)) {
            if ([string]$process.CommandLine -match $escaped) { $ids += [int]$process.ProcessId }
        }
    } catch {}
    return @($ids | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
}

function Start-SupervisorProcess {
    param([Parameter(Mandatory=$true)][string]$PowerShellPath)
    $previous = $env:RUNNER_TRACKING_ID
    $env:RUNNER_TRACKING_ID = ''
    try {
        return Start-Process $PowerShellPath -ArgumentList @(
            '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden',
            '-File',('"{0}"' -f $supervisor)
        ) -WindowStyle Hidden -PassThru
    } finally {
        $env:RUNNER_TRACKING_ID = $previous
    }
}

function Wait-SupervisorHeartbeat {
    param([Parameter(Mandatory=$true)][int]$ProcessId,[int]$TimeoutSeconds = 8)
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
            try {
                $status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([int]$status.processId -eq $ProcessId) { return $true }
            } catch {}
        }
        Start-Sleep -Milliseconds 200
    } while ([datetime]::UtcNow -lt $deadline)
    return $false
}

$startup = if ([string]::IsNullOrWhiteSpace($StartupDirectory)) {
    [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
} else {
    [Environment]::ExpandEnvironmentVariables($StartupDirectory)
}
New-Item -ItemType Directory -Force -Path $startup | Out-Null
$linkPath = Join-Path $startup 'Jolly Runner Hub Supervisor.lnk'
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($linkPath)
$link.TargetPath = $powershell
$link.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $supervisor + '"'
$link.WorkingDirectory = $AppRoot
$link.WindowStyle = 7
$link.Description = 'Jolly Runner Hub managed runner supervisor'
$link.Save()

$previousPids = @(Get-SupervisorProcessIds -ScriptPath $supervisor)
$stoppedPids = @()
$startedPid = 0
$heartbeatObserved = $false

if (-not $NoStart) {
    if ($RestartExisting -and $previousPids.Count -gt 0) {
        foreach ($processId in $previousPids) {
            try {
                Stop-Process -Id $processId -Force -ErrorAction Stop
                $stoppedPids += $processId
            } catch {
                throw "Failed to stop old managed Supervisor PID $processId: $($_.Exception.Message)"
            }
        }
        $deadline = [datetime]::UtcNow.AddSeconds(5)
        do {
            $remaining = @(Get-SupervisorProcessIds -ScriptPath $supervisor)
            if ($remaining.Count -eq 0) { break }
            Start-Sleep -Milliseconds 200
        } while ([datetime]::UtcNow -lt $deadline)
        $remaining = @(Get-SupervisorProcessIds -ScriptPath $supervisor)
        if ($remaining.Count -gt 0) { throw "Old managed Supervisor did not exit: $($remaining -join ',')" }
    }

    $running = @(Get-SupervisorProcessIds -ScriptPath $supervisor)
    if ($running.Count -eq 0) {
        $started = Start-SupervisorProcess -PowerShellPath $powershell
        $startedPid = [int]$started.Id
        $heartbeatObserved = Wait-SupervisorHeartbeat -ProcessId $startedPid -TimeoutSeconds 8
        if (-not $heartbeatObserved) {
            throw "New managed Supervisor PID $startedPid did not publish a heartbeat within 8 seconds"
        }
    } else {
        $startedPid = [int]$running[0]
        $heartbeatObserved = Wait-SupervisorHeartbeat -ProcessId $startedPid -TimeoutSeconds 2
    }
}

[ordered]@{
    registeredAt=(Get-Date).ToString('o')
    startupLink=$linkPath
    supervisor=$supervisor
    started=(-not $NoStart)
    restartRequested=[bool]$RestartExisting
    previousProcessIds=@($previousPids)
    stoppedProcessIds=@($stoppedPids)
    activeProcessId=$startedPid
    heartbeatObserved=[bool]$heartbeatObserved
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $AppRoot 'supervisor-registration.json') -Encoding UTF8
Write-Host ('managed runner supervisor registered pid=' + [string]$startedPid + ' restarted=' + [string]([bool]$RestartExisting) + ' heartbeat=' + [string]$heartbeatObserved)
