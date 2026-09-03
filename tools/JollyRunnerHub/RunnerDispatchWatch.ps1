Set-StrictMode -Version Latest

function ConvertTo-JollyDispatchLabelSet {
    param([string[]]$Labels = @())
    $set = @{}
    foreach ($raw in @($Labels)) {
        $label = [string]$raw
        if ([string]::IsNullOrWhiteSpace($label)) { continue }
        $set[$label.ToLowerInvariant()] = $true
    }
    return $set
}

function Test-JollyDispatchLabelsEligible {
    param(
        [string[]]$RequiredLabels = @(),
        [string[]]$RunnerLabels = @()
    )
    $available = ConvertTo-JollyDispatchLabelSet $RunnerLabels
    foreach ($raw in @($RequiredLabels)) {
        $label = [string]$raw
        if ([string]::IsNullOrWhiteSpace($label)) { continue }
        if (-not $available.ContainsKey($label.ToLowerInvariant())) { return $false }
    }
    return $true
}

function Get-JollyDispatchProfileInt {
    param(
        [Parameter(Mandatory=$true)]$Profile,
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][int]$Default,
        [Parameter(Mandatory=$true)][int]$Minimum,
        [Parameter(Mandatory=$true)][int]$Maximum
    )
    $value = $Default
    $property = $Profile.PSObject.Properties[$Name]
    if ($null -ne $property) {
        $parsed = 0
        if ([int]::TryParse([string]$property.Value,[ref]$parsed)) { $value = $parsed }
    }
    return [math]::Min($Maximum,[math]::Max($Minimum,$value))
}

function Test-JollyDispatchWatchEnabled {
    param([Parameter(Mandatory=$true)]$Profile)
    $property = $Profile.PSObject.Properties['dispatchWatchEnabled']
    if ($null -eq $property) { return $true }
    return [bool]$property.Value
}

function Test-JollyDispatchAutoRecoverEnabled {
    param([Parameter(Mandatory=$true)]$Profile)
    $property = $Profile.PSObject.Properties['dispatchAutoRecover']
    if ($null -eq $property) { return $true }
    return [bool]$property.Value
}

function Get-JollyDispatchWarnSeconds {
    param([Parameter(Mandatory=$true)]$Profile)
    return Get-JollyDispatchProfileInt -Profile $Profile -Name 'dispatchWarnSeconds' -Default 45 -Minimum 15 -Maximum 900
}

function Get-JollyDispatchRecoverSeconds {
    param([Parameter(Mandatory=$true)]$Profile)
    $warn = Get-JollyDispatchWarnSeconds $Profile
    $minimum = [math]::Max(60,$warn + 30)
    return Get-JollyDispatchProfileInt -Profile $Profile -Name 'dispatchRecoverSeconds' -Default 180 -Minimum $minimum -Maximum 1800
}

function Get-JollyDispatchProbeMaxAgeSeconds {
    param([Parameter(Mandatory=$true)]$Profile)
    return Get-JollyDispatchProfileInt -Profile $Profile -Name 'dispatchProbeMaxAgeSeconds' -Default 45 -Minimum 15 -Maximum 300
}

function Get-JollyDispatchRoutingLabels {
    param([Parameter(Mandatory=$true)]$Profile)
    $property = $Profile.PSObject.Properties['routingLabels']
    if ($null -eq $property) { return @() }
    $labels = @()
    foreach ($raw in @($property.Value)) {
        $label = [string]$raw
        if (-not [string]::IsNullOrWhiteSpace($label)) { $labels += $label }
    }
    return $labels
}

