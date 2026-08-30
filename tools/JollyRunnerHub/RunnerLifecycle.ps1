Set-StrictMode -Version Latest

function ConvertTo-JollySafeName {
    param([Parameter(Mandatory=$true)][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return 'unknown' }
    return ($Text -replace '[^A-Za-z0-9_.-]','_')
}

function Get-JollyEphemeralRoot {
    param([Parameter(Mandatory=$true)][string]$AppRoot)
    # Runner workspaces can add the repository name twice below _work.
    # Keep executable/work data on a deliberately short path to avoid
    # MAX_PATH failures, while lifecycle state remains under AppRoot.
    $temp = [IO.Path]::GetTempPath()
    if ([string]::IsNullOrWhiteSpace($temp)) { throw 'Windows temporary directory is unavailable' }
    return Join-Path $temp 'JollyER'
}

function Get-JollyLegacyEphemeralRoot {
    param([Parameter(Mandatory=$true)][string]$AppRoot)
    return Join-Path $AppRoot 'ephemeral'
}

function Test-JollyEphemeralOwnedPath {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$AppRoot
    )
    if (Test-JollyPathInside -Path $Path -Root (Get-JollyEphemeralRoot $AppRoot)) { return $true }
    return Test-JollyPathInside -Path $Path -Root (Get-JollyLegacyEphemeralRoot $AppRoot)
}

function Get-JollyEphemeralStateRoot {
    param([Parameter(Mandatory=$true)][string]$AppRoot)
    return Join-Path $AppRoot 'ephemeral-state'
}

function Test-JollyPathInside {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Root
    )
    try {
        $fullPath = [IO.Path]::GetFullPath($Path).TrimEnd('\')
        $fullRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
        if ($fullPath.Equals($fullRoot,[StringComparison]::OrdinalIgnoreCase)) { return $true }
        return $fullPath.StartsWith($fullRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)
    }
    catch { return $false }
}

function Get-JollyProfileRepository {
    param([Parameter(Mandatory=$true)]$Profile)
    $url = [string]$Profile.repoUrl
    if ($url -match '^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$') {
        return ('{0}/{1}' -f $Matches[1],$Matches[2])
    }
    throw "Unsupported GitHub repository URL: $url"
}

function Test-JollyEphemeralEnabled {
    param([Parameter(Mandatory=$true)]$Profile)
    $property = $Profile.PSObject.Properties['ephemeralEnabled']
    if ($null -eq $property) { return $true }
    return [bool]$property.Value
}

function Get-JollyEphemeralTtlMinutes {
    param([Parameter(Mandatory=$true)]$Profile)
    $ttl = 30
    $property = $Profile.PSObject.Properties['ephemeralTtlMinutes']
    if ($null -ne $property) {
        $parsed = 0
        if ([int]::TryParse([string]$property.Value,[ref]$parsed)) { $ttl = $parsed }
    }
    if ($ttl -lt 5) { $ttl = 5 }
    if ($ttl -gt 120) { $ttl = 120 }
    return $ttl
}

function Get-JollyEphemeralLabels {
    param([Parameter(Mandatory=$true)]$Profile)
    $labels = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($label in @('jolly-ephemeral',(ConvertTo-JollySafeName ([string]$Profile.id)))) {
        if (-not [string]::IsNullOrWhiteSpace($label) -and -not $seen.ContainsKey($label)) {
            $seen[$label] = $true
            [void]$labels.Add($label)
        }
    }
    $property = $Profile.PSObject.Properties['ephemeralLabels']
    if ($null -ne $property) {
        foreach ($raw in @($property.Value)) {
            $label = ConvertTo-JollySafeName ([string]$raw)
            if (-not [string]::IsNullOrWhiteSpace($label) -and -not $seen.ContainsKey($label)) {
                $seen[$label] = $true
                [void]$labels.Add($label)
            }
        }
    }
    return $labels.ToArray()
}

