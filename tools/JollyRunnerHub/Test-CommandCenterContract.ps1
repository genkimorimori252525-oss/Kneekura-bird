Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$hubPath = Join-Path $PSScriptRoot 'JollyRunnerHub.ps1'
$text = Get-Content -LiteralPath $hubPath -Raw -Encoding UTF8

function Assert-Contains([string]$Needle,[string]$Message) {
    if (-not $text.Contains($Needle)) { throw $Message }
}

function Assert-NotContains([string]$Needle,[string]$Message) {
    if ($text.Contains($Needle)) { throw $Message }
}

Assert-Contains '$CommandCenterSettingsPath = Join-Path $DurableRuntimeRoot ''ui-settings.json''' 'Desired state must come from Durable ui-settings.json.'
Assert-Contains '$CommandCenterHealthUrl = ''http://127.0.0.1:8000/health''' 'Health URL must be fixed loopback.'
Assert-Contains '$CommandCenterUiUrl = ''http://127.0.0.1:8000/command-center''' 'UI URL must be fixed loopback.'
Assert-Contains 'function Resolve-DurableCommandCenterHelper' 'Durable helper discovery is missing.'
Assert-Contains '''Set-CommandCenter.ps1''' 'Hub must apply settings through the Durable helper.'
Assert-Contains 'Start-Process powershell.exe' 'Command Center apply process is missing.'
Assert-Contains '-WindowStyle Hidden -PassThru' 'Command Center apply must be hidden and asynchronous.'
Assert-Contains 'function Update-CommandCenterUi' 'Command Center UI refresh is missing.'
Assert-Contains '$commandCenterDesired = New-CommandCenterValue ''希望''' 'Desired-state indicator is missing.'
Assert-Contains '$commandCenterObserved = New-CommandCenterValue ''実測''' 'Observed-state indicator is missing.'
Assert-Contains '$commandCenterBrowser = New-CommandCenterValue ''Browser Companion''' 'Browser sensor indicator is missing.'
Assert-Contains '$commandCenterNotification = New-CommandCenterValue ''通知''' 'Notification sensor indicator is missing.'
Assert-Contains '$runnerLayout.RowCount = 4' 'Runner layout must reserve the Command Center row.'
Assert-Contains '$runnerLayout.Controls.Add($runnerGrid,0,2)' 'Runner grid must remain below the Command Center card.'
Assert-Contains '$runnerLayout.Controls.Add($runnerButtons,0,3)' 'Runner buttons must remain below the runner grid.'
Assert-Contains '旧版 / 未対応' 'Version-skew state must be explicit.'
Assert-Contains '希望値と実測値が不一致' 'Desired/observed mismatch must be explicit.'
Assert-Contains '$commandCenterOpen.Enabled' 'Open action must be gated by observed state.'
Assert-Contains 'if ($CommandCenterUiUrl -ne ''http://127.0.0.1:8000/command-center'')' 'Open action must enforce its fixed URL contract.'
Assert-Contains '$null -ne $script:CommandCenterApplyProcess' 'Apply completion must be polled asynchronously.'

Assert-NotContains 'setx DURABLE_COMMAND_CENTER_ENABLED' 'Hub must not mutate global/user Windows environment.'
Assert-NotContains '[Environment]::SetEnvironmentVariable(' 'Hub must not write Windows environment variables.'
Assert-NotContains 'Register-ScheduledTask' 'Hub must not re-register the Durable production task for a UI toggle.'
Assert-NotContains 'Stop-ScheduledTask' 'Hub must not stop the Durable production task for a UI toggle.'

'command center hub contract tests: ok'