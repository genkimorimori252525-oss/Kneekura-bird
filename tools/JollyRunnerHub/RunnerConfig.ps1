Set-StrictMode -Version Latest

function Merge-JollyRunnerConfigDefaults {
    param(
        [Parameter(Mandatory=$true)]$CurrentConfig,
        [Parameter(Mandatory=$true)]$DefaultConfig
    )

    $changed = $false
    if ($null -eq $CurrentConfig.PSObject.Properties['profiles']) {
        Add-Member -InputObject $CurrentConfig -NotePropertyName profiles -NotePropertyValue @()
        $changed = $true
    }

    $knownIds = @{}
    foreach ($profile in @($CurrentConfig.profiles)) {
        $knownIds[[string]$profile.id] = $true
    }

    foreach ($defaultProfile in @($DefaultConfig.profiles)) {
        $defaultId = [string]$defaultProfile.id
        if (-not $knownIds.ContainsKey($defaultId)) {
            $CurrentConfig.profiles = @($CurrentConfig.profiles) + @($defaultProfile)
            $knownIds[$defaultId] = $true
            $changed = $true
            continue
        }

        $existing = @($CurrentConfig.profiles | Where-Object { [string]$_.id -eq $defaultId } | Select-Object -First 1)
        if ($existing.Count -eq 0) { continue }
        $target = $existing[0]
        foreach ($property in @($defaultProfile.PSObject.Properties)) {
            $name = [string]$property.Name
            if ($name -eq 'id') { continue }
            if ($null -eq $target.PSObject.Properties[$name]) {
                Add-Member -InputObject $target -NotePropertyName $name -NotePropertyValue $property.Value
                $changed = $true
            }
        }
    }

    $defaultVersion = 0
    [void][int]::TryParse([string]$DefaultConfig.version,[ref]$defaultVersion)
    $currentVersion = 0
    if ($null -ne $CurrentConfig.PSObject.Properties['version']) {
        [void][int]::TryParse([string]$CurrentConfig.version,[ref]$currentVersion)
    }
    if ($defaultVersion -gt $currentVersion) {
        if ($null -eq $CurrentConfig.PSObject.Properties['version']) {
            Add-Member -InputObject $CurrentConfig -NotePropertyName version -NotePropertyValue $defaultVersion
        } else {
            $CurrentConfig.version = $defaultVersion
        }
        $changed = $true
    }

    foreach ($property in @($DefaultConfig.PSObject.Properties)) {
        $name = [string]$property.Name
        if ($name -in @('profiles','version')) { continue }
        if ($null -eq $CurrentConfig.PSObject.Properties[$name]) {
            Add-Member -InputObject $CurrentConfig -NotePropertyName $name -NotePropertyValue $property.Value
            $changed = $true
        }
    }

    return [pscustomobject]@{Config=$CurrentConfig;Changed=[bool]$changed}
}

function Read-JollyRunnerConfig {
    param(
        [Parameter(Mandatory=$true)][string]$ConfigPath,
        [Parameter(Mandatory=$true)][string]$DefaultConfigPath
    )
    if (-not (Test-Path -LiteralPath $DefaultConfigPath -PathType Leaf)) {
        throw "Default config not found: $DefaultConfigPath"
    }
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        $parent = Split-Path -Parent $ConfigPath
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        Copy-Item -LiteralPath $DefaultConfigPath -Destination $ConfigPath -Force
    }

    $current = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $defaults = Get-Content -LiteralPath $DefaultConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $merged = Merge-JollyRunnerConfigDefaults -CurrentConfig $current -DefaultConfig $defaults
    if ($merged.Changed) {
        $merged.Config | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
    }
    return $merged.Config
}
