param(
    [string]$WorkspaceRoot = 'C:\actions-runner\_work\warfare_wings-1.1.4-1.20.1-forge\warfare_wings-1.1.4-1.20.1-forge',
    [int]$RefreshSeconds = 2,
    [string]$OutputPath = 'C:\actions-runner\ww-live-telemetry.html',
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Encode-Html([object]$Value) {
    return [System.Net.WebUtility]::HtmlEncode([string]$Value)
}

function Read-JsonTail([string]$Path, [int]$Tail = 1200) {
    $rows = [System.Collections.Generic.List[object]]::new()
    if (-not (Test-Path $Path)) { return $rows }
    foreach ($line in Get-Content -LiteralPath $Path -Tail $Tail -ErrorAction SilentlyContinue) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try { $rows.Add(($line | ConvertFrom-Json -Depth 30)) } catch { }
    }
    return $rows
}

function Reason-Value([string]$Reason, [string]$Name) {
    if ($Reason -match "(?:^|:)$([regex]::Escape($Name))=([^:]+)") { return $Matches[1] }
    return ''
}

function Latest-RunDirectory {
    $base = Join-Path $WorkspaceRoot 'ww-debug-benchmark\run-gametest\world\wwdebug\autopilot'
    if (-not (Test-Path $base)) { return $null }
    return Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName 'aircraft') } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Render-Waiting([string]$Message) {
    $html = @"
<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta http-equiv="refresh" content="$RefreshSeconds">
<title>Warfare Wings Live Telemetry</title><style>
body{font-family:Segoe UI,sans-serif;background:#10151d;color:#e7edf5;margin:24px}.box{background:#18212d;padding:22px;border-radius:14px}small{color:#9fb0c4}
</style></head><body><div class="box"><h1>Warfare Wings Live Telemetry</h1><p>$(Encode-Html $Message)</p><small>2秒ごとに自動更新</small></div></body></html>
"@
    $directory = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temp = "$OutputPath.tmp"
    Set-Content -LiteralPath $temp -Value $html -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $OutputPath -Force
}

$browserOpened = $false
while ($true) {
    try {
        $runDir = Latest-RunDirectory
        if ($null -eq $runDir) {
            Render-Waiting '最新のJavaテレメトリを待っています。GameTestが始まると自動表示します。'
            Start-Sleep -Seconds $RefreshSeconds
            continue
        }

        $aircraftFiles = Get-ChildItem -LiteralPath (Join-Path $runDir.FullName 'aircraft') -Filter '*.jsonl' -File -ErrorAction SilentlyContinue
        if (-not $aircraftFiles) {
            Render-Waiting '機体別JSONLの作成を待っています。'
            Start-Sleep -Seconds $RefreshSeconds
            continue
        }

        $cards = [System.Collections.Generic.List[string]]::new()
        $consoleRows = [System.Collections.Generic.List[object]]::new()
        $allEvents = [System.Collections.Generic.List[object]]::new()
        $latestSeparation = ''

        foreach ($file in $aircraftFiles) {
            $rows = Read-JsonTail $file.FullName
            $frame = $rows | Where-Object { $_.event -eq 'frame' } | Select-Object -Last 1
            $event = $rows | Where-Object { $_.event -ne 'frame' } | Select-Object -Last 1
            $coupled = $rows | Where-Object { [string]$_.event -like 'energy_coupled*' } | Select-Object -Last 1
            $mutual = $rows | Where-Object { $_.event -eq 'mutual_dogfight_validation_status' } | Select-Object -Last 1
            if ($mutual) { $latestSeparation = Reason-Value ([string]$mutual.reason) 'separation' }
            foreach ($row in ($rows | Where-Object { $_.event -ne 'frame' } | Select-Object -Last 12)) {
                $allEvents.Add([pscustomobject]@{ Tick=$row.server_tick; Aircraft=$row.aircraft_entity_id; Event=$row.event; Reason=$row.reason })
            }
            if (-not $frame) { continue }

            $reason = if ($coupled) { [string]$coupled.reason } elseif ($event) { [string]$event.reason } else { '' }
            $stage = Reason-Value $reason 'stage'
            $rawAngle = Reason-Value $reason 'raw_target_angle'
            $leadAngle = Reason-Value $reason 'predicted_lead_angle'
            $closure = Reason-Value $reason 'closure'
            $bestError = Reason-Value $reason 'best_capture_horizontal_error'
            $position = $frame.position
            $name = [string]$frame.aircraft_name
            $entity = [string]$frame.aircraft_entity_id
            $latestEventName = if ($event) { [string]$event.event } else { 'frame' }
            $latestEventReason = if ($event) { [string]$event.reason } else { [string]$frame.action_reason }

            $consoleRows.Add([pscustomobject]@{
                Aircraft = $entity
                Tick = $frame.server_tick
                Phase = $frame.phase
                Stage = $stage
                Speed = ('{0:N1}' -f [double]$frame.speed_bps)
                AGL = ('{0:N1}' -f [double]$frame.altitude_above_ground)
                Pitch = ('{0:N1}' -f [double]$frame.pitch_deg)
                Yaw = ('{0:N1}' -f [double]$frame.yaw_deg)
                Event = $latestEventName
            })

            $cards.Add(@"
<section class="card"><h2>$(Encode-Html $name)</h2>
<div class="grid">
<div><b>Tick</b><span>$(Encode-Html $frame.server_tick)</span></div><div><b>Phase</b><span>$(Encode-Html $frame.phase)</span></div>
<div><b>Coupled stage</b><span>$(Encode-Html $(if($stage){$stage}else{'—'}))</span></div><div><b>Speed</b><span>$('{0:N2}' -f [double]$frame.speed_bps) BPS</span></div>
<div><b>AGL</b><span>$('{0:N2}' -f [double]$frame.altitude_above_ground)</span></div><div><b>Position</b><span>$('{0:N1}, {1:N1}, {2:N1}' -f [double]$position.x,[double]$position.y,[double]$position.z)</span></div>
<div><b>Pitch / Yaw / Roll</b><span>$('{0:N1} / {1:N1} / {2:N1}' -f [double]$frame.pitch_deg,[double]$frame.yaw_deg,[double]$frame.roll_deg)</span></div>
<div><b>Control X / Z</b><span>$('{0:N2} / {1:N2}' -f [double]$frame.control_x_logical,[double]$frame.control_z)</span></div>
<div><b>Raw / Lead angle</b><span>$(Encode-Html $(if($rawAngle){"$rawAngle / $leadAngle"}else{'—'}))</span></div>
<div><b>Closure</b><span>$(Encode-Html $(if($closure){$closure}else{'—'}))</span></div>
<div><b>Best capture error</b><span>$(Encode-Html $(if($bestError){$bestError}else{'—'}))</span></div>
<div><b>Safety</b><span>stall=$(Encode-Html $frame.stall_risk), terrain=$(Encode-Html $frame.terrain_risk), ground=$(Encode-Html $frame.on_ground)</span></div>
</div><h3>直近イベント</h3><code>$(Encode-Html $latestEventName)</code><pre>$(Encode-Html $latestEventReason)</pre></section>
"@)
        }

        $eventRows = ($allEvents | Sort-Object Tick -Descending | Select-Object -First 20 | ForEach-Object {
            "<tr><td>$(Encode-Html $_.Tick)</td><td>$(Encode-Html $_.Aircraft)</td><td>$(Encode-Html $_.Event)</td><td><code>$(Encode-Html $_.Reason)</code></td></tr>"
        }) -join "`n"

        $html = @"
<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta http-equiv="refresh" content="$RefreshSeconds">
<title>Warfare Wings Live Telemetry</title><style>
body{font-family:Segoe UI,sans-serif;background:#0d131b;color:#e8eef6;margin:20px}header{display:flex;justify-content:space-between;align-items:end}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:16px}.card,.events{background:#17212d;border:1px solid #2a394a;border-radius:14px;padding:18px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.grid div{background:#101923;padding:9px;border-radius:8px}.grid b{display:block;color:#8fb5dc;font-size:12px}.grid span{font-size:17px}pre{white-space:pre-wrap;word-break:break-word;color:#c8d7e8}table{width:100%;border-collapse:collapse}td,th{padding:7px;border-bottom:1px solid #29384a;text-align:left;vertical-align:top}code{color:#b9d7ff}.good{color:#80d69d}.warn{color:#ffd27a}small{color:#94a7bb}
</style></head><body><header><div><h1>Warfare Wings Live Telemetry</h1><p>Run: $(Encode-Html $runDir.Name)　最新 separation: <b>$(Encode-Html $(if($latestSeparation){$latestSeparation}else{'—'}))</b></p></div><small>更新: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') / $RefreshSeconds 秒ごと</small></header>
<div class="cards">$($cards -join "`n")</div><section class="events"><h2>最新イベント</h2><table><thead><tr><th>Tick</th><th>Aircraft</th><th>Event</th><th>Reason</th></tr></thead><tbody>$eventRows</tbody></table></section></body></html>
"@
        $directory = Split-Path -Parent $OutputPath
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
        $temp = "$OutputPath.tmp"
        Set-Content -LiteralPath $temp -Value $html -Encoding UTF8
        Move-Item -LiteralPath $temp -Destination $OutputPath -Force

        Clear-Host
        Write-Host "Warfare Wings live telemetry: $($runDir.Name)" -ForegroundColor Cyan
        Write-Host "Browser dashboard: $OutputPath | refresh ${RefreshSeconds}s | separation=$latestSeparation"
        $consoleRows | Format-Table -AutoSize

        if (-not $browserOpened -and -not $NoBrowser) {
            Start-Process $OutputPath
            $browserOpened = $true
        }
    }
    catch {
        Render-Waiting "テレメトリ読込中: $($_.Exception.Message)"
        Write-Warning $_.Exception.Message
    }
    Start-Sleep -Seconds $RefreshSeconds
}
