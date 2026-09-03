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

# RunnerDispatchWatch also contains the shared classifications. Override only the
# gh process adapter here so every real background probe uses StrictMode-safe
# process/text handling without changing the classification contract.
function Read-ProbeTextFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
    $value = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($null -eq $value) { return '' }
    return [string]$value
}

function Invoke-JollyGhApiJson {
    param(
        [Parameter(Mandatory=$true)][string]$Route,
        [ValidateRange(1,30)][int]$TimeoutSeconds = 5
    )
    $gh = Get-Command gh.exe -ErrorAction SilentlyContinue
    if ($null -eq $gh) { $gh = Get-Command gh -ErrorAction SilentlyContinue }
    if ($null -eq $gh) {
        return [pscustomobject]@{Ok=$false;Payload=$null;Error='gh unavailable';TimedOut=$false}
    }

    $base = Join-Path ([IO.Path]::GetTempPath()) ('JollyRunnerHub-gh-' + [guid]::NewGuid().ToString('N'))
    $stdout = $base + '.out'
    $stderr = $base + '.err'
    $process = $null
    try {
        $process = Start-Process -FilePath $gh.Source -ArgumentList @('api','--method','GET',$Route) `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { Start-Process taskkill.exe -ArgumentList '/PID',[string]$process.Id,'/T','/F' -Wait -WindowStyle Hidden | Out-Null } catch {}
            return [pscustomobject]@{Ok=$false;Payload=$null;Error=('gh timeout after {0}s' -f $TimeoutSeconds);TimedOut=$true}
        }
        try { $process.WaitForExit() } catch {}
        try { $process.Refresh() } catch {}

        [string]$outText = Read-ProbeTextFile $stdout
        [string]$errText = Read-ProbeTextFile $stderr
        $exitCode = $null
        try {
            $rawExitCode = $process.ExitCode
            if ($null -ne $rawExitCode -and -not [string]::IsNullOrWhiteSpace([string]$rawExitCode)) {
                $parsedExitCode = 0
                if ([int]::TryParse([string]$rawExitCode,[ref]$parsedExitCode)) { $exitCode = $parsedExitCode }
            }
        } catch {}

        if ($null -ne $exitCode -and [int]$exitCode -ne 0) {
            if ($errText.Length -gt 800) { $errText = $errText.Substring(0,800) }
            $detail = $errText.Trim()
            if ([string]::IsNullOrWhiteSpace($detail)) { $detail = 'no stderr' }
            return [pscustomobject]@{Ok=$false;Payload=$null;Error=('gh exit={0}: {1}' -f $exitCode,$detail);TimedOut=$false}
        }
        if ([string]::IsNullOrWhiteSpace($outText)) {
            if ($null -eq $exitCode) {
                $detail = $errText.Trim()
                if ([string]::IsNullOrWhiteSpace($detail)) { $detail = 'no stderr' }
                return [pscustomobject]@{Ok=$false;Payload=$null;Error=('gh exit unavailable: {0}' -f $detail);TimedOut=$false}
            }
            return [pscustomobject]@{Ok=$false;Payload=$null;Error='gh returned empty response';TimedOut=$false}
        }

        try {
            $payload = $outText | ConvertFrom-Json
        } catch {
            return [pscustomobject]@{Ok=$false;Payload=$null;Error=('gh returned invalid JSON: {0}' -f $_.Exception.Message);TimedOut=$false}
        }
        return [pscustomobject]@{Ok=$true;Payload=$payload;Error='';TimedOut=$false}
    }
    catch {
        return [pscustomobject]@{Ok=$false;Payload=$null;Error=$_.Exception.Message;TimedOut=$false}
    }
    finally {
        Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
    }
}

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
