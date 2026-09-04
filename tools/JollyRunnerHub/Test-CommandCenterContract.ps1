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

function Assert-True([bool]$Condition,[string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Assert-Equal($Expected,$Actual,[string]$Message) {
    if ($Expected -ne $Actual) {
        throw "$Message Expected='$Expected' Actual='$Actual'"
    }
}

function Assert-Match([string]$Value,[string]$Pattern,[string]$Message) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch $Pattern) {
        throw "$Message Value='$Value' Pattern='$Pattern'"
    }
}

# Static security and UI contracts. These deliberately guard the integration boundary:
# RunnerHub may control the Durable helper, but must not take ownership of Durable's
# scheduled task, environment, or an arbitrary URL.
Assert-Contains 'CommandCenterSettingsPath' 'Desired-state settings path is missing.'
Assert-Contains 'ui-settings.json' 'Desired state must use Durable ui-settings.json.'
Assert-Contains 'CommandCenterHealthUrl' 'Health endpoint constant is missing.'
Assert-Contains 'http://127.0.0.1:8000/health' 'Health URL must be fixed loopback.'
Assert-Contains 'CommandCenterStateUrl' 'State endpoint constant is missing.'
Assert-Contains 'http://127.0.0.1:8000/command-center/state' 'State URL must be fixed loopback.'
Assert-Contains 'CommandCenterUiUrl' 'Command Center UI endpoint constant is missing.'
Assert-Contains 'http://127.0.0.1:8000/command-center' 'UI URL must be fixed loopback.'
Assert-Contains 'Resolve-DurableCommandCenterHelper' 'Durable helper discovery is missing.'
Assert-Contains 'Set-CommandCenter.ps1' 'Hub must apply settings through the Durable helper.'
Assert-Contains 'Start-Process powershell.exe' 'Command Center apply process is missing.'
Assert-Contains '-WindowStyle Hidden -PassThru' 'Command Center apply must be hidden and asynchronous.'
Assert-Contains "'-TimeoutSeconds'" 'Durable helper invocation must remain bounded by a timeout.'
Assert-Contains "'30'" 'Durable helper timeout contract must remain 30 seconds.'
Assert-Contains 'Update-CommandCenterUi' 'Command Center UI refresh is missing.'
Assert-Contains 'commandCenterDesired = New-CommandCenterValue' 'Desired-state indicator is missing.'
Assert-Contains '希望' 'Desired-state Japanese label is missing.'
Assert-Contains 'commandCenterObserved = New-CommandCenterValue' 'Observed-state indicator is missing.'
Assert-Contains '実測' 'Observed-state Japanese label is missing.'
Assert-Contains 'commandCenterBrowser = New-CommandCenterValue' 'Browser sensor indicator is missing.'
Assert-Contains 'Browser Companion' 'Browser sensor label is missing.'
Assert-Contains 'commandCenterNotification = New-CommandCenterValue' 'Notification sensor indicator is missing.'
Assert-Contains '通知' 'Notification sensor label is missing.'
Assert-Contains 'runnerLayout.RowCount = 4' 'Runner layout must reserve the Command Center row.'
Assert-Contains 'runnerLayout.Controls.Add($runnerGrid,0,2)' 'Runner grid must remain below the Command Center card.'
Assert-Contains 'runnerLayout.Controls.Add($runnerButtons,0,3)' 'Runner buttons must remain below the runner grid.'
Assert-Contains '旧版 / 未対応' 'Version-skew state must be explicit.'
Assert-Contains '希望値と実測値が不一致' 'Desired/observed mismatch must be explicit.'
Assert-Contains 'commandCenterOpen.Enabled' 'Open action must be gated by observed state.'
Assert-Contains 'Command Center URL contract is invalid.' 'Open action must verify the fixed URL contract.'
Assert-Contains 'CommandCenterApplyProcess' 'Apply completion must be polled asynchronously.'
Assert-Contains '$startSelectedRunner.add_Click' 'Existing selected-runner start control disappeared.'
Assert-Contains '$stopSelectedRunner.add_Click' 'Existing selected-runner stop control disappeared.'
Assert-Contains 'function Get-SelectedRunnerProfile' 'Runner action scope resolver disappeared.'
Assert-Contains 'Hub profileに未登録。自動起動・停止・復旧の対象外' 'Unmanaged runners must remain display-only.'

