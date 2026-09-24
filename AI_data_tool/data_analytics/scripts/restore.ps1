<#
.SYNOPSIS
    Restores a Datalytics backup: the database dump and the uploaded files.

.DESCRIPTION
    THIS OVERWRITES THE CURRENT DEPLOYMENT. It drops and recreates the restored
    objects (`pg_restore --clean`) and empties the uploads volume before
    unpacking. It refuses to run without `-Confirm` or `-WhatIf`, because a
    restore fired by accident destroys exactly what a backup exists to protect.

    Both artifacts are restored together, never one alone. A database restored
    without its files looks completely intact -- datasets listed, reports
    openable -- and fails at the first import-mode widget. That is a worse
    failure than an obvious one, so this script will not do it.

    Ordering here is the mirror of backup.ps1: the DATABASE goes first, then
    the files. Backup takes files first so a stray file is the only possible
    inconsistency; restore lays the database down first for the same reason --
    at every intermediate moment, extra files are harmless and missing ones are
    not.

    Step 4 is the real success check. `/health/ready` returns 503 until Alembic
    has finished, so a 200 means the restored database is reachable AND at the
    schema version this build expects.

.PARAMETER Dump
    Path to a `datalytics-*.dump` produced by backup.ps1.

.PARAMETER Uploads
    Path to the matching `uploads-*.tar.gz`.

.PARAMETER WhatIf
    Validate the inputs and print the plan without changing anything.

.EXAMPLE
    .\scripts\restore.ps1 -Dump .\datalytics-20260829.dump -Uploads .\uploads-20260829.tar.gz -WhatIf

.EXAMPLE
    .\scripts\restore.ps1 -Dump .\datalytics-20260829.dump -Uploads .\uploads-20260829.tar.gz -Confirm
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $Dump,
    [Parameter(Mandatory = $true)] [string] $Uploads,
    [switch] $WhatIf,
    [switch] $Confirm,
    [int]    $ReadyTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'

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

try {
    # ── Validate BEFORE touching anything ─────────────────────────────────
    foreach ($p in @($Dump, $Uploads)) {
        if (-not (Test-Path $p)) { throw "not found: $p" }
        if ((Get-Item $p).Length -eq 0) { throw "empty file: $p" }
    }
    $magic = [System.Text.Encoding]::ASCII.GetString(
        [byte[]](Get-Content $Dump -Encoding Byte -TotalCount 5))
    if ($magic -ne 'PGDMP') {
        throw "$Dump is not a pg_dump custom-format archive (starts '$magic')"
    }

    $ErrorActionPreference = 'Continue'
    $volume = (docker volume ls --format '{{.Name}}' 2>&1 |
               Where-Object { $_ -match 'uploaded_files$' } | Select-Object -First 1)
    $ErrorActionPreference = 'Stop'
    if (-not $volume) { throw "could not find the uploaded_files volume" }

    $dumpFull = (Resolve-Path $Dump).Path
    $upFull   = (Resolve-Path $Uploads).Path
    $upDir    = Split-Path -Parent $upFull
    $upName   = Split-Path -Leaf $upFull

    Write-Host ''
    Write-Host 'Restore plan' -ForegroundColor Cyan
    Write-Host "  database  <- $dumpFull"
    Write-Host "  uploads   <- $upFull"
    Write-Host "  volume    :  $volume"
    Write-Host ''

    if ($WhatIf) {
        Write-Host 'WhatIf: inputs are valid; nothing was changed.' -ForegroundColor Green
        Write-Host 'Re-run with -Confirm to perform the restore.'
        return
    }
    if (-not $Confirm) {
        throw ("This OVERWRITES the current database and uploaded files. " +
               "Re-run with -Confirm once you are sure, or -WhatIf to check the inputs.")
    }

    # ── 1. Only postgres, so the backend cannot write mid-restore ─────────
    Write-Host '[1] Bringing up postgres alone' -ForegroundColor Cyan
    Invoke-Native { docker compose up -d postgres } 'docker compose up postgres'

    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        $ErrorActionPreference = 'Continue'
        docker compose exec -T postgres pg_isready -U datalytics *> $null
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = 'Stop'
        if ($ok) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'postgres did not become ready' }

    # ── 2. Database first (see the note above) ────────────────────────────
    Write-Host '[2] Restoring the database' -ForegroundColor Cyan
    $ErrorActionPreference = 'Continue'
    # --clean --if-exists so a restore over an existing database replaces it
    # rather than colliding. Fed as BYTES: piping the archive through
    # PowerShell would re-encode and corrupt it.
    $args = @('compose','exec','-T','postgres','pg_restore',
              '-U','datalytics','-d','datalytics','--clean','--if-exists')
    $proc = Start-Process -FilePath 'docker' -ArgumentList $args -NoNewWindow -Wait -PassThru `
                          -RedirectStandardInput $dumpFull `
                          -RedirectStandardError "$dumpFull.restore.err"
    $ErrorActionPreference = 'Stop'
    $errText = if (Test-Path "$dumpFull.restore.err") { Get-Content "$dumpFull.restore.err" -Raw } else { '' }
    Remove-Item "$dumpFull.restore.err" -ErrorAction SilentlyContinue
    # pg_restore exits non-zero on "does not exist" notices from --clean against
    # a fresh database, which are expected and harmless. Only a real failure
    # mentions an error line.
    if ($proc.ExitCode -ne 0 -and $errText -match '(?m)^pg_restore: error:') {
        throw "pg_restore failed:`n$errText"
    }
    if ($errText) { Write-Host '    (pg_restore emitted warnings; this is normal for --clean)' -ForegroundColor DarkGray }

    # ── 3. Then the files ─────────────────────────────────────────────────
    Write-Host '[3] Restoring uploaded files' -ForegroundColor Cyan
    Invoke-Native {
        docker run --rm -v "${volume}:/data" -v "${upDir}:/backup:ro" `
            alpine sh -c "rm -rf /data/* /data/.[!.]* 2>/dev/null; tar xzf '/backup/$upName' -C /data"
    } 'uploads restore'

    # ── 4. Bring everything up and let the app judge the result ───────────
    Write-Host '[4] Starting the stack' -ForegroundColor Cyan
    Invoke-Native { docker compose up -d } 'docker compose up'

    Write-Host '[5] Waiting for /health/ready' -ForegroundColor Cyan
    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri 'http://localhost:8000/health/ready' `
                                   -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch { }   # 503 while Alembic runs is expected, not a failure
        Start-Sleep -Seconds 3
        Write-Host '.' -NoNewline
    }
    Write-Host ''
    if (-not $ready) {
        throw ("the app did not become ready within $ReadyTimeoutSeconds s. The data may " +
               "be restored but the schema mismatched -- check: docker compose logs backend")
    }

    Write-Host ''
    Write-Host '-------------------------------------------------------------'
    Write-Host ' Restore complete and the app reports itself servable' -ForegroundColor Green
    Write-Host '-------------------------------------------------------------'
    Write-Host '  Sign in and open one import-mode report: that is the check'
    Write-Host '  that proves the FILES came back, not just the database.'
    Write-Host '-------------------------------------------------------------'
}
finally {
    Pop-Location
}
