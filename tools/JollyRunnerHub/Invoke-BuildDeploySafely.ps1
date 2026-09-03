param(
    [switch]$Install = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$buildDeploy = Join-Path $root 'Build-Deploy.ps1'
if (-not (Test-Path -LiteralPath $buildDeploy -PathType Leaf)) {
    throw "Build-Deploy.ps1 was not found: $buildDeploy"
}

function Test-JollyTransientRuntimeFileLock {
    param([Parameter(Mandatory=$true)]$ErrorRecord)
    $text = $ErrorRecord | Out-String
    return $text -match '(?i)(used by another process|being used by another process|process cannot access the file|System\.IO\.IOException)'
}

if ($Install) {
    for ($attempt = 1; $attempt -le 4; $attempt++) {
        try {
            & $buildDeploy -Install:$true
            return
        }
        catch {
            if ($attempt -ge 4 -or -not (Test-JollyTransientRuntimeFileLock $_)) {
                throw
            }
            Write-Host ("Transient JollyRunnerHub runtime file lock; retry {0}/4 after 2s." -f $attempt)
            Start-Sleep -Seconds 2
        }
    }
    return
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('JollyRunnerHub-pr-smoke-' + [guid]::NewGuid().ToString('N'))
$workRoot = Join-Path $tempRoot 'JollyRunnerHub'
$smokeAppRoot = Join-Path $tempRoot 'app'

function Replace-JollyRequiredText {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Needle,
        [Parameter(Mandatory=$true)][string]$Replacement,
        [Parameter(Mandatory=$true)][string]$Description
    )
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if (-not $text.Contains($Needle)) {
        throw "Isolation patch target was not found: $Description"
    }
    $updated = $text.Replace($Needle,$Replacement)
    Set-Content -LiteralPath $Path -Value $updated -Encoding UTF8
}

try {
    New-Item -ItemType Directory -Force -Path $workRoot,$smokeAppRoot | Out-Null
    Copy-Item -Path (Join-Path $root '*') -Destination $workRoot -Recurse -Force

    $escapedSmokePs = $smokeAppRoot.Replace("'","''")
    $buildCopy = Join-Path $workRoot 'Build-Deploy.ps1'
    $hubCopy = Join-Path $workRoot 'JollyRunnerHub.ps1'
    $launcherCopy = Join-Path $workRoot 'Launcher.cs'

    $buildNeedle = @'
$appData = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'
'@.Trim()
    Replace-JollyRequiredText -Path $buildCopy -Needle $buildNeedle -Replacement ("`$appData = '{0}'" -f $escapedSmokePs) -Description 'Build-Deploy AppRoot'

    $hubNeedle = @'
$AppRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'
'@.Trim()
    Replace-JollyRequiredText -Path $hubCopy -Needle $hubNeedle -Replacement ("`$AppRoot = '{0}'" -f $escapedSmokePs) -Description 'Runner Hub AppRoot'

    $launcherText = Get-Content -LiteralPath $launcherCopy -Raw -Encoding UTF8
    $launcherPattern = 'string appRoot = Path\.Combine\(\s*Environment\.GetFolderPath\(Environment\.SpecialFolder\.LocalApplicationData\),\s*"JollyRunnerHub"\);'
    if (-not [regex]::IsMatch($launcherText,$launcherPattern)) {
        throw 'Isolation patch target was not found: Launcher AppRoot'
    }
    $escapedSmokeCs = $smokeAppRoot.Replace('"','""')
    $launcherText = [regex]::Replace($launcherText,$launcherPattern,('string appRoot = @"{0}";' -f $escapedSmokeCs),1)
    Set-Content -LiteralPath $launcherCopy -Value $launcherText -Encoding UTF8

    & $buildCopy -Install:$false

    $runtimeProof = Join-Path $smokeAppRoot 'JollyRunnerHub.runtime.ps1'
    $bootstrapProof = Join-Path $smokeAppRoot 'JollyRunnerHub.bootstrap.ps1'
    if (-not (Test-Path -LiteralPath $runtimeProof -PathType Leaf) -or
        -not (Test-Path -LiteralPath $bootstrapProof -PathType Leaf)) {
        throw 'Isolated smoke test did not produce runtime proof in the temporary AppRoot.'
    }
    Write-Host "PR smoke test stayed isolated from the installed JollyRunnerHub AppRoot."
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
