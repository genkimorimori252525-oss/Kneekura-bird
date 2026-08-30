[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('spawn','status','stop','gc')][string]$Command,
    [string]$Repository,
    [string[]]$Labels,
    [string]$SourceRunnerRoot,
    [ValidateRange(5,1440)][int]$TtlMinutes = 60,
    [string]$InstanceId,
    [string]$BasePath,
    [long]$ExpectedRunId = 0,
    [ValidateRange(1,365)][int]$RetentionDays = 7
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'EphemeralRunnerController.psm1') -Force

switch ($Command) {
    'spawn' {
        if ([string]::IsNullOrWhiteSpace($Repository) -or
            [string]::IsNullOrWhiteSpace($SourceRunnerRoot) -or
            @($Labels).Count -eq 0) {
            throw 'spawn requires Repository, Labels, and SourceRunnerRoot.'
        }
        $spawned = Start-JollyEphemeralRunner -Repository $Repository -Labels $Labels `
            -SourceRunnerRoot $SourceRunnerRoot -TtlMinutes $TtlMinutes `
            -BasePath $BasePath -ExpectedRunId $ExpectedRunId
        Wait-JollyEphemeralRunnerOnline -InstanceId ([string]$spawned.id) -BasePath $BasePath | ConvertTo-Json -Depth 8
    }
    'status' {
        if ([string]::IsNullOrWhiteSpace($InstanceId)) { throw 'status requires InstanceId.' }
        Get-JollyEphemeralRunnerStatus -InstanceId $InstanceId -BasePath $BasePath -RefreshGitHub | ConvertTo-Json -Depth 8
    }
    'stop' {
        if ([string]::IsNullOrWhiteSpace($InstanceId)) { throw 'stop requires InstanceId.' }
        Stop-JollyEphemeralRunner -InstanceId $InstanceId -BasePath $BasePath | ConvertTo-Json -Depth 8
    }
    'gc' {
        @(Invoke-JollyEphemeralRunnerGc -BasePath $BasePath -RetentionDays $RetentionDays) | ConvertTo-Json
    }
}
