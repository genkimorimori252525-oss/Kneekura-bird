Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RunnerControlState.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('JollyDesired-' + [guid]::NewGuid().ToString('N'))
try {
    $profile = [pscustomobject]@{id='test-runner'}
    $config = [pscustomobject]@{autoConnect=$true}
    if ((Get-JollyDesiredRunnerState -AppRoot $root -Profile $profile -Config $config) -ne 'running') { throw 'autoConnect default should be running' }
    [void](Set-JollyDesiredRunnerState -AppRoot $root -ProfileId 'test-runner' -State stopped)
    if ((Get-JollyDesiredRunnerState -AppRoot $root -Profile $profile -Config $config) -ne 'stopped') { throw 'manual stop must override autoConnect' }
    $config.autoConnect = $false
    [void](Set-JollyDesiredRunnerState -AppRoot $root -ProfileId 'test-runner' -State running)
    if ((Get-JollyDesiredRunnerState -AppRoot $root -Profile $profile -Config $config) -ne 'running') { throw 'manual start must override autoConnect false' }
    Write-Host 'runner desired-state tests: ok'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
