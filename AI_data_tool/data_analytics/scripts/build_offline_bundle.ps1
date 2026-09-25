<#
.SYNOPSIS
    Builds the Datalytics deployment images and packages them into a
    transferable offline bundle for an isolated (no-internet) network.

.DESCRIPTION
    Production runs with NO internet access. Everything that needs the
    internet (package installs, npm installs, base image pulls) must
    happen HERE, on a machine that has internet, before the artifacts
    are carried across the air gap.

    This script:
      1. Reads pre-built ("image:") services out of docker-compose.yml
         via regex (currently postgres:16-alpine; will also pick up
         valkey/valkey:8-alpine automatically once the O2 task adds it
         to the compose file - no edits needed here).
      2. Builds every service that only declares "build:" (no "image:")
         -- discovered by regex over docker-compose.yml, e.g. backend,
         frontend, embeddings (Task M1) -- via `docker compose build`,
         and locates the resulting local image names.
      3. `docker save`s every image (pulled + built) to
         offline_bundle/<image-name-sanitized>.tar
      4. Writes offline_bundle/MANIFEST.json: image names, digests (via
         `docker inspect`), the current git commit, and the build date.
      5. Prints the transfer + `docker load` + `docker compose up`
         instructions for the isolated network.

.NOTES
    PowerShell 5.1 compatible: no `&&`, no ternary (`?:`), no
    null-conditional operators.

.PARAMETER DryRun
    Skip `docker build` / `docker save` (which can take minutes and a
    lot of disk) and only print what WOULD be built/saved, still
    writing a structural MANIFEST.json placeholder. Useful for a fast
    structure check.

.PARAMETER SkipBuild
    Skip `docker compose build` for backend/frontend (assumes the
    images already exist locally) but still save + manifest them.
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$RepoRoot     = Split-Path -Parent $PSScriptRoot
$ComposeFile  = Join-Path $RepoRoot "docker-compose.yml"
$BundleDir    = Join-Path $RepoRoot "offline_bundle"
$ManifestPath = Join-Path $BundleDir "MANIFEST.json"

if (-not (Test-Path $ComposeFile)) {
    throw "docker-compose.yml not found at $ComposeFile"
}

New-Item -ItemType Directory -Force -Path $BundleDir | Out-Null

Write-Host "== Datalytics offline bundle builder ==" -ForegroundColor Cyan
Write-Host "Repo root:    $RepoRoot"
Write-Host "Compose file: $ComposeFile"
Write-Host "Bundle dir:   $BundleDir"
if ($DryRun)    { Write-Host "Mode:         DRY RUN (no build/save)" -ForegroundColor Yellow }
if ($SkipBuild) { Write-Host "Mode:         SKIP BUILD (assumes images exist)" -ForegroundColor Yellow }
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Pre-built ("image:") services from docker-compose.yml
# ---------------------------------------------------------------------------
$composeText = Get-Content -Path $ComposeFile -Raw
$imageMatches = [regex]::Matches($composeText, "(?m)^\s*image:\s*(\S+)\s*$")

$pulledImages = New-Object System.Collections.ArrayList
foreach ($m in $imageMatches) {
    $img = $m.Groups[1].Value.Trim()
    if ($pulledImages -notcontains $img) {
        [void]$pulledImages.Add($img)
    }
}

Write-Host "Pre-built images found in docker-compose.yml:" -ForegroundColor Cyan
foreach ($img in $pulledImages) { Write-Host "  - $img" }
Write-Host ""

# ---------------------------------------------------------------------------
# 2. Build backend + frontend (services with `build:` but no `image:`)
# ---------------------------------------------------------------------------
# Project name = compose default naming = lower-cased repo directory name.
$ProjectName = (Split-Path -Leaf $RepoRoot).ToLowerInvariant() -replace '[^a-z0-9_-]', ''

# Build-only ("build:", no "image:") services are discovered by regex
# rather than hand-maintained, so a future service (like Task M1's
# `embeddings`, added here) is picked up without editing this list again.
# Matches a 2-space-indented service name, then scans its body (lines
# indented 4+ spaces, up to the next 2-indent-or-less line) for a `build:`
# key.
$serviceHeaders = [regex]::Matches($composeText, "(?m)^  ([A-Za-z][\w-]*):\s*$")
$BuiltServices = New-Object System.Collections.ArrayList
for ($i = 0; $i -lt $serviceHeaders.Count; $i++) {
    $name = $serviceHeaders[$i].Groups[1].Value
    $bodyStart = $serviceHeaders[$i].Index + $serviceHeaders[$i].Length
    $bodyEnd = if ($i + 1 -lt $serviceHeaders.Count) { $serviceHeaders[$i + 1].Index } else { $composeText.Length }
    $body = $composeText.Substring($bodyStart, $bodyEnd - $bodyStart)
    if ($body -match "(?m)^\s{4,}build:\s*$") {
        [void]$BuiltServices.Add($name)
    }
}
if ($BuiltServices.Count -eq 0) {
    # Regex discovery found nothing (unexpected compose formatting) --
    # fall back to the known set rather than silently bundling nothing.
    Write-Warning "No build:-only services discovered via regex; falling back to known list (backend, frontend)."
    [void]$BuiltServices.Add("backend")
    [void]$BuiltServices.Add("frontend")
}

