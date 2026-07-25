function ConvertFrom-JollyUtf8Base64 {
    param([Parameter(Mandatory=$true)][string]$Value)
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Value))
}

function Get-JollyRunnerConnectionState {
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