function Get-JollyRunnerCapabilities {
    param(
        [Parameter(Mandatory=$true)][string]$RunnerRoot,
        [switch]$CommandsOnly
    )
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($null -eq $git) { $git = Get-Command git -ErrorAction SilentlyContinue }
    $gh = Get-Command gh.exe -ErrorAction SilentlyContinue
    if ($null -eq $gh) { $gh = Get-Command gh -ErrorAction SilentlyContinue }
    $docker = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($null -eq $docker) { $docker = Get-Command docker -ErrorAction SilentlyContinue }
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    $pwsh = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($null -eq $pwsh) { $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue }
    $java = Get-Command java.exe -ErrorAction SilentlyContinue
    if ($null -eq $java) { $java = Get-Command java -ErrorAction SilentlyContinue }

    $runnerFiles = (Test-Path -LiteralPath (Join-Path $RunnerRoot 'run.cmd')) -and (Test-Path -LiteralPath (Join-Path $RunnerRoot 'config.cmd'))
    $dockerReady = $false
    if ($null -ne $docker -and -not $CommandsOnly) {
        try {
            $dockerReady = (Test-Path -LiteralPath '\\.\pipe\docker_engine') -or (Test-Path -LiteralPath '\\.\pipe\dockerDesktopLinuxEngine')
        }
        catch { $dockerReady = $false }
    }

    $items = New-Object System.Collections.Generic.List[string]
    if ($runnerFiles) { [void]$items.Add('runner') }
    if ($null -ne $git) { [void]$items.Add('git') }
    if ($null -ne $gh) { [void]$items.Add('gh') }
    if ($null -ne $docker) { [void]$items.Add($(if ($dockerReady) { 'docker-ready' } else { 'docker-cli' })) }
    if ($null -ne $wsl) { [void]$items.Add('wsl') }
    if ($null -ne $python) { [void]$items.Add('python') }
    if ($null -ne $pwsh) { [void]$items.Add('pwsh') }
    if ($null -ne $java) { [void]$items.Add('java') }

    return [pscustomobject]@{
        RunnerFiles = [bool]$runnerFiles
        Git = ($null -ne $git)
        Gh = ($null -ne $gh)
        DockerCli = ($null -ne $docker)
        DockerReady = [bool]$dockerReady
        Wsl = ($null -ne $wsl)
        Python = ($null -ne $python)
        Pwsh = ($null -ne $pwsh)
        Java = ($null -ne $java)
        Summary = ($items -join ', ')
    }
}

function Get-JollyEphemeralStatePath {
    param(
        [Parameter(Mandatory=$true)][string]$AppRoot,
        [Parameter(Mandatory=$true)][string]$StateId
    )
    $stateRoot = Get-JollyEphemeralStateRoot $AppRoot
    New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
    return Join-Path $stateRoot ((ConvertTo-JollySafeName $StateId) + '.json')
}

