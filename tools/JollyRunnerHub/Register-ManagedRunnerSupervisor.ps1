[CmdletBinding()]
param(
    [string]$AppRoot = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'),
    [switch]$NoStart,
    [switch]$RestartIfRunning
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$supervisor = Join-Path $AppRoot 'ManagedRunnerSupervisor.ps1'
if (-not (Test-Path -LiteralPath $supervisor -PathType Leaf)) { throw "Supervisor not found: $supervisor" }

$startup = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
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

$existingSupervisorPids = @()
try {
    $escaped = [regex]::Escape($supervisor)
    $existingSupervisorPids = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -match $escaped } |
        ForEach-Object { [int]$_.ProcessId } |
        Where-Object { $_ -gt 0 -and $_ -ne $PID } |
        Sort-Object -Unique)
} catch {}

$restarted = $false
if (-not $NoStart) {
    if ($RestartIfRunning -and $existingSupervisorPids.Count -gt 0) {
        foreach ($processId in $existingSupervisorPids) {
            try {
                Start-Process taskkill.exe -ArgumentList '/PID',[string]$processId,'/T','/F' -Wait -WindowStyle Hidden | Out-Null
            } catch {}
        }
        $restarted = $true
        Start-Sleep -Milliseconds 300
        $existingSupervisorPids = @()
    }

    if ($existingSupervisorPids.Count -eq 0) {
        $previous = $env:RUNNER_TRACKING_ID
        $env:RUNNER_TRACKING_ID = ''
        try {
            Start-Process $powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',('"{0}"' -f $supervisor)) -WindowStyle Hidden | Out-Null
        } finally {
            $env:RUNNER_TRACKING_ID = $previous
        }
    }
}

[ordered]@{
    registeredAt=(Get-Date).ToString('o')
    startupLink=$linkPath
    supervisor=$supervisor
    started=(-not $NoStart)
    restartRequested=[bool]$RestartIfRunning
    restarted=[bool]$restarted
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $AppRoot 'supervisor-registration.json') -Encoding UTF8
Write-Host 'managed runner supervisor registered'
