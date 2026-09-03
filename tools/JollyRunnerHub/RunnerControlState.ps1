Set-StrictMode -Version Latest

function Get-JollyDesiredStatePath {
    param([Parameter(Mandatory=$true)][string]$AppRoot)
    return Join-Path $AppRoot 'desired-state.json'
}

function Read-JollyDesiredState {
    param([Parameter(Mandatory=$true)][string]$AppRoot)
    $path = Get-JollyDesiredStatePath $AppRoot
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return [pscustomobject]@{version=1;profiles=[pscustomobject]@{}}
    }
    try {
        $state = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -eq $state.PSObject.Properties['profiles']) {
            Add-Member -InputObject $state -NotePropertyName profiles -NotePropertyValue ([pscustomobject]@{})
        }
        return $state
    } catch {
        return [pscustomobject]@{version=1;profiles=[pscustomobject]@{}}
    }
}

function Get-JollyDesiredRunnerState {
    param(
        [Parameter(Mandatory=$true)][string]$AppRoot,
        [Parameter(Mandatory=$true)]$Profile,
        $Config
    )
    $state = Read-JollyDesiredState $AppRoot
    $id = [string]$Profile.id
    $property = $state.profiles.PSObject.Properties[$id]
    if ($null -ne $property -and [string]$property.Value -in @('running','stopped')) {
        return [string]$property.Value
    }

    $autoConnect = $true
    if ($null -ne $Config -and $null -ne $Config.PSObject.Properties['autoConnect']) {
        $autoConnect = [bool]$Config.autoConnect
    }
    if ($null -ne $Profile.PSObject.Properties['autoConnect']) {
        $autoConnect = [bool]$Profile.autoConnect
    }
    return $(if ($autoConnect) { 'running' } else { 'stopped' })
}

function Set-JollyDesiredRunnerState {
    param(
        [Parameter(Mandatory=$true)][string]$AppRoot,
        [Parameter(Mandatory=$true)][string]$ProfileId,
        [Parameter(Mandatory=$true)][ValidateSet('running','stopped')][string]$State
    )
    New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null
    $current = Read-JollyDesiredState $AppRoot
    if ($null -eq $current.profiles.PSObject.Properties[$ProfileId]) {
        Add-Member -InputObject $current.profiles -NotePropertyName $ProfileId -NotePropertyValue $State
    } else {
        $current.profiles.PSObject.Properties[$ProfileId].Value = $State
    }
    $current.version = 1
    $path = Get-JollyDesiredStatePath $AppRoot
    $temp = $path + '.tmp-' + [guid]::NewGuid().ToString('N')
    try {
        $current | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temp -Encoding UTF8
        Move-Item -LiteralPath $temp -Destination $path -Force
    } finally {
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
    return $State
}
