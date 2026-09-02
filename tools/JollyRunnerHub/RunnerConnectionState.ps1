function ConvertFrom-JollyUtf8Base64 {
    param([Parameter(Mandatory=$true)][string]$Value)
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Value))
}

function Get-JollyRunnerConnectionState {
    param(
        [Parameter(Mandatory=$true)][bool]$ProcessRunning,
        [string[]]$LogLines = @(),
        [datetime]$LogUpdatedAtUtc = [datetime]::MinValue,
        [datetime]$NowUtc = [datetime]::MinValue,
        [ValidateSet('online','busy','offline','unknown')][string]$GitHubStatus = 'unknown',
        [int]$StaleAfterSeconds = 120,
        [bool]$DiagnosticsReadable = $true
    )
    $now = if ($NowUtc -ne [datetime]::MinValue) { $NowUtc.ToUniversalTime() } else { [datetime]::UtcNow }
    $logAgeSeconds = $null
    $freshness = if (-not $DiagnosticsReadable) { 'unreadable' } else { 'unknown' }
    if ($LogUpdatedAtUtc -ne [datetime]::MinValue) {
        $logAgeSeconds = [math]::Max(0, [int][math]::Floor(($now - $LogUpdatedAtUtc.ToUniversalTime()).TotalSeconds))
        $freshness = if ($logAgeSeconds -le [math]::Max(1,$StaleAfterSeconds)) { 'fresh' } else { 'stale' }
    }
    $state = Get-JollyRunnerConnectionStateLegacy -ProcessRunning $ProcessRunning -LogLines $LogLines
    if ($state.Code -eq 'stopped') { $state.Code = 'stopped' }
    if (-not $ProcessRunning) { $state.Evidence = 'process=stopped; github=' + $GitHubStatus }
    elseif (-not $DiagnosticsReadable) {
        $state = [pscustomobject]@{Code='diagnostics_unreadable';Text=(ConvertFrom-JollyUtf8Base64 '6Ki65pat44Ot44Kw44KS5YaN6Kqt6L685Lit');Tone='warn';Evidence='process=alive; diagnostics=unreadable; retry=scheduled'}
    }
    elseif ($GitHubStatus -eq 'busy') {
        $state = [pscustomobject]@{Code='running_job';Text=(ConvertFrom-JollyUtf8Base64 '44K444On44OW5a6f6KGM5Lit77yIR2l0SHVi56K66KqN5riI44G/77yJ');Tone='good';Evidence='process=alive; github=busy'}
    }
    elseif ($GitHubStatus -eq 'online') {
        $state = [pscustomobject]@{Code='listening';Text=(ConvertFrom-JollyUtf8Base64 'R2l0SHViIOW+heapn+S4re+8iEdpdEh1Yueiuuiqjea4iOOBv++8iQ==');Tone='good';Evidence='process=alive; github=online'}
    }
    elseif ($freshness -eq 'stale' -and $state.Code -eq 'reconnecting') {
        $state = [pscustomobject]@{Code='stale_diagnostics';Text=(ConvertFrom-JollyUtf8Base64 '6Ki65pat44Ot44Kw44GM5Y+k44GE44Gf44KB5o6l57aa44KS5YaN56K66KqN5Lit');Tone='warn';Evidence=('process=alive; diagnostics=stale ({0}s); github={1}' -f $logAgeSeconds,$GitHubStatus)}
    }
    elseif ($freshness -eq 'stale' -and $state.Code -eq 'starting') {
        $state.Code = 'stale_diagnostics'
        $state.Text = ConvertFrom-JollyUtf8Base64 '6Ki65pat44Ot44Kw44GM5Y+k44GE44Gf44KB5o6l57aa44KS5YaN56K66KqN5Lit'
        $state.Evidence = ('process=alive; diagnostics=stale ({0}s); github={1}' -f $logAgeSeconds,$GitHubStatus)
    }
    $state | Add-Member -NotePropertyName ProcessRunning -NotePropertyValue ([bool]$ProcessRunning) -Force
    $state | Add-Member -NotePropertyName DiagnosticsFreshness -NotePropertyValue $freshness -Force
    $state | Add-Member -NotePropertyName LogAgeSeconds -NotePropertyValue $logAgeSeconds -Force
    $state | Add-Member -NotePropertyName GitHubStatus -NotePropertyValue $GitHubStatus -Force
    return $state
}

function Get-JollyRunnerConnectionStateLegacy {
    param(
        [Parameter(Mandatory=$true)][bool]$ProcessRunning,
        [string[]]$LogLines = @()
    )

    if (-not $ProcessRunning) {
        return [pscustomobject]@{
            Code = 'stopped'
            Text = ConvertFrom-JollyUtf8Base64 '5YGc5q2i5Lit'
            Tone = 'bad'
            Evidence = 'Runner.Listener.exe not found'
        }
    }

    for ($index = @($LogLines).Count - 1; $index -ge 0; $index--) {
        $line = [string]$LogLines[$index]
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        if ($line -match '(?i)Running job:') {
            return [pscustomobject]@{
                Code = 'running_job'
                Text = ConvertFrom-JollyUtf8Base64 '5a6f6KGM5Lit77yIR2l0SHVi5o6l57aa77yJ'
                Tone = 'good'
                Evidence = $line.Trim()
            }
        }

        if ($line -match '(?i)Listening for Jobs') {
            return [pscustomobject]@{
                Code = 'listening'
                Text = ConvertFrom-JollyUtf8Base64 '5b6F5qmf5Lit77yIR2l0SHVi5o6l57aa77yJ'
                Tone = 'good'
                Evidence = $line.Trim()
            }
        }

        if ($line -match '(?i)(completed with result|job completed|finish job request)') {
            return [pscustomobject]@{
                Code = 'post_job'
                Text = ConvertFrom-JollyUtf8Base64 '5o6l57aa56K66KqN5Lit'
                Tone = 'warn'
                Evidence = $line.Trim()
            }
        }

        if ($line -match '(?i)(failed to create a session|runner connect error|session for this runner already exists|disconnected from the server|connection.*(?:failed|timed out|refused|reset)|http request timed out|name resolution|no such host|shutdown signal|runner listener exit)') {
            return [pscustomobject]@{
                Code = 'reconnecting'
                Text = ConvertFrom-JollyUtf8Base64 '5YaN5o6l57aa5Lit'
                Tone = 'warn'
                Evidence = $line.Trim()
            }
        }

        if ($line -match '(?i)(Connected to GitHub|session.*established|message queue listen loop started)') {
            return [pscustomobject]@{
                Code = 'connected_starting'
                Text = ConvertFrom-JollyUtf8Base64 '5o6l57aa5Lit77yI5b6F5qmf5rqW5YKZ77yJ'
                Tone = 'good'
                Evidence = $line.Trim()
            }
        }
    }

    return [pscustomobject]@{
        Code = 'starting'
        Text = ConvertFrom-JollyUtf8Base64 '6LW35YuV5Lit77yI5o6l57aa56K66KqN5b6F44Gh77yJ'
        Tone = 'warn'
        Evidence = 'Runner process exists but no GitHub connection marker was found'
    }
}
