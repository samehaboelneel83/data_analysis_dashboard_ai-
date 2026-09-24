# Backup and Recovery

What is durable in a Datalytics deployment, how to back it up, and how to prove the
backup works. Written for an air-gapped install, where there is no managed database
service to fall back on and no vendor to call.

> **If you read nothing else:** `postgres_data` is the only volume whose loss is
> unrecoverable. Back it up on a schedule, and restore it somewhere at least once
> before you need to.

> **There are scripts for this now.** `.\scripts\backup.ps1` and
> `.\scripts\restore.ps1` implement exactly the procedure below,
> including the ordering rule that is easy to get backwards. The manual commands
> stay because an operator on a non-Windows host still needs them, and because a
> script you cannot read is one you cannot trust in an emergency.
>
> ```powershell
> .\scripts\backup.ps1 -BackupDir D:\backups -RetentionDays 30
> .\scripts\restore.ps1 -Dump <dump> -Uploads <tar.gz> -WhatIf   # then -Confirm
> ```
>
> `backup.ps1` verifies the dump's `PGDMP` header **before** rotating anything, so a
> run of failures cannot delete the last good backup. `restore.ps1` refuses to run
> without `-Confirm`, and waits on `/health/ready` afterwards rather than declaring
> success when the files finish copying.

---

## What state exists

| Store | Volume / location | Durable? | Loss means |
|-------|------------------|----------|-----------|
| **PostgreSQL** | `postgres_data` | **Yes — critical** | Total loss. Every report, dataset definition, user, org, RLS rule, agent run, share link, schedule |
| **Uploaded files** | `uploaded_files` | **Yes — important** | Import-mode datasets lose their source data; report definitions survive but cannot render |
| **Valkey cache** | container-local | No | Nothing. Rebuilt on demand; a cold cache is slower, not broken |
| **Embeddings model** | baked into the image | No | Nothing. Restore by redeploying the image |

Two volumes matter. The rest is reconstructible.

### Why `uploaded_files` is not optional

A restored database without `uploaded_files` yields a system that looks intact —
datasets listed, reports openable — and fails at the first widget render, because the
Parquet/CSV behind each import-mode dataset is gone. **Back up both volumes, from the
same moment**, or restores will be subtly wrong rather than obviously broken.

---

## Backing up

### Database

`pg_dump` from the running container. Custom format (`-Fc`) is compressed and lets
`pg_restore` run in parallel:

```bash
docker compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-datalytics}" -d "${POSTGRES_DB:-datalytics}" -Fc \
  > "backup/datalytics-$(date +%Y%m%d-%H%M%S).dump"
```

Restore requires the **same major PostgreSQL version** (16, per `docker-compose.yml`).
Record the version alongside the dump.

### Uploaded files

```bash
docker run --rm \
  -v datalytics_uploaded_files:/data:ro \
  -v "$(pwd)/backup:/backup" \
  alpine tar czf "/backup/uploads-$(date +%Y%m%d-%H%M%S).tar.gz" -C /data .
```

Confirm the volume name first — Compose prefixes it with the project directory:

```bash
docker volume ls | grep uploaded_files
```

### Consistency between the two

The dump and the tarball should describe the same instant. Uploads are
write-once-then-referenced, so the safe ordering is:

1. Snapshot `uploaded_files` **first**
2. `pg_dump` **second**

A file present on disk but absent from the database is inert. A row referencing a file
that was never captured is a broken dataset. Taking files first makes the harmless
direction the only possible one.

For a strictly consistent pair, stop the backend for the duration:

```bash
docker compose stop backend    # frontend keeps serving; API returns errors
# ... take both backups ...
docker compose start backend
```

---

## Scheduling

Any scheduler works; the platform does not provide one for this. A daily dump with
14 days of retention:

```bash
#!/usr/bin/env bash
# backup-datalytics.sh — run daily via cron/Task Scheduler
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/srv/datalytics-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 1. files first (see "Consistency" above)
docker run --rm \
  -v datalytics_uploaded_files:/data:ro \
  -v "$BACKUP_DIR:/backup" \
  alpine tar czf "/backup/uploads-$STAMP.tar.gz" -C /data .

# 2. then the database
docker compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-datalytics}" -d "${POSTGRES_DB:-datalytics}" -Fc \
  > "$BACKUP_DIR/datalytics-$STAMP.dump"

# 3. fail loudly on an empty or truncated dump rather than rotating a good one away
if [ ! -s "$BACKUP_DIR/datalytics-$STAMP.dump" ]; then
  echo "FATAL: dump is empty — not rotating" >&2
  exit 1
fi

# 4. retention
find "$BACKUP_DIR" -name 'datalytics-*.dump'   -mtime +14 -delete
find "$BACKUP_DIR" -name 'uploads-*.tar.gz'    -mtime +14 -delete
```

Step 3 matters more than it looks: without it, a run of failed backups quietly deletes
the last good one.

---

## Restoring

### Full recovery onto a clean host

```bash
# 1. bring up ONLY postgres, so the backend cannot write during the restore
docker compose up -d postgres
docker compose exec postgres pg_isready -U datalytics    # wait for ready

# 2. restore the database
docker compose exec -T postgres \
  pg_restore -U datalytics -d datalytics --clean --if-exists \
  < backup/datalytics-20260828-020000.dump

# 3. restore uploaded files
docker run --rm \
  -v datalytics_uploaded_files:/data \
  -v "$(pwd)/backup:/backup" \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/uploads-20260828-020000.tar.gz -C /data"

# 4. start the rest
docker compose up -d

# 5. confirm the app considers itself servable
curl -fsS localhost:8000/health/ready | python -m json.tool
```

Step 5 is the actual success check. `/health/ready` returns 503 until migrations have
completed, so a 200 with `"postgres": {"status": "ok"}` means the restored database is
reachable *and* at the schema version this build expects.

### On schema version

The dump carries the schema it was taken from. Starting a **newer** build against an
older dump is fine — Alembic runs at startup under an advisory lock and migrates
forward. Restoring a **newer** dump into an **older** build is not supported; keep the
image tag with the backup.

---

## Verifying the backup

An untested backup is a guess. Run this quarterly, and after any change to the stack.

**Drill:**

1. Copy the most recent dump and tarball to a scratch host (or a second compose
   project with a distinct `COMPOSE_PROJECT_NAME`)
2. Restore per the steps above
3. Confirm, in order:
   - `curl -f localhost:8000/health/ready` returns 200
   - Logging in works — proves `users`, `organizations`, `roles` restored
   - A report list loads — proves report tables restored
   - **Open a report with an import-mode widget and confirm it renders** — the only
     step that proves `uploaded_files` and the database agree
   - A DirectQuery widget renders, if the environment can reach its source
4. Write down the date, the dump used, and the wall-clock time from start to serving

Step 3's fourth item is the one that catches the failure mode this document exists to
prevent. Steps 1–3 can all pass with a completely empty uploads volume.

**Record the drill.** "We have backups" is not a recovery plan; "we restored on
2026-08-28 in 22 minutes" is.

---

## What this does not cover

- **Point-in-time recovery.** Daily `pg_dump` means up to 24 hours of loss. If the
  business needs tighter, configure WAL archiving (`archive_mode=on`) and a base
  backup — out of scope here, and it changes the Postgres service definition.
- **Off-host replication.** Copying backups off the machine is deployment-specific and,
  in an air-gapped environment, usually a physical-media procedure.
- **Encryption at rest.** Dumps contain every row in the system, including anything
  classified as PII. Treat the backup directory with the same controls as the database.