function Get-JollyDispatchClassification {
    param(
        [Parameter(Mandatory=$true)][string]$LocalCode,
        $Probe,
        [Parameter(Mandatory=$true)][int]$WarnSeconds,
        [Parameter(Mandatory=$true)][int]$RecoverSeconds,
        [int]$ProbeAgeSeconds = 0
    )

    if ($null -eq $Probe) {
        return [pscustomobject]@{
            Code='probe_pending'; Text='診断待ち'; Tone='warn'; CanRecover=$false
            Evidence='dispatch probe has not completed yet'
        }
    }

    if ($ProbeAgeSeconds -gt 120) {
        return [pscustomobject]@{
            Code='probe_stale'; Text='配送診断が古い'; Tone='warn'; CanRecover=$false
            Evidence=('dispatch probe stale age={0}s' -f $ProbeAgeSeconds)
        }
    }

    if (-not [bool]$Probe.apiOk) {
        return [pscustomobject]@{
            Code='api_error'; Text='GitHub診断失敗'; Tone='warn'; CanRecover=$false
            Evidence=('dispatch API error: {0}' -f [string]$Probe.error)
        }
    }

    $routeCandidateCount = 0
    [void][int]::TryParse([string]$Probe.routeCandidateCount,[ref]$routeCandidateCount)
    if ($routeCandidateCount -gt 1) {
        return [pscustomobject]@{
            Code='route_duplicate'; Text='配送先が重複'; Tone='bad'; CanRecover=$false
            Evidence=('multiple non-ephemeral runners match routing labels: {0}' -f $routeCandidateCount)
        }
    }

    if (-not [bool]$Probe.runnerFound) {
        return [pscustomobject]@{
            Code='registration_missing'; Text='GitHub登録なし'; Tone='bad'; CanRecover=$false
            Evidence='configured local runner name was not found in repository runner registrations'
        }
    }

    $githubStatus = [string]$Probe.runnerStatus
    $busy = [bool]$Probe.runnerBusy
    $eligible = 0
    [void][int]::TryParse([string]$Probe.eligibleQueuedCount,[ref]$eligible)
    $assigned = 0
    [void][int]::TryParse([string]$Probe.assignedQueuedCount,[ref]$assigned)
    $oldest = 0
    [void][int]::TryParse([string]$Probe.oldestQueuedSeconds,[ref]$oldest)

    if ($busy -or $LocalCode -eq 'running_job') {
        return [pscustomobject]@{
            Code='running'; Text='ジョブ実行中'; Tone='good'; CanRecover=$false
            Evidence=('github busy={0}; local={1}' -f $busy,$LocalCode)
        }
    }

    if ($githubStatus -eq 'offline') {
        return [pscustomobject]@{
            Code='github_offline'; Text='GitHub側オフライン'; Tone='bad'; CanRecover=$false
            Evidence=('runner registration is offline; eligibleQueued={0}' -f $eligible)
        }
    }

    $locallyReady = $LocalCode -in @('listening','connected_starting','post_job')
    if ($githubStatus -eq 'online' -and -not $locallyReady) {
        return [pscustomobject]@{
            Code='ghost_online'; Text='Ghost online疑い'; Tone='bad'; CanRecover=($eligible -gt 0 -and $oldest -ge $RecoverSeconds)
            Evidence=('GitHub=online but local state={0}; eligibleQueued={1}; oldest={2}s' -f $LocalCode,$eligible,$oldest)
        }
    }

    if ($eligible -le 0) {
        if ($locallyReady -and $githubStatus -eq 'online') {
            return [pscustomobject]@{
                Code='ready'; Text='配送待機OK'; Tone='good'; CanRecover=$false
                Evidence='GitHub online + local listener ready + no eligible queued job'
            }
        }
        return [pscustomobject]@{
            Code='idle_unknown'; Text='待機状態確認中'; Tone='warn'; CanRecover=$false
            Evidence=('github={0}; local={1}; eligibleQueued=0' -f $githubStatus,$LocalCode)
        }
    }

    if ($assigned -gt 0) {
        return [pscustomobject]@{
            Code='assigned'; Text='Runnerへ配送済み'; Tone='good'; CanRecover=$false
            Evidence=('eligibleQueued={0}; assignedQueued={1}; oldest={2}s' -f $eligible,$assigned,$oldest)
        }
    }

    if ($oldest -ge $RecoverSeconds -and $locallyReady -and $githubStatus -eq 'online') {
        return [pscustomobject]@{
            Code='dispatch_stalled'; Text=('配送停止? {0}s' -f $oldest); Tone='bad'; CanRecover=$true
            Evidence=('eligible queued job remains unassigned; runner online/busy=false/local ready; oldest={0}s' -f $oldest)
        }
    }

    if ($oldest -ge $WarnSeconds) {
        return [pscustomobject]@{
            Code='dispatch_slow'; Text=('配送遅延 {0}s' -f $oldest); Tone='warn'; CanRecover=$false
            Evidence=('eligible queued jobs waiting unassigned; count={0}; oldest={1}s' -f $eligible,$oldest)
        }
    }

    return [pscustomobject]@{
        Code='queue_waiting'; Text=('配送待ち {0}s' -f $oldest); Tone='warn'; CanRecover=$false
        Evidence=('eligible queued jobs waiting normally; count={0}; oldest={1}s' -f $eligible,$oldest)
    }
}

