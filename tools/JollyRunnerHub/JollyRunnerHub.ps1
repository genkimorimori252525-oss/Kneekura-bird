#requires -version 5.1
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms.DataVisualization
[System.Windows.Forms.Application]::EnableVisualStyles()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$AppRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'
$ConfigPath = Join-Path $AppRoot 'profiles.json'
$DefaultConfigPath = Join-Path $AppRoot 'profiles.default.json'
$IconPath = Join-Path $AppRoot 'JollyRunnerHub.ico'
$HistoryRoot = Join-Path $AppRoot 'history'
$UiStatePath = Join-Path $AppRoot 'ui-state.json'
$CapabilitiesPath = Join-Path $AppRoot 'capabilities.json'
$CapabilitiesScriptPath = Join-Path $AppRoot 'RunnerCapabilities.ps1'
$CapabilitiesCliPath = Join-Path $AppRoot 'Inspect-RunnerCapabilities.ps1'
$RunnerLifecyclePath = Join-Path $PSScriptRoot 'RunnerLifecycle.ps1'
if (-not (Test-Path -LiteralPath $RunnerLifecyclePath)) {
    $RunnerLifecyclePath = Join-Path (Split-Path -Parent $PSScriptRoot) 'RunnerLifecycle.ps1'
}
if (-not (Test-Path -LiteralPath $RunnerLifecyclePath)) { throw 'RunnerLifecycle.ps1 was not found.' }
. $RunnerLifecyclePath

$script:Config = $null
$script:Profile = $null
$script:LastConfigWrite = [datetime]::MinValue
$script:RunnerCache = @{}
$script:RunnerCacheAt = @{}
$script:CapabilityCache = @{}
$script:CapabilityCacheAt = @{}
$script:GitHubRunnerStatusCache = @{}
$script:GitHubRunnerStatusCacheAt = @{}
$script:CapabilitiesSnapshot = $null
$script:CapabilitiesSnapshotAt = [datetime]::MinValue
$script:CapabilitiesReadFailures = 0
$script:RunnerRecoveryState = @{}
$script:LastEphemeralGc = [datetime]::UtcNow.AddMinutes(-10)
$script:LiveSamples = New-Object System.Collections.Generic.List[object]
$script:HistorySeen = @{}
$script:CurrentLiveRun = ''
$script:HistoryRecords = @()
$script:LastHistoryRefresh = [datetime]::MinValue
$script:RunnerOverviewRefreshing = $false
$script:LastRunnerOverviewRefresh = [datetime]::MinValue
$script:RunnerOverviewIntervalSeconds = 3
$script:RunnerInventoryCache = @()
$script:RunnerInventoryCacheAt = [datetime]::MinValue
$script:LastSnapshotKey = ''
$script:LastLogRefresh = [datetime]::MinValue
$script:PreferredRunnerSelectionId = ''

$ColorWindow = [Drawing.Color]::FromArgb(242,245,249)
$ColorSurface = [Drawing.Color]::White
$ColorHeader = [Drawing.Color]::FromArgb(28,39,58)
$ColorHeaderMuted = [Drawing.Color]::FromArgb(197,207,222)
$ColorText = [Drawing.Color]::FromArgb(35,45,60)
$ColorMuted = [Drawing.Color]::FromArgb(105,117,134)
$ColorGrid = [Drawing.Color]::FromArgb(226,231,238)
$ColorAccent = [Drawing.Color]::FromArgb(47,111,237)
$ColorGood = [Drawing.Color]::FromArgb(30,143,82)
$ColorWarn = [Drawing.Color]::FromArgb(214,135,19)
$ColorBad = [Drawing.Color]::FromArgb(194,50,55)

function Show-Error([string]$Text) {
    [System.Windows.Forms.MessageBox]::Show(
        $Text, 'ジョリー Runner Hub',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
}

function Read-CapabilitySnapshot {
    if (-not (Test-Path -LiteralPath $CapabilitiesPath)) { return $null }
    try {
        $raw = Get-Content -LiteralPath $CapabilitiesPath -Raw -Encoding UTF8 -ErrorAction Stop
        if ([string]::IsNullOrWhiteSpace($raw)) { throw 'capabilities snapshot is empty' }
        $snapshot = $raw | ConvertFrom-Json
        if ($null -eq $snapshot -or $null -eq $snapshot.PSObject.Properties['capabilities']) { throw 'capabilities snapshot is incomplete' }
        $script:CapabilitiesSnapshot = $snapshot
        $script:CapabilitiesSnapshotAt = [datetime]::UtcNow
        $script:CapabilitiesReadFailures = 0
        return $snapshot
    } catch {
        $script:CapabilitiesReadFailures++
        return $script:CapabilitiesSnapshot
    }
}

function Invoke-RunnerAutoRecovery($Profile,$State) {
    if ($null -eq $Profile -or $null -eq $State) { return }
    $autoConnect = if ($Profile.PSObject.Properties.Name -contains 'autoConnect') { [bool]$Profile.autoConnect } else { [bool]$script:Config.autoConnect }
    if (-not $autoConnect -or [string]$State.Code -ne 'stopped' -or -not (Test-RunnerConfigured $Profile)) { return }
    $id = Safe-Name ([string]$Profile.id)
    if (-not $script:RunnerRecoveryState.ContainsKey($id)) {
        $script:RunnerRecoveryState[$id] = [pscustomobject]@{ Attempts=0; LastAttempt=[datetime]::MinValue }
    }
    $recovery = $script:RunnerRecoveryState[$id]
    $delay = [math]::Min(60,[math]::Pow(2,[math]::Min(4,[int]$recovery.Attempts))*2)
    if (([datetime]::UtcNow-[datetime]$recovery.LastAttempt).TotalSeconds -lt $delay) { return }
    $recovery.LastAttempt = [datetime]::UtcNow
    try {
        Start-Runner $Profile
        $recovery.Attempts = 0
    } catch {
        $recovery.Attempts = [math]::Min(5,[int]$recovery.Attempts+1)
    }
}

function Set-DoubleBuffered($Control) {
    try {
        $property = $Control.GetType().GetProperty(
            'DoubleBuffered',
            [Reflection.BindingFlags]'Instance,NonPublic')
        if ($null -ne $property) { $property.SetValue($Control, $true, $null) }
    } catch {}
}

function Load-Config {
    New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $HistoryRoot | Out-Null
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        Copy-Item -LiteralPath $DefaultConfigPath -Destination $ConfigPath -Force
    }
    $script:Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $defaultConfig = Get-Content -LiteralPath $DefaultConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $knownIds = @{}
    foreach ($profile in @($script:Config.profiles)) {
        $knownIds[[string]$profile.id] = $true
    }
    $configChanged = $false
    foreach ($profile in @($defaultConfig.profiles)) {
        if (-not $knownIds.ContainsKey([string]$profile.id)) {
            $script:Config.profiles = @($script:Config.profiles) + @($profile)
            $knownIds[[string]$profile.id] = $true
            $configChanged = $true
        }
    }
    if ($configChanged) {
        $script:Config | ConvertTo-Json -Depth 12 |
            Set-Content -LiteralPath $ConfigPath -Encoding UTF8
    }
    if ($null -eq $script:Config.profiles -or @($script:Config.profiles).Count -eq 0) {
        throw 'profiles.json にprofilesがありません。'
    }
    $script:LastConfigWrite = (Get-Item -LiteralPath $ConfigPath).LastWriteTimeUtc
}


function Normalize-RunnerRoot([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return '' }
    try {
        $expanded = [Environment]::ExpandEnvironmentVariables($Path)
        return ([IO.Path]::GetFullPath($expanded)).TrimEnd([char[]]@('\','/')).ToLowerInvariant()
    } catch {
        return ''
    }
}

function Read-UiState {
    if (-not (Test-Path -LiteralPath $UiStatePath -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $UiStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Save-UiState {
    try {
        $runnerId = ''
        if ($runnerGrid.SelectedRows.Count -gt 0) {
            $runnerId = [string]$runnerGrid.SelectedRows[0].Cells['Id'].Value
        }
        $state = [ordered]@{
            profileId = if ($null -ne $script:Profile) { [string]$script:Profile.id } else { '' }
            tabIndex = [int]$tabs.SelectedIndex
            runnerId = $runnerId
        }
        $state | ConvertTo-Json | Set-Content -LiteralPath $UiStatePath -Encoding UTF8
    } catch {}
}

function Get-RunnerInventory([switch]$Force) {
    if (-not $Force -and ([datetime]::UtcNow-$script:RunnerInventoryCacheAt).TotalSeconds -lt 10) {
        return $script:RunnerInventoryCache
    }

    $managedRoots = @{}
    foreach ($profile in @($script:Config.profiles)) {
        $normalized = Normalize-RunnerRoot ([string]$profile.runnerRoot)
        if ($normalized) { $managedRoots[$normalized] = [string]$profile.id }
    }

    $candidateRoots = @{}
    foreach ($normalized in @($managedRoots.Keys)) { $candidateRoots[$normalized] = $normalized }

    $localActionsRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'GitHubActions'
    if (Test-Path -LiteralPath $localActionsRoot -PathType Container) {
        foreach ($directory in @(Get-ChildItem -LiteralPath $localActionsRoot -Directory -ErrorAction SilentlyContinue)) {
            $normalized = Normalize-RunnerRoot $directory.FullName
            if ($normalized) { $candidateRoots[$normalized] = $normalized }
        }
    }

    $driveRoot = [IO.Path]::GetPathRoot($AppRoot)
    if (Test-Path -LiteralPath $driveRoot -PathType Container) {
        foreach ($directory in @(Get-ChildItem -LiteralPath $driveRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like 'actions-runner*' })) {
            $normalized = Normalize-RunnerRoot $directory.FullName
            if ($normalized) { $candidateRoots[$normalized] = $normalized }
        }
    }

    $listenerRoots = @{}
    try {
        foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name='Runner.Listener.exe'" -ErrorAction SilentlyContinue)) {
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) { continue }
            $root = Split-Path -Parent (Split-Path -Parent ([string]$process.ExecutablePath))
            $normalized = Normalize-RunnerRoot $root
            if ($normalized) { $listenerRoots[$normalized] = $true }
        }
    } catch {}

    $items = New-Object System.Collections.Generic.List[object]
    foreach ($normalized in @($candidateRoots.Keys | Sort-Object)) {
        $root = $candidateRoots[$normalized]
        if (-not (Test-Path -LiteralPath (Join-Path $root 'run.cmd')) -and
            -not (Test-Path -LiteralPath (Join-Path $root '.runner'))) { continue }

        $scope = if ($managedRoots.ContainsKey($normalized)) {
            'managed'
        } elseif (Test-JollyEphemeralOwnedPath -Path $root -AppRoot $AppRoot) {
            'ephemeral'
        } else {
            'unmanaged'
        }

        $runnerName = Split-Path -Leaf $root
        $repository = ''
        $runnerFile = Join-Path $root '.runner'
        if (Test-Path -LiteralPath $runnerFile -PathType Leaf) {
            try {
                $runnerConfig = Get-Content -LiteralPath $runnerFile -Raw -Encoding UTF8 | ConvertFrom-Json
                foreach ($property in @('agentName','name')) {
                    if ($runnerConfig.PSObject.Properties.Name -contains $property -and
                        -not [string]::IsNullOrWhiteSpace([string]$runnerConfig.$property)) {
                        $runnerName = [string]$runnerConfig.$property
                        break
                    }
                }
                foreach ($property in @('gitHubUrl','serverUrl')) {
                    if ($runnerConfig.PSObject.Properties.Name -contains $property -and
                        -not [string]::IsNullOrWhiteSpace([string]$runnerConfig.$property)) {
                        $repository = ([string]$runnerConfig.$property).TrimEnd('/') -replace '^https://github.com/',''
                        break
                    }
                }
            } catch {}
        }

        [void]$items.Add([pscustomobject]@{
            Id = if ($scope -eq 'managed') { [string]$managedRoots[$normalized] } else { "$scope::$normalized" }
            Name = $runnerName
            Repository = $repository
            Root = $root
            Scope = $scope
            Running = $listenerRoots.ContainsKey($normalized)
        })
    }

    $script:RunnerInventoryCache = @()
    foreach ($inventoryItem in $items) {
        $script:RunnerInventoryCache += $inventoryItem
    }
    $script:RunnerInventoryCacheAt = [datetime]::UtcNow
    return $script:RunnerInventoryCache
}

function Get-Value($Object, [string]$Path) {
    if ($null -eq $Object) { return $null }
    $value = $Object
    foreach ($part in $Path.Split('.')) {
        if ($null -eq $value) { return $null }
        $property = $value.PSObject.Properties[$part]
        if ($null -eq $property) { return $null }
        $value = $property.Value
    }
    return $value
}

function Get-MapValue($Map, [string]$Key) {
    if ($null -eq $Map) { return $null }
    if ($Map -is [System.Collections.IDictionary]) {
        if ($Map.Contains($Key)) { return $Map[$Key] }
        return $null
    }
    $property = $Map.PSObject.Properties[$Key]
    if ($null -ne $property) { return $property.Value }
    return $null
}

function Get-OptionalInt($Object, [string]$Name, [int]$Default) {
    if ($null -eq $Object) { return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $Default }
    $value = 0
    if ([int]::TryParse([string]$property.Value, [ref]$value)) { return $value }
    return $Default
}

function Parse-Reason([string]$Text) {
    $map = @{}
    if ([string]::IsNullOrWhiteSpace($Text)) { return $map }
    foreach ($part in $Text.Split(':')) {
        $i = $part.IndexOf('=')
        if ($i -gt 0) { $map[$part.Substring(0,$i)] = $part.Substring($i+1) }
    }
    return $map
}

function Tail-Lines([string]$Path, [int]$Bytes = 524288) {
    $lines = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $Path)) { return $lines }
    $stream = New-Object System.IO.FileStream(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite)
    try {
        $start = [math]::Max(0,$stream.Length-$Bytes)
        [void]$stream.Seek($start,[System.IO.SeekOrigin]::Begin)
        $reader = New-Object System.IO.StreamReader(
            $stream,[Text.Encoding]::UTF8,$true,4096,$true)
        try {
            if ($start -gt 0) { [void]$reader.ReadLine() }
            while (-not $reader.EndOfStream) {
                $line = $reader.ReadLine()
                if (-not [string]::IsNullOrWhiteSpace($line)) { $lines.Add($line) }
            }
        } finally { $reader.Dispose() }
    } finally { $stream.Dispose() }
    return $lines
}

