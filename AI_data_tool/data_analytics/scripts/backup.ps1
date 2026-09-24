<#
.SYNOPSIS
    Backs up the two volumes whose loss cannot be recovered: uploaded files
    and the PostgreSQL database.

.DESCRIPTION
    docs/BACKUP_AND_RECOVERY.md specifies this procedure; this script is that
    procedure, so nobody has to retype it correctly at 2am.

    THE ORDER MATTERS AND IS NOT ARBITRARY. Files are captured FIRST, the
    database SECOND:

      * a file on disk that no row references is inert -- wasted bytes;
      * a row referencing a file that was never captured is a broken dataset,
        which looks intact until the first widget render.

    Taking files first makes the harmless direction the only one possible. A
    script that reversed these two steps would produce backups that pass every
    smoke test and restore subtly wrong, which is the failure this ordering
    exists to prevent.

    An empty or truncated dump ABORTS before retention runs. Without that, a
    run of failing backups quietly deletes the last good one -- the single
    worst outcome available to a backup system.

.PARAMETER BackupDir
    Where to write. Created if absent.

.PARAMETER RetentionDays
    Delete backups older than this. 0 keeps everything.

.PARAMETER Quiesce
    Stop the backend for the duration, for a strictly consistent pair. The
    frontend keeps serving; the API returns errors while it is down.

.EXAMPLE
    .\scripts\backup.ps1

.EXAMPLE
    .\scripts\backup.ps1 -BackupDir D:\backups -RetentionDays 30 -Quiesce
#>
[CmdletBinding()]
param(
    [string] $BackupDir = "$env:USERPROFILE\datalytics-backups",
    [int]    $RetentionDays = 14,
    [switch] $Quiesce
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 promotes ANY native stderr to a terminating error when
# ErrorActionPreference is 'Stop', and docker writes its normal progress there.
# Native calls therefore run with the preference relaxed and are judged on their
# exit code, which is the only thing that actually reports failure.
function Invoke-Native {
    param([scriptblock] $Command, [string] $What, [switch] $Quiet)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($Quiet) { & $Command 2>&1 | Out-Null } else { & $Command 2>&1 | ForEach-Object { Write-Host "    $_" } }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
    if ($code -ne 0) { throw "$What failed (exit $code)" }
}

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    $dumpPath = Join-Path $BackupDir "datalytics-$stamp.dump"
    $tarPath  = Join-Path $BackupDir "uploads-$stamp.tar.gz"

    # Compose prefixes volume names with the project directory, so it cannot be
    # hardcoded -- a wrong name here would back up an empty volume silently.
    $ErrorActionPreference = 'Continue'
    $volume = (docker volume ls --format '{{.Name}}' 2>&1 |
               Where-Object { $_ -match 'uploaded_files$' } | Select-Object -First 1)
    $ErrorActionPreference = 'Stop'
    if (-not $volume) { throw "could not find the uploaded_files volume - is the stack up?" }
    Write-Host "[0] volume: $volume" -ForegroundColor Cyan

    if ($Quiesce) {
        Write-Host "[q] Stopping the backend for a consistent pair" -ForegroundColor Cyan
        Invoke-Native { docker compose stop backend } 'docker compose stop'
    }

    try {
        # ── 1. FILES FIRST. See the note above; do not reorder. ───────────
        Write-Host "[1] Uploaded files -> $tarPath" -ForegroundColor Cyan
        Invoke-Native {
            docker run --rm -v "${volume}:/data:ro" -v "${BackupDir}:/backup" `
                alpine tar czf "/backup/uploads-$stamp.tar.gz" -C /data .
        } 'uploads snapshot'

        # ── 2. THEN THE DATABASE ──────────────────────────────────────────
        Write-Host "[2] Database -> $dumpPath" -ForegroundColor Cyan
        $ErrorActionPreference = 'Continue'
        # -Fc: compressed custom format, the only one pg_restore can take
        # selectively. Redirected as BYTES -- piping through PowerShell would
        # re-encode the stream and corrupt it in a way that only shows up at
        # restore time.
        $dumpArgs = @('compose','exec','-T','postgres','pg_dump',
                      '-U', $(if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { 'datalytics' }),
                      '-d', $(if ($env:POSTGRES_DB)   { $env:POSTGRES_DB }   else { 'datalytics' }),
                      '-Fc')
        $proc = Start-Process -FilePath 'docker' -ArgumentList $dumpArgs -NoNewWindow -Wait -PassThru `
                              -RedirectStandardOutput $dumpPath -RedirectStandardError "$dumpPath.err"
        $ErrorActionPreference = 'Stop'
        if ($proc.ExitCode -ne 0) {
            $err = if (Test-Path "$dumpPath.err") { Get-Content "$dumpPath.err" -Raw } else { '' }
            throw "pg_dump failed (exit $($proc.ExitCode))`n$err"
        }
        Remove-Item "$dumpPath.err" -ErrorAction SilentlyContinue
    }
    finally {
        if ($Quiesce) {
            Write-Host "[q] Restarting the backend" -ForegroundColor Cyan
            Invoke-Native { docker compose start backend } 'docker compose start'
        }
    }

    # ── 3. Verify BEFORE rotating ─────────────────────────────────────────
    # A run of failed backups that rotates away the last good one is the worst
    # outcome a backup system has. Both artifacts are checked first.
    $dump = Get-Item $dumpPath -ErrorAction SilentlyContinue
    $tar  = Get-Item $tarPath  -ErrorAction SilentlyContinue
    if (-not $dump -or $dump.Length -eq 0) { throw "the dump is empty - NOT rotating older backups" }
    if (-not $tar  -or $tar.Length  -eq 0) { throw "the uploads archive is empty - NOT rotating older backups" }

    # A custom-format dump starts with the magic bytes "PGDMP". Checking them
    # catches the classic failure where an error message lands in the file and
    # the size check passes.
    $magic = [System.Text.Encoding]::ASCII.GetString(
        [byte[]](Get-Content $dumpPath -Encoding Byte -TotalCount 5))
    if ($magic -ne 'PGDMP') { throw "the dump does not look like a pg_dump archive (starts '$magic')" }

    Write-Host ("    dump {0:N1} MB · uploads {1:N1} MB" -f ($dump.Length/1MB), ($tar.Length/1MB)) -ForegroundColor Green

    # ── 4. Retention ──────────────────────────────────────────────────────
    if ($RetentionDays -gt 0) {
        $cutoff = (Get-Date).AddDays(-$RetentionDays)
        $old = Get-ChildItem $BackupDir -File |
               Where-Object { $_.LastWriteTime -lt $cutoff -and
                              ($_.Name -like 'datalytics-*.dump' -or $_.Name -like 'uploads-*.tar.gz') }
        if ($old) {
            Write-Host "[3] Removing $($old.Count) backup(s) older than $RetentionDays days" -ForegroundColor Cyan
            $old | Remove-Item -Force
        }
    }

    Write-Host ''
    Write-Host '-------------------------------------------------------------'
    Write-Host ' Backup complete' -ForegroundColor Green
    Write-Host '-------------------------------------------------------------'
    Write-Host "  $dumpPath"
    Write-Host "  $tarPath"
    Write-Host ''
    Write-Host '  A backup nobody has restored is a hypothesis. Prove it:'
    Write-Host "    .\scripts\restore.ps1 -Dump `"$dumpPath`" -Uploads `"$tarPath`" -WhatIf"
    Write-Host '-------------------------------------------------------------'
}
finally {
    Pop-Location
}