function Write-JollyEphemeralState {
    param(
        [Parameter(Mandatory=$true)][string]$AppRoot,
        [Parameter(Mandatory=$true)]$State
    )
    $stateId = [string]$State.stateId
    if ([string]::IsNullOrWhiteSpace($stateId)) { throw 'Ephemeral stateId is required' }
    $path = Get-JollyEphemeralStatePath -AppRoot $AppRoot -StateId $stateId
    $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

function Get-JollyEphemeralStates {
    param([Parameter(Mandatory=$true)][string]$AppRoot)
    $stateRoot = Get-JollyEphemeralStateRoot $AppRoot
    $ephemeralRoot = Get-JollyEphemeralRoot $AppRoot
    if (-not (Test-Path -LiteralPath $stateRoot)) { return @() }
    $states = New-Object System.Collections.Generic.List[object]
    foreach ($file in @(Get-ChildItem -LiteralPath $stateRoot -Filter '*.json' -File -ErrorAction SilentlyContinue)) {
        try {
            $state = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($null -eq $state.PSObject.Properties['stateId']) {
                Add-Member -InputObject $state -NotePropertyName stateId -NotePropertyValue $file.BaseName
            }
            Add-Member -InputObject $state -NotePropertyName statePath -NotePropertyValue $file.FullName -Force
            Add-Member -InputObject $state -NotePropertyName rootValid -NotePropertyValue (Test-JollyEphemeralOwnedPath -Path ([string]$state.root) -AppRoot $AppRoot) -Force
            [void]$states.Add($state)
        }
        catch {}
    }
    return $states.ToArray()
}

function Get-JollyEphemeralStatus {
    param(
        [Parameter(Mandatory=$true)]$State,
        [datetime]$Now = ([datetime]::UtcNow)
    )
    if ($State.PSObject.Properties['rootValid'] -and -not [bool]$State.rootValid) {
        return [pscustomobject]@{Code='invalid_root';ProcessRunning=$false;RemainingMinutes=0;Summary='invalid root'}
    }
    $processRunning = $false
    $processId = 0
    if ([int]::TryParse([string]$State.processId,[ref]$processId) -and $processId -gt 0) {
        $processRunning = $null -ne (Get-Process -Id $processId -ErrorAction SilentlyContinue)
    }
    $expires = [datetime]::MaxValue
    $parsedExpires = [datetime]::MinValue
    if ([datetime]::TryParse([string]$State.expiresAt,[ref]$parsedExpires)) { $expires = $parsedExpires.ToUniversalTime() }
    $remaining = [int][math]::Ceiling(($expires - $Now.ToUniversalTime()).TotalMinutes)
    if (-not $processRunning) {
        return [pscustomobject]@{Code='finished';ProcessRunning=$false;RemainingMinutes=$remaining;Summary='finished / GC pending'}
    }
    if ($expires -le $Now.ToUniversalTime()) {
        return [pscustomobject]@{Code='expired';ProcessRunning=$true;RemainingMinutes=0;Summary='TTL expired / GC check'}
    }
    $safeRemaining = [math]::Max(0,$remaining)
    return [pscustomobject]@{Code='active';ProcessRunning=$true;RemainingMinutes=$safeRemaining;Summary=('active / TTL {0}m' -f $safeRemaining)}
}

function Find-JollyGitHubRunner {
    param(
        [Parameter(Mandatory=$true)][string]$Repository,
        [Parameter(Mandatory=$true)][string]$RunnerName
    )
    if ($null -eq (Get-Command gh.exe -ErrorAction SilentlyContinue) -and $null -eq (Get-Command gh -ErrorAction SilentlyContinue)) {
        return [pscustomobject]@{Ok=$false;Runner=$null;Error='gh unavailable'}
    }
    try {
        $json = (& gh api --method GET "repos/$Repository/actions/runners?per_page=100" 2>$null) -join [Environment]::NewLine
        if ($LASTEXITCODE -ne 0) { return [pscustomobject]@{Ok=$false;Runner=$null;Error='GitHub runner query failed'} }
        $payload = $json | ConvertFrom-Json
        $runner = @($payload.runners) | Where-Object { [string]$_.name -eq $RunnerName } | Select-Object -First 1
        return [pscustomobject]@{Ok=$true;Runner=$runner;Error=''}
    }
    catch { return [pscustomobject]@{Ok=$false;Runner=$null;Error='GitHub runner query failed'} }
}

function Remove-JollyGitHubRunnerRegistration {
    param(
        [Parameter(Mandatory=$true)][string]$Repository,
        [Parameter(Mandatory=$true)][string]$RunnerName
    )
    $lookup = Find-JollyGitHubRunner -Repository $Repository -RunnerName $RunnerName
    if (-not $lookup.Ok) { return [pscustomobject]@{Ok=$false;Removed=$false;Error=$lookup.Error} }
    if ($null -eq $lookup.Runner) { return [pscustomobject]@{Ok=$true;Removed=$false;Error=''} }
    try {
        & gh api --method DELETE "repos/$Repository/actions/runners/$($lookup.Runner.id)" *> $null
        if ($LASTEXITCODE -ne 0) { return [pscustomobject]@{Ok=$false;Removed=$false;Error='GitHub runner delete failed'} }
        return [pscustomobject]@{Ok=$true;Removed=$true;Error=''}
    }
    catch { return [pscustomobject]@{Ok=$false;Removed=$false;Error='GitHub runner delete failed'} }
}

function Stop-JollyEphemeralProcess {
    param(
        [Parameter(Mandatory=$true)]$State,
        [Parameter(Mandatory=$true)][string]$AppRoot
    )
    if (-not (Test-JollyEphemeralOwnedPath -Path ([string]$State.root) -AppRoot $AppRoot)) { return $false }
    $processId = 0
    if (-not [int]::TryParse([string]$State.processId,[ref]$processId) -or $processId -le 0) { return $true }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $true }
    if ([string]$process.ProcessName -notin @('cmd','Runner.Listener','Runner.Worker')) { return $false }
    Start-Process taskkill.exe -ArgumentList '/PID',[string]$processId,'/T','/F' -Wait -WindowStyle Hidden | Out-Null
    return $null -eq (Get-Process -Id $processId -ErrorAction SilentlyContinue)
}