function Json-Tail([string]$Path, [int]$Bytes = 524288) {
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($line in (Tail-Lines $Path $Bytes)) {
        try { $rows.Add(($line | ConvertFrom-Json)) } catch {}
    }
    return $rows
}

function Format-Metric($Value,$Metric) {
    if ($null -eq $Value -or [string]$Value -eq '') {
        $defaultProperty = $Metric.PSObject.Properties['default']
        if ($null -ne $defaultProperty) { return $defaultProperty.Value }
        return 0
    }
    $formatProperty = $Metric.PSObject.Properties['format']
    if ($null -ne $formatProperty -and
        -not [string]::IsNullOrWhiteSpace([string]$formatProperty.Value)) {
        $number = 0.0
        if ([double]::TryParse(
            [string]$Value,
            [Globalization.NumberStyles]::Any,
            [Globalization.CultureInfo]::InvariantCulture,
            [ref]$number)) {
            return $number.ToString(
                [string]$formatProperty.Value,
                [Globalization.CultureInfo]::InvariantCulture)
        }
    }
    return $Value
}

function Try-Number($Value, [ref]$Result) {
    if ($null -eq $Value) { return $false }
    return [double]::TryParse(
        [string]$Value,
        [Globalization.NumberStyles]::Any,
        [Globalization.CultureInfo]::InvariantCulture,
        $Result)
}

function Metric-ByKey($Profile, [string]$Key) {
    return @($Profile.metrics) |
        Where-Object { [string]$_.key -eq $Key } |
        Select-Object -First 1
}

function Numeric-Metrics($Profile) {
    $excluded = @('tick','phase','stage','event','stall','terrain','ground')
    $metrics = New-Object System.Collections.Generic.List[object]
    foreach ($metric in @($Profile.metrics)) {
        $key = [string]$metric.key
        if ($key -in $excluded) { continue }
        $formatProperty = $metric.PSObject.Properties['format']
        if ($null -ne $formatProperty -or $key -in @('speed','agl','separation','closure')) {
            $metrics.Add([pscustomobject]@{
                key = $key
                label = [string]$metric.label
            })
        }
    }
    return $metrics
}

function Idle-Snapshot($Profile) {
    $aircraft = New-Object System.Collections.Generic.List[object]
    $names = @($Profile.expectedAircraft)
    if ($names.Count -eq 0) { $names = @('Aircraft') }
    foreach ($name in $names) {
        $values = [ordered]@{}
        foreach ($metric in @($Profile.metrics)) {
            $defaultProperty = $metric.PSObject.Properties['default']
            $values[[string]$metric.key] =
                if ($null -ne $defaultProperty) { $defaultProperty.Value } else { 0 }
        }
        $aircraft.Add([pscustomobject]@{
            Name = [string]$name
            Values = $values
        })
    }
    return [pscustomobject]@{
        Active = $false
        Run = 'IDLE'
        Updated = $null
        Aircraft = $aircraft
        Events = @()
    }
}

function Read-Snapshot($Profile) {
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.telemetryRoot)
    if (-not (Test-Path -LiteralPath $root)) { return Idle-Snapshot $Profile }

    $run = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($null -eq $run) { return Idle-Snapshot $Profile }

    $pattern = [string]$Profile.filePattern
    if ([string]::IsNullOrWhiteSpace($pattern)) { $pattern='*.jsonl' }
    $files = @(Get-ChildItem -LiteralPath $run.FullName -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue)
    if ($files.Count -eq 0) { return Idle-Snapshot $Profile }

    $newest = ($files | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).LastWriteTimeUtc
    $stale = [int]$Profile.staleSeconds
    if ($stale -lt 3) { $stale = 3 }
    if ($newest -lt [datetime]::UtcNow.AddSeconds(-$stale)) {
        return Idle-Snapshot $Profile
    }

    $planes = New-Object System.Collections.Generic.List[object]
    $events = New-Object System.Collections.Generic.List[object]
    foreach ($file in $files) {
        $records = @(Json-Tail $file.FullName)
        $frame = $records |
            Where-Object { [string](Get-Value $_ 'event') -eq 'frame' } |
            Select-Object -Last 1
        if ($null -eq $frame) { continue }

        $event = $records |
            Where-Object { [string](Get-Value $_ 'event') -ne 'frame' } |
            Select-Object -Last 1
        $coupled = $records |
            Where-Object { [string](Get-Value $_ 'event') -like 'energy_coupled*' } |
            Select-Object -Last 1

        $reasonText =
            if ($null -ne $coupled) {
                [string](Get-Value $coupled 'reason')
            } else {
                [string](Get-Value $event 'reason')
            }
        $reason = Parse-Reason $reasonText

        $name = [string](Get-Value $frame 'aircraft_name')
        if ([string]::IsNullOrWhiteSpace($name)) {
            $name = [string](Get-Value $frame 'aircraft_entity_id')
        }
        if ([string]::IsNullOrWhiteSpace($name)) { $name = $file.BaseName }

        $values = [ordered]@{}
        foreach ($metric in @($Profile.metrics)) {
            $source = [string]$metric.source
            $value = $null
            if ($source -eq 'frame') {
                $value = Get-Value $frame ([string]$metric.path)
            } elseif ($source -eq 'event') {
                $value = Get-Value $event ([string]$metric.path)
            } elseif ($source -eq 'coupled') {
                $value = Get-Value $coupled ([string]$metric.path)
            } elseif ($source -eq 'reason' -and $reason.ContainsKey([string]$metric.path)) {
                $value = $reason[[string]$metric.path]
            }
            $values[[string]$metric.key] = Format-Metric $value $metric
        }
        $planes.Add([pscustomobject]@{Name=$name;Values=$values})

        foreach ($record in ($records |
            Where-Object {[string](Get-Value $_ 'event') -ne 'frame'} |
            Select-Object -Last 16)) {
            $events.Add([pscustomobject]@{
                Tick = Get-Value $record 'server_tick'
                Aircraft = $name
                Event = Get-Value $record 'event'
                Reason = Get-Value $record 'reason'
            })
        }
    }

    if ($planes.Count -eq 0) { return Idle-Snapshot $Profile }
    return [pscustomobject]@{
        Active = $true
        Run = $run.Name
        Updated = $newest.ToLocalTime()
        Aircraft = $planes
        Events = @($events | Sort-Object Tick -Descending | Select-Object -First 80)
    }
}

function Safe-Name([string]$Text) {
    if ([string]::IsNullOrWhiteSpace($Text)) { return 'unknown' }
    return ($Text -replace '[^A-Za-z0-9_.-]','_')
}

function History-ProfileRoot($Profile) {
    $path = Join-Path $HistoryRoot (Safe-Name ([string]$Profile.id))
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    return $path
}

function History-FilePath($Profile, [string]$Run) {
    return Join-Path (History-ProfileRoot $Profile) ((Safe-Name $Run) + '.jsonl')
}

function Reset-LiveSamples([string]$Run) {
    $script:LiveSamples.Clear()
    $script:HistorySeen = @{}
    $script:CurrentLiveRun = $Run
}

function Record-Snapshot($Snapshot, $Profile) {
    if (-not $Snapshot.Active) { return $false }

    $run = [string]$Snapshot.Run
    if ($script:CurrentLiveRun -ne $run) { Reset-LiveSamples $run }

    $path = History-FilePath $Profile $run
    $wrote = $false
    foreach ($aircraft in @($Snapshot.Aircraft)) {
        $tick = Get-MapValue $aircraft.Values 'tick'
        $fingerprint = '{0}|{1}|{2}' -f $run,[string]$aircraft.Name,[string]$tick
        if ($script:HistorySeen.ContainsKey($fingerprint)) { continue }

        $record = [pscustomobject]@{
            timestamp = (Get-Date).ToString('o')
            run = $run
            aircraft = [string]$aircraft.Name
            values = $aircraft.Values
        }
        $script:HistorySeen[$fingerprint] = $true
        $script:LiveSamples.Add($record)
        ($record | ConvertTo-Json -Compress -Depth 8) |
            Add-Content -LiteralPath $path -Encoding UTF8
        $wrote = $true
    }

    while ($script:LiveSamples.Count -gt 1200) {
        $script:LiveSamples.RemoveAt(0)
    }
    return $wrote
}

