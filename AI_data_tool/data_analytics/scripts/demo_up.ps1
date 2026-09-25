<#
.SYNOPSIS
    Brings up the full Datalytics stack and seeds the demo, then prints
    every login you need to explore it.

.DESCRIPTION
    A freshly-composed stack has NOBODY WHO CAN SIGN IN. Startup
    (main.py::_backfill_default_org) creates a default Organization and an
    Admin role, but no User, and routers/auth.py exposes /login with no
    signup endpoint. So `docker compose up` alone gets you a login form and
    no credentials. This script creates that first admin itself.

    Steps:
      1. docker compose up -d --build
      2. Wait on GET /health/ready. The readiness probe reports 503 until
         lifespan has finished Alembic and the backfills, so it is exactly
         the signal to wait on -- a fixed sleep would either be too short
         on a cold migration or waste time on a warm one.
      3. Create the first admin idempotently, inside the backend container,
         via services/auth_provisioning.create_organization_with_admin --
         reused rather than re-inserting rows, so password hashing and role
         wiring stay in one place. Skipped when a User already exists, so
         re-running is safe.
      4. POST /api/v1/demo/seed with that admin's token.
      5. Print the URLs and every login.

.PARAMETER AdminEmail
    Email for the bootstrap admin. Only used when no user exists yet.

.PARAMETER AdminPassword
    Password for the bootstrap admin. Only used when no user exists yet.

.PARAMETER SkipBuild
    Reuse existing images instead of rebuilding. Much faster on a re-run.

.EXAMPLE
    .\scripts\demo_up.ps1

.EXAMPLE
    .\scripts\demo_up.ps1 -SkipBuild
