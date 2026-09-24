# Insights on DirectQuery — Implementation Plan

> **For agentic workers:** steps use checkbox (`- [ ]`) syntax. Tick a step only after its
> command has been RUN and its output read.

**Goal:** the six statistical detectors run against a live source, so a DirectQuery dataset
gets the same unprompted findings — and the same deterministic, no-AI dashboard — an import
dataset gets. Today all three of these refuse it:

| Endpoint | Message |
|---|---|
| `POST /datasets/{id}/insights` | "Insights run over import-mode datasets" |
| `POST /datasets/{id}/suggest-dashboards` | "Dashboard suggestions run over import-mode datasets" |
| `POST /reports/{id}/suggest-widgets` | (same guard) |

The refusal is honest about the implementation and wrong about the requirement: **every one of
the six detectors is an aggregate**, and pushing aggregates into SQL is precisely what
DirectQuery already does for widgets.

## Why this is smaller than it looks

`services/direct_query.py` already supplies everything the detectors need:

- **`_base_query_sql(dataset, rls_where)`** — the secured base query with row-level security
  pushed down. Every detector query wraps this, so the security story needs no new thinking:
  a detector sees exactly the rows a widget would.
- **`_build_where(filters)`** and **`_validate_known_columns`** — filters and the
  column allowlist.
- **`_finalize_for_dialect(sql, dialect)`** — sqlglot transpile, so one builder serves every
  supported engine rather than one per dialect.
- **`CORR(a, b)` is already emitted** by `build_correlation_matrix_sql`. The correlation
  detector is the one people assume is hardest and it has a working precedent in this file.
- **`_RANDOM_FN`** — random sampling per dialect, already mapped.

## The design decision: exact aggregates, never a sample

The tempting shortcut is to fetch N rows and run the existing pandas detectors over them.
Reject it. `insights.py`'s stated contract is *"Every number is computed here, never guessed:
each finding carries the figures its sentence states, so the UI can show exactly what the
words claim."* A finding that says "Cardiology carries 62% of wait time" must be 62% of the
data, not 62% of a sample — and a `LIMIT` without `ORDER BY random()` is not even a sample,
it is whatever the engine returned first.

So each detector becomes a GROUP BY, and the numbers stay exact. The sampling helpers stay
where they belong: fetching rows for scatter-shaped widgets, which are about individual marks
rather than totals.

## What each detector becomes

Five queries cover all six detectors (standout and laggard read the same result set):

| Detector | SQL |
|---|---|
| `trend` | `SELECT date_trunc('month', d) p, SUM(m) FROM base GROUP BY 1 ORDER BY 1` |
| `standout` / `laggard` | `SELECT cat, SUM(m), COUNT(*) FROM base GROUP BY 1` + the grand total |
| `correlation` | `SELECT CORR(a,b) ... ` — the existing builder's shape, per measure pair |
| `outlier_impact` | `percentile_cont(0.25 / 0.75) WITHIN GROUP (ORDER BY m)` for the fences, then a second pass counting and summing beyond them |
| `data_quality` | `COUNT(*) - COUNT(col)` per column; `MIN(d)`, `MAX(d)`, `COUNT(DISTINCT date_trunc('month', d))` for coverage gaps |

`outlier_impact` is the only one needing a capability not already exercised here
(`percentile_cont`). Engines without it must be **named and skipped**, not silently dropped —
"not run on this source" and "found nothing" are different statements and only one of them is
about the data.

## Global constraints

- Every query wraps `_base_query_sql`, so RLS is pushed down. Do not add an
  `apply_rls_filter` call site — `tests/test_rls_base_frame_choke_point.py` allowlists them.
- Denied columns are dropped BEFORE any SQL is built, exactly as the import path drops them
  from the frame. A column this role cannot see must never reach a `SELECT` list.
- The detectors' **scores, thresholds and sentence wording stay in `insights.py`**. This work
  changes where the NUMBERS come from, never what counts as interesting — otherwise the two
  modes drift into two different products.
- Column count is bounded the way the import path bounds it: `MAX_MEASURES = 6`,
  `MAX_CATEGORIES = 6`, `MIN_ROWS = 20`.
- One round trip per detector, not per column pair. A 40-column dataset must not become 800
  queries against the customer's database.
- Services never import FastAPI (`tests/test_layer_conformance.py`).

---

## Task 1: The aggregate builders

**Files:** `backend/app/services/insights_sql.py` (new), `backend/tests/test_insights_sql.py` (new FILE — bump both doc counts)

- [ ] 1.1 `build_trend_sql`, `build_category_share_sql`, `build_correlation_sql`,
      `build_outlier_fence_sql`, `build_quality_sql` — each takes `(dataset, columns, rls_where)`
      and returns `(sql, params)`, wrapping `_base_query_sql`
- [ ] 1.2 Every builder goes through `_finalize_for_dialect`
- [ ] 1.3 Tests assert on EXECUTED ROWS against a real SQLite/Postgres fixture, never on the
      SQL string — a builder that compiles and returns the wrong number is the defect this
      repository has shipped before

## Task 2: A detector source that is not a DataFrame

**Files:** `backend/app/services/insights.py`, `backend/tests/test_insights.py`

- [ ] 2.1 Extract each detector's INPUT into a small struct (periods+totals, category
      shares, correlation pairs, fences, null counts) so the detector body is identical
      whichever mode produced it
- [ ] 2.2 `generate_insights_from_aggregates(aggs, roles, labels, value_labels)` — the same
      findings, the same scores, the same sentences
- [ ] 2.3 A parity test: the SAME data as an import frame and as a DirectQuery source must
      produce the SAME findings. This is the test that keeps the two modes one product

## Task 3: Lift the three guards

**Files:** `backend/app/routers/datasets.py`, `backend/app/routers/reports.py`, their tests

- [ ] 3.1 `/datasets/{id}/insights` routes DirectQuery to the aggregate path
- [ ] 3.2 `/datasets/{id}/suggest-dashboards` with an EMPTY goal — the deterministic path —
      works on DirectQuery. (With a goal it also can: the profile is aggregates too)
- [ ] 3.3 `/reports/{id}/suggest-widgets` and `compose-page`
- [ ] 3.4 The guards do not disappear, they narrow: a source whose engine cannot serve a
      detector still refuses THAT detector, with its name and reason
- [ ] 3.5 Endpoint tests for both modes

## Task 4: Say which mode answered

**Files:** frontend insights surfaces, `ColumnMeaningPanel`-style honesty

- [ ] 4.1 The response says whether findings came from the frame or from pushed-down
      aggregates, and names any detector skipped for lack of engine support
- [ ] 4.2 The Insights page shows it. A person comparing two datasets deserves to know one
      was measured over every row live and the other over an imported snapshot

---

## Already fixed on the way in (2026-09-19)

`SuggestDashboardsDialog` printed axios's `Request failed with status code 400` and discarded
the server's `detail`, which is how a precise, actionable message ("Dashboard suggestions run
over import-mode datasets") reached a user as noise. Both catch blocks now prefer
`response.data.detail`; 2 tests pin it.

## Verification before "done"

- [ ] The parity test passes: identical data, identical findings, both modes
- [ ] `test_rls_base_frame_choke_point.py` and `test_layer_conformance.py` pass
- [ ] A DirectQuery dataset on the live Olist connection produces findings through the
      ENDPOINT, not just the service
- [ ] Query count per insights run is bounded and measured, not assumed
- [ ] Full backend and frontend suites green
