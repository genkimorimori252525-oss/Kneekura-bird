param(
    [switch]$Install = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$appData = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'
$desktop = [Environment]::GetFolderPath('Desktop')
$buildDir = Join-Path $root 'build'
$iconPath = Join-Path $buildDir 'JollyRunnerHub.ico'
$exePath = Join-Path $buildDir 'JollyRunnerHub.exe'
$manifestPath = Join-Path $root 'app.manifest'
$launcherPath = Join-Path $root 'Launcher.cs'
$defaultConfig = Join-Path $root 'profiles.default.json'
$scriptPath = Join-Path $root 'JollyRunnerHub.ps1'
$connectionStatePath = Join-Path $root 'RunnerConnectionState.ps1'
$ephemeralModulePath = Join-Path $root 'EphemeralRunnerController.psm1'
$ephemeralWatchdogPath = Join-Path $root 'EphemeralRunnerWatchdog.ps1'
$ephemeralCliPath = Join-Path $root 'Manage-EphemeralRunner.ps1'
$ephemeralTestPath = Join-Path $root 'Test-EphemeralRunnerController.ps1'
$capabilitiesPath = Join-Path $root 'RunnerCapabilities.ps1'
$capabilitiesCliPath = Join-Path $root 'Inspect-RunnerCapabilities.ps1'
$capabilitiesTestPath = Join-Path $root 'Test-RunnerCapabilities.ps1'
$localGradlePath = Join-Path $root 'Use-LocalGradle.ps1'
$lifecyclePath = Join-Path $root 'RunnerLifecycle.ps1'
$commandCenterTestPath = Join-Path $root 'Test-CommandCenterContract.ps1'
$runtimeSourcePath = Join-Path $buildDir 'JollyRunnerHub.source.ps1'

$scriptText = Get-Content -LiteralPath $scriptPath -Raw -Encoding UTF8
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseInput(
    $scriptText, [ref]$tokens, [ref]$parseErrors) | Out-Null
if (@($parseErrors).Count -gt 0) {
    $details = @($parseErrors | ForEach-Object {
        '{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message
    }) -join [Environment]::NewLine
    throw "JollyRunnerHub.ps1 syntax validation failed:`n$details"
}

$connectionStateText = Get-Content -LiteralPath $connectionStatePath -Raw -Encoding UTF8
$connectionTokens = $null
$connectionParseErrors = $null
[System.Management.Automation.Language.Parser]::ParseInput(
    $connectionStateText, [ref]$connectionTokens, [ref]$connectionParseErrors) | Out-Null
if (@($connectionParseErrors).Count -gt 0) {
    $details = @($connectionParseErrors | ForEach-Object {
        '{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message
    }) -join [Environment]::NewLine
    throw "RunnerConnectionState.ps1 syntax validation failed:`n$details"
}

. $connectionStatePath
function Assert-RunnerConnectionState {
    param(
        [Parameter(Mandatory=$true)][string]$Expected,
        [Parameter(Mandatory=$true)][bool]$ProcessRunning,
        [string[]]$Lines = @()
    )
    $actual = Get-JollyRunnerConnectionState -ProcessRunning $ProcessRunning -LogLines $Lines
    if ([string]$actual.Code -ne $Expected) {
        throw "Runner connection classifier expected '$Expected' but returned '$($actual.Code)' from '$($actual.Evidence)'"
    }
}
Assert-RunnerConnectionState -Expected 'stopped' -ProcessRunning $false
Assert-RunnerConnectionState -Expected 'starting' -ProcessRunning $true -Lines @('Runner boot sequence')
Assert-RunnerConnectionState -Expected 'connected_starting' -ProcessRunning $true -Lines @('Connected to GitHub')
Assert-RunnerConnectionState -Expected 'listening' -ProcessRunning $true -Lines @('Connected to GitHub','Listening for Jobs')
Assert-RunnerConnectionState -Expected 'running_job' -ProcessRunning $true -Lines @('Listening for Jobs','Running job: validate')
Assert-RunnerConnectionState -Expected 'reconnecting' -ProcessRunning $true -Lines @('Listening for Jobs','Runner connect error: The HTTP request timed out')
$healthNow = [datetime]'2026-09-02T13:00:00Z'
$staleHealth = Get-JollyRunnerConnectionState -ProcessRunning $true -LogLines @('Runner connect error: The HTTP request timed out') -LogUpdatedAtUtc ([datetime]'2026-09-02T12:55:00Z') -NowUtc $healthNow
if ($staleHealth.Code -ne 'stale_diagnostics' -or $staleHealth.DiagnosticsFreshness -ne 'stale' -or $staleHealth.LogAgeSeconds -ne 300) {
    throw "Stale diagnostics contract failed: $($staleHealth | ConvertTo-Json -Compress)"
}
$onlineHealth = Get-JollyRunnerConnectionState -ProcessRunning $true -LogLines @('old reconnect marker') -LogUpdatedAtUtc ([datetime]'2026-09-02T12:55:00Z') -NowUtc $healthNow -GitHubStatus online
if ($onlineHealth.Code -ne 'listening' -or $onlineHealth.GitHubStatus -ne 'online') { throw 'GitHub online state did not override stale diagnostics.' }
$unreadableHealth = Get-JollyRunnerConnectionState -ProcessRunning $true -DiagnosticsReadable $false
if ($unreadableHealth.Code -ne 'diagnostics_unreadable') { throw 'Unreadable diagnostics state was not classified.' }

foreach ($ephemeralPath in @($ephemeralModulePath,$ephemeralWatchdogPath,$ephemeralCliPath,$ephemeralTestPath)) {
    $ephemeralText = Get-Content -LiteralPath $ephemeralPath -Raw -Encoding UTF8
    $ephemeralTokens = $null
    $ephemeralParseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseInput(
        $ephemeralText,[ref]$ephemeralTokens,[ref]$ephemeralParseErrors) | Out-Null
    if (@($ephemeralParseErrors).Count -gt 0) {
        $details = @($ephemeralParseErrors | ForEach-Object {
            '{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message
        }) -join [Environment]::NewLine
        throw "Ephemeral runner script syntax validation failed for $ephemeralPath`n$details"
    }
}
& $ephemeralTestPath | Out-Host
foreach ($capabilityScript in @($capabilitiesPath,$capabilitiesCliPath,$capabilitiesTestPath,$localGradlePath)) {
    $capabilityText = Get-Content -LiteralPath $capabilityScript -Raw -Encoding UTF8
    $capabilityTokens = $null
    $capabilityParseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseInput(
        $capabilityText,[ref]$capabilityTokens,[ref]$capabilityParseErrors) | Out-Null
    if (@($capabilityParseErrors).Count -gt 0) {
        $details = @($capabilityParseErrors | ForEach-Object {
            '{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message
        }) -join [Environment]::NewLine
        throw "Runner capability script syntax validation failed for $capabilityScript`n$details"
    }
}
& $capabilitiesTestPath | Out-Host

$commandCenterTestText = Get-Content -LiteralPath $commandCenterTestPath -Raw -Encoding UTF8
$commandCenterTokens = $null
$commandCenterParseErrors = $null
[System.Management.Automation.Language.Parser]::ParseInput(
    $commandCenterTestText,[ref]$commandCenterTokens,[ref]$commandCenterParseErrors) | Out-Null
if (@($commandCenterParseErrors).Count -gt 0) {
    $details = @($commandCenterParseErrors | ForEach-Object {
        '{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message
    }) -join [Environment]::NewLine
    throw ('Command Center contract test syntax validation failed:' + [Environment]::NewLine + $details)
}
& $commandCenterTestPath | Out-Host

& $localGradlePath -Version '8.8' | Out-Host

$lifecycleText = Get-Content -LiteralPath $lifecyclePath -Raw -Encoding UTF8
$lifecycleTokens = $null
$lifecycleParseErrors = $null
[System.Management.Automation.Language.Parser]::ParseInput(
    $lifecycleText, [ref]$lifecycleTokens, [ref]$lifecycleParseErrors) | Out-Null
if (@($lifecycleParseErrors).Count -gt 0) {
    $details = @($lifecycleParseErrors | ForEach-Object {
        '{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message
    }) -join [Environment]::NewLine
    throw "RunnerLifecycle.ps1 syntax validation failed:`n$details"
}

. $lifecyclePath
if ((Get-JollyEphemeralTtlMinutes ([pscustomobject]@{})) -ne 30) { throw 'Default ephemeral TTL contract failed.' }
if ((Get-JollyEphemeralTtlMinutes ([pscustomobject]@{ephemeralTtlMinutes=1})) -ne 5) { throw 'Minimum ephemeral TTL contract failed.' }
if ((Get-JollyEphemeralTtlMinutes ([pscustomobject]@{ephemeralTtlMinutes=999})) -ne 120) { throw 'Maximum ephemeral TTL contract failed.' }
$lifecycleTestRoot = Join-Path $buildDir 'lifecycle-contract-test'
Remove-Item -LiteralPath $lifecycleTestRoot -Recurse -Force -ErrorAction SilentlyContinue
try {
    $inside = Join-Path (Get-JollyEphemeralRoot $lifecycleTestRoot) 'inside'
    $outside = Join-Path $buildDir 'outside-lifecycle-test'
    if (-not (Test-JollyPathInside -Path $inside -Root (Get-JollyEphemeralRoot $lifecycleTestRoot))) { throw 'Ephemeral root guard rejected an owned path.' }
    if (Test-JollyPathInside -Path $outside -Root (Get-JollyEphemeralRoot $lifecycleTestRoot)) { throw 'Ephemeral root guard accepted an outside path.' }
    $caps = Get-JollyRunnerCapabilities -RunnerRoot $root -CommandsOnly
    if ($null -eq $caps.PSObject.Properties['Summary']) { throw 'Runner capability contract is missing Summary.' }
    $finishedRoot = Join-Path (Get-JollyEphemeralRoot $lifecycleTestRoot) 'finished'
    New-Item -ItemType Directory -Force -Path $finishedRoot | Out-Null
    $finished = [pscustomobject][ordered]@{stateId='finished';profileId='test';repository='owner/repo';runnerName='finished';root=$finishedRoot;processId=2147483647;createdAt=[datetime]::UtcNow.AddMinutes(-10).ToString('o');expiresAt=[datetime]::UtcNow.AddMinutes(-5).ToString('o');ttlMinutes=5;labels=@('jolly-ephemeral')}
    [void](Write-JollyEphemeralState -AppRoot $lifecycleTestRoot -State $finished)
    $gc = @(Invoke-JollyEphemeralGc -AppRoot $lifecycleTestRoot -SkipGitHub)
    if (@($gc | Where-Object { $_.Action -eq 'cleaned_finished' }).Count -ne 1) { throw 'Finished ephemeral GC recovery contract failed.' }
    $liveRoot = Join-Path (Get-JollyEphemeralRoot $lifecycleTestRoot) 'expired-live'
    New-Item -ItemType Directory -Force -Path $liveRoot | Out-Null
    $expired = [pscustomobject][ordered]@{stateId='expired-live';profileId='test';repository='owner/repo';runnerName='expired-live';root=$liveRoot;processId=$PID;createdAt=[datetime]::UtcNow.AddMinutes(-10).ToString('o');expiresAt=[datetime]::UtcNow.AddMinutes(-1).ToString('o');ttlMinutes=5;labels=@('jolly-ephemeral')}
    [void](Write-JollyEphemeralState -AppRoot $lifecycleTestRoot -State $expired)
    $dryRun = @(Invoke-JollyEphemeralGc -AppRoot $lifecycleTestRoot -DryRun -SkipGitHub)
    if (@($dryRun | Where-Object { $_.Action -eq 'would_clean_expired' }).Count -ne 1) { throw 'Expired ephemeral dry-run TTL contract failed.' }
    Remove-Item -LiteralPath $liveRoot -Recurse -Force -ErrorAction SilentlyContinue

    $legacyRoot = Join-Path (Get-JollyLegacyEphemeralRoot $lifecycleTestRoot) 'legacy'
    New-Item -ItemType Directory -Force -Path $legacyRoot | Out-Null
    if (-not (Test-JollyEphemeralOwnedPath -Path $legacyRoot -AppRoot $lifecycleTestRoot)) { throw 'Legacy ephemeral ownership compatibility failed.' }
    Remove-Item -LiteralPath $legacyRoot -Recurse -Force -ErrorAction SilentlyContinue
}
finally { Remove-Item -LiteralPath $lifecycleTestRoot -Recurse -Force -ErrorAction SilentlyContinue }

try {
    Add-Type -AssemblyName System.Windows.Forms.DataVisualization -ErrorAction Stop
}
catch {
    throw 'System.Windows.Forms.DataVisualization is required for the real-time dashboard charts.'
}

$null = Get-Content -LiteralPath $defaultConfig -Raw -Encoding UTF8 | ConvertFrom-Json

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
New-Item -ItemType Directory -Force -Path $appData | Out-Null

$dashboardTabTarget = '$dashboardTab.BackColor = $ColorWindow'
$dashboardTabReplacement = @'
$dashboardTab.BackColor = $ColorWindow
$dashboardTab.AutoScroll = $true
$dashboardTab.AutoScrollMargin = New-Object Drawing.Size(0,16)
'@
if (-not $scriptText.Contains($dashboardTabTarget)) {
    throw 'Runner Hub scroll patch target was not found: dashboard tab.'
}
$runtimeScriptText = $scriptText.Replace($dashboardTabTarget,$dashboardTabReplacement.TrimEnd())
$runtimeScriptText = $runtimeScriptText.Replace("`r`n","`n")

$runnerLifecycleLoader = @'
$RunnerLifecyclePath = Join-Path $PSScriptRoot 'RunnerLifecycle.ps1'
if (-not (Test-Path -LiteralPath $RunnerLifecyclePath)) {
    $RunnerLifecyclePath = Join-Path (Split-Path -Parent $PSScriptRoot) 'RunnerLifecycle.ps1'
}
if (-not (Test-Path -LiteralPath $RunnerLifecyclePath)) { throw 'RunnerLifecycle.ps1 was not found.' }
. $RunnerLifecyclePath
'@
$runnerLifecycleLoaderText = $runnerLifecycleLoader.Trim().Replace("`r`n","`n")
if (-not $runtimeScriptText.Contains($runnerLifecycleLoaderText)) {
    throw 'Runner Hub lifecycle loader patch target was not found.'
}
$runtimeScriptText = $runtimeScriptText.Replace(
    $runnerLifecycleLoaderText,
    $lifecycleText.TrimEnd().Replace("`r`n","`n"))

$dashboardLayoutTarget = '$dashboardTab.Controls.Add($dashboardLayout)'
$dashboardLayoutReplacement = @'
$dashboardLayout.Dock = 'Top'
$dashboardLayout.Height = 1040
$dashboardLayout.MinimumSize = New-Object Drawing.Size(0,1040)
$dashboardTab.AutoScrollMinSize = New-Object Drawing.Size(0,1060)
[void]$dashboardTab.Controls.Add($dashboardLayout)
'@
if (-not $runtimeScriptText.Contains($dashboardLayoutTarget)) {
    throw 'Runner Hub scroll patch target was not found: dashboard layout.'
}
$runtimeScriptText = $runtimeScriptText.Replace(
    $dashboardLayoutTarget,
    $dashboardLayoutReplacement.TrimEnd())

$runnerAdapterTarget = 'function Start-Runner($Profile) {'
$runnerAdapter = @'
function Get-RunnerConnectionLogSnapshot($Profile) {
    $files = New-Object System.Collections.Generic.List[object]

    $hubLog = Log-Path $Profile
    if (Test-Path -LiteralPath $hubLog) {
        [void]$files.Add((Get-Item -LiteralPath $hubLog))
    }

    $runnerRoot = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    $diagRoot = Join-Path $runnerRoot '_diag'
    if (Test-Path -LiteralPath $diagRoot) {
        $diagLog = Get-ChildItem -LiteralPath $diagRoot -Filter 'Runner_*.log' -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($null -ne $diagLog) { [void]$files.Add($diagLog) }
    }

    $lines = New-Object System.Collections.Generic.List[string]
    $latestWrite = [datetime]::MinValue
    $readable = $true
    foreach ($file in @($files | Sort-Object LastWriteTimeUtc)) {
        try {
            if ($file.LastWriteTimeUtc -gt $latestWrite) { $latestWrite = $file.LastWriteTimeUtc }
            foreach ($line in (Tail-Lines $file.FullName 1048576)) {
                [void]$lines.Add([string]$line)
            }
        } catch {
            $readable = $false
        }
    }
    return [pscustomobject]@{ Lines=$lines.ToArray(); UpdatedAtUtc=$latestWrite; Readable=$readable }
}

function Get-RunnerConnectionLogLines($Profile) {
    return @((Get-RunnerConnectionLogSnapshot $Profile).Lines)
}

function Get-RunnerGitHubStatus($Profile) {
    if ($null -eq $script:GitHubRunnerStatusCache) { $script:GitHubRunnerStatusCache = @{} }
    if ($null -eq $script:GitHubRunnerStatusCacheAt) { $script:GitHubRunnerStatusCacheAt = @{} }
    $id = Safe-Name ([string]$Profile.id)
    $cachedAt = if ($script:GitHubRunnerStatusCacheAt.ContainsKey($id)) { [datetime]$script:GitHubRunnerStatusCacheAt[$id] } else { [datetime]::MinValue }
    if ($script:GitHubRunnerStatusCache.ContainsKey($id) -and ([datetime]::UtcNow-$cachedAt).TotalSeconds -lt 15) {
        return $script:GitHubRunnerStatusCache[$id]
    }
    $status = 'unknown'
    $evidence = 'github=unknown'
    try {
        $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
        $runnerFile = Join-Path $root '.runner'
        $runnerName = ''
        if (Test-Path -LiteralPath $runnerFile) {
            $runnerConfig = Get-Content -LiteralPath $runnerFile -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($property in @('agentName','name')) {
                if ($runnerConfig.PSObject.Properties.Name -contains $property -and -not [string]::IsNullOrWhiteSpace([string]$runnerConfig.$property)) { $runnerName = [string]$runnerConfig.$property; break }
            }
        }
        $repository = ([string]$Profile.repoUrl).TrimEnd('/') -replace '^https://github.com/',''
        if ([string]::IsNullOrWhiteSpace($runnerName) -or [string]::IsNullOrWhiteSpace($repository)) {
            $evidence = 'github=unknown (runner name unavailable)'
        } else {
            $lookup = Find-JollyGitHubRunner -Repository $repository -RunnerName $runnerName
            if ($lookup.Ok -and $null -ne $lookup.Runner) {
                $candidate = [string]$lookup.Runner.status
                if ($candidate -in @('online','offline','busy')) { $status = $candidate; $evidence = 'github=' + $candidate }
            } elseif (-not $lookup.Ok) { $evidence = 'github=unknown (query failed)' }
            else { $status = 'offline'; $evidence = 'github=offline (runner not listed)' }
        }
    } catch { $evidence = 'github=unknown (query exception)' }
    $result = [pscustomobject]@{Status=$status;Evidence=$evidence}
    $script:GitHubRunnerStatusCache[$id] = $result
    $script:GitHubRunnerStatusCacheAt[$id] = [datetime]::UtcNow
    return $result
}

function Read-RunnerConnectionState($Profile) {
    $running = Runner-Running $Profile
    $remote = Get-RunnerGitHubStatus $Profile
    if (-not $running) {
        $state = Get-JollyRunnerConnectionState -ProcessRunning $false -LogLines @() -GitHubStatus $remote.Status
        $state.Evidence += '; ' + $remote.Evidence
        return $state
    }
    $snapshot = Get-RunnerConnectionLogSnapshot $Profile
    $state = Get-JollyRunnerConnectionState -ProcessRunning $true -LogLines @($snapshot.Lines) -LogUpdatedAtUtc $snapshot.UpdatedAtUtc -GitHubStatus $remote.Status -DiagnosticsReadable ([bool]$snapshot.Readable)
    $state.Evidence += '; ' + $remote.Evidence
    return $state
}

function Start-Runner($Profile) {
'@
if (-not $runtimeScriptText.Contains($runnerAdapterTarget)) {
    throw 'Runner Hub connection patch target was not found: Start-Runner.'
}
$runnerRuntimeFunctions = $connectionStateText.TrimEnd() + [Environment]::NewLine +
    [Environment]::NewLine + $runnerAdapter.TrimEnd()
$runtimeScriptText = $runtimeScriptText.Replace($runnerAdapterTarget,$runnerRuntimeFunctions)

$runnerStatusPattern = @'
(?ms)^[ \t]*if \(Runner-Running \$script:Profile\) \{\r?\n[ \t]*\$runnerStatus\.Value\.Text = '[^']*'\r?\n[ \t]*\$runnerStatus\.Value\.ForeColor = \[Drawing\.Color\]::FromArgb\(105,228,154\)\r?\n[ \t]*\} else \{\r?\n[ \t]*\$runnerStatus\.Value\.Text = '[^']*'\r?\n[ \t]*\$runnerStatus\.Value\.ForeColor = \[Drawing\.Color\]::FromArgb\(255,137,141\)\r?\n[ \t]*\}
'@
$runnerStatusReplacement = @'
        $runnerConnection = Read-RunnerConnectionState $script:Profile
        $runnerStatus.Value.Text = [string]$runnerConnection.Text
        $runnerStatus.Value.AccessibleDescription = [string]$runnerConnection.Evidence
        switch ([string]$runnerConnection.Tone) {
            'good' { $runnerStatus.Value.ForeColor = [Drawing.Color]::FromArgb(105,228,154) }
            'warn' { $runnerStatus.Value.ForeColor = [Drawing.Color]::FromArgb(255,205,112) }
            default { $runnerStatus.Value.ForeColor = [Drawing.Color]::FromArgb(255,137,141) }
        }
'@
$runnerStatusExpression = $runnerStatusPattern.Trim()
$runnerStatusOptions = ([System.Text.RegularExpressions.RegexOptions]::Multiline -bor
    [System.Text.RegularExpressions.RegexOptions]::Singleline)
$runnerStatusRegex = New-Object System.Text.RegularExpressions.Regex -ArgumentList @(
    $runnerStatusExpression,
    $runnerStatusOptions
)
if (-not $runnerStatusRegex.IsMatch($runtimeScriptText)) {
    throw 'Runner Hub connection patch target was not found: status timer.'
}
$runtimeScriptText = $runnerStatusRegex.Replace(
    $runtimeScriptText,
    $runnerStatusReplacement.TrimEnd(),
    1)

Set-Content -LiteralPath $runtimeSourcePath -Value $runtimeScriptText -Encoding UTF8

$runtimeTokens = $null
$runtimeParseErrors = $null
[System.Management.Automation.Language.Parser]::ParseInput(
    $runtimeScriptText, [ref]$runtimeTokens, [ref]$runtimeParseErrors) | Out-Null
if (@($runtimeParseErrors).Count -gt 0) {
    $details = @($runtimeParseErrors | ForEach-Object {
        '{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message
    }) -join [Environment]::NewLine
    throw "Scrollable Runner Hub runtime syntax validation failed:`n$details"
}

$iconParts = @(Get-ChildItem -LiteralPath $root -Filter 'JollyRunnerHub.ico.b64.part*' -File |
    Sort-Object Name)
if ($iconParts.Count -gt 0) {
    $b64 = (($iconParts | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw }) -join '') -replace '\s',''
} else {
    $b64 = (Get-Content -LiteralPath (Join-Path $root 'JollyRunnerHub.ico.b64') -Raw) -replace '\s',''
}
[System.IO.File]::WriteAllBytes($iconPath, [Convert]::FromBase64String($b64))

$cscCandidates = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$csc = $cscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $csc) {
    throw 'Windows .NET Framework C# compiler (csc.exe) was not found.'
}