function Invoke-JollyGhApiJson {
    param(
        [Parameter(Mandatory=$true)][string]$Route,
        [ValidateRange(1,30)][int]$TimeoutSeconds = 5
    )
    $gh = Get-Command gh.exe -ErrorAction SilentlyContinue
    if ($null -eq $gh) { $gh = Get-Command gh -ErrorAction SilentlyContinue }
    if ($null -eq $gh) {
        return [pscustomobject]@{Ok=$false;Payload=$null;Error='gh unavailable';TimedOut=$false}
    }

    $base = Join-Path ([IO.Path]::GetTempPath()) ('JollyRunnerHub-gh-' + [guid]::NewGuid().ToString('N'))
    $stdout = $base + '.out'
    $stderr = $base + '.err'
    $process = $null
    try {
        $process = Start-Process -FilePath $gh.Source -ArgumentList @('api','--method','GET',$Route) `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { Start-Process taskkill.exe -ArgumentList '/PID',[string]$process.Id,'/T','/F' -Wait -WindowStyle Hidden | Out-Null } catch {}
            return [pscustomobject]@{Ok=$false;Payload=$null;Error=('gh timeout after {0}s' -f $TimeoutSeconds);TimedOut=$true}
        }
        $outText = if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout -Raw -Encoding UTF8 } else { '' }
        $errText = if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Raw -Encoding UTF8 } else { '' }
        if ($process.ExitCode -ne 0) {
            if ($errText.Length -gt 800) { $errText = $errText.Substring(0,800) }
            return [pscustomobject]@{Ok=$false;Payload=$null;Error=('gh exit={0}: {1}' -f $process.ExitCode,$errText.Trim());TimedOut=$false}
        }
        if ([string]::IsNullOrWhiteSpace($outText)) {
            return [pscustomobject]@{Ok=$false;Payload=$null;Error='gh returned empty response';TimedOut=$false}
        }
        return [pscustomobject]@{Ok=$true;Payload=($outText | ConvertFrom-Json);Error='';TimedOut=$false}
    }
    catch {
        return [pscustomobject]@{Ok=$false;Payload=$null;Error=$_.Exception.Message;TimedOut=$false}
    }
    finally {
        Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
    }
}

function Get-JollyDispatchProbe {
    param(
        [Parameter(Mandatory=$true)][string]$Repository,
        [Parameter(Mandatory=$true)][string]$RunnerName,
        [string[]]$RoutingLabels = @(),
        [ValidateRange(1,30)][int]$TimeoutSeconds = 5,
        [ValidateRange(1,20)][int]$MaxQueuedRuns = 6,
        [datetime]$NowUtc = ([datetime]::UtcNow)
    )

    $started = [datetime]::UtcNow
    $result = [ordered]@{
        schema = 'jolly.dispatch-probe'
        version = 1
        repository = $Repository
        runnerName = $RunnerName
        routingLabels = @($RoutingLabels)
        apiOk = $false
        error = ''
        runnerFound = $false
        runnerId = 0
        runnerStatus = 'unknown'
        runnerBusy = $false
        runnerLabels = @()
        exactNameCount = 0
        routeCandidateCount = 0
        eligibleQueuedCount = 0
        assignedQueuedCount = 0
        oldestQueuedSeconds = 0
        oldestRunId = 0
        oldestJobName = ''
        probedAt = ''
        durationMs = 0
    }

    $runnerQuery = Invoke-JollyGhApiJson -Route ("repos/{0}/actions/runners?per_page=100" -f $Repository) -TimeoutSeconds $TimeoutSeconds
    if (-not $runnerQuery.Ok) {
        $result.error = $runnerQuery.Error
        $result.probedAt = ([datetime]::UtcNow).ToString('o')
        $result.durationMs = [int]([datetime]::UtcNow-$started).TotalMilliseconds
        return [pscustomobject]$result
    }

    $runners = @($runnerQuery.Payload.runners)
    $matches = @($runners | Where-Object { [string]$_.name -eq $RunnerName })
    $result.exactNameCount = $matches.Count

    $routeCandidates = 0
    if (@($RoutingLabels).Count -gt 0) {
        foreach ($candidate in $runners) {
            $candidateLabels = @($candidate.labels | ForEach-Object { [string]$_.name })
            $ephemeral = $candidateLabels -contains 'jolly-ephemeral'
            if (-not $ephemeral -and (Test-JollyDispatchLabelsEligible -RequiredLabels $RoutingLabels -RunnerLabels $candidateLabels)) {
                $routeCandidates++
            }
        }
    }
    $result.routeCandidateCount = $routeCandidates

    if ($matches.Count -gt 0) {
        $runner = $matches[0]
        $result.runnerFound = $true
        $result.runnerId = [int]$runner.id
        $result.runnerStatus = [string]$runner.status
        $result.runnerBusy = [bool]$runner.busy
        $result.runnerLabels = @($runner.labels | ForEach-Object { [string]$_.name })
    }

    $runQuery = Invoke-JollyGhApiJson -Route ("repos/{0}/actions/runs?status=queued&per_page=20" -f $Repository) -TimeoutSeconds $TimeoutSeconds
    if (-not $runQuery.Ok) {
        $result.error = $runQuery.Error
        $result.probedAt = ([datetime]::UtcNow).ToString('o')
        $result.durationMs = [int]([datetime]::UtcNow-$started).TotalMilliseconds
        return [pscustomobject]$result
    }

    $runs = @($runQuery.Payload.workflow_runs | Select-Object -First $MaxQueuedRuns)
    foreach ($run in $runs) {
        $runId = [int64]$run.id
        $jobQuery = Invoke-JollyGhApiJson -Route ("repos/{0}/actions/runs/{1}/jobs?filter=latest&per_page=100" -f $Repository,$runId) -TimeoutSeconds $TimeoutSeconds
        if (-not $jobQuery.Ok) { continue }

        $created = [datetime]::MinValue
        [void][datetime]::TryParse([string]$run.created_at,[ref]$created)
        $age = if ($created -ne [datetime]::MinValue) {
            [math]::Max(0,[int][math]::Floor(($NowUtc.ToUniversalTime()-$created.ToUniversalTime()).TotalSeconds))
        } else { 0 }

        foreach ($job in @($jobQuery.Payload.jobs)) {
            if ([string]$job.status -ne 'queued') { continue }
            $jobLabels = @($job.labels | ForEach-Object { [string]$_ })
            $eligible = $false
            if ($result.runnerFound) {
                $eligible = Test-JollyDispatchLabelsEligible -RequiredLabels $jobLabels -RunnerLabels @($result.runnerLabels)
            } elseif (@($RoutingLabels).Count -gt 0) {
                $eligible = Test-JollyDispatchLabelsEligible -RequiredLabels $jobLabels -RunnerLabels @($RoutingLabels)
            }
            if (-not $eligible) { continue }

            $result.eligibleQueuedCount++
            if ($age -gt $result.oldestQueuedSeconds) {
                $result.oldestQueuedSeconds = $age
                $result.oldestRunId = $runId
                $result.oldestJobName = [string]$job.name
            }

            $jobRunnerId = 0
            [void][int]::TryParse([string]$job.runner_id,[ref]$jobRunnerId)
            if (($result.runnerId -gt 0 -and $jobRunnerId -eq $result.runnerId) -or
                ([string]$job.runner_name -eq $RunnerName -and -not [string]::IsNullOrWhiteSpace([string]$job.runner_name))) {
                $result.assignedQueuedCount++
            }
        }
    }

    $result.apiOk = $true
    $result.probedAt = ([datetime]::UtcNow).ToString('o')
    $result.durationMs = [int]([datetime]::UtcNow-$started).TotalMilliseconds
    return [pscustomobject]$result
}
