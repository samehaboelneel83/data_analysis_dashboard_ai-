# Demo Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Load demo content" action that fills the current org with datasets and reports exercising all 42 widget types and the app's major features, so a new user sees a working product and a developer gets a live regression surface.

**Architecture:** A backend service (`app/services/demo_content.py`) builds CSV files, Dataset rows and Report/Page/Widget rows in one transaction, behind `POST /api/v1/demo/seed`. A button on the Datasets page calls it. Everything it creates is named with a `Demo — ` prefix and tagged in config, so re-seeding replaces only demo content and never touches the user's own.

**Tech Stack:** FastAPI, SQLAlchemy async, pandas, React 18 + TypeScript.

**Spec:** none — design settled directly with the user:
- delivery: in-app button plus endpoint (not a script, not auto-seed on org creation)
- coverage: all 42 widget types
- features: display rules + formatting, interactions, calculated columns + measures, one DirectQuery dataset

## Global Constraints

- **Org scoping is mandatory.** Every row created carries `org_id` of the requesting user. A demo seed must never be visible from another org. Follow the existing `org_scope` helpers; do not hand-roll filters.
- **Idempotent and non-destructive.** Re-seeding deletes only rows this feature created, identified by a marker, never by name matching alone. A user's own dataset called "Demo — Sales" must survive.
- **`display_rules` fail OPEN; `apply_rls_filter` fails CLOSED.** Do not change either.
- **Config keys are contracts.** Use the exact keys the renderers read; a typo yields a widget that looks configured and renders nothing. Verify each against its consumer.
- Commit only files actually changed, by explicit path. Never `git add -A`.
- Backend baseline **711 passed**; frontend **465 passed / 46 files**.
- Tests must distinguish pass from fail: for each, confirm it fails before the code exists.

---

### Task 1: Demo datasets

**Files:**
- Create: `backend/app/services/demo_content.py`, `backend/tests/test_demo_datasets.py`

**Interfaces:**
- Produces: `build_demo_frames() -> dict[str, pandas.DataFrame]` and `DEMO_MARKER = "__demo__"`.

Four frames, each shaped for the widgets that need it. Widgets are not interchangeable in their data needs: a Gantt needs start/end dates, a word cloud needs text, a waterfall needs sequential deltas, a correlation matrix needs several correlated numerics.

| frame | columns | serves |
|---|---|---|
| `sales` | `date, region, country, product, category, channel, revenue, units, cost, margin_pct, target` | bar, line, area, pie, donut, table, crosstab, matrix, list, kpi, card, gauge, funnel, ribbon, treemap, heatmap, slicer, step, dot_plot, needle, butterfly, dual_axis_*, comparative_time_series, waterfall |
| `metrics` | `sample_id, height, weight, bmi, score_a, score_b, group` | histogram, box_plot, scatter, bubble, bubble_change, correlation_matrix, parallel_coordinates, numeric_series, vector_plot |
| `projects` | `task, owner, phase, start_date, end_date, progress_pct` | schedule (Gantt) |
| `feedback` | `comment, sentiment, topic` | word_cloud |

Requirements that matter:
- `sales` spans **24 consecutive months** so time-series widgets have a real axis, and carries at least one **negative** `margin_pct` and one negative `revenue` (a refund) so display-rule bands and diverging charts have something to show.
- `metrics` must have a genuine correlation between `height`/`weight` and a deliberately weak one between `score_a`/`score_b`, or the correlation matrix demo shows nothing worth seeing.
- Data is generated from a **fixed seed**, so the demo is reproducible and tests can assert exact totals.
- Row counts modest (sales ~2000, others ~200) — big enough to be interesting, small enough to seed fast.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_demo_datasets.py
import pandas as pd
from app.services.demo_content import build_demo_frames


def test_every_frame_is_present_and_non_empty():
    frames = build_demo_frames()
    assert set(frames) == {"sales", "metrics", "projects", "feedback"}
    for name, df in frames.items():
        assert len(df) > 0, name


def test_generation_is_deterministic_so_the_demo_is_reproducible():
    a, b = build_demo_frames()["sales"], build_demo_frames()["sales"]
    pd.testing.assert_frame_equal(a, b)


def test_sales_spans_two_years_of_months_for_the_time_series_widgets():
    s = build_demo_frames()["sales"]
    months = pd.to_datetime(s["date"]).dt.to_period("M").nunique()
    assert months == 24