function Prune-History($Profile) {
    $root = History-ProfileRoot $Profile
    $days = Get-OptionalInt $Profile 'historyDays' 30
    if ($days -lt 1) { $days = 1 }
    $maxRuns = Get-OptionalInt $Profile 'historyMaxRuns' 100
    if ($maxRuns -lt 5) { $maxRuns = 5 }

    $files = @(Get-ChildItem -LiteralPath $root -Filter '*.jsonl' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending)
    foreach ($file in $files) {
        if ($file.LastWriteTimeUtc -lt [datetime]::UtcNow.AddDays(-$days)) {
            Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
        }
    }
    $files = @(Get-ChildItem -LiteralPath $root -Filter '*.jsonl' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending)
    if ($files.Count -gt $maxRuns) {
        foreach ($file in ($files | Select-Object -Skip $maxRuns)) {
            Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
        }
    }
}

function Read-History([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        return @()
    }
    return @(Json-Tail $Path 16777216)
}

function Runner-Processes($Profile) {
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot).TrimEnd('\')
    $rootPattern = [regex]::Escape($root) + '(?:\\|["\s]|$)'
    try {
        return @(Get-CimInstance Win32_Process -Filter "Name='Runner.Listener.exe'" |
            Where-Object {
                ([string]$_.ExecutablePath -match "^$rootPattern") -or
                ([string]$_.CommandLine -match $rootPattern)
            })
    } catch { return @() }
}

function Runner-PidStatePath($Profile) {
    $id = Safe-Name ([string]$Profile.id)
    return Join-Path $AppRoot ("runner-$id.pid.json")
}

function Get-TrackedRunnerProcess($Profile) {
    $path = Runner-PidStatePath $Profile
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try {
        $state = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        $process = Get-Process -Id ([int]$state.processId) -ErrorAction SilentlyContinue
        if ($null -ne $process -and [string]$process.ProcessName -eq 'cmd') { return $process }
    } catch {}
    return $null
}

function Test-RunnerActiveLog($Profile) {
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    $diagRoot = Join-Path $root '_diag'
    if (-not (Test-Path -LiteralPath $diagRoot)) { return $false }
    $log = Get-ChildItem -LiteralPath $diagRoot -Filter 'Runner_*.log' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($null -eq $log) { return $false }
    try {
        $stream = [IO.File]::Open(
            $log.FullName,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            [IO.FileShare]::None)
        $stream.Dispose()
        return $false
    } catch [IO.IOException] {
        return $true
    } catch {
        return $false
    }
}

function Runner-Running($Profile,[switch]$Force) {
    $id = Safe-Name ([string]$Profile.id)
    $cachedAt = if ($script:RunnerCacheAt.ContainsKey($id)) {
        [datetime]$script:RunnerCacheAt[$id]
    } else {
        [datetime]::MinValue
    }
    if (-not $Force -and ([datetime]::UtcNow-$cachedAt).TotalSeconds -lt 2) {
        return [bool]$script:RunnerCache[$id]
    }
    $script:RunnerCache[$id] =
        (@(Runner-Processes $Profile).Count -gt 0) -or
        ($null -ne (Get-TrackedRunnerProcess $Profile)) -or
        (Test-RunnerActiveLog $Profile)
    $script:RunnerCacheAt[$id] = [datetime]::UtcNow
    return [bool]$script:RunnerCache[$id]
}

function Reset-RunnerCache($Profile) {
    $id = Safe-Name ([string]$Profile.id)
    $script:RunnerCacheAt.Remove($id)
    $script:RunnerCache.Remove($id)
}

function Get-CachedRunnerCapabilities($Profile,[switch]$Force) {
    $id = Safe-Name ([string]$Profile.id)
    $cachedAt = if ($script:CapabilityCacheAt.ContainsKey($id)) { [datetime]$script:CapabilityCacheAt[$id] } else { [datetime]::MinValue }
    if (-not $Force -and $script:CapabilityCache.ContainsKey($id) -and ([datetime]::UtcNow-$cachedAt).TotalSeconds -lt 30) {
        return $script:CapabilityCache[$id]
    }
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    $value = Get-JollyRunnerCapabilities -RunnerRoot $root
    $script:CapabilityCache[$id] = $value
    $script:CapabilityCacheAt[$id] = [datetime]::UtcNow
    return $value
}

function Reset-RunnerCapabilityCache($Profile) {
    $id = Safe-Name ([string]$Profile.id)
    $script:CapabilityCache.Remove($id)
    $script:CapabilityCacheAt.Remove($id)
}

function Get-ProfileById([string]$Id) {
    return @($script:Config.profiles) |
        Where-Object { [string]$_.id -eq $Id } |
        Select-Object -First 1
}

function Test-RunnerConfigured($Profile) {
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    return ((Test-Path -LiteralPath (Join-Path $root 'run.cmd')) -and
        (Test-Path -LiteralPath (Join-Path $root '.runner')))
}

