# Data pipeline — closing the production gaps

Date: 2026-10-10 · Owner request: discuss ETL vs ELT and the six production
capabilities (incremental ingestion, schema validation, data quality, failure
recovery, lineage and audit, performance monitoring), then "close the gap", and
"make sure lineage shows all the process".

## Where Datalytics stands (ETL vs ELT)

A hybrid, which suits a BI tool: **import** is ETL-like (query → Parquet copy),
**prep steps / calculated columns / measures** are ELT-like (the raw import is kept and
transforms run when data is read), and **DirectQuery** is pure push-down. Heavy work
belongs at the source (the guided setup writes that SQL); in-app transforms suit small
or medium data and sources that cannot compute.

## What already existed (found while reading the code)

My first gap table in the discussion under-counted. These were already in place from an
earlier "pipeline plan":

| Capability | Already there |
|---|---|
| Incremental | Watermark column; **merge by key** (upsert); look-back window; periodic full reload; full reload as fallback |
| Schema | Refresh refused if a column something uses disappears (with rename mapping); **notes** on dropped, new and retyped columns on every run |
| Quality | Saved checks: no blanks, unique, allowed values, row count, row drop %, custom rule; **warn or block**. A blocked load keeps the previous data live, and owners are told |
| Recovery | Job system with 3 attempts, resume after a crash, retry as a linked job, no duplicate runs; scheduler backoff |
| Lineage / audit | Lineage page (sources → datasets → reports, joins, built datasets, failing refreshes); "what uses this column"; audit log; refresh run history |
| Monitoring | Each run: status, rows, duration, error, check results; query log |

## What was missing, and what was built

| # | Gap | Built |
|---|---|---|
| P1 | Rows **deleted at the source** stayed in an incremental dataset forever | "Remove rows deleted at the source" (needs a key): each refresh reads the source's current keys and removes rows that are gone. If the source returns **no** keys, nothing is removed and the run says why |
| P2 | No **referential-integrity** check | Check "values exist in another dataset" (e.g. every `customer_id` exists in Customers.id). Same organisation only, and the editor must be able to read that dataset. Counts only, never values |
| P3 | Schema drift was only noted, **never blocking** | Check "columns stay the same": a missing or retyped column (and optionally any new column) fails it, as warn or block |
| P4 | Runs recorded only rows and time | Each successful run records rows/sec and file size. A run is **"slower than usual"** at more than 3× the median of the last 10 successful runs and over 30 s; owners are told once per slow streak |
| P5 | Lineage stopped at the dataset; nothing showed how a **column** is made | Column lineage, numbered in order: **source** (connection › table › column, upload, query, built-from datasets, or each formula input's own source, followed back through renames) → **load** (import or live, full or incremental, key, delete removal, last run's status, rows, time and error, plus the dataset's SQL for editors) → **transformation steps** that make it, change it or change which rows exist (joins and appends name the other dataset) → **formula** → **checks** → **used by** (charts with their report, measures, alerts, filters, hierarchies, summary tables) |

### Older bugs found and fixed on the way

- **An incremental run with no new rows corrupted number columns.** The empty fetch had
  untyped columns; merged onto the file, the whole-number ids became
  `1970-01-01 00:00:00.000000001`. This was confirmed on the committed code. A quiet
  night (the commonest incremental run) was enough to trigger it.
- **Merge by key duplicated rows when the key had gaps**: such keys are stored as 7.0,
  and "7.0" ≠ "7". Keys now compare as normalised text everywhere (merge, delete
  removal, reference check).
- **MySQL incremental filter compared a constant**: the watermark column was quoted
  `"col"`, which MySQL reads as text. It's now quoted for the source's dialect.

### Not built: resumable large imports

An import is one query, capped at 2,000,000 rows; failed jobs already retry 3 times. A
true resume needs a stable order (keyset paging on a key) and staging the partial file:
real work for little gain at this cap. **Revisit if the cap is raised** or imports run
past several minutes.

## Results

| Check | Result |
|---|---|
| `backend/tests/test_pipeline_gaps.py` (real SQLite sources: delete removal, empty-source guard, 7 vs 7.0 merge, no-new-rows regression, MySQL quoting, both new checks, org isolation, slow-run detection and single alert, whole-process lineage incl. rename trace-back and reader vs editor) | 20 pass |
| Related backend suites (refresh, incremental, checks, pipeline, scheduler, jobs, dependencies, lineage, dataflows, datasets, schema) | 558 pass |
| Frontend: 342 files / 4,285 tests, type check, build | pass |
| Live (Cars dataset, PostgreSQL): `price_egp` lineage → Cars DB › cars_hatla2ee › price_egp → full import, last load ok 9,319 rows in 0.3 s → used by 11 charts of "Pricing & Inventory Health" | ✅ |
| Live: manual refresh recorded 31,697 rows/s and 1.16 MB; history shows "0.3 s · 31,697 rows/s" | ✅ |
| Live: both new checks ran on real data (temporary, then removed); a reference to a missing column was refused with a plain reason | ✅ |
| Console on a fresh load | clean |

Migration `0060_pipeline_gaps` adds `watermarks.reconcile_deletes` and
`refresh_runs.metrics` (applied locally).
