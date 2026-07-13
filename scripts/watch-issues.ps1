[CmdletBinding()]
param(
    [string]$Path = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
if (-not $Path) {
    $Path = Join-Path $repoRoot "logs\issues.ndjson"
}

$parent = Split-Path -Parent $Path
New-Item -ItemType Directory -Force -Path $parent | Out-Null
if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType File -Path $Path | Out-Null
}

Write-Host "Watching Auto Initiativ issues only:" -ForegroundColor Cyan
Write-Host $Path
Write-Host "New backend 5xx responses, exceptions, blocked workflows, and browser errors will appear here."
Write-Host "Press Ctrl+C to stop watching."
Write-Host ""

Get-Content -LiteralPath $Path -Tail 0 -Wait | ForEach-Object {
    try {
        $issue = $_ | ConvertFrom-Json
        $time = ([datetimeoffset]$issue.timestamp).ToLocalTime().ToString("HH:mm:ss")
        $source = if ($issue.source) { " [$($issue.source)]" } else { "" }
        Write-Host "$time  $($issue.kind)$source" -ForegroundColor Yellow
        Write-Host "  $($issue.message)" -ForegroundColor Red
    }
    catch {
        Write-Host $_ -ForegroundColor DarkYellow
    }
}