function Remove-JollyOwnedDirectoryTree {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$AppRoot
    )
    if (-not (Test-JollyEphemeralOwnedPath -Path $Path -AppRoot $AppRoot)) { return $false }
    if (-not (Test-Path -LiteralPath $Path)) { return $true }

    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return -not (Test-Path -LiteralPath $Path)
    }
    catch {
        # Windows PowerShell 5.1 can enumerate a checked-out tree yet fail to
        # delete a deep descendant with DirectoryNotFoundException when the
        # legacy path limit is crossed. Robocopy's mirror engine handles the
        # deep tree natively; mirror an empty directory only after the same
        # strict ownership check above, then remove the now-empty root.
        $emptyRoot = Join-Path (Get-JollyEphemeralRoot $AppRoot) (
            '_empty-' + [guid]::NewGuid().ToString('N')
        )
        New-Item -ItemType Directory -Force -Path $emptyRoot | Out-Null
        try {
            $oldPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            & robocopy $emptyRoot $Path /MIR /R:0 /W:0 /NFL /NDL /NJH /NJS /NP | Out-Null
            $mirrorCode = $LASTEXITCODE
            $ErrorActionPreference = $oldPreference
            if ($mirrorCode -gt 7) {
                throw "Long-path cleanup mirror failed with robocopy exit code $mirrorCode"
            }
            if (Test-Path -LiteralPath $Path) {
                Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            }
            return -not (Test-Path -LiteralPath $Path)
        }
        finally {
            $ErrorActionPreference = 'SilentlyContinue'
            Remove-Item -LiteralPath $emptyRoot -Recurse -Force -ErrorAction SilentlyContinue
            $ErrorActionPreference = 'Stop'
        }
    }
}

function Remove-JollyEphemeralLocalState {
    param(
        [Parameter(Mandatory=$true)]$State,
        [Parameter(Mandatory=$true)][string]$AppRoot
    )
    $root = [string]$State.root
    if (-not (Test-JollyEphemeralOwnedPath -Path $root -AppRoot $AppRoot)) { return $false }
    if (-not (Remove-JollyOwnedDirectoryTree -Path $root -AppRoot $AppRoot)) { return $false }
    $statePath = [string]$State.statePath
    if (-not [string]::IsNullOrWhiteSpace($statePath) -and (Test-Path -LiteralPath $statePath)) {
        Remove-Item -LiteralPath $statePath -Force -ErrorAction Stop
    }
    return $true
}

function Invoke-JollyEphemeralGc {
    param(
        [Parameter(Mandatory=$true)][string]$AppRoot,
        [datetime]$Now = ([datetime]::UtcNow),
        [switch]$DryRun,
        [switch]$SkipGitHub
    )
    $results = New-Object System.Collections.Generic.List[object]
    foreach ($state in @(Get-JollyEphemeralStates $AppRoot)) {
        $status = Get-JollyEphemeralStatus -State $state -Now $Now
        $action = 'retained_active'
        $detail = [string]$status.Summary
        if ([string]$status.Code -eq 'invalid_root') {
            $action = 'retained_invalid_root'
        }
        elseif ([string]$status.Code -eq 'finished') {
            if ($DryRun) {
                $action = 'would_clean_finished'
            }
            else {
                if (-not $SkipGitHub) {
                    $remove = Remove-JollyGitHubRunnerRegistration -Repository ([string]$state.repository) -RunnerName ([string]$state.runnerName)
                    if (-not $remove.Ok) {
                        $action = 'retained_api_error'
                        $detail = $remove.Error
                        [void]$results.Add([pscustomobject]@{StateId=$state.stateId;RunnerName=$state.runnerName;Action=$action;Detail=$detail})
                        continue
                    }
                }
                if (Remove-JollyEphemeralLocalState -State $state -AppRoot $AppRoot) { $action = 'cleaned_finished' }
                else { $action = 'retained_invalid_root' }
            }
        }
        elseif ([string]$status.Code -eq 'expired') {
            if ($SkipGitHub) {
                $action = if ($DryRun) { 'would_clean_expired' } else { 'retained_skip_github' }
            }
            else {
                $lookup = Find-JollyGitHubRunner -Repository ([string]$state.repository) -RunnerName ([string]$state.runnerName)
                if (-not $lookup.Ok) {
                    $action = 'retained_api_error'
                    $detail = $lookup.Error
                }
                elseif ($null -ne $lookup.Runner -and [bool]$lookup.Runner.busy) {
                    $action = 'retained_busy'
                    $detail = 'TTL expired but GitHub reports busy=true; no process was stopped'
                }
                elseif ($DryRun) {
                    $action = 'would_clean_expired'
                }
                else {
                    if ($null -ne $lookup.Runner) {
                        $remove = Remove-JollyGitHubRunnerRegistration -Repository ([string]$state.repository) -RunnerName ([string]$state.runnerName)
                        if (-not $remove.Ok) {
                            $action = 'retained_api_error'
                            $detail = $remove.Error
                            [void]$results.Add([pscustomobject]@{StateId=$state.stateId;RunnerName=$state.runnerName;Action=$action;Detail=$detail})
                            continue
                        }
                    }
                    if (-not (Stop-JollyEphemeralProcess -State $state -AppRoot $AppRoot)) {
                        $action = 'retained_unowned_process'
                        $detail = 'Tracked process did not match the owned ephemeral process contract'
                    }
                    elseif (Remove-JollyEphemeralLocalState -State $state -AppRoot $AppRoot) {
                        $action = 'cleaned_expired'
                    }
                }
            }
        }
        [void]$results.Add([pscustomobject]@{
            StateId=[string]$state.stateId
            RunnerName=[string]$state.runnerName
            Action=$action
            Detail=$detail
        })
    }
    return $results.ToArray()
}

