# Running more than one API process (E02, E14)

Everything below was checked with two API processes on one PostgreSQL 16 and
one Valkey. The Compose stack already runs Valkey and sets `VALKEY_URL`.

## What every process shares, and how

| Concern | Where it lives | Why a second process is safe |
|---|---|---|
| Data, reports, users, jobs | PostgreSQL | The one source of truth. |
| Uploaded and imported files | `UPLOAD_DIR` (`/app/uploads`, the `uploaded_files` volume) | Must be the **same directory** for every process: a dataset row names a file path. On more than one host, mount shared storage there. |
| Durable jobs (imports, refreshes, deliveries, scoring, drift) | `jobs` table | Claims are compare-and-set with a lease; writes are fenced by the lease token. Every process runs a worker; each job runs once. |
| The scheduler (refreshes, deliveries, alerts, drift) | Each process ticks | Dataset refreshes take a PostgreSQL advisory lock per dataset; deliveries and daily drift checks are queued with a key per occurrence, so every process names the same job. |
| Rate limits, AI concurrent asks | Valkey (`core/shared_limits.py`) | One bucket per person, one counter per organisation, taken atomically. Measured: a limit of 10 across two processes answered 10 of 16 requests. |
| Widget and live-query results | Valkey (`services/cache_backend.py`) | A shared cache; every entry can be recomputed. |
| AI budgets, daily query quotas | PostgreSQL | Counted from stored usage, so every process sees the same total. |

## What stays per process

- The widget work gate (`WIDGET_WORK_MAX_CONCURRENCY`, 4 by default): how
  many widget queries one process runs at once. It bounds CPU per process, so
  it should be per process.
- Parsed-file memos (`services/frame_cache.py`): a file is parsed once per
  process.
- The organisation's quota row is cached for 30 seconds per process: a quota
  an admin changes reaches every process within half a minute.
- Without Valkey, or while it is unreachable, rate limits and ask counts fall
  back to each process's own (logged once, retried after 30 s): the ceiling
  is then per process.

## Checklist for a second replica

1. Same `DATABASE_URL`, `VALKEY_URL`, `SECRET_KEY` and `UPLOAD_DIR` storage.
2. Run migrations once (`alembic upgrade head`), not from every replica at
   the same moment.
3. Put the replicas behind one address; sessions are stateless tokens, so
   no stickiness is needed.
4. Check `/health/ready` on each.