$BuiltImages = New-Object System.Collections.ArrayList
foreach ($svc in $BuiltServices) {
    # docker compose v2 default image name: <project>-<service>
    [void]$BuiltImages.Add("$ProjectName-$svc")
}

Write-Host "Images to build locally (docker compose build):" -ForegroundColor Cyan
foreach ($img in $BuiltImages) { Write-Host "  - $img" }
Write-Host ""

if (-not $DryRun -and -not $SkipBuild) {
    Write-Host ("Building " + ($BuiltServices -join ", ") + " images ...") -ForegroundColor Cyan
    Push-Location $RepoRoot
    try {
        docker compose -f $ComposeFile build @BuiltServices
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose build failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
} elseif ($DryRun) {
    Write-Host "[dry-run] skipping docker compose build" -ForegroundColor Yellow
} else {
    Write-Host "[skip-build] assuming images already exist locally" -ForegroundColor Yellow
}
Write-Host ""

# ---------------------------------------------------------------------------
# 2b. Pull the pre-built images too so `docker save` has something local
#     to work with (idempotent if already pulled).
# ---------------------------------------------------------------------------
if (-not $DryRun) {
    foreach ($img in $pulledImages) {
        Write-Host "Pulling $img ..." -ForegroundColor Cyan
        docker pull $img
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "docker pull failed for $img (continuing; it may already be present locally)"
        }
    }
    Write-Host ""
}

# ---------------------------------------------------------------------------
# 3. docker save each image
# ---------------------------------------------------------------------------
$AllImages = New-Object System.Collections.ArrayList
foreach ($img in $pulledImages) { [void]$AllImages.Add($img) }
foreach ($img in $BuiltImages)  { [void]$AllImages.Add($img) }

$manifestImages = New-Object System.Collections.ArrayList

foreach ($img in $AllImages) {
    $safeName = ($img -replace '[\/:]', '_')
    $tarPath = Join-Path $BundleDir "$safeName.tar"

    $digest = ""
    $imageId = ""
    $sizeBytes = 0

    if (-not $DryRun) {
        # Confirm the image actually exists locally before saving.
        $inspectJson = docker inspect $img 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $inspectJson) {
            Write-Warning "Image '$img' not found locally - skipping save. Build/pull it first."
        } else {
            $inspectObj = $inspectJson | ConvertFrom-Json
            $imageId = $inspectObj[0].Id
            if ($inspectObj[0].RepoDigests -and $inspectObj[0].RepoDigests.Count -gt 0) {
                $digest = $inspectObj[0].RepoDigests[0]
            } else {
                $digest = $imageId
            }

            Write-Host "Saving $img -> $tarPath ..." -ForegroundColor Cyan
            docker save -o $tarPath $img
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "docker save failed for $img"
            } elseif (Test-Path $tarPath) {
                $sizeBytes = (Get-Item $tarPath).Length
                $sizeMb = [math]::Round($sizeBytes / 1MB, 1)
                Write-Host "  saved: $sizeMb MB" -ForegroundColor Green
            }
        }
    } else {
        Write-Host "[dry-run] would save $img -> $tarPath" -ForegroundColor Yellow
    }

    [void]$manifestImages.Add([ordered]@{
        image      = $img
        tar_file   = "$safeName.tar"
        image_id   = $imageId
        digest     = $digest
        size_bytes = $sizeBytes
    })
}
Write-Host ""

# ---------------------------------------------------------------------------
# 4. MANIFEST.json
# ---------------------------------------------------------------------------
$gitCommit = ""
try {
    Push-Location $RepoRoot
    $gitCommit = (git rev-parse HEAD 2>$null)
    Pop-Location
} catch {
    $gitCommit = "unknown"
}
if (-not $gitCommit) { $gitCommit = "unknown" }

$manifest = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    git_commit   = $gitCommit.Trim()
    project_name = $ProjectName
    dry_run      = [bool]$DryRun
    images       = $manifestImages
}

$manifest | ConvertTo-Json -Depth 6 | Set-Content -Path $ManifestPath -Encoding utf8
Write-Host "Manifest written: $ManifestPath" -ForegroundColor Green
Write-Host ""

# ---------------------------------------------------------------------------
# 5. Transfer / load instructions
# ---------------------------------------------------------------------------
Write-Host "== Transfer + load instructions (isolated network) ==" -ForegroundColor Cyan
Write-Host "1. Copy the entire 'offline_bundle' directory (all *.tar files"
Write-Host "   + MANIFEST.json) plus this repository checkout across the air gap"
Write-Host "   (USB drive / secure file transfer)."
Write-Host "2. On the target host, for each *.tar file, run:"
Write-Host "     docker load -i offline_bundle\<name>.tar"
Write-Host "3. Verify loaded images match MANIFEST.json:"
Write-Host "     docker images"
Write-Host "4. From the repo root, start the stack:"
Write-Host "     docker compose up -d"
Write-Host "   (compose will use the already-loaded images/tags - no pull needed)."
Write-Host "5. See docs/OFFLINE_DEPLOYMENT.md for first-boot expectations"
Write-Host "   (alembic schema adoption/stamp) and what stays disabled offline."
Write-Host ""
Write-Host "Done." -ForegroundColor Green
