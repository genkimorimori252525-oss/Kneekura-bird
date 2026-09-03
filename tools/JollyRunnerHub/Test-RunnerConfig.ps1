Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RunnerConfig.ps1')

function Assert-True([bool]$Value,[string]$Message) {
    if (-not $Value) { throw $Message }
}
function Assert-Equal($Expected,$Actual,[string]$Message) {
    if ([string]$Expected -ne [string]$Actual) { throw "$Message expected=$Expected actual=$Actual" }
}

$current = [pscustomobject]@{
    version=6
    autoConnect=$false
    profiles=@(
        [pscustomobject]@{id='kneekura-lab';name='Custom KNEEKURA';runnerRoot='D:\custom-runner'}
    )
}
$defaults = [pscustomobject]@{
    version=7
    autoConnect=$true
    profiles=@(
        [pscustomobject]@{
            id='kneekura-lab';name='KNEEKURA LAB';runnerRoot='C:\actions-runner-kneekura-lab'
            dispatchWatchEnabled=$true;dispatchRecoverSeconds=180;routingLabels=@('self-hosted','Windows','X64','kneekura')
        },
        [pscustomobject]@{id='durable-workflow';name='Durable Workflow';runnerRoot='C:\actions-runner-durable-workflow'}
    )
}
$result = Merge-JollyRunnerConfigDefaults -CurrentConfig $current -DefaultConfig $defaults
Assert-True $result.Changed 'schema migration should report a change'
Assert-Equal 7 $result.Config.version 'schema version should migrate'
Assert-Equal 'D:\custom-runner' $result.Config.profiles[0].runnerRoot 'existing user override must be preserved'
Assert-Equal 'Custom KNEEKURA' $result.Config.profiles[0].name 'existing name override must be preserved'
Assert-True ([bool]$result.Config.profiles[0].dispatchWatchEnabled) 'missing dispatch setting should be added'
Assert-True (@($result.Config.profiles[0].routingLabels) -contains 'kneekura') 'routing labels should be added'
Assert-Equal 2 @($result.Config.profiles).Count 'missing default profile should be added'
Assert-Equal 'False' ([string]$result.Config.autoConnect) 'top-level user override must be preserved'

$second = Merge-JollyRunnerConfigDefaults -CurrentConfig $result.Config -DefaultConfig $defaults
Assert-True (-not $second.Changed) 'migration must be idempotent'
Write-Host 'runner config migration tests: ok'
