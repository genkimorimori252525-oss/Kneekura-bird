Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Join-Path ([IO.Path]::GetTempPath()) ('JollySupervisorRegister-' + [guid]::NewGuid().ToString('N'))
$startup = Join-Path $root 'startup'
$activePid = 0
try {
    New-Item -ItemType Directory -Force -Path $root,$startup | Out-Null
    $dummyPath = Join-Path $root 'ManagedRunnerSupervisor.ps1'
    $dummy = @(
        'Set-StrictMode -Version Latest',
        '$root = Split-Path -Parent $MyInvocation.MyCommand.Path',
        '$status = [ordered]@{schema=''jolly.test-supervisor'';processId=$PID;updatedAt=([DateTimeOffset]::UtcNow.ToString(''o''));profiles=@()}',
        '$status | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root ''supervisor-status.json'') -Encoding UTF8',
        'while ($true) { Start-Sleep -Seconds 5 }'
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath $dummyPath -Value $dummy -Encoding ASCII

    $register = Join-Path $PSScriptRoot 'Register-ManagedRunnerSupervisor.ps1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $register -AppRoot $root -StartupDirectory $startup | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "initial registration exit=$LASTEXITCODE" }
    $first = Get-Content -LiteralPath (Join-Path $root 'supervisor-registration.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $firstPid = [int]$first.activeProcessId
    if ($firstPid -le 0 -or [bool]$first.heartbeatObserved -ne $true) { throw 'initial Supervisor heartbeat was not confirmed' }
    if ([string]::IsNullOrWhiteSpace([string]$first.generationStartedAtUtc)) { throw 'initial generation start timestamp was not recorded' }
    if ($null -eq (Get-Process -Id $firstPid -ErrorAction SilentlyContinue)) { throw 'initial Supervisor process is not running' }
    $firstStatus = Get-Content -LiteralPath (Join-Path $root 'supervisor-status.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $firstStarted = [DateTimeOffset]::Parse([string]$first.generationStartedAtUtc,[Globalization.CultureInfo]::InvariantCulture)
    $firstUpdated = [DateTimeOffset]::Parse([string]$firstStatus.updatedAt,[Globalization.CultureInfo]::InvariantCulture)
    if ($firstUpdated -lt $firstStarted) { throw 'initial heartbeat predates the Supervisor generation start' }

    [ordered]@{
        schema='jolly.test-supervisor'
        processId=$firstPid
        updatedAt='2000-01-01T00:00:00.0000000Z'
        staleSentinel=$true
        profiles=@()
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root 'supervisor-status.json') -Encoding UTF8

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $register -AppRoot $root -StartupDirectory $startup -RestartExisting | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "restart registration exit=$LASTEXITCODE" }
    $second = Get-Content -LiteralPath (Join-Path $root 'supervisor-registration.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $activePid = [int]$second.activeProcessId
    if ($activePid -le 0 -or $activePid -eq $firstPid) { throw 'Supervisor generation PID did not change' }
    if ([bool]$second.heartbeatObserved -ne $true) { throw 'replacement Supervisor heartbeat was not confirmed' }
    if ([string]::IsNullOrWhiteSpace([string]$second.generationStartedAtUtc)) { throw 'replacement generation start timestamp was not recorded' }
    if (@($second.stoppedProcessIds) -notcontains $firstPid) { throw 'old Supervisor PID was not recorded as stopped' }
    if ($null -ne (Get-Process -Id $firstPid -ErrorAction SilentlyContinue)) { throw 'old Supervisor process is still running' }
    if ($null -eq (Get-Process -Id $activePid -ErrorAction SilentlyContinue)) { throw 'replacement Supervisor process is not running' }

    $secondStatus = Get-Content -LiteralPath (Join-Path $root 'supervisor-status.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $secondStarted = [DateTimeOffset]::Parse([string]$second.generationStartedAtUtc,[Globalization.CultureInfo]::InvariantCulture)
    $secondUpdated = [DateTimeOffset]::Parse([string]$secondStatus.updatedAt,[Globalization.CultureInfo]::InvariantCulture)
    if ($secondUpdated -lt $secondStarted) { throw 'replacement heartbeat predates the Supervisor generation start' }
    if ($null -ne $secondStatus.PSObject.Properties['staleSentinel']) { throw 'stale status file survived replacement generation startup' }

    $registerSource = Get-Content -LiteralPath $register -Raw -Encoding UTF8
    if ($registerSource -notmatch 'Remove-Item\s+-LiteralPath\s+\$statusPath') { throw 'registration no longer clears stale status before a fresh generation starts' }

    Write-Host 'managed supervisor generation restart tests: ok'
} finally {
    if ($activePid -gt 0) { Stop-Process -Id $activePid -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $root) {
        try {
            $escaped = [regex]::Escape((Join-Path $root 'ManagedRunnerSupervisor.ps1'))
            foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object { [string]$_.CommandLine -match $escaped })) {
                Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
    Start-Sleep -Milliseconds 200
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