function Start-Runner($Profile) {
    if (Runner-Running $Profile -Force) { return }
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    $cmd = Join-Path $root 'run.cmd'
    if (-not (Test-RunnerConfigured $Profile)) {
        throw "Runnerが未登録です: $root"
    }
    $logs = Join-Path $AppRoot 'logs'
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    $id = Safe-Name ([string]$Profile.id)
    $log = Join-Path $logs ("runner-$id.log")
    $line = '""{0}" >> "{1}" 2>&1"' -f $cmd,$log
    $launcher = Start-Process cmd.exe -ArgumentList '/d','/s','/c',$line `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru
    [ordered]@{
        profileId = [string]$Profile.id
        runnerRoot = $root
        processId = [int]$launcher.Id
        startedAt = (Get-Date).ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath (Runner-PidStatePath $Profile) -Encoding UTF8
    Start-Sleep -Milliseconds 700
    Reset-RunnerCache $Profile
}

function Stop-Runner($Profile) {
    $processes = @(Runner-Processes $Profile)
    if ($processes.Count -eq 0) {
        $tracked = Get-TrackedRunnerProcess $Profile
        if ($null -ne $tracked) { $processes = @($tracked) }
    }
    if ($processes.Count -eq 0 -and (Test-RunnerActiveLog $Profile)) {
        throw 'このRunnerはHub起動情報がないため、安全に停止対象を特定できません。'
    }
    foreach ($process in $processes) {
        $processId = if ($null -ne $process.PSObject.Properties['ProcessId']) {
            [int]$process.ProcessId
        } else {
            [int]$process.Id
        }
        Start-Process taskkill.exe `
            -ArgumentList '/PID',[string]$processId,'/T','/F' `
            -Wait -WindowStyle Hidden | Out-Null
    }
    Remove-Item -LiteralPath (Runner-PidStatePath $Profile) -Force -ErrorAction SilentlyContinue
    Reset-RunnerCache $Profile
}

function Log-Path($Profile) {
    $id = Safe-Name ([string]$Profile.id)
    return Join-Path (Join-Path $AppRoot 'logs') ("runner-$id.log")
}

function Style-Grid($Grid) {
    $Grid.ReadOnly = $true
    $Grid.AllowUserToAddRows = $false
    $Grid.AllowUserToDeleteRows = $false
    $Grid.AllowUserToResizeRows = $false
    $Grid.RowHeadersVisible = $false
    $Grid.MultiSelect = $false
    $Grid.SelectionMode = 'FullRowSelect'
    $Grid.BackgroundColor = $ColorSurface
    $Grid.BorderStyle = 'None'
    $Grid.GridColor = $ColorGrid
    $Grid.EnableHeadersVisualStyles = $false
    $Grid.ColumnHeadersHeight = 34
    $Grid.RowTemplate.Height = 29
    $Grid.Font = New-Object Drawing.Font('Segoe UI',9)
    $Grid.ColumnHeadersDefaultCellStyle.BackColor = [Drawing.Color]::FromArgb(232,237,245)
    $Grid.ColumnHeadersDefaultCellStyle.ForeColor = $ColorText
    $Grid.ColumnHeadersDefaultCellStyle.Font =
        New-Object Drawing.Font('Segoe UI',9,[Drawing.FontStyle]::Bold)
    $Grid.DefaultCellStyle.BackColor = $ColorSurface
    $Grid.DefaultCellStyle.ForeColor = $ColorText
    $Grid.DefaultCellStyle.SelectionBackColor = [Drawing.Color]::FromArgb(218,230,251)
    $Grid.DefaultCellStyle.SelectionForeColor = $ColorText
    $Grid.AlternatingRowsDefaultCellStyle.BackColor = [Drawing.Color]::FromArgb(248,250,253)
    Set-DoubleBuffered $Grid
}

function Build-Columns($Profile,$Grid) {
    $Grid.Columns.Clear()
    $column = New-Object Windows.Forms.DataGridViewTextBoxColumn
    $column.Name = 'Aircraft'
    $column.HeaderText = '機体'
    $column.Width = 210
    $column.Frozen = $true
    [void]$Grid.Columns.Add($column)

    foreach ($metric in @($Profile.metrics)) {
        $column = New-Object Windows.Forms.DataGridViewTextBoxColumn
        $column.Name = [string]$metric.key
        $column.HeaderText = [string]$metric.label
        $column.Width =
            if ([string]$metric.key -in @('phase','stage','event')) { 155 } else { 88 }
        [void]$Grid.Columns.Add($column)
    }
}

function Fill-Telemetry($Snapshot,$Profile,$Grid) {
    $Grid.SuspendLayout()
    try {
        $Grid.Rows.Clear()
        foreach ($aircraft in @($Snapshot.Aircraft)) {
            $cells = New-Object Collections.Generic.List[object]
            $cells.Add([string]$aircraft.Name)
            foreach ($metric in @($Profile.metrics)) {
                $cells.Add((Get-MapValue $aircraft.Values ([string]$metric.key)))
            }
            [void]$Grid.Rows.Add($cells.ToArray())
        }
    } finally { $Grid.ResumeLayout() }
}

function Fill-Events($Snapshot,$Grid) {
    $Grid.SuspendLayout()
    try {
        $Grid.Rows.Clear()
        foreach ($event in @($Snapshot.Events)) {
            [void]$Grid.Rows.Add($event.Tick,$event.Aircraft,$event.Event,$event.Reason)
        }
    } finally { $Grid.ResumeLayout() }
}

function New-Chart {
    $chart = New-Object System.Windows.Forms.DataVisualization.Charting.Chart
    $chart.Dock = 'Fill'
    $chart.BackColor = $ColorSurface
    $chart.BorderlineColor = $ColorGrid
    $chart.BorderlineDashStyle = 'Solid'
    $chart.BorderlineWidth = 1

    $area = New-Object System.Windows.Forms.DataVisualization.Charting.ChartArea
    $area.Name = 'Main'
    $area.BackColor = $ColorSurface
    $area.AxisX.LabelStyle.Format = 'HH:mm:ss'
    $area.AxisX.LabelStyle.ForeColor = $ColorMuted
    $area.AxisX.MajorGrid.Enabled = $false
    $area.AxisX.LineColor = $ColorGrid
    $area.AxisY.LabelStyle.ForeColor = $ColorMuted
    $area.AxisY.MajorGrid.LineColor = [Drawing.Color]::FromArgb(235,239,245)
    $area.AxisY.LineColor = $ColorGrid
    $area.AxisY.IsStartedFromZero = $false
    [void]$chart.ChartAreas.Add($area)

    $legend = New-Object System.Windows.Forms.DataVisualization.Charting.Legend
    $legend.Name = 'Legend'
    $legend.Docking = 'Top'
    $legend.Alignment = 'Far'
    $legend.BackColor = $ColorSurface
    $legend.ForeColor = $ColorText
    [void]$chart.Legends.Add($legend)
    Set-DoubleBuffered $chart
    return $chart
}

function Chart-Colors {
    return @(
        [Drawing.Color]::FromArgb(47,111,237),
        [Drawing.Color]::FromArgb(231,76,60),
        [Drawing.Color]::FromArgb(30,143,82),
        [Drawing.Color]::FromArgb(143,93,183),
        [Drawing.Color]::FromArgb(230,126,34),
        [Drawing.Color]::FromArgb(31,151,173)
    )
}

function Update-Chart($Chart, $Records, [string]$MetricKey, $Profile) {
    if ($null -eq $Chart) { return }
    $metric = Metric-ByKey $Profile $MetricKey
    $label = if ($null -ne $metric) { [string]$metric.label } else { $MetricKey }

    $Chart.SuspendLayout()
    try {
        $Chart.Series.Clear()
        $Chart.Titles.Clear()
        $title = New-Object System.Windows.Forms.DataVisualization.Charting.Title
        $title.Text = $label
        $title.Font = New-Object Drawing.Font('Segoe UI',10,[Drawing.FontStyle]::Bold)
        $title.ForeColor = $ColorText
        $title.Alignment = 'TopLeft'
        [void]$Chart.Titles.Add($title)
        $Chart.ChartAreas['Main'].AxisY.Title = $label

        $grouped = @($Records) | Group-Object aircraft
        $colors = Chart-Colors
        $colorIndex = 0
        foreach ($group in $grouped) {
            $series = New-Object System.Windows.Forms.DataVisualization.Charting.Series
            $series.Name = [string]$group.Name
            $series.ChartType =
                [System.Windows.Forms.DataVisualization.Charting.SeriesChartType]::FastLine
            $series.BorderWidth = 2
            $series.XValueType =
                [System.Windows.Forms.DataVisualization.Charting.ChartValueType]::DateTime
            $series.YValueType =
                [System.Windows.Forms.DataVisualization.Charting.ChartValueType]::Double
            $series.Color = $colors[$colorIndex % $colors.Count]
            $colorIndex++

            foreach ($record in @($group.Group | Select-Object -Last 300)) {
                $number = 0.0
                $value = Get-MapValue $record.values $MetricKey
                if (-not (Try-Number $value ([ref]$number))) { continue }
                $timestamp = [datetime]$record.timestamp
                [void]$series.Points.AddXY($timestamp,$number)
            }
            if ($series.Points.Count -gt 0) { [void]$Chart.Series.Add($series) }
        }

        if ($MetricKey -eq 'separation' -and $Chart.Series.Count -gt 0) {
            $allTimes = @($Records | ForEach-Object {[datetime]$_.timestamp})
            if ($allTimes.Count -gt 0) {
                $limit = New-Object System.Windows.Forms.DataVisualization.Charting.Series
                $limit.Name = '安全下限 8'
                $limit.ChartType =
                    [System.Windows.Forms.DataVisualization.Charting.SeriesChartType]::Line
                $limit.BorderWidth = 2
                $limit.BorderDashStyle =
                    [System.Windows.Forms.DataVisualization.Charting.ChartDashStyle]::Dash
                $limit.Color = $ColorBad
                $limit.XValueType =
                    [System.Windows.Forms.DataVisualization.Charting.ChartValueType]::DateTime
                [void]$limit.Points.AddXY(($allTimes | Sort-Object | Select-Object -First 1),8.0)
                [void]$limit.Points.AddXY(($allTimes | Sort-Object | Select-Object -Last 1),8.0)
                [void]$Chart.Series.Add($limit)
            }
        }
    } finally {
        $Chart.ResumeLayout()
        $Chart.Invalidate()
    }
}

function New-AircraftCard($Aircraft) {
    $panel = New-Object Windows.Forms.Panel
    $panel.Size = New-Object Drawing.Size(330,122)
    $panel.Margin = New-Object Windows.Forms.Padding(8,8,2,8)
    $panel.BackColor = $ColorSurface
    $panel.BorderStyle = 'FixedSingle'

    $name = New-Object Windows.Forms.Label
    $name.Text = [string]$Aircraft.Name
    $name.Font = New-Object Drawing.Font('Segoe UI',11,[Drawing.FontStyle]::Bold)
    $name.ForeColor = $ColorText
    $name.Location = New-Object Drawing.Point(12,9)
    $name.Size = New-Object Drawing.Size(180,24)
    $panel.Controls.Add($name)

    $phase = [string](Get-MapValue $Aircraft.Values 'phase')
    $stage = [string](Get-MapValue $Aircraft.Values 'stage')
    $phaseLabel = New-Object Windows.Forms.Label
    $phaseLabel.Text = "$phase  /  $stage"
    $phaseLabel.Font = New-Object Drawing.Font('Segoe UI',8.5)
    $phaseLabel.ForeColor = $ColorMuted
    $phaseLabel.Location = New-Object Drawing.Point(12,35)
    $phaseLabel.Size = New-Object Drawing.Size(300,20)
    $panel.Controls.Add($phaseLabel)

    $speed = Get-MapValue $Aircraft.Values 'speed'
    $speedLabel = New-Object Windows.Forms.Label
    $speedLabel.Text = "$speed BPS"
    $speedLabel.Font = New-Object Drawing.Font('Segoe UI',17,[Drawing.FontStyle]::Bold)
    $speedLabel.ForeColor = $ColorAccent
    $speedLabel.Location = New-Object Drawing.Point(10,57)
    $speedLabel.Size = New-Object Drawing.Size(155,36)
    $panel.Controls.Add($speedLabel)

    $agl = Get-MapValue $Aircraft.Values 'agl'
    $separation = Get-MapValue $Aircraft.Values 'separation'
    $detail = New-Object Windows.Forms.Label
    $detail.Text = "AGL  $agl`n分離  $separation"
    $detail.Font = New-Object Drawing.Font('Segoe UI',9)
    $detail.ForeColor = $ColorText
    $detail.Location = New-Object Drawing.Point(174,58)
    $detail.Size = New-Object Drawing.Size(140,44)
    $panel.Controls.Add($detail)

    $stall = [string](Get-MapValue $Aircraft.Values 'stall') -eq 'True'
    $terrain = [string](Get-MapValue $Aircraft.Values 'terrain') -eq 'True'
    $ground = [string](Get-MapValue $Aircraft.Values 'ground') -eq 'True'
    $safety = New-Object Windows.Forms.Label
    $safety.AutoSize = $false
    $safety.TextAlign = 'MiddleCenter'
    $safety.Font = New-Object Drawing.Font('Segoe UI',8,[Drawing.FontStyle]::Bold)
    $safety.Location = New-Object Drawing.Point(222,8)
    $safety.Size = New-Object Drawing.Size(94,24)
    if ($stall -or $terrain) {
        $safety.Text = if ($stall) { 'STALL RISK' } else { 'TERRAIN' }
        $safety.ForeColor = $ColorBad
        $safety.BackColor = [Drawing.Color]::FromArgb(255,232,233)
    } elseif ($ground) {
        $safety.Text = 'ON GROUND'
        $safety.ForeColor = $ColorWarn
        $safety.BackColor = [Drawing.Color]::FromArgb(255,244,221)
    } else {
        $safety.Text = 'SAFE'
        $safety.ForeColor = $ColorGood
        $safety.BackColor = [Drawing.Color]::FromArgb(226,246,235)
    }
    $panel.Controls.Add($safety)
    return $panel
}

function Fill-Cards($Snapshot,$Panel) {
    $Panel.SuspendLayout()
    try {
        $Panel.Controls.Clear()
        foreach ($aircraft in @($Snapshot.Aircraft)) {
            $Panel.Controls.Add((New-AircraftCard $aircraft))
        }
    } finally { $Panel.ResumeLayout() }
}

function Fill-MetricCombo($Combo,$Profile,[string]$Preferred) {
    $Combo.Items.Clear()
    foreach ($metric in @(Numeric-Metrics $Profile)) { [void]$Combo.Items.Add($metric) }
    $Combo.DisplayMember = 'label'
    $index = 0
    for ($i=0; $i -lt $Combo.Items.Count; $i++) {
        if ([string]$Combo.Items[$i].key -eq $Preferred) { $index = $i; break }
    }
    if ($Combo.Items.Count -gt 0) { $Combo.SelectedIndex = $index }
}

function Selected-MetricKey($Combo,[string]$Default) {
    if ($null -ne $Combo.SelectedItem) { return [string]$Combo.SelectedItem.key }
    return $Default
}

function Create-ToolbarButton([string]$Text,[int]$Width) {
    $button = New-Object Windows.Forms.Button
    $button.Text = $Text
    $button.Size = New-Object Drawing.Size($Width,34)
    $button.Margin = New-Object Windows.Forms.Padding(5,10,0,8)
    $button.FlatStyle = 'Flat'
    $button.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(84,99,122)
    $button.BackColor = [Drawing.Color]::FromArgb(42,56,79)
    $button.ForeColor = [Drawing.Color]::White
    $button.Font = New-Object Drawing.Font('Segoe UI',9)
    return $button
}

function New-StatusPanel([string]$Caption,[int]$Width) {
    $panel = New-Object Windows.Forms.Panel
    $panel.Width = $Width
    $panel.Height = 43
    $panel.Margin = New-Object Windows.Forms.Padding(8,5,0,5)
    $panel.BackColor = [Drawing.Color]::FromArgb(36,49,70)

    $captionLabel = New-Object Windows.Forms.Label
    $captionLabel.Text = $Caption.ToUpperInvariant()
    $captionLabel.Font = New-Object Drawing.Font('Segoe UI',7.5,[Drawing.FontStyle]::Bold)
    $captionLabel.ForeColor = $ColorHeaderMuted
    $captionLabel.Location = New-Object Drawing.Point(10,4)
    $captionLabel.Size = New-Object Drawing.Size($Width-20,14)
    $panel.Controls.Add($captionLabel)

    $valueLabel = New-Object Windows.Forms.Label
    $valueLabel.Text = '-'
    $valueLabel.Font = New-Object Drawing.Font('Segoe UI',9.5,[Drawing.FontStyle]::Bold)
    $valueLabel.ForeColor = [Drawing.Color]::White
    $valueLabel.Location = New-Object Drawing.Point(10,19)
    $valueLabel.Size = New-Object Drawing.Size($Width-20,20)
    $panel.Controls.Add($valueLabel)

    return [pscustomobject]@{Panel=$panel;Value=$valueLabel}
}