#>
[CmdletBinding()]
param(
    [string] $AdminEmail    = 'admin@example.invalid',
    [string] $AdminPassword = 'demo-password',
    [switch] $SkipBuild,
    [int]    $ReadyTimeoutSeconds = 300
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

# Run from the compose root regardless of where the caller invoked this from.
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

# These must match backend/app/services/demo_use_cases.py (DEMO_USER_EMAILS,
# DEMO_USER_PASSWORD). Duplicated rather than read out of Python, because the
# script has to print them without importing the app -- keep them in step if
# those constants are ever renamed.
$BackendUrl  = 'http://localhost:8000'
$FrontendUrl = 'http://localhost:3001'
$DemoEmails  = @('demo-emea@example.invalid', 'demo-global@example.invalid')
$DemoPassword = 'demo-password'

function Write-Step($n, $text) {
    Write-Host ""
    Write-Host "[$n] $text" -ForegroundColor Cyan
}

try {
    # ── 1. Bring the stack up ─────────────────────────────────────────────
    Write-Step 1 'Starting the stack'
    if ($SkipBuild) { Invoke-Native { docker compose up -d } 'docker compose up' }
    else            { Invoke-Native { docker compose up -d --build } 'docker compose up' }

    # ── 2. Wait for readiness, not for a clock ────────────────────────────
    Write-Step 2 "Waiting for $BackendUrl/health/ready"
    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "$BackendUrl/health/ready" -TimeoutSec 5 `
                                   -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch {
            # 503 while migrations run is the expected case, not an error.
        }
        Start-Sleep -Seconds 3
        Write-Host '.' -NoNewline
    }
    Write-Host ''
    if (-not $ready) {
        throw ("backend never became ready within $ReadyTimeoutSeconds s. " +
               "Check: docker compose logs backend")
    }
    Write-Host '    ready' -ForegroundColor Green

    # ── 3. Bootstrap the first admin, idempotently ────────────────────────
    Write-Step 3 "Ensuring an admin exists ($AdminEmail)"

    # Runs inside the backend container: it already has the app, its
    # dependencies and the database URL, so this needs nothing on the host.
    # Written to a temp file rather than passed with -c, because quoting a
    # multi-line Python program through PowerShell into docker exec is a
    # reliable source of silent corruption.
    $bootstrap = @'
import asyncio, os, sys

# Python puts THIS FILE's directory on sys.path, not the working directory, so
# a copy living in /tmp cannot import the app package at /app however it is
# invoked. Stated here so the script works wherever it is dropped.
sys.path.insert(0, "/app")

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.models import Organization, Role, User
from app.services.auth_provisioning import create_organization_with_admin

EMAIL = os.environ["DEMO_ADMIN_EMAIL"]
PASSWORD = os.environ["DEMO_ADMIN_PASSWORD"]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(
            select(User).where(User.email == EMAIL))).scalars().first()
        if existing is not None:
            print("EXISTS")
            return

        # A stack that has been used already has users, just not this one.
        # Attach the new admin to the org that is already there rather than
        # creating a second one, so re-running against a live stack does not
        # fragment it into parallel organisations.
        org = (await db.execute(select(Organization))).scalars().first()
        if org is None:
            await create_organization_with_admin(
                db, "Demo organisation", EMAIL, PASSWORD)
        else:
            from app.core.security import hash_password
            role = (await db.execute(
                select(Role).where(Role.org_id == org.id,
                                   Role.is_org_admin.is_(True)))).scalars().first()
            if role is None:
                role = Role(org_id=org.id, name="Admin", is_org_admin=True)
                db.add(role)
                await db.flush()
            db.add(User(org_id=org.id, role_id=role.id, email=EMAIL,
                        password_hash=hash_password(PASSWORD)))
        await db.commit()
        print("CREATED")


asyncio.run(main())
'@

    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) 'datalytics_bootstrap_admin.py'
    Set-Content -Path $tmp -Value $bootstrap -Encoding utf8
    Invoke-Native { docker compose cp $tmp backend:/tmp/bootstrap_admin.py } `
                  'copying the bootstrap script into the backend container' 

    $ErrorActionPreference = 'Continue'
    # --workdir /app is required, not cosmetic: the app package lives at /app
    # (the image's WORKDIR) and is not installed, so running the script from
    # /tmp fails with ModuleNotFoundError: No module named 'app'.
    $out = docker compose exec -T --workdir /app `
        -e DEMO_ADMIN_EMAIL=$AdminEmail `
        -e DEMO_ADMIN_PASSWORD=$AdminPassword `
        backend python /tmp/bootstrap_admin.py 2>&1 | Out-String
    $bootstrapExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($bootstrapExit -ne 0) { throw "admin bootstrap failed:`n$out" }
    Remove-Item $tmp -ErrorAction SilentlyContinue

    if ($out -match 'EXISTS') {
        Write-Host '    already present, left alone' -ForegroundColor Green
    } else {
        Write-Host '    created' -ForegroundColor Green
    }

    # ── 4. Sign in and seed ───────────────────────────────────────────────
    Write-Step 4 'Seeding the demo'
    $login = Invoke-RestMethod -Uri "$BackendUrl/api/v1/auth/login" -Method Post `
        -ContentType 'application/json' `
        -Body (@{ email = $AdminEmail; password = $AdminPassword } | ConvertTo-Json)
    $token = $login.access_token
    if (-not $token) { throw 'login returned no access_token' }

    $seeded = Invoke-RestMethod -Uri "$BackendUrl/api/v1/demo/seed" -Method Post `
        -Headers @{ Authorization = "Bearer $token" }
    Write-Host "    $($seeded | ConvertTo-Json -Compress)" -ForegroundColor Green

    # ── 5. Everything you need to explore it ──────────────────────────────
    Write-Host ''
    Write-Host '-------------------------------------------------------------'
    Write-Host ' Datalytics demo is up' -ForegroundColor Green
    Write-Host '-------------------------------------------------------------'
    Write-Host "  App        $FrontendUrl"
    Write-Host "  API docs   $BackendUrl/docs"
    Write-Host ''
    Write-Host '  Admin (sees everything, can manage every folder)'
    Write-Host "    $AdminEmail / $AdminPassword"
    Write-Host ''
    Write-Host '  Demo logins (password: ' -NoNewline; Write-Host "$DemoPassword)"
    foreach ($e in $DemoEmails) { Write-Host "    $e" }
    Write-Host ''
    Write-Host '  The two demo logins see DIFFERENT workspace menus: the'
    Write-Host '  "Use cases" folder is granted to the EMEA role only, while'
    Write-Host '  "Widget gallery" is unrestricted. Sign in as each to see it.'
    Write-Host ''
    Write-Host '  Tear down with: .\scripts\demo_down.ps1'
    Write-Host '-------------------------------------------------------------'
}
finally {
    Pop-Location
}