Assert-NotContains 'setx DURABLE_COMMAND_CENTER_ENABLED' 'Hub must not mutate global/user Windows environment.'
Assert-NotContains 'SetEnvironmentVariable' 'Hub must not write Windows environment variables.'
Assert-NotContains 'Register-ScheduledTask' 'Hub must not re-register the Durable production task for a UI toggle.'
Assert-NotContains 'Stop-ScheduledTask' 'Hub must not stop the Durable production task for a UI toggle.'
Assert-NotContains 'Start-Runner $item' 'Unmanaged inventory items must never become start targets.'
Assert-NotContains 'Stop-Runner $item' 'Unmanaged inventory items must never become stop targets.'

# There must be exactly one fixed UI URL assignment, and the click handler must
# re-check that fixed contract immediately before opening it.
$urlPattern = @'
(?m)^\s*\$CommandCenterUiUrl\s*=\s*'([^']+)'\s*$
'@.Trim()
$urlAssignments = [regex]::Matches($text,$urlPattern)
Assert-Equal 1 $urlAssignments.Count 'Command Center UI URL must have exactly one assignment.'
Assert-Equal 'http://127.0.0.1:8000/command-center' $urlAssignments[0].Groups[1].Value 'Command Center UI URL is not the allowlisted loopback endpoint.'
$openHandler = [regex]::Match($text,'(?ms)\$commandCenterOpen\.add_Click\(\{.*?\r?\n\}\)')
Assert-True $openHandler.Success 'Command Center open click handler is missing.'
Assert-True ($openHandler.Value.Contains("if (`$CommandCenterUiUrl -ne 'http://127.0.0.1:8000/command-center')")) 'Open click handler no longer rejects a changed URL contract.'
Assert-True ($openHandler.Value.Contains('Start-Process $CommandCenterUiUrl')) 'Open click handler no longer launches only the fixed URL variable.'

# Parse the real Hub source and import only the non-UI functions under test. This
# avoids launching WinForms while still executing the production function bodies.
$tokens = $null
$parseErrors = $null
$hubAst = [System.Management.Automation.Language.Parser]::ParseInput(
    $text,[ref]$tokens,[ref]$parseErrors)
if (@($parseErrors).Count -gt 0) {
    $details = @($parseErrors | ForEach-Object {
        '{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message
    }) -join [Environment]::NewLine
    throw "JollyRunnerHub.ps1 has parser errors:`n$details"
}