def test_sales_carries_negative_values_so_bands_and_diverging_charts_have_something_to_show():
    s = build_demo_frames()["sales"]
    assert (s["margin_pct"] < 0).any()
    assert (s["revenue"] < 0).any()


def test_metrics_correlate_where_the_correlation_matrix_needs_them_to():
    m = build_demo_frames()["metrics"]
    strong = m["height"].corr(m["weight"])
    weak = m["score_a"].corr(m["score_b"])
    # Asserting BOTH is the point: a frame of pure noise passes the first check alone
    # if the threshold is low, and a frame of one repeated pattern passes the second.
    assert strong > 0.7
    assert abs(weak) < 0.3


def test_projects_have_ordered_date_ranges_a_gantt_can_draw():
    p = build_demo_frames()["projects"]
    assert (pd.to_datetime(p["end_date"]) > pd.to_datetime(p["start_date"])).all()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest -q tests/test_demo_datasets.py`
Expected: FAIL — no module `app.services.demo_content`

- [ ] **Step 3: Implement `build_demo_frames`**

Use `numpy.random.default_rng(20260822)` for every draw. Derive `margin_pct` from `revenue`/`cost` rather than drawing it independently, so the numbers are internally consistent and a calculated-column demo can recompute it.

- [ ] **Step 4: Run to verify it passes**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/demo_content.py backend/tests/test_demo_datasets.py
git commit -m "Add demo dataset frames"
```

---

### Task 2: Persisting the demo datasets

**Files:**
- Modify: `backend/app/services/demo_content.py`
- Create: `backend/tests/test_demo_seed_datasets.py`

**Interfaces:**
- Consumes: `build_demo_frames`, `DEMO_MARKER`.
- Produces: `async def seed_demo_datasets(db, org_id) -> dict[str, Dataset]`.

Writes each frame to a CSV under `settings.upload_dir` and creates the `Dataset` + `DatasetColumn` rows, exactly as an upload would — the demo must go through the same representation as real data, or it stops being a regression surface.

- Mark demo rows so cleanup is exact. Put `DEMO_MARKER` in `Dataset.column_meta` under a reserved key; **do not** identify demo rows by name.
- Set `row_count`, `col_count`, `file_size` and per-column `dtype` the same way the upload path does; reuse its helpers rather than duplicating detection.
- Seeding twice must leave one copy, not two.

Tests: datasets are created with the right `org_id`; a second seed replaces rather than duplicates; a same-named dataset **without** the marker survives a re-seed; the CSV is readable by the loader the app uses.

- [ ] **Step 1: Write the failing tests** (per the bullets above; assert the marker path explicitly)
- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 3: Demo reports — core and distribution widgets

**Files:**
- Modify: `backend/app/services/demo_content.py`
- Create: `backend/tests/test_demo_reports.py`

**Interfaces:**
- Produces: `async def seed_demo_reports(db, org_id, datasets) -> list[Report]`.

Two reports for now:

1. **Demo — Sales Overview** (`sales`): kpi ×3, card, bar, line, area, pie, donut, table, crosstab, matrix, list, gauge, funnel, ribbon, treemap, heatmap, slicer, text, button, shape, image, waterfall, step, dot_plot, needle, butterfly
2. **Demo — Distributions** (`metrics`): histogram, box_plot, scatter, bubble, correlation_matrix, parallel_coordinates, numeric_series, vector_plot

Every widget needs a `layout` that does not overlap its neighbours and a `config` whose keys the renderer actually reads. **Verify each config key against its consumer before using it** — `WidgetRenderer.tsx` and `app/services/widget_data.py` are the authorities. A widget that renders empty is worse than one omitted.

The test that matters: for each widget in each demo report, call the widget-data path and assert it returns a non-empty result, so a mis-keyed config fails the build rather than shipping a blank tile.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 4: Demo reports — time, change, and text

**Files:**
- Modify: `backend/app/services/demo_content.py`
- Modify: `backend/tests/test_demo_reports.py`

Two more reports, completing the 42:

3. **Demo — Time & Change** (`sales`): dual_axis_bar, dual_axis_line, dual_axis_bar_line, dual_axis_time_series, comparative_time_series, bubble_change
4. **Demo — Projects & Feedback** (`projects`, `feedback`): schedule (Gantt), word_cloud