& $csc /nologo /target:winexe /platform:anycpu /optimize+ /codepage:65001 `
    "/win32icon:$iconPath" "/win32manifest:$manifestPath" `
    "/out:$exePath" "/reference:System.dll" "/reference:System.Windows.Forms.dll" `
    $launcherPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $exePath)) {
    throw "Launcher compilation failed with exit code $LASTEXITCODE"
}

$smokeDefaultConfig = Join-Path $appData 'profiles.default.json'
$smokeProfile = Join-Path $appData 'profiles.json'
if (-not (Test-Path -LiteralPath $smokeDefaultConfig)) {
    Copy-Item -LiteralPath $defaultConfig -Destination $smokeDefaultConfig -Force
}
if (-not (Test-Path -LiteralPath $smokeProfile)) {
    Copy-Item -LiteralPath $defaultConfig -Destination $smokeProfile -Force
}

$previousSmokeSource = [Environment]::GetEnvironmentVariable('JOLLY_RUNNER_HUB_SOURCE','Process')
[Environment]::SetEnvironmentVariable('JOLLY_RUNNER_HUB_SOURCE',$runtimeSourcePath,'Process')
try {
    $smoke = Start-Process -FilePath $exePath -ArgumentList '--smoke-test' `
        -PassThru -Wait -WindowStyle Hidden
    if ($smoke.ExitCode -ne 0) {
        $smokeLog = Join-Path $appData 'startup-error.log'
        $detail = if (Test-Path -LiteralPath $smokeLog) {
            Get-Content -LiteralPath $smokeLog -Raw -Encoding UTF8
        } else {
            'No startup-error.log was produced.'
        }
        throw "JollyRunnerHub startup smoke test failed with exit code $($smoke.ExitCode):`n$detail"
    }
}
finally {
    [Environment]::SetEnvironmentVariable(
        'JOLLY_RUNNER_HUB_SOURCE',$previousSmokeSource,'Process')
}

