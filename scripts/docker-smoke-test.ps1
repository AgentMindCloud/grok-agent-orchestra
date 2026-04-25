<#
.SYNOPSIS
  Build the grok-agent-orchestra image, run it, and verify the dashboard
  answers HTTP 200 on /api/health.

.DESCRIPTION
  Mirror of scripts/docker-smoke-test.sh for PowerShell users. Designed to
  exit non-zero on any failure and to clean up the test container even on
  error (try/finally).

.PARAMETER Image
  Image tag to build (or pull when -NoBuild is set). Default: a timestamped
  test tag so the user's :latest is never overwritten.

.PARAMETER Port
  Host port to bind. Default 18000 to avoid colliding with a local 8000.

.PARAMETER NoBuild
  Skip `docker build` — useful when the image was just pulled from ghcr.io.

.EXAMPLE
  .\scripts\docker-smoke-test.ps1

.EXAMPLE
  $env:IMAGE = "ghcr.io/agentmindcloud/grok-agent-orchestra:latest"
  .\scripts\docker-smoke-test.ps1 -NoBuild
#>

[CmdletBinding()]
param(
    [string]$Image = $(if ($env:IMAGE) { $env:IMAGE } else { "orchestra-test:smoke-$(Get-Date -UFormat %s)" }),
    [int]$Port = $(if ($env:PORT) { [int]$env:PORT } else { 18000 }),
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$ContainerName = "orchestra-smoke-$([System.Guid]::NewGuid().ToString().Substring(0, 8))"

function Step([string]$msg) { Write-Host "`n▸ $msg" -ForegroundColor Cyan }
function Ok  ([string]$msg) { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Fail([string]$msg) { Write-Host "  ✗ $msg" -ForegroundColor Red; exit 1 }

try {
    if (-not $NoBuild) {
        Step "Build $Image"
        docker build -t $Image .
        if ($LASTEXITCODE -ne 0) { Fail "docker build failed" }
        Ok "build succeeded"
    }

    Step "Verify CLI entry point inside the image"
    $version = docker run --rm $Image --version 2>&1
    if ($LASTEXITCODE -ne 0 -or -not ($version -match "grok-orchestra")) {
        Fail "grok-orchestra --version did not respond as expected: $version"
    }
    Ok "grok-orchestra --version: $($version -join ' ')"

    Step "Boot the dashboard on host port $Port"
    docker run --rm -d -p "${Port}:8000" --name $ContainerName $Image | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "docker run failed" }
    Ok "container started"

    Step "Wait for /api/health (<= 30s)"
    $healthUrl = "http://127.0.0.1:$Port/api/health"
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri $healthUrl
            if ($resp.StatusCode -eq 200 -and $resp.Content -match '"status":"ok"') {
                Ok "health endpoint returned $($resp.Content)"
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) { Fail "health endpoint did not become ready in 30s" }

    Step "Teardown"
    docker stop $ContainerName | Out-Null
    Ok "container stopped"

    Write-Host "`nAll smoke checks passed." -ForegroundColor Green
}
finally {
    # Always clean up — even if the script exited early.
    $existing = docker ps -aq --filter "name=^$ContainerName`$" 2>$null
    if ($existing) {
        docker rm -f $ContainerName | Out-Null
    }
}
