<#
.SYNOPSIS
    Seed local users and demo content for browser QA (qa/TEST_PLAN.md).

.DESCRIPTION
    Idempotent. Safe to re-run.

    1. Start docker compose if the backend is not running.
    2. Wait for GET http://localhost:8000/health/ready.
    3. Ensure a bootstrap admin and POST /api/v1/demo/seed (via scripts/demo_up.ps1).
    4. Copy scripts/seed_dev_accounts.py into the backend container and run it
       so admin@datalytics.local and the extra orgs exist.

    Accounts: qa/TEST_DATA.md
#>
[CmdletBinding()]
param(
    [switch] $SkipBuild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-Native {
    param([scriptblock] $Command, [string] $What)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Command 2>&1 | ForEach-Object { Write-Host "    $_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
    if ($code -ne 0) { throw "$What failed (exit $code)" }
}

Write-Host '[qa/seed] 1. Stack + demo content' -ForegroundColor Cyan
$running = docker ps --filter 'name=datalytics_backend' --format '{{.Names}}' 2>$null
if (-not $running) {
    Write-Host '    backend is down — calling scripts/demo_up.ps1'
    if ($SkipBuild) { & "$root\scripts\demo_up.ps1" -SkipBuild }
    else { & "$root\scripts\demo_up.ps1" }
} else {
    Write-Host '    backend already running — demo_up -SkipBuild (idempotent seed)'
    & "$root\scripts\demo_up.ps1" -SkipBuild
}

Write-Host '[qa/seed] 2. Dev accounts (admin@datalytics.local, Contoso, Northwind)' -ForegroundColor Cyan
$src = Join-Path $root 'scripts\seed_dev_accounts.py'
if (-not (Test-Path $src)) { throw "missing $src" }
Invoke-Native { docker cp $src datalytics_backend:/tmp/seed_dev_accounts.py } 'docker cp seed_dev_accounts.py'
Invoke-Native { docker exec datalytics_backend python /tmp/seed_dev_accounts.py } 'seed_dev_accounts.py'

Write-Host ''
Write-Host 'QA seed ready' -ForegroundColor Green
Write-Host '  App     http://localhost:3001'
Write-Host '  Admin   admin@datalytics.local / demo-password'
Write-Host '  Also    demo-global@example.invalid / demo-password'
Write-Host '  Also    demo-emea@example.invalid / demo-password'
Write-Host '  Plan    qa/TEST_PLAN.md'
Write-Host '  Report  copy qa/REPORT_TEMPLATE.md to qa/REPORT.md'
