Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Join-Path ([IO.Path]::GetTempPath()) ('JollySupervisorRegistration-' + [guid]::NewGuid().ToString('N'))
$startup = Join-Path $root 'Startup'
$fixture = Join-Path $root 'ManagedRunnerSupervisor.ps1'
$heartbeat = Join-Path $root 'fixture-pid.txt'
$newPid = 0
try {
    New-Item -ItemType Directory -Force -Path $root,$startup | Out-Null
    $fixtureText = @(
        'Set-StrictMode -Version Latest',
        ('$heartbeat = ' + [Management.Automation.Language.CodeGeneration]::QuoteArgument($heartbeat)),
        '$PID | Set-Content -LiteralPath $heartbeat -Encoding ASCII',
        'while ($true) { Start-Sleep -Seconds 1 }'
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath $fixture -Value $fixtureText -Encoding ASCII

    $first = Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"{0}"' -f $fixture)) -PassThru -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $heartbeat -PathType Leaf)) { Start-Sleep -Milliseconds 100 }
    if (-not (Test-Path -LiteralPath $heartbeat -PathType Leaf)) { throw 'fixture Supervisor did not start' }
    $oldPid = [int](Get-Content -LiteralPath $heartbeat -Raw)
    if ($oldPid -ne $first.Id) { throw 'fixture Supervisor PID mismatch' }

    $register = Join-Path $PSScriptRoot 'Register-ManagedRunnerSupervisor.ps1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $register -AppRoot $root -StartupFolder $startup -RestartIfRunning
    if ($LASTEXITCODE -ne 0) { throw "registration script exit=$LASTEXITCODE" }

    $registration = Get-Content -LiteralPath (Join-Path $root 'supervisor-registration.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($registration.restarted -ne $true) { throw 'registration did not report hot reload' }
    if (-not (Test-Path -LiteralPath (Join-Path $startup 'Jolly Runner Hub Supervisor.lnk') -PathType Leaf)) { throw 'isolated Startup shortcut missing' }

    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 100
        if (Test-Path -LiteralPath $heartbeat -PathType Leaf) {
            $candidate = 0
            [void][int]::TryParse((Get-Content -LiteralPath $heartbeat -Raw),[ref]$candidate)
            if ($candidate -gt 0 -and $candidate -ne $oldPid) { $newPid=$candidate; break }
        }
    } while ((Get-Date) -lt $deadline)
    if ($newPid -le 0) { throw 'Supervisor hot reload did not produce a new PID' }
    if (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) { throw 'old Supervisor PID survived hot reload' }
    if (-not (Get-Process -Id $newPid -ErrorAction SilentlyContinue)) { throw 'new Supervisor PID is not alive' }
    Write-Host 'supervisor registration hot-reload tests: ok'
} finally {
    if ($newPid -gt 0) { try { Start-Process taskkill.exe -ArgumentList '/PID',[string]$newPid,'/T','/F' -Wait -WindowStyle Hidden | Out-Null } catch {} }
    try { if ($null -ne $first -and -not $first.HasExited) { Start-Process taskkill.exe -ArgumentList '/PID',[string]$first.Id,'/T','/F' -Wait -WindowStyle Hidden | Out-Null } } catch {}
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
