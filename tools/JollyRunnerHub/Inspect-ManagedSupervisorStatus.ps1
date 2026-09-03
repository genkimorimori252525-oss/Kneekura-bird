[CmdletBinding()]
param(
    [string]$AppRoot = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolver = Join-Path $PSScriptRoot 'RunnerRootResolver.ps1'
if (-not (Test-Path -LiteralPath $resolver -PathType Leaf)) { $resolver = Join-Path $AppRoot 'RunnerRootResolver.ps1' }
if (-not (Test-Path -LiteralPath $resolver -PathType Leaf)) { throw 'RunnerRootResolver.ps1 was not found.' }
. $resolver

$configPath = Join-Path $AppRoot 'profiles.json'
$statusPath = Join-Path $AppRoot 'supervisor-status.json'
$eventPath = Join-Path $AppRoot 'managed-supervisor.jsonl'
$dispatchRoot = Join-Path $AppRoot 'dispatch'
$trimChars = [char[]]@([IO.Path]::DirectorySeparatorChar,[IO.Path]::AltDirectorySeparatorChar)

function Leaf([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
    try {
        $expanded = [Environment]::ExpandEnvironmentVariables($Value).TrimEnd($trimChars)
        return Split-Path -Leaf $expanded
    } catch { return '' }
}

function Read-Json([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
}

function Get-StatusAgeSeconds([string]$Timestamp) {
    if ([string]::IsNullOrWhiteSpace($Timestamp)) { return $null }
    try {
        $parsed = [DateTimeOffset]::Parse($Timestamp,[Globalization.CultureInfo]::InvariantCulture)
        $seconds = ([DateTimeOffset]::UtcNow - $parsed.ToUniversalTime()).TotalSeconds
        return [math]::Max(0,[int][math]::Floor($seconds))
    } catch {
        return $null
    }
}

function Get-SafeDiagnosticText([string]$Value,[int]$MaxLength = 400) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
    $text = $Value -replace '(?i)\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b','<redacted-token>'
    $text = $text -replace '(?i)(Authorization:\s*(?:token|bearer|basic)?\s*)\S+','$1<redacted>'
    $text = $text -replace '[\r\n]+',' '
    if ($text.Length -gt $MaxLength) { $text = $text.Substring(0,$MaxLength) }
    return $text
}

function Read-DispatchProbe([string]$ProfileId) {
    if ([string]::IsNullOrWhiteSpace($ProfileId)) { return $null }
    $safeId = $ProfileId -replace '[^A-Za-z0-9_.-]','_'
    return Read-Json (Join-Path $dispatchRoot ("dispatch-$safeId.json"))
}

$config = Read-Json $configPath
$status = Read-Json $statusPath
$configuredRoots = if ($null -ne $config) { @($config.profiles | ForEach-Object { [string]$_.runnerRoot } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) } else { @() }
$candidateRoots = @(Get-JollyRunnerRootCandidates -AdditionalRoots $configuredRoots)

$listenerRoots = @{}
try {
    foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name='Runner.Listener.exe'" -ErrorAction SilentlyContinue)) {
        if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) { continue }
        try {
            $root = Split-Path -Parent (Split-Path -Parent ([string]$process.ExecutablePath))
            $key = [IO.Path]::GetFullPath($root).TrimEnd($trimChars).ToLowerInvariant()
            $listenerRoots[$key] = $true
        } catch {}
    }
} catch {}

$candidateSummary = @()
foreach ($root in $candidateRoots) {
    if (-not (Test-JollyConfiguredRunnerRoot $root)) { continue }
    $key = ''
    try { $key = [IO.Path]::GetFullPath($root).TrimEnd($trimChars).ToLowerInvariant() } catch {}
    $candidateSummary += [pscustomobject]@{
        rootLeaf = Leaf $root
        repository = Get-JollyRunnerRepositoryFromRoot $root
        listenerRunning = ($key -and $listenerRoots.ContainsKey($key))
    }
}

$statusById = @{}
if ($null -ne $status) {
    foreach ($item in @($status.profiles)) { $statusById[[string]$item.id] = $item }
}

$profileSummary = @()
if ($null -ne $config) {
    foreach ($profile in @($config.profiles)) {
        $profileId = [string]$profile.id
        $binding = Resolve-JollyRunnerRootBinding -Profile $profile -CandidateRoots $candidateRoots
        $live = if ($statusById.ContainsKey($profileId)) { $statusById[$profileId] } else { $null }
        $probe = Read-DispatchProbe $profileId
        $profileSummary += [pscustomobject]@{
            id = $profileId
            repository = ConvertTo-JollyRepositorySlug ([string]$profile.repoUrl)
            configuredRootLeaf = Leaf ([string]$binding.ConfiguredRoot)
            binding = [string]$binding.Status
            effectiveRootLeaf = Leaf ([string]$binding.Root)
            matchCount = @($binding.Candidates).Count
            desiredState = if ($null -ne $live) { [string]$live.desiredState } else { '' }
            configured = if ($null -ne $live) { [bool]$live.configured } else { $false }
            processRunning = if ($null -ne $live) { [bool]$live.processRunning } else { $false }
            localCode = if ($null -ne $live) { [string]$live.localCode } else { '' }
            dispatchCode = if ($null -ne $live) { [string]$live.dispatchCode } else { '' }
            dispatchProbePresent = ($null -ne $probe)
            dispatchProbeApiOk = if ($null -ne $probe) { [bool]$probe.apiOk } else { $null }
            dispatchProbeAgeSeconds = if ($null -ne $probe) { Get-StatusAgeSeconds ([string]$probe.probedAt) } else { $null }
            dispatchProbeError = if ($null -ne $probe) { Get-SafeDiagnosticText ([string]$probe.error) } else { '' }
            action = if ($null -ne $live) { [string]$live.action } else { '' }
            reason = if ($null -ne $live) { [string]$live.decisionReason } else { '' }
        }
    }
}

$events = @()
if (Test-Path -LiteralPath $eventPath -PathType Leaf) {
    foreach ($line in @(Get-Content -LiteralPath $eventPath -Tail 60 -Encoding UTF8 -ErrorAction SilentlyContinue)) {
        try {
            $entry = $line | ConvertFrom-Json
            $events += [pscustomobject]@{
                timestamp = [string]$entry.timestamp
                profileId = [string]$entry.profileId
                action = [string]$entry.action
                result = [string]$entry.result
                reason = Get-SafeDiagnosticText ([string]$entry.reason) 800
            }
        } catch {}
    }
}

$ageSeconds = if ($null -ne $status) { Get-StatusAgeSeconds ([string]$status.updatedAt) } else { $null }

$result = [ordered]@{
    schema = 'jolly.managed-supervisor-diagnostic'
    version = 3
    generatedAtUtc = ([DateTimeOffset]::UtcNow.ToString('o'))
    statusPresent = ($null -ne $status)
    statusAgeSeconds = $ageSeconds
    supervisorProcessId = if ($null -ne $status) { [int]$status.processId } else { 0 }
    profiles = $profileSummary
    candidates = $candidateSummary
    recentEvents = @($events | Select-Object -Last 20)
}
Write-Output ('SUPERVISOR_DIAG=' + ($result | ConvertTo-Json -Depth 8 -Compress))
