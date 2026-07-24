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
        dashboard_version = 3
        startup_smoke_test = 'passed'
        dashboard_scroll = 'vertical'
    }
    $installInfo | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $appData 'install-status.json') -Encoding UTF8
    Write-Host "Installed JollyRunnerHub to $desktop (pending_restart=$pendingRestart)"
}

Write-Host "Built and startup-smoke-tested: $exePath"
