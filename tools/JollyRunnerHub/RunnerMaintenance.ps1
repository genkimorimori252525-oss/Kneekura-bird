[CmdletBinding()]
param(
    [string]$AppRoot = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:RUNNER_TRACKING_ID = ''
$lifecycle = Join-Path $AppRoot 'RunnerLifecycle.ps1'
if (-not (Test-Path -LiteralPath $lifecycle -PathType Leaf)) { exit 0 }
. $lifecycle
try {
    $results = @(Invoke-JollyEphemeralGc -AppRoot $AppRoot)
    [ordered]@{timestamp=([datetime]::UtcNow).ToString('o');ok=$true;inspected=$results.Count} |
        ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $AppRoot 'maintenance-status.json') -Encoding UTF8
} catch {
    [ordered]@{timestamp=([datetime]::UtcNow).ToString('o');ok=$false;error=$_.Exception.Message} |
        ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $AppRoot 'maintenance-status.json') -Encoding UTF8
    exit 1
}