$functionTexts = New-Object System.Collections.Generic.List[string]
foreach ($functionName in @(
    'Read-CommandCenterDesiredState',
    'Start-CommandCenterApply',
    'Complete-CommandCenterApply'
)) {
    $nameForLookup = $functionName
    $functionAst = $hubAst.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            [string]$node.Name -eq [string]$nameForLookup
        )
    },$true)
    if ($null -eq $functionAst) { throw "Production function was not found: $functionName" }
    [void]$functionTexts.Add([string]$functionAst.Extent.Text)
}
Invoke-Expression ($functionTexts -join ([Environment]::NewLine + [Environment]::NewLine))

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('JollyRunnerHub-command-center-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$previousLegacyEnv = [Environment]::GetEnvironmentVariable('DURABLE_COMMAND_CENTER_ENABLED','Process')
try {
    $CommandCenterSettingsPath = Join-Path $testRoot 'ui-settings.json'
    $script:CommandCenterApplyStdout = Join-Path $testRoot 'apply.stdout.log'
    $script:CommandCenterApplyStderr = Join-Path $testRoot 'apply.stderr.log'
    $script:CommandCenterApplyProcess = $null
    $script:CommandCenterApplyRequested = $null
    $script:CommandCenterApplyMessage = ''

    # Missing settings intentionally fail closed to local default OFF. A legacy
    # process environment variable must not override the persisted settings model.
    [Environment]::SetEnvironmentVariable('DURABLE_COMMAND_CENTER_ENABLED','1','Process')
    Remove-Item -LiteralPath $CommandCenterSettingsPath -Force -ErrorAction SilentlyContinue
    $desired = Read-CommandCenterDesiredState
    Assert-True $desired.Valid 'Missing settings should be a valid default state.'
    Assert-Equal $false ([bool]$desired.Enabled) 'Missing settings must default Command Center to OFF.'
    Assert-Equal 'default' ([string]$desired.Source) 'Missing settings must report default source.'

    # Schema v1 ON/OFF settings are both accepted.
    [ordered]@{schemaVersion=1;commandCenterEnabled=$true} | ConvertTo-Json |
        Set-Content -LiteralPath $CommandCenterSettingsPath -Encoding UTF8
    $desired = Read-CommandCenterDesiredState
    Assert-True $desired.Valid 'Schema v1 ON settings should be valid.'
    Assert-Equal $true ([bool]$desired.Enabled) 'Schema v1 ON setting was not read as ON.'
    Assert-Equal 'local-settings' ([string]$desired.Source) 'Valid settings source changed unexpectedly.'

    [ordered]@{schemaVersion=1;commandCenterEnabled=$false} | ConvertTo-Json |
        Set-Content -LiteralPath $CommandCenterSettingsPath -Encoding UTF8
    $desired = Read-CommandCenterDesiredState
    Assert-True $desired.Valid 'Schema v1 OFF settings should be valid.'
    Assert-Equal $false ([bool]$desired.Enabled) 'Schema v1 OFF setting was not read as OFF.'

    # Unsupported/legacy schema, malformed JSON, and non-boolean values must all
    # degrade visibly instead of being silently coerced into a current setting.
    [ordered]@{schemaVersion=0;commandCenterEnabled=$true} | ConvertTo-Json |
        Set-Content -LiteralPath $CommandCenterSettingsPath -Encoding UTF8
    $desired = Read-CommandCenterDesiredState
    Assert-Equal $false ([bool]$desired.Valid) 'Legacy schema must not be silently accepted.'
    Assert-Equal 'invalid-settings' ([string]$desired.Source) 'Legacy schema must be classified as invalid-settings.'

    '{broken-json' | Set-Content -LiteralPath $CommandCenterSettingsPath -Encoding UTF8
    $desired = Read-CommandCenterDesiredState
    Assert-Equal $false ([bool]$desired.Valid) 'Malformed JSON must be rejected.'
    Assert-Equal 'invalid-settings' ([string]$desired.Source) 'Malformed JSON must be classified as invalid-settings.'

    [ordered]@{schemaVersion=1;commandCenterEnabled='true'} | ConvertTo-Json |
        Set-Content -LiteralPath $CommandCenterSettingsPath -Encoding UTF8
    $desired = Read-CommandCenterDesiredState
    Assert-Equal $false ([bool]$desired.Valid) 'String commandCenterEnabled must not be coerced to boolean.'

    # Mock only the process boundary. Start-CommandCenterApply itself is the real
    # production function extracted above, so ON/OFF and timeout arguments are
    # verified as they are actually assembled by RunnerHub.
    $script:TestHelperPath = Join-Path $testRoot 'Set-CommandCenter.ps1'
    '# test helper placeholder' | Set-Content -LiteralPath $script:TestHelperPath -Encoding UTF8
    function Resolve-DurableCommandCenterHelper { return $script:TestHelperPath }

    function New-FakeCommandCenterProcess([bool]$HasExited,[int]$ExitCode = 0) {
        $fake = [pscustomobject]@{
            Id = 4242
            HasExited = $HasExited
            ExitCode = $ExitCode
            Disposed = $false
        }
        $fake | Add-Member -MemberType ScriptMethod -Name Refresh -Value { return }
        $fake | Add-Member -MemberType ScriptMethod -Name Dispose -Value { $this.Disposed = $true }
        return $fake
    }

    $script:CapturedStartProcess = $null
    function Start-Process {
        [CmdletBinding()]
        param(
            [Parameter(Position=0)][string]$FilePath,
            [string]$ArgumentList,
            [string]$WindowStyle,
            [switch]$PassThru,
            [string]$RedirectStandardOutput,
            [string]$RedirectStandardError
        )
        $script:CapturedStartProcess = [pscustomobject][ordered]@{
            FilePath = $FilePath
            ArgumentList = $ArgumentList
            WindowStyle = $WindowStyle
            PassThru = [bool]$PassThru
            RedirectStandardOutput = $RedirectStandardOutput
            RedirectStandardError = $RedirectStandardError
        }
        return (New-FakeCommandCenterProcess -HasExited $false)
    }

    Start-CommandCenterApply -Enable $true
    Assert-Equal 'powershell.exe' ([string]$script:CapturedStartProcess.FilePath) 'Apply must use Windows PowerShell helper process.'
    Assert-Equal 'Hidden' ([string]$script:CapturedStartProcess.WindowStyle) 'Apply helper must stay hidden.'
    Assert-Equal $true ([bool]$script:CapturedStartProcess.PassThru) 'Apply helper must be asynchronous/pass-thru.'
    Assert-Match ([string]$script:CapturedStartProcess.ArgumentList) '(?:^|\s)-State\s+on(?:\s|$)' 'Enable action did not pass -State on.'
    Assert-Match ([string]$script:CapturedStartProcess.ArgumentList) '(?:^|\s)-TimeoutSeconds\s+30(?:\s|$)' 'Enable action lost the bounded 30-second timeout.'
    Assert-Equal $true ([bool]$script:CommandCenterApplyRequested) 'Enable action did not record requested ON state.'

    $script:CommandCenterApplyProcess = $null
    $script:CapturedStartProcess = $null
    Start-CommandCenterApply -Enable $false
    Assert-Match ([string]$script:CapturedStartProcess.ArgumentList) '(?:^|\s)-State\s+off(?:\s|$)' 'Disable action did not pass -State off.'
    Assert-Match ([string]$script:CapturedStartProcess.ArgumentList) '(?:^|\s)-TimeoutSeconds\s+30(?:\s|$)' 'Disable action lost the bounded 30-second timeout.'
    Assert-Equal $false ([bool]$script:CommandCenterApplyRequested) 'Disable action did not record requested OFF state.'

    # A helper/restart failure must surface an error and clear the in-flight state,
    # so the UI can recover instead of being stuck forever in "applying".
    $failedProcess = New-FakeCommandCenterProcess -HasExited $true -ExitCode 9
    $script:CommandCenterApplyProcess = $failedProcess
    $script:CommandCenterApplyRequested = $true
    $script:CapturedError = ''
    function Show-Error([string]$Text) { $script:CapturedError = $Text }
    Remove-Item -LiteralPath $script:CommandCenterApplyStdout -Force -ErrorAction SilentlyContinue
    'simulated bounded restart failure' |
        Set-Content -LiteralPath $script:CommandCenterApplyStderr -Encoding UTF8
    Complete-CommandCenterApply
    Assert-True ([string]$script:CapturedError -like '*simulated bounded restart failure*') 'Helper failure was not surfaced to the user.'
    Assert-True ([string]$script:CommandCenterApplyMessage -like '*simulated bounded restart failure*') 'Helper failure message was not retained for status display.'
    Assert-Equal $null $script:CommandCenterApplyProcess 'Failed apply process must be cleared.'
    Assert-Equal $null $script:CommandCenterApplyRequested 'Failed apply request marker must be cleared.'
    Assert-Equal $true ([bool]$failedProcess.Disposed) 'Failed apply process object must be disposed.'

    # Success path must also clear the in-flight state and consume the helper's
    # structured final message.
    $okProcess = New-FakeCommandCenterProcess -HasExited $true -ExitCode 0
    $script:CommandCenterApplyProcess = $okProcess
    $script:CommandCenterApplyRequested = $false
    '{"message":"command center applied"}' |
        Set-Content -LiteralPath $script:CommandCenterApplyStdout -Encoding UTF8
    Remove-Item -LiteralPath $script:CommandCenterApplyStderr -Force -ErrorAction SilentlyContinue
    Complete-CommandCenterApply
    Assert-Equal 'command center applied' ([string]$script:CommandCenterApplyMessage) 'Successful helper message was not consumed.'
    Assert-Equal $null $script:CommandCenterApplyProcess 'Successful apply process must be cleared.'
    Assert-Equal $true ([bool]$okProcess.Disposed) 'Successful apply process object must be disposed.'
}
finally {
    [Environment]::SetEnvironmentVariable('DURABLE_COMMAND_CENTER_ENABLED',$previousLegacyEnv,'Process')
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output 'command center hub contract + behavior tests: ok'