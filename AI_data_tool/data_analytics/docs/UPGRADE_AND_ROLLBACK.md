# Upgrade and Rollback

How to move a running Datalytics from one version to the next, how to go back,
and what a rehearsal of both showed (E02). Read with
[`BACKUP_AND_RECOVERY.md`](BACKUP_AND_RECOVERY.md): every upgrade starts with a
backup, and one of the two ways back is a restore.

> **If you read nothing else:** back up first; the new version migrates the
> database by itself when it starts, and `/health/ready` answers 503 until it
> has. To go back, either downgrade the schema *with the new version's
> image* and then start the old one, or restore the backup you took first.

---

## What changes the database

The backend migrates on startup (`main._run_alembic`, under an advisory lock so
two replicas cannot both run it). A failed migration is recorded and
`/health/ready` answers 503 with the error, so a broken upgrade never looks
healthy. The schema revision is in `alembic_version`:

```powershell
docker compose exec postgres psql -U datalytics -d datalytics -tAc "select version_num from alembic_version"
```

| Version | Schema revision |
|---|---|
| `e5e4ea0` (last pushed, `origin/main` on 2026-09-26) | `0038_user_tokens_valid_after` |
| `local_main` on 2026-09-26 (not yet pushed) | `0041_report_releases` (adds `datasets.content_sha256`, `jobs`, `report_releases`) |

Every revision has a `downgrade`. `0039`–`0041` are schema-only: they add a
column and two tables and rewrite no existing row, so downgrading them removes
what they added and leaves everything else as it was. (Two older revisions,
`0020` and `0022`, do move data; a rollback past them is a restore, not a
downgrade.)

## Upgrade

```powershell
.\scripts\backup.ps1 -BackupDir D:\backups          # 1. a backup you have just verified
git pull                                             # 2. the new version
docker compose build backend frontend
docker compose up -d                                 # 3. it migrates as it starts
Invoke-WebRequest http://localhost:8000/health/ready # 4. repeat until 200
```

Then open a dashboard you know and check its numbers, and run the browser
journeys (`frontend/e2e/journeys/*.mjs`) if you have them set up.

## Rollback

Two ways back. Choose by what happened since the upgrade.

**A. Downgrade the schema, keep the data** (the upgrade is broken, but people
have already done work on it that you want to keep). The downgrade has to run
with the **new** image, because only it has the revisions to undo:

```powershell
docker compose stop backend
docker compose run --rm --no-deps backend alembic downgrade 0038_user_tokens_valid_after
git checkout <previous version>
docker compose build backend frontend
docker compose up -d
```

What is lost: only what the rolled-back revisions hold. From `0041` to `0038`
that is the job history (`jobs`), dashboard releases (`report_releases`; a
published dashboard shows its draft again, as it did before releases existed)
and the upload fingerprints (`datasets.content_sha256`; duplicate-upload
detection starts afresh). Datasets, dashboards, edits and imports made while
upgraded all stay.

**B. Restore the backup** (the upgrade damaged data, or nothing done since
matters). Everything after the backup is lost; that interval is your recovery
point.

```powershell
git checkout <previous version>
docker compose build backend frontend
.\scripts\restore.ps1 -Dump <dump> -Uploads <tar.gz> -WhatIf   # then -Confirm
```

## Restarts

A restart, a crash or `kill -9` loses no committed work and repeats none.
Queued imports and refreshes are durable jobs (`services/jobs.py`): a job whose
worker died keeps its row, its lease runs out (60 s), and the next worker
resumes it as the next attempt. A refresh fetches without touching the dataset
file and writes it only after it has fenced its own success, so an incremental
refresh interrupted part-way appends its rows once. Work that runs inside a
request (a synchronous import or refresh) either committed before the crash or
did not happen; there is nothing to resume, and the person sees the request fail.

---

## Rehearsal record: 2026-09-26

On PostgreSQL 16 in the cloud workspace, with the two versions running as
plain processes (no Docker there). The Compose commands above are the same
steps; the image build was not part of it.

| Step | What was done | Result |
|---|---|---|
| 1. Clean install | `e5e4ea0` on an empty database | Migrated to `0038`, ready in 4.8 s. Admin, demo seed (6 datasets, 8 dashboards, 121 widgets), a 12,000-row import from a connection, a new dashboard published |
| 2. Backup | `pg_dump -Fc` and the uploads folder | 0.3 s, 1.4 MB |
| 3. Upgrade | `local_main` (with the E12 refresh jobs) started on that database | `0039`, `0040`, `0041` applied at startup; ready in 3.8 s. Same datasets, dashboards and widget figures as before; the only table changes are the three new ones, empty. On the upgraded data: the first edit of the published dashboard made its release; a queued import and a queued refresh both succeeded |
| 4. Rollback A | `alembic downgrade 0038` with the new code, then `e5e4ea0` | Downgrade 0.9 s; ready in 3.6 s. Everything from before the upgrade is as it was; the import and the dashboard edit made while upgraded are still there; jobs and releases are gone |
| 5. Upgrade again | `local_main` on the rolled-back database | The three revisions applied again; ready in 3.6 s; same figures |
| 6. Rollback B | The step-2 backup restored into a new database, then `e5e4ea0` | Restore 3.3 s, ready 3.4 s later. Datasets, dashboards, widget figures and every table count equal to backup time |
| 7. Restart mid-import | A queued 2,000,000-row import; `kill -9` of the server while it read the source; restart | The job resumed as attempt 2 when its lease ran out (44 s after the restart) and succeeded: one dataset of 2,000,000 rows, no orphan file |
| 8. Restart mid-refresh | A queued incremental refresh adding 100,000 rows; `kill -9` while it ran; restart | Nothing written before the kill (file, row count and watermark unchanged); attempt 2 appended once: 2,100,000 rows, all ids distinct, watermark advanced once |

Also seen: an incremental refresh that would take a dataset past `IMPORT_ROW_CAP`
(2,000,000 by default) is refused and writes nothing; step 8 ran with the cap
raised to 3,000,000.

**Recovery point and time.** Not yet agreed with the owner (plan E02). What the
rehearsal measured at this size: restore plus startup in under 7 seconds. Both
scale with the database and the uploads: time `restore.ps1` on a copy of the
real backup to know the recovery time, and the backup schedule sets the
recovery point (a nightly `backup.ps1` means up to a day of work).
