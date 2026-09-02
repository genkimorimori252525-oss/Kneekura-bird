param(
    [string[]]$RunnerRoots = @(),
    [string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RunnerCapabilities.ps1')
$snapshot = Get-JollyRunnerCapabilities -RunnerRoots $RunnerRoots
$json = $snapshot | ConvertTo-Json -Depth 8
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $outputFull = [IO.Path]::GetFullPath($OutputPath)
    $parent = Split-Path -Parent $outputFull
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $tempPath = '{0}.tmp.{1}.{2}' -f $outputFull,$PID,([guid]::NewGuid().ToString('N'))
    $backupPath = '{0}.bak' -f $outputFull
    try {
        [IO.File]::WriteAllText($tempPath,$json,(New-Object Text.UTF8Encoding($false)))
        [void]($json | ConvertFrom-Json)
        if (Test-Path -LiteralPath $outputFull) {
            [IO.File]::Replace($tempPath,$outputFull,$backupPath,$true)
            Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
        } else {
            Move-Item -LiteralPath $tempPath -Destination $outputFull -Force
        }
    } finally {
        Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
    }
}
$json
