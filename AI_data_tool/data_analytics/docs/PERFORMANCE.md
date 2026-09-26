# Performance: targets and a measured baseline (E14)

The plan asks for performance that is measured, not asserted: targets at 1, 10
and 50 concurrent users, fairness between heavy and light work, and
cancellation that frees work. This page states the targets, how to measure
them, and the first measurement.

## How it is measured

`backend/scripts/bench_users.py` runs against a running stack. Each simulated
user is a **separate account** (made for the run with the admin role, deleted
after; limits are per person, so one account shared by fifty simulated people
would measure the rate limiter, not the product). Each user repeats what a
person reading dashboards does: list the dashboards, open one (the report, then
every widget's data in parallel, as the page does), list the datasets, preview
one, then read for 2 to 5 seconds. Alongside, a probe requests `/health/live`
four times a second: that trivial request stays fast only while heavy work is
kept off the event loop, so it is the fairness measure.

```
python backend/scripts/bench_users.py --base http://localhost:8000 \
    --email admin@datalytics.local --password demo-password \
    --users 1,10,50 --seconds 60 --out perf.json
```

It only reads. Numbers belong to the machine they were taken on: compare runs
on the same hardware.

## Targets (proposed; to agree with the owner)

| Measure | 1 user | 10 users | 50 users |
|---|---|---|---|
| A whole dashboard page (all widgets), p95 | ≤ 1 s | ≤ 3 s | ≤ 8 s |
| One widget's data, p95 | ≤ 1 s | ≤ 2 s | ≤ 5 s |
| Opening a dashboard, listing, a preview, p95 | ≤ 300 ms | ≤ 1 s | ≤ 5 s |
| A trivial request during the load, p95 (fairness) | ≤ 100 ms | ≤ 250 ms | ≤ 500 ms |
| Errors | 0 | 0 | 0 |

## Baseline: cloud workspace, 2026-09-26

Two API processes (each with its scheduler and job worker) on one PostgreSQL
16, a **2-CPU** Intel Xeon 2.8 GHz virtual machine with 7 GB of memory, the
demo seed plus the journeys' leftovers: 11 dashboards whose first page holds 1
to 38 widgets, over 6 imported datasets of 250 to 12,000 rows; DuckDB pushdown
on. 60 seconds per level.

| Request | 1 user p50 / p95 | 10 users p50 / p95 | 50 users p50 / p95 |
|---|---|---|---|
| Whole page (all widgets) | 136 / 528 ms | 176 / 1,875 ms | 2,611 / 6,194 ms |
| Widget data | 155 / 727 ms | 239 / 1,389 ms | 1,499 / 4,291 ms |
| Open dashboard | 21 / 24 ms | 31 / 256 ms | 1,261 / 4,422 ms |
| List dashboards | 26 / 32 ms | 36 / 514 ms | 1,493 / 3,464 ms |
| List datasets | 12 / 14 ms | 18 / 266 ms | 1,081 / 3,865 ms |
| Dataset preview | 12 / 15 ms | 18 / 158 ms | 800 / 3,065 ms |
| Trivial request during load | 4 / 6 ms | 5 / 76 ms | 98 / 306 ms |

451, 2,135 and 4,042 requests; **no errors** at any level.

**Reading it.** Every target is met on this small machine. At 50 users the
two CPUs are saturated: everything queues, including the light requests
(listing a dashboard waits behind widget queries), but nothing fails and the
trivial request stays under half a second, so the event loop is not blocked
by the heavy work. Widget data dominates a page: it is where more CPU, more
API processes or caching pay off first.

## Work nobody is waiting for is not done

A dashboard's widgets queue for a few work slots per API process
(`widget_work_max_concurrency`, 4 by default), behind a client queue of 6
requests per tab. Closing the page or changing a filter used to leave every
queued query to run to the end, holding slots the next readers waited for.
Now:

- **In the browser** (`services/api.ts`, `WidgetRenderer.tsx`): a widget lets
  go of its request when it unmounts or asks again. A request still in the
  tab's queue is never sent; one in flight is aborted, which closes its
  connection. A request shared by two widgets (identical bodies are sent
  once) is aborted only when both have let go. A late answer can no longer
  overwrite a newer one.
- **On the server** (`routers/widget_data.py`, `_run_gated`): a request
  whose connection closed while it waited for a slot is dropped without
  running (`499 client_closed`, counted per process). One already running
  finishes: a pandas pipeline cannot be stopped from outside its thread; its
  result is cached, so it is not lost if the reader returns. Exports,
  deliveries and background renders always run. Guest links and embeds drop
  like the app.

Measured: leaving the 38-widget demo dashboard 2.5 s after opening it, 6
requests were in flight (all aborted) and the other 32 were never sent.
Against real uvicorn with one work slot held, five requests whose clients
closed while queued were dropped and only the reader who stayed was run.

## Not done yet (E14)

- The same run on the owner's hardware and data, and the targets agreed.
- Fairness **across** processes: the rate limiter and the AI budgets'
  concurrent-ask counter are per process (documented in `core/rate_limit.py`).
- Stopping a widget query that is already running (DuckDB could be
  interrupted; pandas cannot).
- Larger data: a benchmark over the 1-million-row synthetic set
  (`bench_widget_data.py`, `bench_dashboard.py` exist for single-request
  timings).