function Get-JollyEphemeralSummary {
    param(
        [Parameter(Mandatory=$true)][string]$AppRoot,
        [Parameter(Mandatory=$true)][string]$ProfileId
    )
    $states = @(Get-JollyEphemeralStates $AppRoot | Where-Object { [string]$_.profileId -eq $ProfileId })
    if ($states.Count -eq 0) { return 'none' }
    $active = 0
    $expired = 0
    $finished = 0
    $minimumTtl = 9999
    foreach ($state in $states) {
        $status = Get-JollyEphemeralStatus $state
        switch ([string]$status.Code) {
            'active' { $active++; $minimumTtl = [math]::Min($minimumTtl,[int]$status.RemainingMinutes) }
            'expired' { $expired++ }
            'finished' { $finished++ }
            default {}
        }
    }
    $parts = New-Object System.Collections.Generic.List[string]
    if ($active -gt 0) { [void]$parts.Add(('{0} active / TTL {1}m' -f $active,$minimumTtl)) }
    if ($expired -gt 0) { [void]$parts.Add(('{0} expired' -f $expired)) }
    if ($finished -gt 0) { [void]$parts.Add(('{0} GC pending' -f $finished)) }
    return $parts -join ', '
}

function Start-JollyEphemeralRunner {
    param(
        [Parameter(Mandatory=$true)]$Profile,
        [Parameter(Mandatory=$true)][string]$AppRoot
    )
    if (-not (Test-JollyEphemeralEnabled $Profile)) { throw 'Ephemeral runner is disabled for this profile' }
    $sourceRoot = [Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot).TrimEnd('\')
    $capabilities = Get-JollyRunnerCapabilities -RunnerRoot $sourceRoot -CommandsOnly
    if (-not $capabilities.RunnerFiles) { throw "Runner template is not available: $sourceRoot" }
    if (-not $capabilities.Gh) { throw 'GitHub CLI (gh) is required to create an ephemeral runner' }

    $repository = Get-JollyProfileRepository $Profile
    $repoUrl = ([string]$Profile.repoUrl).TrimEnd('/')
    $ttlMinutes = Get-JollyEphemeralTtlMinutes $Profile
    $labels = @(Get-JollyEphemeralLabels $Profile)
    $safeProfile = ConvertTo-JollySafeName ([string]$Profile.id)
    $pathProfile = $safeProfile
    if ($pathProfile.Length -gt 12) { $pathProfile = $pathProfile.Substring(0,12) }
    $stamp = (Get-Date).ToUniversalTime().ToString('MMddHHmmss')
    $random = Get-Random -Minimum 1000 -Maximum 9999
    $stateId = "$pathProfile-$stamp-$random"
    $runnerName = "Jolly-$safeProfile-Ephemeral-$stamp-$random"
    $ephemeralRoot = Get-JollyEphemeralRoot $AppRoot
    $dest = Join-Path $ephemeralRoot $stateId
    $state = $null
    $launcher = $null
    $registrationCreated = $false
    $token = $null

    New-Item -ItemType Directory -Force -Path $ephemeralRoot | Out-Null
    if (Test-Path -LiteralPath $dest) { throw "Ephemeral runner directory already exists: $dest" }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null

    try {
        $ErrorActionPreference = 'Continue'
        & robocopy $sourceRoot $dest /E /XD _work _diag /XF .runner .runner_migrated .credentials .credentials_migrated .credentials_rsaparams .service | Out-Host
        $copyCode = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($copyCode -gt 7) { throw "Ephemeral runner copy failed with exit code $copyCode" }

        # A configured source runner can contain migration markers that make a
        # byte-for-byte copy look configured even when .runner itself is
        # excluded. Ephemeral clones must always begin from an unconfigured
        # local state before a fresh short-lived registration token is used.
        $configurationArtifacts = @(
            '.runner',
            '.runner_migrated',
            '.credentials',
            '.credentials_migrated',
            '.credentials_rsaparams',
            '.service'
        )
        foreach ($artifact in $configurationArtifacts) {
            Remove-Item -LiteralPath (Join-Path $dest $artifact) -Force -ErrorAction SilentlyContinue
        }
        $remainingConfiguration = @($configurationArtifacts | Where-Object {
            Test-Path -LiteralPath (Join-Path $dest $_)
        })
        if ($remainingConfiguration.Count -gt 0) {
            throw "Ephemeral runner copy still contains configured-runner metadata: $($remainingConfiguration -join ', ')"
        }

        $token = (& gh api --method POST "repos/$repository/actions/runners/registration-token" --jq .token).Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) { throw 'Could not mint GitHub runner registration token' }

        $configCmd = Join-Path $dest 'config.cmd'
        $configArgs = @('--unattended','--url',$repoUrl,'--token',$token,'--name',$runnerName,'--labels',($labels -join ','),'--work','_work','--ephemeral','--disableupdate')
        Push-Location $dest
        try {
            $ErrorActionPreference = 'Continue'
            & $configCmd @configArgs | Out-Host
            $configCode = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            if ($configCode -ne 0) { throw "Ephemeral runner config failed with exit code $configCode" }
            $registrationCreated = $true
        }
        finally { Pop-Location }
        $token = $null

        $hadTrackingId = Test-Path Env:\RUNNER_TRACKING_ID
        $oldTrackingId = $env:RUNNER_TRACKING_ID
        $env:RUNNER_TRACKING_ID = ''
        try {
            $launcher = Start-Process -FilePath (Join-Path $dest 'run.cmd') -WorkingDirectory $dest -WindowStyle Hidden -PassThru
        }
        finally {
            if ($hadTrackingId) { $env:RUNNER_TRACKING_ID = $oldTrackingId }
            else { Remove-Item Env:\RUNNER_TRACKING_ID -ErrorAction SilentlyContinue }
        }

        $createdAt = [datetime]::UtcNow
        $state = [pscustomobject][ordered]@{
            kind='ephemeral'
            stateId=$stateId
            profileId=[string]$Profile.id
            repository=$repository
            repoUrl=$repoUrl
            runnerName=$runnerName
            root=$dest
            processId=[int]$launcher.Id
            createdAt=$createdAt.ToString('o')
            expiresAt=$createdAt.AddMinutes($ttlMinutes).ToString('o')
            ttlMinutes=$ttlMinutes
            labels=$labels
        }
        [void](Write-JollyEphemeralState -AppRoot $AppRoot -State $state)

        $online = $false
        for ($i=0; $i -lt 15; $i++) {
            $lookup = Find-JollyGitHubRunner -Repository $repository -RunnerName $runnerName
            if ($lookup.Ok -and $null -ne $lookup.Runner -and [string]$lookup.Runner.status -eq 'online') { $online = $true; break }
            Start-Sleep -Seconds 2
        }
        if (-not $online) { throw 'Ephemeral runner started but online state was not confirmed; TTL/GC state was retained for recovery' }
        return $state
    }
    catch {
        $token = $null
        if ($null -eq $state) {
            if ($registrationCreated) { [void](Remove-JollyGitHubRunnerRegistration -Repository $repository -RunnerName $runnerName) }
            if ($null -ne $launcher) {
                try { Start-Process taskkill.exe -ArgumentList '/PID',[string]$launcher.Id,'/T','/F' -Wait -WindowStyle Hidden | Out-Null }
                catch {}
            }
            if (Test-JollyEphemeralOwnedPath -Path $dest -AppRoot $AppRoot) {
                Remove-Item -LiteralPath $dest -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        throw
    }
    finally { $token = $null }
}
