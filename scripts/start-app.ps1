[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload,
    [switch]$UseUv
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

Set-Location $repoRoot

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-Error "Port $Port is already in use by process $($listener.OwningProcess). Stop that process or pass -Port <other-port>."
}

$uvicornArgs = @("backend.app.main:app", "--host", $BindHost, "--port", "$Port")
if ($Reload) {
    $uvicornArgs += "--reload"
}

Write-Host "Starting Auto Initiativ..."
Write-Host "API:       http://$BindHost`:$Port"
Write-Host "Dashboard: http://$BindHost`:$Port/dashboard"
Write-Host "Health:    http://$BindHost`:$Port/health"
Write-Host "Issues:    $repoRoot\logs\issues.ndjson"
Write-Host "Monitor:   .\scripts\watch-issues.cmd  (run in a second terminal)"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

if (-not $UseUv -and (Test-Path $python)) {
    & $python -m uvicorn @uvicornArgs
    exit $LASTEXITCODE
}

$env:UV_NO_CACHE = "1"
& uv run --no-cache --python 3.12 uvicorn @uvicornArgs
exit $LASTEXITCODE
