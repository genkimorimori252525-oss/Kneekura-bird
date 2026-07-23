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

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
New-Item -ItemType Directory -Force -Path $appData | Out-Null

$b64 = (Get-Content -LiteralPath (Join-Path $root 'JollyRunnerHub.ico.b64') -Raw) -replace '\s',''
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

if ($Install) {
    Copy-Item -LiteralPath $scriptPath -Destination (Join-Path $appData 'JollyRunnerHub.ps1') -Force
    Copy-Item -LiteralPath $defaultConfig -Destination (Join-Path $appData 'profiles.default.json') -Force
    Copy-Item -LiteralPath $iconPath -Destination (Join-Path $appData 'JollyRunnerHub.ico') -Force

    $profilePath = Join-Path $appData 'profiles.json'
    if (-not (Test-Path -LiteralPath $profilePath)) {
        Copy-Item -LiteralPath $defaultConfig -Destination $profilePath -Force
    }

    if (-not (Test-Path -LiteralPath $desktop)) {
        New-Item -ItemType Directory -Force -Path $desktop | Out-Null
    }
    Copy-Item -LiteralPath $exePath -Destination (Join-Path $desktop 'JollyRunnerHub.exe') -Force

    $installInfo = [ordered]@{
        installed_at = (Get-Date).ToString('o')
        executable = (Join-Path $desktop 'JollyRunnerHub.exe')
        app_root = $appData
        config = $profilePath
        icon_sha256 = (Get-FileHash -LiteralPath $iconPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $installInfo | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $appData 'install-status.json') -Encoding UTF8
    Write-Host "Installed JollyRunnerHub to $desktop"
}

Write-Host "Built: $exePath"
