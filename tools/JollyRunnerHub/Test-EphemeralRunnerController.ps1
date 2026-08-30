Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'EphemeralRunnerController.psm1') -Force
$testBase = Join-Path ([IO.Path]::GetTempPath()) "JollyRunnerHub-test-$([Guid]::NewGuid().ToString('N'))"
$source = Join-Path $testBase 'source'
New-Item -ItemType Directory -Path $source -Force | Out-Null
Set-Content -LiteralPath (Join-Path $source 'config.cmd') -Value '@echo off' -Encoding Ascii
Set-Content -LiteralPath (Join-Path $source 'run.cmd') -Value '@echo off' -Encoding Ascii

function Assert-True([bool]$Condition,[string]$Message) {
    if (-not $Condition) { throw $Message }
}

try {
    $planA = New-JollyEphemeralRunnerPlan -Repository 'owner/repo-a' -Labels @('alpha','Windows') `
        -SourceRunnerRoot $source -TtlMinutes 30 -BasePath $testBase -InstanceId 'instance-a1'
    $planB = New-JollyEphemeralRunnerPlan -Repository 'owner/repo-b' -Labels @('beta','Windows') `
        -SourceRunnerRoot $source -TtlMinutes 30 -BasePath $testBase -InstanceId 'instance-b2'
    Assert-True ($planA.runnerRoot -ne $planB.runnerRoot) 'Parallel plans must use unique runner roots.'
    Assert-True ($planA.runnerName -ne $planB.runnerName) 'Parallel plans must use unique runner names.'
    Assert-True ($planA.labels.Count -eq 2) 'Labels were not preserved.'

    $state = [pscustomobject]@{
        id=$planA.id; instanceRoot=$planA.instanceRoot; runnerRoot=$planA.runnerRoot;
        statePath=$planA.statePath; repository=$planA.repository; runnerName=$planA.runnerName;
        status='completed'; updatedAt=[DateTimeOffset]::UtcNow.AddDays(-20).ToString('o')
    }
    Write-JollyEphemeralRunnerState -State $state
    $serialized = Get-Content -LiteralPath $planA.statePath -Raw -Encoding UTF8
    Assert-True (-not ($serialized -match 'token|credential')) 'State must not persist token or credential fields.'
    $loaded = Read-JollyEphemeralRunnerState -StatePath $planA.statePath
    Assert-True ($loaded.id -eq 'instance-a1') 'State round-trip failed.'

    $candidates = @(Invoke-JollyEphemeralRunnerGc -BasePath $testBase -RetentionDays 7 -WhatIf)
    Assert-True ($candidates -contains 'instance-a1') 'GC did not identify expired terminal evidence.'
    Assert-True (Test-Path -LiteralPath $planA.instanceRoot) 'WhatIf GC removed evidence.'

    $escaped = $false
    try { [void](Assert-JollyChildPath -Parent $testBase -Child (Split-Path -Parent $testBase)) } catch { $escaped = $true }
    Assert-True $escaped 'Path containment did not reject an escaped root.'

    $watchdogText = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'EphemeralRunnerWatchdog.ps1') -Raw
    Assert-True ($watchdogText.Contains("`$env:RUNNER_TRACKING_ID = ''")) 'Watchdog must detach runner tracking from the parent job.'
    Assert-True ($watchdogText.Contains('expiresAt')) 'Watchdog must enforce TTL.'
    'ephemeral controller tests: ok'
}
finally {
    $safeTestRoot = [IO.Path]::GetFullPath($testBase)
    $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if ($safeTestRoot.StartsWith($tempPrefix,[StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $safeTestRoot)) {
        Remove-Item -LiteralPath $safeTestRoot -Recurse -Force
    }
}
