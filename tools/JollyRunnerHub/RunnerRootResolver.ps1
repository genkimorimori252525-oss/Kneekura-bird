Set-StrictMode -Version Latest

function ConvertTo-JollyRepositorySlug {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
    $text = ([string]$Value).Trim().TrimEnd('/')
    $text = $text -replace '^https://github.com/',''
    if ($text -match '^[^/]+/[^/]+$') { return $text.ToLowerInvariant() }
    return ''
}

function Get-JollyRunnerRepositoryFromRoot {
    param([Parameter(Mandatory=$true)][string]$Root)
    $runnerFile = Join-Path $Root '.runner'
    if (-not (Test-Path -LiteralPath $runnerFile -PathType Leaf)) { return '' }
    try {
        $config = Get-Content -LiteralPath $runnerFile -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($name in @('gitHubUrl','serverUrl')) {
            $property = $config.PSObject.Properties[$name]
            if ($null -eq $property) { continue }
            $slug = ConvertTo-JollyRepositorySlug ([string]$property.Value)
            if ($slug) { return $slug }
        }
    } catch {}
    return ''
}

function Test-JollyConfiguredRunnerRoot {
    param([string]$Root)
    if ([string]::IsNullOrWhiteSpace($Root)) { return $false }
    $expanded = [Environment]::ExpandEnvironmentVariables($Root)
    return (Test-Path -LiteralPath (Join-Path $expanded 'run.cmd') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $expanded '.runner') -PathType Leaf)
}

function Get-JollyRunnerRootCandidates {
    param([string[]]$AdditionalRoots = @())
    $roots = @{}
    foreach ($raw in @($AdditionalRoots)) {
        if ([string]::IsNullOrWhiteSpace([string]$raw)) { continue }
        try {
            $root = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables([string]$raw)).TrimEnd('\','/')
            $roots[$root.ToLowerInvariant()] = $root
        } catch {}
    }

    $localActions = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'GitHubActions'
    if (Test-Path -LiteralPath $localActions -PathType Container) {
        foreach ($directory in @(Get-ChildItem -LiteralPath $localActions -Directory -ErrorAction SilentlyContinue)) {
            try {
                $root = $directory.FullName.TrimEnd('\','/')
                $roots[$root.ToLowerInvariant()] = $root
            } catch {}
        }
    }

    $driveRoot = [IO.Path]::GetPathRoot($env:SystemDrive + '\')
    if (Test-Path -LiteralPath $driveRoot -PathType Container) {
        foreach ($directory in @(Get-ChildItem -LiteralPath $driveRoot -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'actions-runner*' })) {
            $root = $directory.FullName.TrimEnd('\','/')
            $roots[$root.ToLowerInvariant()] = $root
        }
    }
    return @($roots.Values)
}

function Resolve-JollyRunnerRootBinding {
    param(
        [Parameter(Mandatory=$true)]$Profile,
        [string[]]$CandidateRoots = @()
    )
    $expectedRepo = ConvertTo-JollyRepositorySlug ([string]$Profile.repoUrl)
    $configuredRoot = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)

    if (Test-JollyConfiguredRunnerRoot $configuredRoot) {
        $repo = Get-JollyRunnerRepositoryFromRoot $configuredRoot
        if (-not $expectedRepo -or -not $repo -or $repo -eq $expectedRepo) {
            return [pscustomobject]@{Status='configured';Root=$configuredRoot;ConfiguredRoot=$configuredRoot;Repository=$repo;Candidates=@($configuredRoot)}
        }
    }

    $allRoots = @($CandidateRoots)
    if ($allRoots.Count -eq 0) {
        $allRoots = @(Get-JollyRunnerRootCandidates -AdditionalRoots @($configuredRoot))
    }
    $matches = New-Object System.Collections.Generic.List[string]
    foreach ($raw in $allRoots) {
        if (-not (Test-JollyConfiguredRunnerRoot $raw)) { continue }
        $repo = Get-JollyRunnerRepositoryFromRoot $raw
        if ($expectedRepo -and $repo -eq $expectedRepo) { [void]$matches.Add([Environment]::ExpandEnvironmentVariables([string]$raw)) }
    }
    $unique = @($matches | Sort-Object -Unique)
    if ($unique.Count -eq 1) {
        return [pscustomobject]@{Status='fallback';Root=$unique[0];ConfiguredRoot=$configuredRoot;Repository=$expectedRepo;Candidates=$unique}
    }
    if ($unique.Count -gt 1) {
        return [pscustomobject]@{Status='ambiguous';Root='';ConfiguredRoot=$configuredRoot;Repository=$expectedRepo;Candidates=$unique}
    }
    return [pscustomobject]@{Status='missing';Root='';ConfiguredRoot=$configuredRoot;Repository=$expectedRepo;Candidates=@()}
}

function New-JollyProfileWithRunnerRoot {
    param(
        [Parameter(Mandatory=$true)]$Profile,
        [Parameter(Mandatory=$true)][string]$RunnerRoot
    )
    $copy = [pscustomobject]@{}
    foreach ($property in @($Profile.PSObject.Properties)) {
        Add-Member -InputObject $copy -NotePropertyName ([string]$property.Name) -NotePropertyValue $property.Value
    }
    if ($null -eq $copy.PSObject.Properties['runnerRoot']) {
        Add-Member -InputObject $copy -NotePropertyName runnerRoot -NotePropertyValue $RunnerRoot
    } else {
        $copy.runnerRoot = $RunnerRoot
    }
    return $copy
}
