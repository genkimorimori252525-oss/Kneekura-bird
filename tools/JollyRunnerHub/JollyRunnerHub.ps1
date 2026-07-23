#requires -version 5.1
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$AppRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'JollyRunnerHub'
$ConfigPath = Join-Path $AppRoot 'profiles.json'
$DefaultConfigPath = Join-Path $AppRoot 'profiles.default.json'
$IconPath = Join-Path $AppRoot 'JollyRunnerHub.ico'
$script:Config = $null
$script:Profile = $null
$script:LastConfigWrite = [datetime]::MinValue
$script:RunnerCache = $false
$script:RunnerCacheAt = [datetime]::MinValue

function Show-Error([string]$Text) {
    [System.Windows.Forms.MessageBox]::Show(
        $Text, 'ジョリー Runner Hub',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
}

function Load-Config {
    New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        Copy-Item -LiteralPath $DefaultConfigPath -Destination $ConfigPath -Force
    }
    $script:Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $script:Config.profiles -or @($script:Config.profiles).Count -eq 0) {
        throw 'profiles.json にprofilesがありません。'
    }
    $script:LastConfigWrite = (Get-Item -LiteralPath $ConfigPath).LastWriteTimeUtc
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
        $Path,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::ReadWrite)
    try {
        $start = [math]::Max(0,$stream.Length-$Bytes)
        [void]$stream.Seek($start,[System.IO.SeekOrigin]::Begin)
        $reader = New-Object System.IO.StreamReader($stream,[Text.Encoding]::UTF8,$true,4096,$true)
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

function Json-Tail([string]$Path) {
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($line in (Tail-Lines $Path)) {
        try { $rows.Add(($line | ConvertFrom-Json)) } catch {}
    }
    return $rows
}

function Format-Metric($Value,$Metric) {
    if ($null -eq $Value -or [string]$Value -eq '') {
        $d = $Metric.PSObject.Properties['default']
        if ($null -ne $d) { return $d.Value }
        return 0
    }
    $f = $Metric.PSObject.Properties['format']
    if ($null -ne $f -and -not [string]::IsNullOrWhiteSpace([string]$f.Value)) {
        $n = 0.0
        if ([double]::TryParse([string]$Value,[Globalization.NumberStyles]::Any,
            [Globalization.CultureInfo]::InvariantCulture,[ref]$n)) {
            return $n.ToString([string]$f.Value,[Globalization.CultureInfo]::InvariantCulture)
        }
    }
    return $Value
}

function Idle-Snapshot($Profile) {
    $aircraft = New-Object System.Collections.Generic.List[object]
    $names = @($Profile.expectedAircraft)
    if ($names.Count -eq 0) { $names = @('Aircraft') }
    foreach ($name in $names) {
        $values = [ordered]@{}
        foreach ($metric in @($Profile.metrics)) {
            $d = $metric.PSObject.Properties['default']
            $values[[string]$metric.key] = if ($null -ne $d) { $d.Value } else { 0 }
        }
        $aircraft.Add([pscustomobject]@{Name=[string]$name;Values=$values})
    }
    return [pscustomobject]@{Active=$false;Run='IDLE';Updated=$null;Aircraft=$aircraft;Events=@()}
}

function Read-Snapshot($Profile) {
    $root = [Environment]::ExpandEnvironmentVariables([string]$Profile.telemetryRoot)
    if (-not (Test-Path -LiteralPath $root)) { return Idle-Snapshot $Profile }
    $run = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if ($null -eq $run) { return Idle-Snapshot $Profile }

    $pattern = [string]$Profile.filePattern
    if ([string]::IsNullOrWhiteSpace($pattern)) { $pattern='*.jsonl' }
    $files = @(Get-ChildItem -LiteralPath $run.FullName -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue)
    if ($files.Count -eq 0) { return Idle-Snapshot $Profile }

    $newest = ($files | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).LastWriteTimeUtc
    $stale = [int]$Profile.staleSeconds
    if ($stale -lt 3) { $stale=3 }
    if ($newest -lt [datetime]::UtcNow.AddSeconds(-$stale)) { return Idle-Snapshot $Profile }

    $planes = New-Object System.Collections.Generic.List[object]
    $events = New-Object System.Collections.Generic.List[object]
    foreach ($file in $files) {
        $records = @(Json-Tail $file.FullName)
        $frame = $records | Where-Object { [string](Get-Value $_ 'event') -eq 'frame' } | Select-Object -Last 1
        if ($null -eq $frame) { continue }
        $event = $records | Where-Object { [string](Get-Value $_ 'event') -ne 'frame' } | Select-Object -Last 1
        $coupled = $records | Where-Object { [string](Get-Value $_ 'event') -like 'energy_coupled*' } | Select-Object -Last 1
        $reasonText = if ($null -ne $coupled) {[string](Get-Value $coupled 'reason')} else {[string](Get-Value $event 'reason')}
        $reason = Parse-Reason $reasonText

        $name = [string](Get-Value $frame 'aircraft_name')
        if ([string]::IsNullOrWhiteSpace($name)) { $name=[string](Get-Value $frame 'aircraft_entity_id') }
        if ([string]::IsNullOrWhiteSpace($name)) { $name=$file.BaseName }

        $values=[ordered]@{}
        foreach ($metric in @($Profile.metrics)) {
            $source=[string]$metric.source
            $value=$null
            if ($source -eq 'frame') {$value=Get-Value $frame ([string]$metric.path)}
            elseif ($source -eq 'event') {$value=Get-Value $event ([string]$metric.path)}
            elseif ($source -eq 'coupled') {$value=Get-Value $coupled ([string]$metric.path)}
            elseif ($source -eq 'reason' -and $reason.ContainsKey([string]$metric.path)) {$value=$reason[[string]$metric.path]}
            $values[[string]$metric.key]=Format-Metric $value $metric
        }
        $planes.Add([pscustomobject]@{Name=$name;Values=$values})

        foreach ($r in ($records | Where-Object {[string](Get-Value $_ 'event') -ne 'frame'} | Select-Object -Last 12)) {
            $events.Add([pscustomobject]@{
                Tick=Get-Value $r 'server_tick';Aircraft=$name
                Event=Get-Value $r 'event';Reason=Get-Value $r 'reason'
            })
        }
    }
    if ($planes.Count -eq 0) { return Idle-Snapshot $Profile }
    return [pscustomobject]@{
        Active=$true;Run=$run.Name;Updated=$newest.ToLocalTime();Aircraft=$planes
        Events=@($events|Sort-Object Tick -Descending|Select-Object -First 40)
    }
}

function Runner-Processes($Profile) {
    $root=[Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot).TrimEnd('\')
    $escaped=[regex]::Escape($root)
    try {
        return @(Get-CimInstance Win32_Process -Filter "Name='Runner.Listener.exe'" |
            Where-Object {([string]$_.ExecutablePath -match "^$escaped") -or ([string]$_.CommandLine -match $escaped)})
    } catch { return @() }
}

function Runner-Running($Profile,[switch]$Force) {
    if (-not $Force -and ([datetime]::UtcNow-$script:RunnerCacheAt).TotalSeconds -lt 2) {
        return [bool]$script:RunnerCache
    }
    $script:RunnerCache=@(Runner-Processes $Profile).Count -gt 0
    $script:RunnerCacheAt=[datetime]::UtcNow
    return $script:RunnerCache
}

function Start-Runner($Profile) {
    if (Runner-Running $Profile -Force) { return }
    $root=[Environment]::ExpandEnvironmentVariables([string]$Profile.runnerRoot)
    $cmd=Join-Path $root 'run.cmd'
    if (-not (Test-Path -LiteralPath $cmd)) { throw "run.cmdが見つかりません: $cmd" }
    $logs=Join-Path $AppRoot 'logs'; New-Item -ItemType Directory -Force -Path $logs|Out-Null
    $id=([string]$Profile.id)-replace '[^A-Za-z0-9_.-]','_'
    $log=Join-Path $logs ("runner-$id.log")
    $line='""{0}" >> "{1}" 2>&1"' -f $cmd,$log
    Start-Process cmd.exe -ArgumentList '/d','/s','/c',$line -WorkingDirectory $root -WindowStyle Hidden|Out-Null
    Start-Sleep -Milliseconds 700
    $script:RunnerCacheAt=[datetime]::MinValue
}

function Stop-Runner($Profile) {
    foreach ($p in @(Runner-Processes $Profile)) {
        Start-Process taskkill.exe -ArgumentList '/PID',[string]$p.ProcessId,'/T','/F' -Wait -WindowStyle Hidden|Out-Null
    }
    $script:RunnerCacheAt=[datetime]::MinValue
}

function Log-Path($Profile) {
    $id=([string]$Profile.id)-replace '[^A-Za-z0-9_.-]','_'
    return Join-Path (Join-Path $AppRoot 'logs') ("runner-$id.log")
}

function Build-Columns($Profile,$Grid) {
    $Grid.Columns.Clear()
    $c=New-Object Windows.Forms.DataGridViewTextBoxColumn
    $c.Name='Aircraft';$c.HeaderText='Aircraft';$c.Width=220;$c.Frozen=$true
    [void]$Grid.Columns.Add($c)
    foreach ($m in @($Profile.metrics)) {
        $c=New-Object Windows.Forms.DataGridViewTextBoxColumn
        $c.Name=[string]$m.key;$c.HeaderText=[string]$m.label
        $c.Width=if ([string]$m.key -in @('phase','stage','event')){170}else{100}
        [void]$Grid.Columns.Add($c)
    }
}

function Fill-Telemetry($Snapshot,$Profile,$Grid) {
    $Grid.Rows.Clear()
    foreach ($a in @($Snapshot.Aircraft)) {
        $cells=New-Object Collections.Generic.List[object];$cells.Add([string]$a.Name)
        foreach ($m in @($Profile.metrics)) {$cells.Add($a.Values[[string]$m.key])}
        [void]$Grid.Rows.Add($cells.ToArray())
    }
}

function Fill-Events($Snapshot,$Grid) {
    $Grid.Rows.Clear()
    foreach ($e in @($Snapshot.Events)) {[void]$Grid.Rows.Add($e.Tick,$e.Aircraft,$e.Event,$e.Reason)}
}

try { Load-Config } catch { Show-Error $_.Exception.Message; exit 1 }

$form=New-Object Windows.Forms.Form
$form.Text='ジョリー Runner Hub';$form.Size=New-Object Drawing.Size(1360,820)
$form.MinimumSize=New-Object Drawing.Size(980,620);$form.StartPosition='CenterScreen'
if(Test-Path $IconPath){$form.Icon=New-Object Drawing.Icon($IconPath)}

$top=New-Object Windows.Forms.Panel;$top.Dock='Top';$top.Height=86;$form.Controls.Add($top)
$title=New-Object Windows.Forms.Label;$title.Text='ジョリー Runner Hub'
$title.Font=New-Object Drawing.Font('Segoe UI',16,[Drawing.FontStyle]::Bold)
$title.Location=New-Object Drawing.Point(12,8);$title.Size=New-Object Drawing.Size(260,32);$top.Controls.Add($title)
$profiles=New-Object Windows.Forms.ComboBox;$profiles.DropDownStyle='DropDownList'
$profiles.Location=New-Object Drawing.Point(280,10);$profiles.Size=New-Object Drawing.Size(270,28);$top.Controls.Add($profiles)

function Add-Button($Text,$X,$Width) {
    $b=New-Object Windows.Forms.Button;$b.Text=$Text;$b.Location=New-Object Drawing.Point($X,8)
    $b.Size=New-Object Drawing.Size($Width,32);$top.Controls.Add($b);return $b
}
$connect=Add-Button '接続' 560 84;$disconnect=Add-Button '切断' 652 84
$configButton=Add-Button '設定JSON' 744 96;$actionsButton=Add-Button 'GitHub Actions' 848 116
$dataButton=Add-Button 'データ場所' 972 100;$reloadButton=Add-Button '再読込' 1080 84

$runnerLabel=New-Object Windows.Forms.Label;$runnerLabel.Location=New-Object Drawing.Point(14,52)
$runnerLabel.Size=New-Object Drawing.Size(330,24);$runnerLabel.Font=New-Object Drawing.Font('Segoe UI',10,[Drawing.FontStyle]::Bold)
$top.Controls.Add($runnerLabel)
$validationLabel=New-Object Windows.Forms.Label;$validationLabel.Location=New-Object Drawing.Point(360,52)
$validationLabel.Size=New-Object Drawing.Size(940,24);$top.Controls.Add($validationLabel)

$tabs=New-Object Windows.Forms.TabControl;$tabs.Dock='Fill';$form.Controls.Add($tabs);$top.BringToFront()
$t1=New-Object Windows.Forms.TabPage;$t1.Text='リアルタイムデータ';$tabs.TabPages.Add($t1)
$grid=New-Object Windows.Forms.DataGridView;$grid.Dock='Fill';$grid.ReadOnly=$true
$grid.AllowUserToAddRows=$false;$grid.RowHeadersVisible=$false;$grid.BackgroundColor=[Drawing.Color]::White;$t1.Controls.Add($grid)
$t2=New-Object Windows.Forms.TabPage;$t2.Text='イベント';$tabs.TabPages.Add($t2)
$eventGrid=New-Object Windows.Forms.DataGridView;$eventGrid.Dock='Fill';$eventGrid.ReadOnly=$true
$eventGrid.AllowUserToAddRows=$false;$eventGrid.RowHeadersVisible=$false;$eventGrid.BackgroundColor=[Drawing.Color]::White
[void]$eventGrid.Columns.Add('Tick','Tick');[void]$eventGrid.Columns.Add('Aircraft','Aircraft')
[void]$eventGrid.Columns.Add('Event','Event');[void]$eventGrid.Columns.Add('Reason','Reason')
$eventGrid.Columns[0].Width=90;$eventGrid.Columns[1].Width=220;$eventGrid.Columns[2].Width=250;$eventGrid.Columns[3].AutoSizeMode='Fill'
$t2.Controls.Add($eventGrid)
$t3=New-Object Windows.Forms.TabPage;$t3.Text='Runnerログ';$tabs.TabPages.Add($t3)
$logBox=New-Object Windows.Forms.TextBox;$logBox.Dock='Fill';$logBox.Multiline=$true;$logBox.ReadOnly=$true
$logBox.ScrollBars='Both';$logBox.WordWrap=$false;$logBox.Font=New-Object Drawing.Font('Consolas',9);$t3.Controls.Add($logBox)

function Reload-Profiles([string]$Id) {
    $profiles.Items.Clear()
    foreach($p in @($script:Config.profiles)){[void]$profiles.Items.Add($p)}
    $profiles.DisplayMember='name';$index=0
    for($i=0;$i -lt $profiles.Items.Count;$i++){if([string]$profiles.Items[$i].id -eq $Id){$index=$i;break}}
    if($profiles.Items.Count -gt 0){$profiles.SelectedIndex=$index}
}
function Select-Profile {
    if($profiles.SelectedIndex -lt 0){return}
    $script:Profile=$profiles.SelectedItem;Build-Columns $script:Profile $grid
    $idle=Idle-Snapshot $script:Profile;Fill-Telemetry $idle $script:Profile $grid;Fill-Events $idle $eventGrid
    $script:RunnerCacheAt=[datetime]::MinValue
}
$profiles.add_SelectedIndexChanged({Select-Profile})
$connect.add_Click({try{Start-Runner $script:Profile}catch{Show-Error $_.Exception.Message}})
$disconnect.add_Click({
    if([Windows.Forms.MessageBox]::Show('Runnerを停止しますか？','ジョリー Runner Hub',
        [Windows.Forms.MessageBoxButtons]::YesNo,[Windows.Forms.MessageBoxIcon]::Question) -eq 'Yes'){
        try{Stop-Runner $script:Profile}catch{Show-Error $_.Exception.Message}
    }
})
$configButton.add_Click({Start-Process notepad.exe -ArgumentList ('"{0}"' -f $ConfigPath)})
$actionsButton.add_Click({if($script:Profile.repoUrl){Start-Process (([string]$script:Profile.repoUrl).TrimEnd('/')+'/actions')}})
$dataButton.add_Click({
    $p=[Environment]::ExpandEnvironmentVariables([string]$script:Profile.telemetryRoot)
    if(Test-Path $p){Start-Process explorer.exe -ArgumentList ('"{0}"' -f $p)}else{Show-Error "データ場所がまだありません。`n$p"}
})
$reloadButton.add_Click({try{$id=[string]$script:Profile.id;Load-Config;Reload-Profiles $id}catch{Show-Error $_.Exception.Message}})

Reload-Profiles ''
Select-Profile

$timer=New-Object Windows.Forms.Timer;$timer.Interval=1000
$timer.add_Tick({
    if($null -eq $script:Profile){return}
    try{
        if((Get-Item $ConfigPath).LastWriteTimeUtc -gt $script:LastConfigWrite){
            $id=[string]$script:Profile.id;Load-Config;Reload-Profiles $id
        }
        if(Runner-Running $script:Profile){
            $runnerLabel.Text='Runner: 接続中';$runnerLabel.ForeColor=[Drawing.Color]::ForestGreen
        }else{
            $runnerLabel.Text='Runner: 停止中';$runnerLabel.ForeColor=[Drawing.Color]::Firebrick
        }
        $s=Read-Snapshot $script:Profile;Fill-Telemetry $s $script:Profile $grid;Fill-Events $s $eventGrid
        if($s.Active){
            $validationLabel.Text="検証: 実行中  Run=$($s.Run)  更新=$($s.Updated.ToString('HH:mm:ss'))"
            $validationLabel.ForeColor=[Drawing.Color]::DarkGreen
        }else{
            $validationLabel.Text='検証: 待機中（数値は0）';$validationLabel.ForeColor=[Drawing.Color]::DimGray
        }
        $lp=Log-Path $script:Profile
        if(Test-Path $lp){$logBox.Text=(Tail-Lines $lp 196608)-join [Environment]::NewLine}
        else{$logBox.Text='Runner Hubから起動すると、ここにRunnerログが表示されます。'}
    }catch{$validationLabel.Text='読込エラー: '+$_.Exception.Message;$validationLabel.ForeColor=[Drawing.Color]::Firebrick}
})
$timer.Start()
$form.add_Shown({if([bool]$script:Config.autoConnect){try{Start-Runner $script:Profile}catch{Show-Error $_.Exception.Message}}})
$form.add_FormClosed({$timer.Stop()})
[void]$form.ShowDialog()
