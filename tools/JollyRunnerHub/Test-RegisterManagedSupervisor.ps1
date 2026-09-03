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
        '$status = [ordered]@{schema=''jolly.test-supervisor'';processId=$PID;updatedAt=([datetime]::UtcNow).ToString(''o'');profiles=@()}',
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
    if ($null -eq (Get-Process -Id $firstPid -ErrorAction SilentlyContinue)) { throw 'initial Supervisor process is not running' }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $register -AppRoot $root -StartupDirectory $startup -RestartExisting | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "restart registration exit=$LASTEXITCODE" }
    $second = Get-Content -LiteralPath (Join-Path $root 'supervisor-registration.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $activePid = [int]$second.activeProcessId
    if ($activePid -le 0 -or $activePid -eq $firstPid) { throw 'Supervisor generation PID did not change' }
    if ([bool]$second.heartbeatObserved -ne $true) { throw 'replacement Supervisor heartbeat was not confirmed' }
    if (@($second.stoppedProcessIds) -notcontains $firstPid) { throw 'old Supervisor PID was not recorded as stopped' }
    if ($null -ne (Get-Process -Id $firstPid -ErrorAction SilentlyContinue)) { throw 'old Supervisor process is still running' }
    if ($null -eq (Get-Process -Id $activePid -ErrorAction SilentlyContinue)) { throw 'replacement Supervisor process is not running' }
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