try { Load-Config } catch { Show-Error $_.Exception.Message; exit 1 }

$form = New-Object Windows.Forms.Form
$form.Text = 'ジョリー Runner Hub'
$form.Size = New-Object Drawing.Size(1500,920)
$form.MinimumSize = New-Object Drawing.Size(1120,720)
$form.StartPosition = 'CenterScreen'
$form.BackColor = $ColorWindow
$form.AutoScaleMode = 'Dpi'
if (Test-Path $IconPath) { $form.Icon = New-Object Drawing.Icon($IconPath) }

$header = New-Object Windows.Forms.TableLayoutPanel
$header.Dock = 'Top'
$header.Height = 116
$header.RowCount = 2
$header.ColumnCount = 2
$header.BackColor = $ColorHeader
[void]$header.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',58)))
[void]$header.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',58)))
[void]$header.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',40)))
[void]$header.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',60)))
$form.Controls.Add($header)

$brandPanel = New-Object Windows.Forms.FlowLayoutPanel
$brandPanel.Dock = 'Fill'
$brandPanel.FlowDirection = 'LeftToRight'
$brandPanel.WrapContents = $false
$brandPanel.Padding = New-Object Windows.Forms.Padding(14,8,0,0)
$brandPanel.BackColor = $ColorHeader
$header.Controls.Add($brandPanel,0,0)

$title = New-Object Windows.Forms.Label
$title.Text = 'ジョリー Runner Hub'
$title.AutoSize = $false
$title.Size = New-Object Drawing.Size(258,42)
$title.Font = New-Object Drawing.Font('Segoe UI',17,[Drawing.FontStyle]::Bold)
$title.ForeColor = [Drawing.Color]::White
$title.TextAlign = 'MiddleLeft'
$brandPanel.Controls.Add($title)

$profiles = New-Object Windows.Forms.ComboBox
$profiles.DropDownStyle = 'DropDownList'
$profiles.Size = New-Object Drawing.Size(260,30)
$profiles.Margin = New-Object Windows.Forms.Padding(8,7,0,0)
$profiles.Font = New-Object Drawing.Font('Segoe UI',9)
$brandPanel.Controls.Add($profiles)

$buttonFlow = New-Object Windows.Forms.FlowLayoutPanel
$buttonFlow.Dock = 'Fill'
$buttonFlow.FlowDirection = 'RightToLeft'
$buttonFlow.WrapContents = $false
$buttonFlow.Padding = New-Object Windows.Forms.Padding(0,0,14,0)
$buttonFlow.BackColor = $ColorHeader
$header.Controls.Add($buttonFlow,1,0)

$reloadButton = Create-ToolbarButton '再読込' 82
$dataButton = Create-ToolbarButton 'データ場所' 96
$actionsButton = Create-ToolbarButton 'GitHub Actions' 112
$configButton = Create-ToolbarButton '設定JSON' 92
$disconnect = Create-ToolbarButton '切断' 74
$connect = Create-ToolbarButton '接続' 74
foreach ($button in @($reloadButton,$dataButton,$actionsButton,$configButton,$disconnect,$connect)) {
    $buttonFlow.Controls.Add($button)
}

$statusFlow = New-Object Windows.Forms.FlowLayoutPanel
$statusFlow.Dock = 'Fill'
$statusFlow.FlowDirection = 'LeftToRight'
$statusFlow.WrapContents = $false
$statusFlow.Padding = New-Object Windows.Forms.Padding(6,0,8,0)
$statusFlow.BackColor = $ColorHeader
$header.Controls.Add($statusFlow,0,1)
$header.SetColumnSpan($statusFlow,2)

$runnerStatus = New-StatusPanel 'Runner' 250
$validationStatus = New-StatusPanel 'Validation' 590
$historyStatus = New-StatusPanel 'History' 300
$statusFlow.Controls.Add($runnerStatus.Panel)
$statusFlow.Controls.Add($validationStatus.Panel)
$statusFlow.Controls.Add($historyStatus.Panel)

$tabs = New-Object Windows.Forms.TabControl
$tabs.Dock = 'Fill'
$tabs.Font = New-Object Drawing.Font('Segoe UI',9)
$form.Controls.Add($tabs)
$header.BringToFront()

$runnerTab = New-Object Windows.Forms.TabPage
$runnerTab.Text = 'Runner 管理'
$runnerTab.BackColor = $ColorWindow
[void]$tabs.TabPages.Add($runnerTab)

$runnerLayout = New-Object Windows.Forms.TableLayoutPanel
$runnerLayout.Dock = 'Fill'
$runnerLayout.RowCount = 3
$runnerLayout.ColumnCount = 1
$runnerLayout.Padding = New-Object Windows.Forms.Padding(12)
[void]$runnerLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',58)))
[void]$runnerLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100)))
[void]$runnerLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',52)))
$runnerTab.Controls.Add($runnerLayout)

$runnerIntro = New-Object Windows.Forms.Label
$runnerIntro.Dock = 'Fill'
$runnerIntro.Text = 'Hub管理Runnerを一元管理します。未管理Runnerを検出した場合はここに警告表示し、自動操作の対象にはしません。'
$runnerIntro.Font = New-Object Drawing.Font('Segoe UI',10)
$runnerIntro.ForeColor = $ColorText
$runnerIntro.TextAlign = 'MiddleLeft'
$runnerLayout.Controls.Add($runnerIntro,0,0)

$runnerGrid = New-Object Windows.Forms.DataGridView
$runnerGrid.Dock = 'Fill'
$runnerGrid.SelectionMode = 'FullRowSelect'
$runnerGrid.MultiSelect = $false
Style-Grid $runnerGrid
foreach ($columnInfo in @(
    @('Id','ID',160),
    @('Name','Runner',210),
    @('Scope','管轄',105),
    @('Repository','Repository',300),
    @('Root','ローカル配置',330),
    @('State','状態',180),
    @('Capabilities','能力',260),
    @('Evidence','判定根拠',320),
    @('Ephemeral','Ephemeral / TTL',230)
)) {
    $column = New-Object Windows.Forms.DataGridViewTextBoxColumn
    $column.Name = $columnInfo[0]
    $column.HeaderText = $columnInfo[1]
    $column.Width = $columnInfo[2]
    [void]$runnerGrid.Columns.Add($column)
}
$runnerGrid.Columns['Id'].Visible = $false
$runnerLayout.Controls.Add($runnerGrid,0,1)

$runnerButtons = New-Object Windows.Forms.FlowLayoutPanel
$runnerButtons.Dock = 'Fill'
$runnerButtons.FlowDirection = 'LeftToRight'
$runnerButtons.WrapContents = $false
$runnerButtons.Padding = New-Object Windows.Forms.Padding(0,8,0,0)
$runnerButtons.BackColor = $ColorWindow
$runnerLayout.Controls.Add($runnerButtons,0,2)

function New-RunnerButton([string]$Text,[int]$Width) {
    $button = New-Object Windows.Forms.Button
    $button.Text = $Text
    $button.Size = New-Object Drawing.Size($Width,34)
    $button.FlatStyle = 'Flat'
    $button.BackColor = $ColorSurface
    $button.ForeColor = $ColorText
    $button.Font = New-Object Drawing.Font('Segoe UI',9,[Drawing.FontStyle]::Bold)
    return $button
}

$startSelectedRunner = New-RunnerButton '選択を起動' 112
$stopSelectedRunner = New-RunnerButton '選択を停止' 112
$startAllRunners = New-RunnerButton 'すべて起動' 112
$stopAllRunners = New-RunnerButton 'すべて停止' 112
$refreshRunners = New-RunnerButton '状態を更新' 112
$refreshCapabilities = New-RunnerButton '能力を更新' 112
$startEphemeralRunner = New-RunnerButton 'Ephemeral起動' 122
$gcEphemeralRunners = New-RunnerButton 'Ephemeral GC' 112
foreach ($button in @($startSelectedRunner,$stopSelectedRunner,$startAllRunners,$stopAllRunners,$startEphemeralRunner,$gcEphemeralRunners,$refreshRunners,$refreshCapabilities)) {
    $runnerButtons.Controls.Add($button)
}

$dashboardTab = New-Object Windows.Forms.TabPage
$dashboardTab.Text = 'ダッシュボード'
$dashboardTab.BackColor = $ColorWindow
[void]$tabs.TabPages.Add($dashboardTab)

$dashboardLayout = New-Object Windows.Forms.TableLayoutPanel
$dashboardLayout.Dock = 'Fill'
$dashboardLayout.RowCount = 3
$dashboardLayout.ColumnCount = 1
$dashboardLayout.Padding = New-Object Windows.Forms.Padding(8)
[void]$dashboardLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',144)))
[void]$dashboardLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100)))
[void]$dashboardLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',188)))
$dashboardTab.Controls.Add($dashboardLayout)

$cardsPanel = New-Object Windows.Forms.FlowLayoutPanel
$cardsPanel.Dock = 'Fill'
$cardsPanel.AutoScroll = $true
$cardsPanel.WrapContents = $false
$cardsPanel.FlowDirection = 'LeftToRight'
$cardsPanel.BackColor = $ColorWindow
$dashboardLayout.Controls.Add($cardsPanel,0,0)

$chartGrid = New-Object Windows.Forms.TableLayoutPanel
$chartGrid.Dock = 'Fill'
$chartGrid.ColumnCount = 2
$chartGrid.RowCount = 1
$chartGrid.Padding = New-Object Windows.Forms.Padding(0,0,0,8)
[void]$chartGrid.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',50)))
[void]$chartGrid.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',50)))
$dashboardLayout.Controls.Add($chartGrid,0,1)

function New-ChartBox([string]$Caption) {
    $box = New-Object Windows.Forms.TableLayoutPanel
    $box.Dock = 'Fill'
    $box.RowCount = 2
    $box.ColumnCount = 1
    $box.Margin = New-Object Windows.Forms.Padding(4)
    $box.BackColor = $ColorSurface
    [void]$box.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',38)))
    [void]$box.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100)))

    $bar = New-Object Windows.Forms.Panel
    $bar.Dock = 'Fill'
    $bar.BackColor = $ColorSurface
    $box.Controls.Add($bar,0,0)

    $label = New-Object Windows.Forms.Label
    $label.Text = $Caption
    $label.Font = New-Object Drawing.Font('Segoe UI',9,[Drawing.FontStyle]::Bold)
    $label.ForeColor = $ColorText
    $label.Location = New-Object Drawing.Point(10,10)
    $label.Size = New-Object Drawing.Size(120,22)
    $bar.Controls.Add($label)

    $combo = New-Object Windows.Forms.ComboBox
    $combo.DropDownStyle = 'DropDownList'
    $combo.Dock = 'Right'
    $combo.Width = 180
    $combo.Margin = New-Object Windows.Forms.Padding(0,6,10,6)
    $bar.Controls.Add($combo)

    $chart = New-Chart
    $box.Controls.Add($chart,0,1)
    return [pscustomobject]@{Box=$box;Combo=$combo;Chart=$chart}
}

