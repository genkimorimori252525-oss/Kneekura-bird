function Get-JollyRunnerConnectionState {
    param(
        [Parameter(Mandatory=$true)][bool]$ProcessRunning,
        [string[]]$LogLines = @()
    )

    if (-not $ProcessRunning) {
        return [pscustomobject]@{
            Code = 'stopped'
            Text = '停止中'
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
                Text = '実行中（GitHub接続）'
                Tone = 'good'
                Evidence = $line.Trim()
            }
        }

        if ($line -match '(?i)Listening for Jobs') {
            return [pscustomobject]@{
                Code = 'listening'
                Text = '待機中（GitHub接続）'
                Tone = 'good'
                Evidence = $line.Trim()
            }
        }

        if ($line -match '(?i)(completed with result|job completed|finish job request)') {
            return [pscustomobject]@{
                Code = 'post_job'
                Text = '接続確認中'
                Tone = 'warn'
                Evidence = $line.Trim()
            }
        }

        if ($line -match '(?i)(failed to create a session|runner connect error|session for this runner already exists|disconnected from the server|connection.*(?:failed|timed out|refused|reset)|http request timed out|name resolution|no such host|shutdown signal|runner listener exit)') {
            return [pscustomobject]@{
                Code = 'reconnecting'
                Text = '再接続中'
                Tone = 'warn'
                Evidence = $line.Trim()
            }
        }

        if ($line -match '(?i)(Connected to GitHub|session.*established|message queue listen loop started)') {
            return [pscustomobject]@{
                Code = 'connected_starting'
                Text = '接続中（待機準備）'
                Tone = 'good'
                Evidence = $line.Trim()
            }
        }
    }

    return [pscustomobject]@{
        Code = 'starting'
        Text = '起動中（接続確認待ち）'
        Tone = 'warn'
        Evidence = 'Runner process exists but no GitHub connection marker was found'
    }
}