Add a test asserting **all 42 widget types from `WidgetType` appear across the demo reports** — derived from the type list, not a hardcoded copy, so a newly added widget type fails this test until the demo covers it.

- [ ] **Step 1: Write the failing test (coverage over the real type list)**
- [ ] **Step 2: Run to verify it fails**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify it passes**
- [ ] **Step 5: Commit**

---

### Task 5: The feature layer

**Files:**
- Modify: `backend/app/services/demo_content.py`
- Create: `backend/tests/test_demo_features.py`

Layer the app's own features onto the demo content:

- **Calculated column** on `sales` (e.g. `profit = revenue - cost`) and a **measure** (post-aggregation, e.g. margin on the group's totals) — these exercise two different engines and must not be confused for each other.
- **Column formats**: currency on `revenue`, percent on `margin_pct`.
- **Display rules**: an `interval` (bands) rule on the gauge, a `value_map` on a table column, and an `expression` rule — one of each kind, since all three are now authorable.
- **Table chrome**: totals on, banding, row lines.
- **Interactions**: a slicer, cross-filtering between two widgets on the Sales page, a `hierarchy` for drill-down, a bookmark, and a button navigating to another page.

Tests: each artefact exists and is wired to something that reads it. For the display rules specifically, evaluate them against real shaped results and assert they produce styles **and no `rule_errors`** — a rule pointed at the wrong column fails open and would otherwise ship silently broken.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 6: A DirectQuery demo dataset

**Files:**
- Modify: `backend/app/services/demo_content.py`
- Create: `backend/tests/test_demo_directquery.py`

Create a `DataSource` and a fifth dataset in `mode="directquery"` against it, plus a small report using it, so the pushdown, sampling and totals paths are demonstrated.

**Judgement call to make and record:** the demo's own Postgres is the obvious target, but a demo must not fail on a deployment without one. Prefer a SQLite source file written beside the CSVs — it needs no credentials, works everywhere, and still exercises the DirectQuery code path. If you choose otherwise, say why in your report.

Tests: the dataset is `mode="directquery"`; a widget over it returns data through `run_direct_query`; totals are the whole table, not the fetched page.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 7: The endpoint

**Files:**
- Create: `backend/app/routers/demo.py`, `backend/tests/test_demo_endpoint.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `POST /api/v1/demo/seed` → `{datasets: int, reports: int, widgets: int}`, and `DELETE /api/v1/demo/seed` removing demo content.

Requirements:
- Authenticated; seeds into **the caller's org**, never another.
- One transaction: a failure leaves no half-built demo.
- Re-seeding replaces the previous demo set and leaves the user's own data untouched.
- Registered under the `/api/v1` prefix like every other router.

Tests: unauthenticated is rejected; two orgs seeding cannot see each other's content (**the security-relevant test — assert from the second org's side that the first org's rows are invisible**); double-seed leaves one set; DELETE removes demo content and only demo content.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 8: The button

**Files:**
- Modify: `frontend/src/services/api.ts`, `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Dashboard.test.tsx` (create if absent)

A "Load demo content" button beside "Upload dataset" on the Datasets page.

- Shown when the org has no datasets (the empty state is where it matters most) **and** in the header, so it is reachable once data exists.
- Confirms first via `useConfirm` when datasets already exist, since re-seeding replaces the previous demo set — state that in the dialog body.
- Busy state while seeding; a toast on success naming what was created; the dataset list refreshes without a manual reload.
- Every control keeps an accessible name.

Tests: the button appears in the empty state; clicking it calls the API and refreshes; a failure surfaces an error rather than a silent no-op.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 9: Drive it in the real app

**Files:** none committed except fixes arising.

Run the app and use the feature as a user: log in, click the button, open each demo report, and look at every page.

This is not optional and not a formality. On this project, four blocking defects survived a fully green suite, and driving the app afterwards found three more that tests could not see. A demo whose widgets render blank is worse than no demo.

Check specifically: every widget renders something; no console errors; the gauge's bands paint; the slicer cross-filters; the Gantt draws bars; the word cloud has words; the DirectQuery report loads; totals rows show the whole dataset.

Report findings, fix what is broken, and record anything deliberately left.

- [ ] **Step 1: Seed via the button in a real browser**
- [ ] **Step 2: Screenshot every demo report page and READ the screenshots**
- [ ] **Step 3: Fix what is broken**
- [ ] **Step 4: Re-verify and commit fixes**