$chartABox = New-ChartBox 'リアルタイム推移'
$chartBBox = New-ChartBox 'リアルタイム推移'
$chartGrid.Controls.Add($chartABox.Box,0,0)
$chartGrid.Controls.Add($chartBBox.Box,1,0)

$grid = New-Object Windows.Forms.DataGridView
$grid.Dock = 'Fill'
Style-Grid $grid
$dashboardLayout.Controls.Add($grid,0,2)

$historyTab = New-Object Windows.Forms.TabPage
$historyTab.Text = '履歴'
$historyTab.BackColor = $ColorWindow
[void]$tabs.TabPages.Add($historyTab)

$historyLayout = New-Object Windows.Forms.TableLayoutPanel
$historyLayout.Dock = 'Fill'
$historyLayout.RowCount = 2
$historyLayout.ColumnCount = 1
$historyLayout.Padding = New-Object Windows.Forms.Padding(8)
[void]$historyLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',48)))
[void]$historyLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100)))
$historyTab.Controls.Add($historyLayout)

$historyBar = New-Object Windows.Forms.FlowLayoutPanel
$historyBar.Dock = 'Fill'
$historyBar.FlowDirection = 'LeftToRight'
$historyBar.WrapContents = $false
$historyBar.Padding = New-Object Windows.Forms.Padding(5,7,0,0)
$historyLayout.Controls.Add($historyBar,0,0)

$historyRunLabel = New-Object Windows.Forms.Label
$historyRunLabel.Text = '保存済み実行'
$historyRunLabel.AutoSize = $false
$historyRunLabel.Size = New-Object Drawing.Size(95,27)
$historyRunLabel.TextAlign = 'MiddleLeft'
$historyBar.Controls.Add($historyRunLabel)

$historyRuns = New-Object Windows.Forms.ComboBox
$historyRuns.DropDownStyle = 'DropDownList'
$historyRuns.Size = New-Object Drawing.Size(360,27)
$historyRuns.Margin = New-Object Windows.Forms.Padding(0,0,12,0)
$historyBar.Controls.Add($historyRuns)

$historyMetricLabel = New-Object Windows.Forms.Label
$historyMetricLabel.Text = 'グラフ'
$historyMetricLabel.AutoSize = $false
$historyMetricLabel.Size = New-Object Drawing.Size(50,27)
$historyMetricLabel.TextAlign = 'MiddleLeft'
$historyBar.Controls.Add($historyMetricLabel)

$historyMetric = New-Object Windows.Forms.ComboBox
$historyMetric.DropDownStyle = 'DropDownList'
$historyMetric.Size = New-Object Drawing.Size(180,27)
$historyMetric.Margin = New-Object Windows.Forms.Padding(0,0,12,0)
$historyBar.Controls.Add($historyMetric)

$historyRefresh = New-Object Windows.Forms.Button
$historyRefresh.Text = '更新'
$historyRefresh.Size = New-Object Drawing.Size(72,28)
$historyBar.Controls.Add($historyRefresh)

$historyFolder = New-Object Windows.Forms.Button
$historyFolder.Text = '履歴フォルダー'
$historyFolder.Size = New-Object Drawing.Size(112,28)
$historyFolder.Margin = New-Object Windows.Forms.Padding(8,0,0,0)
$historyBar.Controls.Add($historyFolder)

$historySummary = New-Object Windows.Forms.Label
$historySummary.AutoSize = $false
$historySummary.Size = New-Object Drawing.Size(420,27)
$historySummary.Margin = New-Object Windows.Forms.Padding(12,0,0,0)
$historySummary.TextAlign = 'MiddleLeft'
$historySummary.ForeColor = $ColorMuted
$historyBar.Controls.Add($historySummary)

$historySplit = New-Object Windows.Forms.SplitContainer
$historySplit.Dock = 'Fill'
$historySplit.Orientation = 'Horizontal'
$historyLayout.Controls.Add($historySplit,0,1)

$historyChart = New-Chart
$historySplit.Panel1.Controls.Add($historyChart)

$historyGrid = New-Object Windows.Forms.DataGridView
$historyGrid.Dock = 'Fill'
Style-Grid $historyGrid
[void]$historyGrid.Columns.Add('Time','時刻')
[void]$historyGrid.Columns.Add('Aircraft','機体')
[void]$historyGrid.Columns.Add('Phase','Phase')
[void]$historyGrid.Columns.Add('Stage','Stage')
[void]$historyGrid.Columns.Add('Speed','Speed')
[void]$historyGrid.Columns.Add('AGL','AGL')
[void]$historyGrid.Columns.Add('Separation','分離')
[void]$historyGrid.Columns.Add('Event','Event')
$historyGrid.Columns[0].Width = 90
$historyGrid.Columns[1].Width = 200
$historyGrid.Columns[2].Width = 135
$historyGrid.Columns[3].Width = 135
$historyGrid.Columns[4].Width = 78
$historyGrid.Columns[5].Width = 78
$historyGrid.Columns[6].Width = 78
$historyGrid.Columns[7].AutoSizeMode = 'Fill'
$historySplit.Panel2.Controls.Add($historyGrid)

$eventsTab = New-Object Windows.Forms.TabPage
$eventsTab.Text = 'イベント'
$eventsTab.BackColor = $ColorWindow
[void]$tabs.TabPages.Add($eventsTab)

$eventGrid = New-Object Windows.Forms.DataGridView
$eventGrid.Dock = 'Fill'
Style-Grid $eventGrid
[void]$eventGrid.Columns.Add('Tick','Tick')
[void]$eventGrid.Columns.Add('Aircraft','機体')
[void]$eventGrid.Columns.Add('Event','イベント')
[void]$eventGrid.Columns.Add('Reason','理由 / 詳細')
$eventGrid.Columns[0].Width = 90
$eventGrid.Columns[1].Width = 220
$eventGrid.Columns[2].Width = 260
$eventGrid.Columns[3].AutoSizeMode = 'Fill'
$eventsTab.Controls.Add($eventGrid)

$logTab = New-Object Windows.Forms.TabPage
$logTab.Text = 'Runnerログ'
$logTab.BackColor = $ColorSurface
[void]$tabs.TabPages.Add($logTab)

$logBox = New-Object Windows.Forms.TextBox
$logBox.Dock = 'Fill'
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = 'Both'
$logBox.WordWrap = $false
$logBox.Font = New-Object Drawing.Font('Consolas',9)
$logBox.BackColor = [Drawing.Color]::FromArgb(24,29,38)
$logBox.ForeColor = [Drawing.Color]::FromArgb(224,230,239)
$logTab.Controls.Add($logBox)

function Refresh-HistoryList([string]$KeepPath) {
    if ($null -eq $script:Profile) { return }
    $historyRuns.SuspendLayout()
    try {
        $historyRuns.Items.Clear()
        $root = History-ProfileRoot $script:Profile
        $files = @(Get-ChildItem -LiteralPath $root -Filter '*.jsonl' -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending)
        $selected = 0
        for ($i=0; $i -lt $files.Count; $i++) {
            $file = $files[$i]
            $item = [pscustomobject]@{
                label = '{0}   {1}' -f $file.LastWriteTime.ToString('MM/dd HH:mm'),$file.BaseName
                path = $file.FullName
            }
            [void]$historyRuns.Items.Add($item)
            if ($file.FullName -eq $KeepPath) { $selected = $i }
        }
        $historyRuns.DisplayMember = 'label'
        if ($historyRuns.Items.Count -gt 0) {
            $historyRuns.SelectedIndex = [math]::Min($selected,$historyRuns.Items.Count-1)
        } else {
            $script:HistoryRecords = @()
            $historyGrid.Rows.Clear()
            $historySummary.Text = '保存履歴はまだありません。'
            Update-Chart $historyChart @() (Selected-MetricKey $historyMetric 'speed') $script:Profile
        }
        $script:LastHistoryRefresh = Get-Date
    } finally { $historyRuns.ResumeLayout() }
}

function Load-SelectedHistory {
    if ($null -eq $script:Profile -or $null -eq $historyRuns.SelectedItem) { return }
    $path = [string]$historyRuns.SelectedItem.path
    $script:HistoryRecords = @(Read-History $path)

    $historyGrid.SuspendLayout()
    try {
        $historyGrid.Rows.Clear()
        foreach ($record in @($script:HistoryRecords | Select-Object -Last 800 | Sort-Object timestamp -Descending)) {
            [void]$historyGrid.Rows.Add(
                ([datetime]$record.timestamp).ToString('HH:mm:ss'),
                [string]$record.aircraft,
                (Get-MapValue $record.values 'phase'),
                (Get-MapValue $record.values 'stage'),
                (Get-MapValue $record.values 'speed'),
                (Get-MapValue $record.values 'agl'),
                (Get-MapValue $record.values 'separation'),
                (Get-MapValue $record.values 'event'))
        }
    } finally { $historyGrid.ResumeLayout() }

    $metricKey = Selected-MetricKey $historyMetric 'speed'
    Update-Chart $historyChart $script:HistoryRecords $metricKey $script:Profile
    if ($script:HistoryRecords.Count -gt 0) {
        $first = [datetime]$script:HistoryRecords[0].timestamp
        $last = [datetime]$script:HistoryRecords[$script:HistoryRecords.Count-1].timestamp
        $planes = @($script:HistoryRecords | Select-Object -ExpandProperty aircraft -Unique).Count
        $historySummary.Text =
            "$planes 機 / $($script:HistoryRecords.Count) サンプル / $($first.ToString('HH:mm:ss'))–$($last.ToString('HH:mm:ss'))"
    } else {
        $historySummary.Text = '読み取れる履歴データがありません。'
    }
}

function Reload-Profiles([string]$Id) {
    $script:ReloadingProfiles = $true
    try {
        $profiles.BeginUpdate()
        $profiles.Items.Clear()
        foreach ($profile in @($script:Config.profiles)) { [void]$profiles.Items.Add($profile) }
        $profiles.DisplayMember = 'name'
        [int]$index = 0
        for ([int]$i=0; $i -lt $profiles.Items.Count; $i++) {
            if ([string]$profiles.Items[$i].id -eq $Id) { $index=$i;break }
        }
        if ($profiles.Items.Count -gt 0) { $profiles.SelectedIndex = [int]$index }
    } finally {
        $profiles.EndUpdate()
        $script:ReloadingProfiles = $false
    }
    Select-Profile
}

