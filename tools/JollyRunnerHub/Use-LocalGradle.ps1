[CmdletBinding()]
param(
    [ValidatePattern('^\d+(?:\.\d+){1,2}$')]
    [string]$Version = '8.8'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$distributionRoot = Join-Path $env:USERPROFILE ".gradle\wrapper\dists\gradle-$Version-bin"
$candidates = @(
    Get-ChildItem -LiteralPath $distributionRoot -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "gradle-$Version\bin\gradle.bat" } |
        Where-Object { Test-Path -LiteralPath $_ } |
        Sort-Object
)
if ($candidates.Count -eq 0) {
    throw "TOOLCHAIN_FAILURE: cached Gradle $Version was not found under $distributionRoot"
}

$gradle = $candidates[0]
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $versionOutput = @(& $gradle --version 2>&1)
    $gradleExitCode = $LASTEXITCODE
}
finally { $ErrorActionPreference = $previousPreference }
if ($gradleExitCode -ne 0) {
    throw "TOOLCHAIN_FAILURE: cached Gradle probe failed with exit code $gradleExitCode"
}
$versionLine = $versionOutput | Where-Object { $_ -match '^Gradle\s+' } | Select-Object -First 1
if ([string]$versionLine -notmatch ('^Gradle\s+' + [regex]::Escape($Version) + '$')) {
    throw "TOOLCHAIN_FAILURE: expected Gradle $Version, detected '$versionLine'"
}

$bin = Split-Path -Parent $gradle
if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_PATH)) {
    Add-Content -LiteralPath $env:GITHUB_PATH -Value $bin -Encoding UTF8
}
Write-Output "LOCAL_GRADLE_VERSION=$Version"
Write-Output "LOCAL_GRADLE_BIN=$bin"
