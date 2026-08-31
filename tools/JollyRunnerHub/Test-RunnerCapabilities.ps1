Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RunnerCapabilities.ps1')

$snapshot = [pscustomobject]@{ capabilities=@(
    [pscustomobject]@{name='git';status='ready';evidence='git version test'},
    [pscustomobject]@{name='docker_linux';status='ready';evidence='linux/x86_64'},
    [pscustomobject]@{name='java';status='degraded';evidence='exit=1'}
) }
$summary = Get-JollyCapabilitySummary -Snapshot $snapshot -Required @('git','docker_linux','java')
if ($summary.ready -ne 2 -or $summary.total -ne 3 -or $summary.missing -notcontains 'java') {
    throw 'Capability summary classification failed.'
}
$empty = Get-JollyCapabilitySummary -Snapshot $snapshot -Required @('missing')
if ($empty.ready -ne 0 -or $empty.total -ne 0) { throw 'Unknown capability handling failed.' }
'runner capability tests: ok'