function Select-Profile {
    if ($profiles.SelectedIndex -lt 0) { return }
    $script:Profile = $profiles.SelectedItem
    Build-Columns $script:Profile $grid
    Fill-MetricCombo $chartABox.Combo $script:Profile 'speed'
    Fill-MetricCombo $chartBBox.Combo $script:Profile 'agl'
    Fill-MetricCombo $historyMetric $script:Profile 'speed'
    Reset-LiveSamples ''
    $script:LastSnapshotKey = ''
    Prune-History $script:Profile
    Refresh-HistoryList ''

    $idle = Idle-Snapshot $script:Profile
    Fill-Telemetry $idle $script:Profile $grid
    Fill-Cards $idle $cardsPanel
    Fill-Events $idle $eventGrid
    Update-Chart $chartABox.Chart @() (Selected-MetricKey $chartABox.Combo 'speed') $script:Profile
    Update-Chart $chartBBox.Chart @() (Selected-MetricKey $chartBBox.Combo 'agl') $script:Profile
    Reset-RunnerCache $script:Profile
}


function Find-RunnerGridRow([string]$Id) {
    foreach ($row in @($runnerGrid.Rows)) {
        if ($row.IsNewRow) { continue }
        if ([string]$row.Cells['Id'].Value -eq $Id) { return $row }
    }
    return $null
}

function Set-RunnerGridRow($Model) {
    $row = Find-RunnerGridRow ([string]$Model.Id)
    if ($null -eq $row) {
        $index = $runnerGrid.Rows.Add()
        $row = $runnerGrid.Rows[$index]
    }
    foreach ($cellName in @('Id','Name','Scope','Repository','Root','State','Capabilities','Evidence','Ephemeral')) {
        $value = [string]$Model.$cellName
        if ([string]$row.Cells[$cellName].Value -ne $value) {
            $row.Cells[$cellName].Value = $value
        }
    }
    $row.Cells['State'].Style.ForeColor = switch ([string]$Model.Tone) {
        'good' { $ColorGood }
        'bad' { $ColorBad }
        default { $ColorWarn }
    }
    if ([string]$Model.Scope -eq '未管理') {
        $row.Cells['Scope'].Style.ForeColor = $ColorBad
        $row.Cells['Scope'].Style.Font = New-Object Drawing.Font('Segoe UI',9,[Drawing.FontStyle]::Bold)
    } else {
        $row.Cells['Scope'].Style.ForeColor = $ColorGood
    }
    return $row
}

function Update-RunnerActionAvailability {
    $managed = $null -ne (Get-SelectedRunnerProfile)
    $startSelectedRunner.Enabled = $managed
    $stopSelectedRunner.Enabled = $managed
    $startEphemeralRunner.Enabled = $managed
}

function Refresh-RunnerOverview([switch]$Force) {
    if ($script:RunnerOverviewRefreshing) { return }
    if (-not $Force -and
        ([datetime]::UtcNow-$script:LastRunnerOverviewRefresh).TotalSeconds -lt $script:RunnerOverviewIntervalSeconds) {
        return
    }

    $script:RunnerOverviewRefreshing = $true
    try {
        $selectedId = ''
        if ($runnerGrid.SelectedRows.Count -gt 0) {
            $selectedId = [string]$runnerGrid.SelectedRows[0].Cells['Id'].Value
        } elseif (-not [string]::IsNullOrWhiteSpace($script:PreferredRunnerSelectionId)) {
            $selectedId = $script:PreferredRunnerSelectionId
        }

        $firstDisplayedRow = -1
        try { $firstDisplayedRow = $runnerGrid.FirstDisplayedScrollingRowIndex } catch {}

        $models = New-Object System.Collections.Generic.List[object]
        $capabilitySnapshot = Read-CapabilitySnapshot

        foreach ($profile in @($script:Config.profiles)) {
            $root = [Environment]::ExpandEnvironmentVariables([string]$profile.runnerRoot)
            $repository = ([string]$profile.repoUrl).TrimEnd('/') -replace '^https://github.com/',''
            $stateCode = 'unregistered'
            if (Test-RunnerConfigured $profile) {
                $state = Read-RunnerConnectionState $profile
                Invoke-RunnerAutoRecovery $profile $state
                $stateText = [string]$state.Text
                $stateCode = [string]$state.Code
                $evidence = [string]$state.Evidence
            } else {
                $stateText = '未登録'
                $evidence = 'run.cmd または .runner がありません'
            }

            $cachedCapabilities = Get-CachedRunnerCapabilities $profile
            $capabilityText = [string]$cachedCapabilities.Summary
            if ($null -ne $capabilitySnapshot) {
                $required = if ($profile.PSObject.Properties.Name -contains 'requiredCapabilities') {
                    @($profile.requiredCapabilities)
                } else { @() }
                $selectedCapabilities = if (@($required).Count -eq 0) {
                    @($capabilitySnapshot.capabilities)
                } else {
                    @($capabilitySnapshot.capabilities | Where-Object { $required -contains [string]$_.name })
                }
                $readyCount = @($selectedCapabilities | Where-Object { $_.status -eq 'ready' }).Count
                $missing = @($selectedCapabilities | Where-Object { $_.status -ne 'ready' } | ForEach-Object { [string]$_.name })
                $capabilityText = if ($missing.Count -eq 0) {
                    "$readyCount/$($selectedCapabilities.Count) ready"
                } else {
                    "$readyCount/$($selectedCapabilities.Count) ready; $($missing -join ', ')"
                }
                if ($script:CapabilitiesReadFailures -gt 0) { $capabilityText += ' (更新再試行中)' }
            } else {
                $capabilityText = '能力情報を再取得中'
            }

            $ephemeral = if (Test-JollyEphemeralEnabled $profile) {
                Get-JollyEphemeralSummary -AppRoot $AppRoot -ProfileId ([string]$profile.id)
            } else { 'disabled' }

            $tone = if ($stateCode -in @('listening','running_job','connected_starting')) {
                'good'
            } elseif ($stateCode -in @('stopped','reconnecting','unregistered')) {
                'bad'
            } else {
                'warn'
            }

            [void]$models.Add([pscustomobject]@{
                Id = [string]$profile.id
                Name = [string]$profile.name
                Scope = '管理'
                Repository = $repository
                Root = $root
                State = $stateText
                Capabilities = $capabilityText
                Evidence = $evidence
                Ephemeral = $ephemeral
                Tone = $tone
            })
        }

        $unmanaged = @(Get-RunnerInventory -Force:$Force | Where-Object { $_.Scope -eq 'unmanaged' })
        foreach ($item in $unmanaged) {
            [void]$models.Add([pscustomobject]@{
                Id = [string]$item.Id
                Name = [string]$item.Name
                Scope = '未管理'
                Repository = if ([string]::IsNullOrWhiteSpace([string]$item.Repository)) { '(不明)' } else { [string]$item.Repository }
                Root = [string]$item.Root
                State = if ($item.Running) { '実行中 / 未管理' } else { '停止 / 未管理' }
                Capabilities = '-'
                Evidence = 'Hub profileに未登録。自動起動・停止・復旧の対象外'
                Ephemeral = 'Hub外'
                Tone = 'bad'
            })
        }

        $desiredIds = @{}
        $runnerGrid.SuspendLayout()
        try {
            foreach ($model in $models) {
                $desiredIds[[string]$model.Id] = $true
                $row = Set-RunnerGridRow $model
                if ([string]$model.Id -eq $selectedId) { $row.Selected = $true }
            }

            for ($i=$runnerGrid.Rows.Count-1; $i -ge 0; $i--) {
                $row = $runnerGrid.Rows[$i]
                if ($row.IsNewRow) { continue }
                $id = [string]$row.Cells['Id'].Value
                if (-not $desiredIds.ContainsKey($id)) {
                    $runnerGrid.Rows.RemoveAt($i)
                }
            }

            if ($runnerGrid.SelectedRows.Count -eq 0 -and $runnerGrid.Rows.Count -gt 0) {
                $runnerGrid.Rows[0].Selected = $true
            }
            if ($firstDisplayedRow -ge 0 -and $firstDisplayedRow -lt $runnerGrid.Rows.Count) {
                try { $runnerGrid.FirstDisplayedScrollingRowIndex = $firstDisplayedRow } catch {}
            }
        } finally {
            $runnerGrid.ResumeLayout()
        }

        $managedCount = @($script:Config.profiles).Count
        $runnerIntro.Text = if ($unmanaged.Count -gt 0) {
            "管理Runner $managedCount 件 / 未管理Runner $($unmanaged.Count) 件を検出。未管理RunnerはHubから操作せず、整理または正式プロファイル化してください。"
        } else {
            "管理Runner $managedCount 件 / 未管理Runner 0 件。新しい一時RunnerはEphemeral起動から作成するとHub管理下で自動GCされます。"
        }
        $runnerIntro.ForeColor = if ($unmanaged.Count -gt 0) { $ColorBad } else { $ColorText }
        $script:PreferredRunnerSelectionId = ''
        $script:LastRunnerOverviewRefresh = [datetime]::UtcNow
        Update-RunnerActionAvailability
    } finally {
        $script:RunnerOverviewRefreshing = $false
    }
}

function Get-SelectedRunnerProfile {
    if ($runnerGrid.SelectedRows.Count -eq 0) { return $null }
    return Get-ProfileById ([string]$runnerGrid.SelectedRows[0].Cells['Id'].Value)
}

