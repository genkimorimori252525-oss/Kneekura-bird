Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RunnerRootResolver.ps1')

$root = Join-Path ([IO.Path]::GetTempPath()) ('JollyRootResolver-' + [guid]::NewGuid().ToString('N'))
function New-Fixture([string]$Name,[string]$Repo) {
    $dir = Join-Path $root $Name
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Set-Content -LiteralPath (Join-Path $dir 'run.cmd') -Value '@echo off' -Encoding ASCII
    [ordered]@{agentName=$Name;gitHubUrl=('https://github.com/' + $Repo)} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dir '.runner') -Encoding UTF8
    return $dir
}
try {
    $a = New-Fixture 'runner-a' 'owner/repo-a'
    $b = New-Fixture 'runner-b' 'owner/repo-b'
    $profile = [pscustomobject]@{runnerRoot=(Join-Path $root 'missing');repoUrl='https://github.com/owner/repo-a'}
    $one = Resolve-JollyRunnerRootBinding -Profile $profile -CandidateRoots @($a,$b)
    if ($one.Status -ne 'fallback' -or $one.Root -ne $a) { throw 'single repository fallback failed' }

    $profile.runnerRoot = $a
    $preferred = Resolve-JollyRunnerRootBinding -Profile $profile -CandidateRoots @($a,$b)
    if ($preferred.Status -ne 'configured' -or $preferred.Root -ne $a) { throw 'configured root must win' }

    $a2 = New-Fixture 'runner-a2' 'owner/repo-a'
    $profile.runnerRoot = Join-Path $root 'missing'
    $ambiguous = Resolve-JollyRunnerRootBinding -Profile $profile -CandidateRoots @($a,$a2,$b)
    if ($ambiguous.Status -ne 'ambiguous' -or @($ambiguous.Candidates).Count -ne 2) { throw 'ambiguous repository binding must fail closed' }

    $noneProfile = [pscustomobject]@{runnerRoot=(Join-Path $root 'missing2');repoUrl='https://github.com/owner/none'}
    $none = Resolve-JollyRunnerRootBinding -Profile $noneProfile -CandidateRoots @($a,$b)
    if ($none.Status -ne 'missing') { throw 'missing repository binding failed' }
    Write-Host 'runner root resolver tests: ok'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
