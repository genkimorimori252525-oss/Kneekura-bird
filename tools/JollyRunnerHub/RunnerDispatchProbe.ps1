param(
    [Parameter(Mandatory=$true)][string]$Repository,
    [Parameter(Mandatory=$true)][string]$RunnerRoot,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string]$RoutingLabelsCsv = '',
    [ValidateRange(1,30)][int]$TimeoutSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RunnerDispatchWatch.ps1')

function Get-ProbeRunnerName([string]$Root) {
    $runnerFile = Join-Path $Root '.runner'
    if (-not (Test-Path -LiteralPath $runnerFile -PathType Leaf)) {
        throw "Runner registration file not found: $runnerFile"
    }
    $config = Get-Content -LiteralPath $runnerFile -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($property in @('agentName','name')) {
        if ($config.PSObject.Properties.Name -contains $property -and
            -not [string]::IsNullOrWhiteSpace([string]$config.$property)) {
            return [string]$config.$property
        }
    }
    throw "Runner name not found in $runnerFile"
}

$started = [datetime]::UtcNow
$RoutingLabels = @($RoutingLabelsCsv.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
try {
    $runnerName = Get-ProbeRunnerName $RunnerRoot
    $probe = Get-JollyDispatchProbe -Repository $Repository -RunnerName $runnerName `
        -RoutingLabels $RoutingLabels -TimeoutSeconds $TimeoutSeconds

    $directory = Split-Path -Parent $OutputPath
    if (-not [string]::IsNullOrWhiteSpace($directory)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }
    $temp = $OutputPath + '.tmp-' + [guid]::NewGuid().ToString('N')
    try {
        $probe | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temp -Encoding UTF8
        Move-Item -LiteralPath $temp -Destination $OutputPath -Force
    }
    finally {
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
}
catch {
    $failure = [ordered]@{
        schema='jolly.dispatch-probe'
        version=1
        repository=$Repository
        apiOk=$false
        error=$_.Exception.Message
        runnerFound=$false
        runnerId=0
        runnerStatus='unknown'
        runnerBusy=$false
        runnerLabels=@()
        exactNameCount=0
        routeCandidateCount=0
        eligibleQueuedCount=0
        assignedQueuedCount=0
        oldestQueuedSeconds=0
        oldestRunId=0
        oldestJobName=''
        probedAt=([datetime]::UtcNow).ToString('o')
        durationMs=[int]([datetime]::UtcNow-$started).TotalMilliseconds
    }
    $directory = Split-Path -Parent $OutputPath
    if (-not [string]::IsNullOrWhiteSpace($directory)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }
    $failure | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    exit 1
}