function Copy-Or-StageUpdate {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$Destination,
        [Parameter(Mandatory=$true)][string]$Staged
    )
    try {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force -ErrorAction Stop
        if (Test-Path -LiteralPath $Staged) {
            Remove-Item -LiteralPath $Staged -Force -ErrorAction SilentlyContinue
        }
        return $false
    }
    catch [System.IO.IOException] {
        Copy-Item -LiteralPath $Source -Destination $Staged -Force
        return $true
    }
    catch [System.UnauthorizedAccessException] {
        Copy-Item -LiteralPath $Source -Destination $Staged -Force
        return $true
    }
}

if ($Install) {
    $installedScriptPath = Join-Path $appData 'JollyRunnerHub.ps1'
    Set-Content -LiteralPath $installedScriptPath -Value $runtimeScriptText -Encoding UTF8
    Copy-Item -LiteralPath $lifecyclePath -Destination (Join-Path $appData 'RunnerLifecycle.ps1') -Force
    Copy-Item -LiteralPath $defaultConfig -Destination $smokeDefaultConfig -Force
    foreach ($ephemeralPath in @($ephemeralModulePath,$ephemeralWatchdogPath,$ephemeralCliPath)) {
        Copy-Item -LiteralPath $ephemeralPath -Destination (Join-Path $appData (Split-Path -Leaf $ephemeralPath)) -Force
    }
    foreach ($capabilityScript in @($capabilitiesPath,$capabilitiesCliPath,$localGradlePath)) {
        Copy-Item -LiteralPath $capabilityScript -Destination (Join-Path $appData (Split-Path -Leaf $capabilityScript)) -Force
    }

    $profilePath = $smokeProfile
    if (-not (Test-Path -LiteralPath $profilePath)) {
        Copy-Item -LiteralPath $defaultConfig -Destination $profilePath -Force
    }

    if (-not (Test-Path -LiteralPath $desktop)) {
        New-Item -ItemType Directory -Force -Path $desktop | Out-Null
    }

    $desktopExe = Join-Path $desktop 'JollyRunnerHub.exe'
    $installedIcon = Join-Path $appData 'JollyRunnerHub.ico'
    $stagedExe = Join-Path $appData 'JollyRunnerHub.pending.exe'
    $stagedIcon = Join-Path $appData 'JollyRunnerHub.pending.ico'

    $exePending = Copy-Or-StageUpdate -Source $exePath -Destination $desktopExe -Staged $stagedExe
    $iconPending = Copy-Or-StageUpdate -Source $iconPath -Destination $installedIcon -Staged $stagedIcon
    $pendingRestart = $exePending -or $iconPending

    if ($pendingRestart) {
        $updaterPath = Join-Path $appData 'Apply-Pending-JollyRunnerHubUpdate.ps1'
        $updater = @'
$ErrorActionPreference = 'SilentlyContinue'
$appData = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'
$desktop = [Environment]::GetFolderPath('Desktop')
$desktopExe = Join-Path $desktop 'JollyRunnerHub.exe'
$installedIcon = Join-Path $appData 'JollyRunnerHub.ico'
$stagedExe = Join-Path $appData 'JollyRunnerHub.pending.exe'
$stagedIcon = Join-Path $appData 'JollyRunnerHub.pending.ico'
for ($attempt = 0; $attempt -lt 21600; $attempt++) {
    if (-not (Get-Process -Name 'JollyRunnerHub' -ErrorAction SilentlyContinue)) {
        if (Test-Path -LiteralPath $stagedExe) {
            Copy-Item -LiteralPath $stagedExe -Destination $desktopExe -Force
            Remove-Item -LiteralPath $stagedExe -Force
        }
        if (Test-Path -LiteralPath $stagedIcon) {
            Copy-Item -LiteralPath $stagedIcon -Destination $installedIcon -Force
            Remove-Item -LiteralPath $stagedIcon -Force
        }
        break
    }
    Start-Sleep -Seconds 1
}
'@
        Set-Content -LiteralPath $updaterPath -Value $updater -Encoding UTF8
        Start-Process powershell.exe -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
            '-File', ('"{0}"' -f $updaterPath)
        ) -WindowStyle Hidden | Out-Null
        Write-Host 'JollyRunnerHub is currently open. The new icon and executable are staged and will replace the old files after the app closes.'
    }

    $installInfo = [ordered]@{
        installed_at = (Get-Date).ToString('o')
        executable = $desktopExe
        app_root = $appData
        config = $profilePath
        icon_sha256 = (Get-FileHash -LiteralPath $iconPath -Algorithm SHA256).Hash.ToLowerInvariant()
        pending_restart = $pendingRestart
        dashboard_version = 4
        startup_smoke_test = 'passed'
        dashboard_scroll = 'vertical'
        runner_connection_state = 'log-classified'
        ephemeral_runner_lifecycle = 'watchdog-ttl-gc'
        runner_ephemeral_lifecycle = 'ttl-gc-v1'
        runner_capabilities = 'cached-v1'
    }
    $installInfo | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $appData 'install-status.json') -Encoding UTF8
    Write-Host "Installed JollyRunnerHub to $desktop (pending_restart=$pendingRestart)"
}

Write-Host "Built and startup-smoke-tested: $exePath"