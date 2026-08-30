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
$lifecyclePath = Join-Path $root 'RunnerLifecycle.ps1'
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

$runnerLifecycleLoader = @'
$RunnerLifecyclePath = Join-Path $PSScriptRoot 'RunnerLifecycle.ps1'
if (-not (Test-Path -LiteralPath $RunnerLifecyclePath)) {
    $RunnerLifecyclePath = Join-Path (Split-Path -Parent $PSScriptRoot) 'RunnerLifecycle.ps1'
}
if (-not (Test-Path -LiteralPath $RunnerLifecyclePath)) { throw 'RunnerLifecycle.ps1 was not found.' }
. $RunnerLifecyclePath
'@
if (-not $runtimeScriptText.Contains($runnerLifecycleLoader.Trim())) {
    throw 'Runner Hub lifecycle loader patch target was not found.'
}
$runtimeScriptText = $runtimeScriptText.Replace(
    $runnerLifecycleLoader.Trim(),
    $lifecycleText.TrimEnd())

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
function Get-RunnerConnectionLogLines($Profile) {
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
    foreach ($file in @($files | Sort-Object LastWriteTimeUtc)) {
        foreach ($line in (Tail-Lines $file.FullName 1048576)) {
            [void]$lines.Add([string]$line)
        }
    }
    return $lines.ToArray()
}

function Read-RunnerConnectionState($Profile) {
    $running = Runner-Running $Profile
    if (-not $running) {
        return Get-JollyRunnerConnectionState -ProcessRunning $false -LogLines @()
    }
    $lines = @(Get-RunnerConnectionLogLines $Profile)
    return Get-JollyRunnerConnectionState -ProcessRunning $true -LogLines $lines
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
        runner_ephemeral_lifecycle = 'ttl-gc-v1'
        runner_capabilities = 'cached-v1'
    }
    $installInfo | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $appData 'install-status.json') -Encoding UTF8
    Write-Host "Installed JollyRunnerHub to $desktop (pending_restart=$pendingRestart)"
}

Write-Host "Built and startup-smoke-tested: $exePath"
