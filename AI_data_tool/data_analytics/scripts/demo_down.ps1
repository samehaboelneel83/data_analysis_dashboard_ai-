<#
.SYNOPSIS
    Removes the seeded demo content, leaving the stack running and any of
    your own data untouched.

.DESCRIPTION
    Calls DELETE /api/v1/demo/seed, which runs remove_demo_content. That
    teardown is already covered by tests: it removes both demo logins, the
    demo reports and their pages, the share link, the embed config, the
    workspace folders and their role grants. A demo you cannot cleanly
    remove is one nobody runs twice.

    This deliberately does NOT stop containers or drop volumes -- unseeding
    and tearing down the stack are different decisions. Use -Stack to also
    stop the containers, and -Volumes to additionally delete the database.

.PARAMETER AdminEmail
    The admin created by demo_up.ps1.

.PARAMETER Stack
    Also run `docker compose down` after unseeding.

.PARAMETER Volumes
    With -Stack, also delete the volumes. This DESTROYS the database,
    including anything you created while exploring.

.EXAMPLE
    .\scripts\demo_down.ps1

.EXAMPLE
    .\scripts\demo_down.ps1 -Stack -Volumes
#>
[CmdletBinding()]
param(
    [string] $AdminEmail    = 'admin@example.invalid',
    [string] $AdminPassword = 'demo-password',
    [switch] $Stack,
    [switch] $Volumes
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 has no $PSNativeCommandUseErrorActionPreference (that
# is 7+), and with ErrorActionPreference='Stop' it turns a native command's
# stderr into a terminating NativeCommandError. `docker compose` writes ALL of
# its progress ("Container x Running") to stderr, so every docker call would
# abort the script on success. Redirecting with 2>&1 does not help: 5.1 wraps
# each stderr line in an ErrorRecord and Stop still fires on it.
#
# So native calls run with the preference relaxed, and are judged on their exit
# code -- which is the only thing that actually reports failure.
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

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

$BackendUrl = 'http://localhost:8000'

try {
    Write-Host ''
    Write-Host "[1] Unseeding the demo as $AdminEmail" -ForegroundColor Cyan

    $login = Invoke-RestMethod -Uri "$BackendUrl/api/v1/auth/login" -Method Post `
        -ContentType 'application/json' `
        -Body (@{ email = $AdminEmail; password = $AdminPassword } | ConvertTo-Json)
    $token = $login.access_token
    if (-not $token) { throw 'login returned no access_token' }

    $removed = Invoke-RestMethod -Uri "$BackendUrl/api/v1/demo/seed" -Method Delete `
        -Headers @{ Authorization = "Bearer $token" }
    Write-Host "    $($removed | ConvertTo-Json -Compress)" -ForegroundColor Green

    if ($Stack) {
        Write-Host ''
        Write-Host '[2] Stopping the stack' -ForegroundColor Cyan
        if ($Volumes) {
            Write-Warning 'Deleting volumes: the database and every uploaded file go with them.'
            Invoke-Native { docker compose down -v } 'docker compose down'
        } else {
            Invoke-Native { docker compose down } 'docker compose down'
        }
    } else {
        Write-Host ''
        Write-Host '    Stack left running. Re-seed with .\scripts\demo_up.ps1 -SkipBuild'
    }
}
finally {
    Pop-Location
}