$runnerGrid.add_SelectionChanged({ Update-RunnerActionAvailability })
$profiles.add_SelectedIndexChanged({
    if (-not $script:ReloadingProfiles) { Select-Profile }
})
$chartABox.Combo.add_SelectedIndexChanged({
    if ($null -ne $script:Profile) {
        Update-Chart $chartABox.Chart $script:LiveSamples `
            (Selected-MetricKey $chartABox.Combo 'speed') $script:Profile
    }
})
$chartBBox.Combo.add_SelectedIndexChanged({
    if ($null -ne $script:Profile) {
        Update-Chart $chartBBox.Chart $script:LiveSamples `
            (Selected-MetricKey $chartBBox.Combo 'agl') $script:Profile
    }
})
$historyRuns.add_SelectedIndexChanged({ Load-SelectedHistory })
$historyMetric.add_SelectedIndexChanged({
    if ($null -ne $script:Profile) {
        Update-Chart $historyChart $script:HistoryRecords `
            (Selected-MetricKey $historyMetric 'speed') $script:Profile
    }
})

$connect.add_Click({
    try { Start-Runner $script:Profile } catch { Show-Error $_.Exception.Message }
})
$disconnect.add_Click({
    if ([Windows.Forms.MessageBox]::Show(
        'Runnerを停止しますか？',
        'ジョリー Runner Hub',
        [Windows.Forms.MessageBoxButtons]::YesNo,
        [Windows.Forms.MessageBoxIcon]::Question) -eq 'Yes') {
        try { Stop-Runner $script:Profile } catch { Show-Error $_.Exception.Message }
    }
})
$startSelectedRunner.add_Click({
    $profile = Get-SelectedRunnerProfile
    if ($null -ne $profile) {
        try { Start-Runner $profile; Refresh-RunnerOverview -Force } catch { Show-Error $_.Exception.Message }
    }
})
$stopSelectedRunner.add_Click({
    $profile = Get-SelectedRunnerProfile
    if ($null -ne $profile -and [Windows.Forms.MessageBox]::Show(
        "$($profile.name) を停止しますか？",
        'ジョリー Runner Hub',
        [Windows.Forms.MessageBoxButtons]::YesNo,
        [Windows.Forms.MessageBoxIcon]::Question) -eq 'Yes') {
        try { Stop-Runner $profile; Refresh-RunnerOverview -Force } catch { Show-Error $_.Exception.Message }
    }
})
$startAllRunners.add_Click({
    $errors = New-Object System.Collections.Generic.List[string]
    foreach ($profile in @($script:Config.profiles)) {
        if (-not (Test-RunnerConfigured $profile)) { continue }
        try { Start-Runner $profile } catch { $errors.Add("$($profile.name): $($_.Exception.Message)") }
    }
    Refresh-RunnerOverview -Force
    if ($errors.Count -gt 0) { Show-Error ($errors -join [Environment]::NewLine) }
})
$stopAllRunners.add_Click({
    if ([Windows.Forms.MessageBox]::Show(
        'Hubに登録された実行中のRunnerをすべて停止しますか？',
        'ジョリー Runner Hub',
        [Windows.Forms.MessageBoxButtons]::YesNo,
        [Windows.Forms.MessageBoxIcon]::Question) -eq 'Yes') {
        foreach ($profile in @($script:Config.profiles)) {
            try { Stop-Runner $profile } catch {}
        }
        Refresh-RunnerOverview -Force
    }
})
$startEphemeralRunner.add_Click({
    $profile = Get-SelectedRunnerProfile
    if ($null -eq $profile) { return }
    if ([Windows.Forms.MessageBox]::Show(
        "$($profile.name) 用の一時Runnerを作成しますか？",
        'ジョリー Runner Hub',
        [Windows.Forms.MessageBoxButtons]::YesNo,
        [Windows.Forms.MessageBoxIcon]::Question) -eq 'Yes') {
        try {
            $state = Start-JollyEphemeralRunner -Profile $profile -AppRoot $AppRoot
            Refresh-RunnerOverview -Force
            [Windows.Forms.MessageBox]::Show(
                "作成しました: $($state.runnerName)`nTTL=$($state.ttlMinutes)分`nLabels=$(@($state.labels) -join ',')",
                'ジョリー Runner Hub',
                [Windows.Forms.MessageBoxButtons]::OK,
                [Windows.Forms.MessageBoxIcon]::Information) | Out-Null
        } catch { Show-Error $_.Exception.Message }
    }
})
$gcEphemeralRunners.add_Click({
    try {
        $results = @(Invoke-JollyEphemeralGc -AppRoot $AppRoot)
        Refresh-RunnerOverview -Force
        $changed = @($results | Where-Object { [string]$_.Action -like 'cleaned_*' }).Count
        [Windows.Forms.MessageBox]::Show(
            "Ephemeral GC: cleaned=$changed / inspected=$($results.Count)",
            'ジョリー Runner Hub',
            [Windows.Forms.MessageBoxButtons]::OK,
            [Windows.Forms.MessageBoxIcon]::Information) | Out-Null
    } catch { Show-Error $_.Exception.Message }
})
$refreshRunners.add_Click({
    foreach ($profile in @($script:Config.profiles)) { Reset-RunnerCapabilityCache $profile }
    Refresh-RunnerOverview -Force
})
$refreshCapabilities.add_Click({
    try {
        if (-not (Test-Path -LiteralPath $CapabilitiesScriptPath)) {
            throw "RunnerCapabilities.ps1 がありません: $CapabilitiesScriptPath"
        }
        if (-not (Test-Path -LiteralPath $CapabilitiesCliPath)) {
            throw "Inspect-RunnerCapabilities.ps1 がありません: $CapabilitiesCliPath"
        }
        $roots = @($script:Config.profiles | ForEach-Object { [string]$_.runnerRoot })
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $CapabilitiesCliPath `
            -RunnerRoots $roots -OutputPath $CapabilitiesPath | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Capability probe failed with exit code $LASTEXITCODE" }
        foreach ($profile in @($script:Config.profiles)) { Reset-RunnerCapabilityCache $profile }
        Refresh-RunnerOverview -Force
    } catch { Show-Error $_.Exception.Message }
})
$configButton.add_Click({
    Start-Process notepad.exe -ArgumentList ('"{0}"' -f $ConfigPath)
})
$actionsButton.add_Click({
    if ($script:Profile.repoUrl) {
        Start-Process (([string]$script:Profile.repoUrl).TrimEnd('/') + '/actions')
    }
})
$dataButton.add_Click({
    $path = [Environment]::ExpandEnvironmentVariables([string]$script:Profile.telemetryRoot)
    if (Test-Path $path) {
        Start-Process explorer.exe -ArgumentList ('"{0}"' -f $path)
    } else {
        Show-Error "データ場所がまだありません。`n$path"
    }
})
$reloadButton.add_Click({
    try {
        $id = [string]$script:Profile.id
        Load-Config
        Reload-Profiles $id
    } catch { Show-Error $_.Exception.Message }
})
$historyRefresh.add_Click({
    $keep = if ($null -ne $historyRuns.SelectedItem) {[string]$historyRuns.SelectedItem.path} else {''}
    Refresh-HistoryList $keep
    Load-SelectedHistory
})
$historyFolder.add_Click({
    $path = History-ProfileRoot $script:Profile
    Start-Process explorer.exe -ArgumentList ('"{0}"' -f $path)
})

$uiState = Read-UiState
$initialProfileId = if ($null -ne $uiState -and $uiState.PSObject.Properties.Name -contains 'profileId') { [string]$uiState.profileId } else { '' }
if ($null -ne $uiState -and $uiState.PSObject.Properties.Name -contains 'runnerId') {
    $script:PreferredRunnerSelectionId = [string]$uiState.runnerId
}
Reload-Profiles $initialProfileId
Refresh-RunnerOverview -Force
if ($null -ne $uiState -and $uiState.PSObject.Properties.Name -contains 'tabIndex') {
    $savedTab = 0
    if ([int]::TryParse([string]$uiState.tabIndex,[ref]$savedTab) -and
        $savedTab -ge 0 -and $savedTab -lt $tabs.TabPages.Count) {
        $tabs.SelectedIndex = $savedTab
    }
}

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 1000
$timer.add_Tick({
    if ($null -eq $script:Profile) { return }
    try {
        if ((Get-Item $ConfigPath).LastWriteTimeUtc -gt $script:LastConfigWrite) {
            $id = [string]$script:Profile.id
            Load-Config
            Reload-Profiles $id
            Refresh-RunnerOverview -Force
        }

        if (([datetime]::UtcNow-$script:LastEphemeralGc).TotalSeconds -ge 30) {
            try { [void](Invoke-JollyEphemeralGc -AppRoot $AppRoot) } catch {}
            $script:LastEphemeralGc = [datetime]::UtcNow
        }

        if ($tabs.SelectedTab -eq $runnerTab) {
            Refresh-RunnerOverview
        }

        if (Runner-Running $script:Profile) {
            $runnerStatus.Value.Text = '接続中'
            $runnerStatus.Value.ForeColor = [Drawing.Color]::FromArgb(105,228,154)
        } else {
            $runnerStatus.Value.Text = '停止中'
            $runnerStatus.Value.ForeColor = [Drawing.Color]::FromArgb(255,137,141)
        }

        $snapshot = Read-Snapshot $script:Profile
        $snapshotKey = '{0}|{1}|{2}|{3}' -f [string]$script:Profile.id,[string]$snapshot.Run,[string]$snapshot.Active,[string]$snapshot.Updated
        if ($snapshotKey -ne $script:LastSnapshotKey) {
            Fill-Telemetry $snapshot $script:Profile $grid
            Fill-Cards $snapshot $cardsPanel
            Fill-Events $snapshot $eventGrid
            $script:LastSnapshotKey = $snapshotKey
        }

        $historyWritten = Record-Snapshot $snapshot $script:Profile
        if ($historyWritten) {
            Update-Chart $chartABox.Chart $script:LiveSamples `
                (Selected-MetricKey $chartABox.Combo 'speed') $script:Profile
            Update-Chart $chartBBox.Chart $script:LiveSamples `
                (Selected-MetricKey $chartBBox.Combo 'agl') $script:Profile
        }

        if ($snapshot.Active) {
            $validationStatus.Value.Text =
                "実行中  Run=$($snapshot.Run)  更新=$($snapshot.Updated.ToString('HH:mm:ss'))"
            $validationStatus.Value.ForeColor = [Drawing.Color]::FromArgb(105,228,154)
        } else {
            $validationStatus.Value.Text = '待機中'
            $validationStatus.Value.ForeColor = $ColorHeaderMuted
        }

        $historyFiles = @(Get-ChildItem -LiteralPath (History-ProfileRoot $script:Profile) `
            -Filter '*.jsonl' -File -ErrorAction SilentlyContinue)
        $historyStatus.Value.Text =
            "$($historyFiles.Count) 実行を保存  /  最新 $($script:LiveSamples.Count) サンプル"
        $historyStatus.Value.ForeColor = [Drawing.Color]::FromArgb(147,190,255)

        if ($historyWritten -and ((Get-Date)-$script:LastHistoryRefresh).TotalSeconds -gt 15) {
            $keep = if ($null -ne $historyRuns.SelectedItem) {[string]$historyRuns.SelectedItem.path} else {''}
            Refresh-HistoryList $keep
        }

        if ($tabs.SelectedTab -eq $logTab -and
            (([datetime]::UtcNow-$script:LastLogRefresh).TotalSeconds -ge 2)) {
            $logPath = Log-Path $script:Profile
            $newLogText = if (Test-Path $logPath) {
                (Tail-Lines $logPath 262144) -join [Environment]::NewLine
            } else {
                'Runner Hubから起動すると、ここにRunnerログが表示されます。'
            }
            if ($logBox.Text -ne $newLogText) {
                $logBox.Text = $newLogText
                $logBox.SelectionStart = $logBox.TextLength
                $logBox.ScrollToCaret()
            }
            $script:LastLogRefresh = [datetime]::UtcNow
        }
    } catch {
        $validationStatus.Value.Text = '読込エラー: ' + $_.Exception.Message
        $validationStatus.Value.ForeColor = [Drawing.Color]::FromArgb(255,137,141)
    }
})
$timer.Start()

$form.add_Shown({
    try { [void](Invoke-JollyEphemeralGc -AppRoot $AppRoot) } catch {}
    $script:LastEphemeralGc = [datetime]::UtcNow
    if ($historySplit.Height -gt 420) {
        $historySplit.Panel1MinSize = 180
        $historySplit.Panel2MinSize = 140
        $historySplit.SplitterDistance = [int]($historySplit.Height * 0.64)
    }
    if ([bool]$script:Config.autoConnect) {
        $errors = New-Object System.Collections.Generic.List[string]
        foreach ($profile in @($script:Config.profiles)) {
            if (-not (Test-RunnerConfigured $profile)) { continue }
            try { Start-Runner $profile } catch {
                $errors.Add("$($profile.name): $($_.Exception.Message)")
            }
        }
        Refresh-RunnerOverview -Force
        if ($errors.Count -gt 0) { Show-Error ($errors -join [Environment]::NewLine) }
    }
})
$form.add_FormClosed({
    Save-UiState
    $timer.Stop()
})
[void]$form.ShowDialog()
