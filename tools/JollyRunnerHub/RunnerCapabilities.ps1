Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-JollyCapability {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][ValidateSet('ready','degraded','unavailable')][string]$Status,
        [string]$Evidence = ''
    )
    return [pscustomobject]@{ name=$Name; status=$Status; evidence=$Evidence }
}

function Invoke-JollyCapabilityCommand {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$Command,
        [string[]]$Arguments = @(),
        [ValidateRange(1,30)][int]$TimeoutSeconds = 5,
        [ValidateSet('Default','Unicode')][string]$OutputEncoding = 'Default'
    )

    $resolved = Get-Command $Command -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $resolved) { return New-JollyCapability -Name $Name -Status unavailable -Evidence 'command not found' }

    $temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) "JollyCapability-$([Guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
    $stdout = Join-Path $temporaryRoot 'stdout.txt'
    $stderr = Join-Path $temporaryRoot 'stderr.txt'
    try {
        $process = Start-Process -FilePath $resolved.Source -ArgumentList $Arguments `
            -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            & taskkill.exe /PID ([string]$process.Id) /T /F 2>$null | Out-Null
            return New-JollyCapability -Name $Name -Status degraded -Evidence 'probe timed out'
        }
        $lines = @()
        if (Test-Path -LiteralPath $stdout) { $lines += @(Get-Content -LiteralPath $stdout -Encoding $OutputEncoding -ErrorAction SilentlyContinue) }
        if (Test-Path -LiteralPath $stderr) { $lines += @(Get-Content -LiteralPath $stderr -Encoding $OutputEncoding -ErrorAction SilentlyContinue) }
        $evidence = (@($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ' ').Trim()
        if ($evidence.Length -gt 240) { $evidence = $evidence.Substring(0,240) }
        if ($process.ExitCode -eq 0) {
            return New-JollyCapability -Name $Name -Status ready -Evidence $evidence
        }
        $degradedEvidence = ("exit=$($process.ExitCode) $evidence").Trim()
        return New-JollyCapability -Name $Name -Status degraded -Evidence $degradedEvidence
    }
    catch {
        return New-JollyCapability -Name $Name -Status degraded -Evidence $_.Exception.Message
    }
    finally {
        $resolvedRoot = [IO.Path]::GetFullPath($temporaryRoot)
        $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
        if ($resolvedRoot.StartsWith($tempPrefix,[StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-JollyRunnerCapabilities {
    param([string[]]$RunnerRoots = @())

    $capabilities = New-Object Collections.Generic.List[object]
    foreach ($probe in @(
        @('git','git',@('--version')),
        @('gh','gh',@('--version')),
        @('node','node',@('--version')),
        @('java','java',@('-version')),
        @('javac','javac',@('-version')),
        @('gradle','gradle',@('--version')),
        @('python','python',@('--version')),
        @('docker','docker',@('version','--format','{{.Client.Version}}')),
        @('docker_linux','docker',@('info','--format','{{.OSType}}/{{.Architecture}}')),
        @('wsl','wsl.exe',@('--status'),'Unicode')
    )) {
        $encoding = if ($probe.Count -gt 3) { $probe[3] } else { 'Default' }
        [void]$capabilities.Add((Invoke-JollyCapabilityCommand -Name $probe[0] -Command $probe[1] -Arguments $probe[2] -OutputEncoding $encoding))
    }

    $dockerLinux = $capabilities | Where-Object { $_.name -eq 'docker_linux' } | Select-Object -First 1
    if ($null -ne $dockerLinux -and $dockerLinux.status -eq 'ready' -and $dockerLinux.evidence -notmatch '^linux/') {
        $dockerLinux.status = 'degraded'
        $dockerLinux.evidence = "Linux engine required; detected $($dockerLinux.evidence)"
    }

    $wslUbuntu = Invoke-JollyCapabilityCommand -Name 'wsl_ubuntu' -Command 'wsl.exe' -Arguments @('--list','--quiet') -OutputEncoding Unicode
    if ($wslUbuntu.status -eq 'ready') {
        # wsl.exe can emit UTF-16 text even when Start-Process redirects to a file.
        # Removing NUL separators keeps distro classification stable on Windows PowerShell 5.1.
        $wslUbuntu.evidence = ($wslUbuntu.evidence -replace "`0", '').Trim()
        $distros = @($wslUbuntu.evidence -split '\s+' | Where-Object { $_ -and $_ -notmatch '^docker-desktop$' })
        if ($distros.Count -eq 0) {
            $wslUbuntu.status = 'unavailable'
            $wslUbuntu.evidence = 'no non-Docker WSL distribution'
        }
    }
    [void]$capabilities.Add($wslUbuntu)

    $toolCacheEvidence = New-Object Collections.Generic.List[string]
    foreach ($runnerRoot in @($RunnerRoots | Where-Object { $_ })) {
        $expanded = [Environment]::ExpandEnvironmentVariables([string]$runnerRoot)
        $toolRoot = Join-Path $expanded '_work\_tool'
        if (-not (Test-Path -LiteralPath $toolRoot)) { continue }
        foreach ($tool in @(Get-ChildItem -LiteralPath $toolRoot -Directory -ErrorAction SilentlyContinue)) {
            $versions = @(Get-ChildItem -LiteralPath $tool.FullName -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
            if ($versions.Count -gt 0) { [void]$toolCacheEvidence.Add("$($tool.Name)=$($versions -join ',')") }
        }
    }
    [void]$capabilities.Add((New-JollyCapability -Name 'runner_toolcache' `
        -Status $(if ($toolCacheEvidence.Count -gt 0) { 'ready' } else { 'unavailable' }) `
        -Evidence ($toolCacheEvidence -join '; ')))

    return [pscustomobject]@{
        version = 1
        generatedAt = [DateTimeOffset]::UtcNow.ToString('o')
        machine = $env:COMPUTERNAME
        capabilities = $capabilities.ToArray()
    }
}

function Get-JollyCapabilitySummary {
    param(
        [Parameter(Mandatory=$true)]$Snapshot,
        [string[]]$Required = @()
    )

    $selected = @(if (@($Required).Count -eq 0) {
        $Snapshot.capabilities
    } else {
        $Snapshot.capabilities | Where-Object { $Required -contains [string]$_.name }
    })
    $ready = @($selected | Where-Object { $_.status -eq 'ready' }).Count
    $missing = @($selected | Where-Object { $_.status -ne 'ready' } | ForEach-Object { [string]$_.name })
    return [pscustomobject]@{
        ready = $ready
        total = $selected.Count
        missing = $missing
        text = if ($missing.Count -eq 0) { "$ready/$($selected.Count) ready" } else { "$ready/$($selected.Count) ready; missing: $($missing -join ', ')" }
    }
}
