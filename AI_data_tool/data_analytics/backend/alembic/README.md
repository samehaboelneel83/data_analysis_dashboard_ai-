# Alembic migrations

Adopted in T1, alongside the existing `create_all` + `app.main._migrate`
path (both are kept this cycle -- see `app/main.py`'s `_run_alembic`
docstring for why). Going forward, **schema changes go through Alembic
revisions**, not new `ALTER TABLE ... IF NOT EXISTS` lines in `_migrate`.

## How startup picks up a revision

`_run_alembic()` runs before `create_all`/`_migrate` on every boot:

- Brand-new database -> `alembic upgrade head`.
- Database already stamped by Alembic -> `alembic upgrade head` (no-op if
  already current).
- Existing database from before T1 (has app tables, no `alembic_version`
  table) -> stamped at `0001_baseline` with no DDL, so it's adopted without
  being touched, then upgraded on the next boot as usual.

Like the enc:v1->v2 secrets migration, this step is wrapped so it can never
brick startup -- a failure is logged and swallowed, and `create_all` +
`_migrate` still run unconditionally right after it.

## Writing a new revision

1. Change the ORM model(s) in `app/models/models.py`.
2. Generate a revision against a scratch database (do not hand-write the
   op calls for anything autogenerate can produce):

   ```bash
   cd backend
   rm -f /tmp/scratch.db
   ALEMBIC_DATABASE_URL="sqlite+aiosqlite:////tmp/scratch.db" alembic upgrade head
   ALEMBIC_DATABASE_URL="sqlite+aiosqlite:////tmp/scratch.db" alembic revision --autogenerate -m "short description"
   ```

   (Run this inside the backend test image if the host doesn't have the
   project's Python env: `docker run --rm -v "<repo>:/repo" -w /repo/backend
   datalytics-backend:test bash -c "pip install -q alembic==1.13.2 && <commands above>"`.)

3. Read the generated file. Autogenerate is good at columns/tables/indexes,
   bad at data migrations, renames (it sees them as drop+add), and some
   constraint changes -- fix those by hand.
4. Also add the equivalent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (or
   similar idempotent statement) to `app.main._migrate` for this cycle, so
   a database that only ever ran `create_all` + `_migrate` (never adopted
   Alembic, e.g. a test harness that builds its own engine directly) still
   gets the column. `_migrate`'s statements are already IF-NOT-EXISTS /
   idempotent by convention -- keep new ones that way.
5. Test both paths: `alembic upgrade head` against a fresh DB, and against
   a DB already at the previous head.

## Why both create_all/_migrate AND Alembic

Belt-and-braces for this cycle: `create_all` provisions new tables for
free and `_migrate`'s idempotent `ALTER ... IF NOT EXISTS` statements are a
second, independent path to the same columns Alembic revisions add. Tests
that build their own engine directly (`tests/conftest.py`'s `db_session`
fixture) go through `create_all` only and never touch Alembic, so a model
change is invisible to them unless it also lands in `Base.metadata` (which
`create_all` reads directly) -- Alembic revisions are for deployed
databases, not for that fixture.
