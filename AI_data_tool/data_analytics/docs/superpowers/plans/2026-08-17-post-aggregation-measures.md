# Post-Aggregation Measures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dataset-level measures — expressions evaluated after filters at the visual's grouping grain — so percent-of-total, ratios, and margins vary correctly by chart crossing.

**Architecture:** A new `Dataset.measures` JSON column stores measure definitions parallel to `calculated_columns`. A new `measure_eval.py` module provides group-aware aggregation functions and `TOTAL()` for grand totals. Shapers resolve measure names before their existing `groupby` path. Import mode only until Phase 4; DirectQuery rejects measure roles explicitly.

**Tech Stack:** Python, FastAPI, pandas, SQLAlchemy, React/TypeScript (existing stack).

**Spec:** `docs/superpowers/specs/2026-08-17-post-aggregation-measures-design.md`

## Global Constraints

- **Security (hard constraint):** measure expressions MUST pass `_validate_expr_safety` — no weakening the AST allowlist, no `ast.Attribute` in user expressions.
- **RLS before measures:** measure evaluation runs only on data already filtered by `apply_rls_filter`; measures cannot bypass RLS.
- **Cache isolation:** when a widget config references a measure, the widget-data cache key MUST include the measure definition(s) used plus `rls_filter_expr` verbatim (same rule as calculated columns).
- **DirectQuery Phases 0–3:** return HTTP 400 `"Measures are not yet supported for DirectQuery datasets"` if `config.measure` or `config.roles.measure` resolves to a dataset measure — mirror the calculated-columns rejection at `routers/widget_data.py:28`.
- **No row-level window functions in measures (Phase 1):** `CUMSUM`, `LAG`, `LEAD`, `GROUPSUM`, etc. are not registered in the measure namespace.
- **Measure-on-measure references:** not supported until Phase 2; expressions referencing another measure name by bare identifier are rejected at save/preview time.
- **Migration style:** idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `backend/app/main.py` `_migrate()` — no Alembic.
- **Test conventions:** `_eval_expr`-style direct unit tests for `measure_eval.py`; fixture-based router tests with `client`, `auth_headers`, real CSV in `tmp_path` for integration (see `backend/tests/test_get_widget_data_rls.py`).

---

### Task 1: Schema migration and Pydantic models

**Files:**
- Modify: `backend/app/models/models.py` (add `measures` column on `Dataset`)
- Modify: `backend/app/main.py` (add `_migrate()` statement)
- Modify: `backend/app/schemas/schemas.py`
- Test: `backend/tests/test_measures_schema.py`

**Interfaces:**
- Produces: `MeasureDef`, `MeasurePreviewRequest` Pydantic models; `Dataset.measures` JSON column defaulting to `[]`.

- [x] **Step 1: Write the failing test**

Create `backend/tests/test_measures_schema.py`:

```python
import pytest
from app.models.models import Dataset


def test_dataset_measures_column_defaults_to_empty_list(db_session):
    ds = Dataset(name="t", org_id=1)
    db_session.add(ds)
    db_session.commit()
    db_session.refresh(ds)
    assert ds.measures == []


def test_measure_def_roundtrip_via_api(client, auth_headers, sample_dataset):
    payload = {
        "name": "Sales Pct",
        "expression": "SUM(sales) / TOTAL(SUM(sales)) * 100",
        "default_aggregation": "sum",
    }
    r = client.post(f"/datasets/{sample_dataset.id}/measures", json=payload, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()[0]["name"] == "Sales Pct"
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_measures_schema.py -v`
Expected: FAIL — no `measures` column / no POST route.

- [x] **Step 3: Add model column and schemas**

In `models.py` on `Dataset`:
```python
measures = Column(JSON, default=list)
```

In `main.py` `_migrate()`:
```python
"ALTER TABLE datasets ADD COLUMN IF NOT EXISTS measures JSONB DEFAULT '[]'",
```

In `schemas.py`:
```python
class MeasureDef(BaseModel):
    name: str
    expression: str
    default_aggregation: Optional[str] = "sum"
    format: Optional[CalcColumnFormat] = None


class MeasurePreviewRequest(BaseModel):
    expression: str
    group_by: Optional[str] = None
    filters: list[dict] = []
    calculated_columns: list[Any] = []
```

- [x] **Step 4: Run test — still fails on route (expected); model test passes after commit**

- [x] **Step 5: Commit**

```bash
git add backend/app/models/models.py backend/app/main.py backend/app/schemas/schemas.py backend/tests/test_measures_schema.py
git commit -m "feat: add Dataset.measures schema and Pydantic models"
```

---

### Task 2: Measures CRUD and preview API

**Files:**
- Modify: `backend/app/routers/datasets.py`
- Modify: `backend/app/schemas/schemas.py` (add `measures` to `DatasetOut` if not auto-included)
- Test: `backend/tests/test_measures_api.py`

**Interfaces:**
- Produces: `GET /{id}/measures`, `POST /{id}/measures`, `DELETE /{id}/measures/{name}`, `POST /{id}/measures/preview`
- Consumes: `MeasureDef`, `MeasurePreviewRequest` from Task 1

- [x] **Step 1: Write failing API tests**

Create `backend/tests/test_measures_api.py` with tests for list, save, delete, preview 400 on empty expression, org scoping (404 for wrong org).

- [x] **Step 2: Run tests — verify FAIL**

Run: `cd backend && python -m pytest tests/test_measures_api.py -v`

- [x] **Step 3: Implement routes**

Mirror calculated-columns handlers in `datasets.py`:

```python
@router.get("/{dataset_id}/measures")
async def list_measures(...):
    ...
    return ds.measures or []


@router.post("/{dataset_id}/measures")
async def save_measure(dataset_id: int, measure: MeasureDef, ...):
    _validate_measure_name(measure.name, ds)
    cols = [m for m in (ds.measures or []) if m.get("name") != measure.name]
    cols.append(measure.model_dump(exclude_none=True))
    ds.measures = cols
    flag_modified(ds, "measures")
    ...


@router.delete("/{dataset_id}/measures/{measure_name}")
async def delete_measure(...):
    ...


@router.post("/{dataset_id}/measures/preview")
async def preview_measure(dataset_id: int, req: MeasurePreviewRequest, ...):
    # load df, apply RLS, apply calc cols, call measure_eval.preview_measure(...)
    ...
```

Add `_validate_measure_name(name, ds)` — reject collision with base column names and calculated column names.

- [x] **Step 4: Run tests — verify PASS**

- [x] **Step 5: Commit**

```bash
git commit -m "feat: add measures CRUD and preview API endpoints"
```

---

### Task 3: Core measure evaluation engine

**Files:**
- Create: `backend/app/services/measure_eval.py`
- Test: `backend/tests/test_measure_eval.py`

**Interfaces:**
- Produces:
  - `resolve_measure(name: str, measures: list[dict]) -> dict | None`
  - `evaluate_measure(expr: str, df: pd.DataFrame, group_cols: list[str]) -> pd.Series | float`
  - `preview_measure(expr: str, df: pd.DataFrame, group_by: str | None) -> dict`
- Consumes: `_validate_expr_safety` from `widget_data`

- [x] **Step 1: Write failing unit tests**

Create `backend/tests/test_measure_eval.py`:

```python
import pandas as pd
from app.services.measure_eval import evaluate_measure


def test_pct_of_total_by_region():
    df = pd.DataFrame({
        "region": ["East", "East", "West", "West"],
        "sales": [100, 50, 200, 100],
    })
    result = evaluate_measure(
        "SUM(sales) / TOTAL(SUM(sales)) * 100",
        df,
        group_cols=["region"],
    )
    assert isinstance(result, pd.Series)
    assert len(result) == 2
    east = result[df["region"] == "East"].iloc[0]
    west = result[df["region"] == "West"].iloc[0]
    assert round(east, 2) == 33.33   # 150 / 450
    assert round(west, 2) == 66.67   # 300 / 450


def test_scalar_profit_margin():
    df = pd.DataFrame({"profit": [10, 20], "revenue": [100, 200]})
    result = evaluate_measure(
        "SUM(profit) / SUM(revenue) * 100",
        df,
        group_cols=[],
    )
    assert result == 10.0   # 30 / 300 * 100


def test_total_nested_rejected():
    import pytest
    df = pd.DataFrame({"sales": [1, 2]})
    with pytest.raises(ValueError, match="TOTAL"):
        evaluate_measure("TOTAL(TOTAL(SUM(sales)))", df, group_cols=[])
```

- [x] **Step 2: Run tests — verify FAIL**

Run: `cd backend && python -m pytest tests/test_measure_eval.py -v`

- [x] **Step 3: Implement measure_eval.py**

Core algorithm:
1. Parse expression with `_validate_expr_safety`.
2. Identify referenced columns (names in `local_ns` after `_build_safe_ns`-style column binding on `df`).
3. For each group in `group_cols` (or single group if empty), compute `SUM(col)`, `AVG(col)`, etc.
4. Implement `TOTAL(inner)` by evaluating `inner` with `group_cols=[]` on the same filtered `df`.
5. Evaluate the expression per group row using a measure-specific namespace where `SUM(s)` means `grouped[s].sum()` not `df[s].sum()`.

Use a recursive descent or two-pass approach:
- Pass 1: compute grand totals dict for `TOTAL(...)` sub-expressions
- Pass 2: compute per-group aggregates and evaluate full expression

- [x] **Step 4: Run tests — verify PASS**

- [x] **Step 5: Commit**

```bash
git commit -m "feat: add measure_eval core engine with TOTAL support"
```

---

### Task 4: Integrate measures into shape_series (import mode)

**Files:**
- Modify: `backend/app/services/widget_data.py` (`shape_series`, `get_widget_data`)
- Modify: `backend/app/routers/widget_data.py`
- Test: `backend/tests/test_widget_data_measures.py`

**Interfaces:**
- Consumes: `evaluate_measure`, `resolve_measure` from Task 3
- Modifies: `get_widget_data(..., measures: list[dict] | None = None)` signature

- [x] **Step 1: Write failing integration test**

Create `backend/tests/test_widget_data_measures.py`:

```python
def test_bar_chart_with_measure_pct_of_total(tmp_path, auth_headers, client):
    # Create CSV with region/sales, dataset with measure, POST widget-data
    # Assert rows sum to ~100 and East/West values match expected
    ...
```

- [x] **Step 2: Run test — verify FAIL**

- [x] **Step 3: Wire measure resolution in shape_series**

At top of grouped-series branch in `shape_series`:

```python
from .measure_eval import resolve_measure, evaluate_measure

measure_def = resolve_measure(meas, measures) if measures else None
if measure_def:
    group_cols = [dim] if dim else []
    values = evaluate_measure(measure_def["expression"], df, group_cols)
    if group_cols:
        grouped = values.reset_index(name="value") if isinstance(values, pd.Series) else ...
    else:
        val = float(values) if not isinstance(values, pd.Series) else float(values.iloc[0])
        grouped = pd.DataFrame({"value": [val]})
    # skip existing df.groupby(dim)[meas].agg path
```

Pass `measures` through `get_widget_data` → `get_widget_data_from_df` → shaper. Update shaper signatures to accept optional `measures` kwarg, or attach to config as `config["_measures"]` to avoid changing every shaper signature in Phase 1 (prefer explicit kwarg with default `None`).

In `routers/widget_data.py`:
```python
measure_defs = list(ds.measures or [])
return get_widget_data(..., measures=measure_defs)
```

Add DirectQuery rejection:
```python
if ds.mode == "directquery" and _config_uses_measure(req.config, measure_defs):
    raise HTTPException(400, "Measures are not yet supported for DirectQuery datasets")
```

- [x] **Step 4: Run integration test — verify PASS**

- [x] **Step 5: Commit**

```bash
git commit -m "feat: integrate measures into shape_series widget path"
```

---

### Task 5: Frontend API client and MeasuresPanel

**Files:**
- Modify: `frontend/src/services/api.ts`
- Create: `frontend/src/components/report/MeasuresPanel.tsx`
- Modify: `frontend/src/pages/DatasetDetail.tsx`
- Test: `frontend/src/components/report/MeasuresPanel.test.tsx`

**Interfaces:**
- Consumes: backend routes from Task 2
- Produces: `measuresApi.list/save/delete/preview`; `MeasuresPanel` component

- [x] **Step 1: Write failing component test**

```typescript
it('renders measures list and opens add modal', async () => {
  vi.mocked(measuresApi.list).mockResolvedValue([{ name: 'Margin', expression: 'SUM(a)/SUM(b)*100' }])
  render(<MeasuresPanel datasetId={1} columns={[]} onChanged={() => {}} />)
  expect(await screen.findByText('Margin')).toBeInTheDocument()
})
```

- [x] **Step 2: Run test — verify FAIL**

Run: `cd frontend && npm test -- MeasuresPanel.test.tsx`

- [x] **Step 3: Implement measuresApi and MeasuresPanel**

In `api.ts`:
```typescript
export interface MeasureDef {
  name: string
  expression: string
  default_aggregation?: string
  format?: CalcColumnFormat
}

export const measuresApi = {
  list: (dsId: number) => api.get<MeasureDef[]>(`/datasets/${dsId}/measures`).then(r => r.data),
  save: (dsId: number, m: MeasureDef) => api.post<MeasureDef[]>(`/datasets/${dsId}/measures`, m).then(r => r.data),
  delete: (dsId: number, name: string) => api.delete<MeasureDef[]>(`/datasets/${dsId}/measures/${encodeURIComponent(name)}`).then(r => r.data),
  preview: (dsId: number, body: { expression: string; group_by?: string }) =>
    api.post(`/datasets/${dsId}/measures/preview`, body).then(r => r.data),
}
```

`MeasuresPanel.tsx` — copy structure from `CalcColumnsPanel.tsx` with these palette differences:
- Title: "ƒx Measures"
- Include Aggregation category + `TOTAL(expr)` entry: `{ label: 'TOTAL(expr)', snippet: 'TOTAL()', back: 1, hint: 'Grand total ignoring dimension' }`
- Exclude Running & Rank and Group By categories
- Add optional `group_by` selector in preview (dropdown of dimension columns)
- Add default aggregation `<select>`

Mount in `DatasetDetail.tsx` below `CalcColumnsPanel`.

- [x] **Step 4: Run test — verify PASS**

- [x] **Step 5: Commit**

```bash
git commit -m "feat: add MeasuresPanel and measures API client"
```

---

### Task 6: Fields pane and widget format wiring

**Files:**
- Modify: `frontend/src/pages/ReportBuilder.tsx`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`
- Modify: `frontend/src/services/api.ts` (`Dataset` type adds `measures`)
- Test: `frontend/src/pages/ReportBuilder.test.tsx`

**Interfaces:**
- Consumes: `dataset.measures` from API
- Produces: separate "Measures" group in Fields sidebar; measure formats applied in renderers

- [ ] **Step 1: Extend ReportBuilder test**

Add assertion that a dataset measure appears under a "Measures" heading distinct from numeric columns.

- [ ] **Step 2: Run test — verify FAIL**

- [ ] **Step 3: Implement Fields pane changes**

In `ReportBuilder.tsx`:
- Load `measures` from primary dataset
- Add Measures group above Columns (rename existing "Measures" group to "Columns" or "Numeric")
- Measure click assigns to selected widget measure role (same as column click)

In `WidgetRenderer.tsx`:
- Accept `measures` prop; build format map from measure definitions alongside calc column formats

- [ ] **Step 4: Run tests — verify PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: wire measures into Fields pane and renderer formats"
```

---

### Task 7: Card, crosstab, and cache hardening

**Files:**
- Modify: `backend/app/services/widget_data.py` (`shape_card`, crosstab branch in `shape_series`)
- Modify: `backend/app/services/widget_data.py` (`_widget_data_cache_key`)
- Test: extend `backend/tests/test_widget_data_measures.py`

**Interfaces:**
- Consumes: `evaluate_measure` from Task 3

- [ ] **Step 1: Write failing tests for card and crosstab measures**

```python
def test_card_widget_evaluates_two_measures_independently(...):
    ...

def test_crosstab_measure_at_intersection(...):
    ...
```

- [ ] **Step 2: Run tests — verify FAIL**

- [ ] **Step 3: Integrate measures into shape_card and crosstab branch**

For `shape_card`: each entry in `roles.measures` that resolves to a measure def uses `evaluate_measure(expr, df, group_cols=[])`.

For crosstab: `group_cols = [dim, dim2]`; pivot the resulting series.

Update cache key:
```python
"measures": measures or [],
```

- [ ] **Step 4: Run all measure tests — verify PASS**

Run: `cd backend && python -m pytest tests/test_measure_eval.py tests/test_measures_api.py tests/test_widget_data_measures.py -v`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: extend measures to card/crosstab and update cache keys"
```

---

### Task 8: CalcColumnsPanel snippet fix (parallel quick win)

**Files:**
- Modify: `frontend/src/components/report/CalcColumnsPanel.tsx`
- Test: optional — manual verification via preview API

**Interfaces:**
- No backend changes; align palette snippets with `_validate_expr_safety`-compatible functions.

- [x] **Step 1: Fix Date palette**

Replace `.dt.*` snippets with backend functions:
```typescript
{ label: 'year(col)',    snippet: 'YEAR()',  back: 1, hint: 'Extract year' },
{ label: 'month(col)',   snippet: 'MONTH()', back: 1, hint: 'Month 1–12' },
{ label: 'day(col)',     snippet: 'DAY()',   back: 1, hint: 'Day of month' },
{ label: 'quarter(col)', snippet: 'QUARTER()', back: 1, hint: 'Quarter 1–4' },
{ label: 'datetrunc(col,unit)', snippet: "DATETRUNC(, 'month')", back: 9, hint: 'Truncate to year/quarter/month/week/day' },
```

Remove `hour(col)` and `weekday(col)` entries (no backend functions yet).

- [x] **Step 2: Fix Text palette**

Remove `.str.*` entries. Keep only:
```typescript
{ label: 'to_text(x)', snippet: 'str()', back: 1, hint: 'Convert value to text' },
```
Add a disabled note in the category header: "Full text functions ship separately."

- [x] **Step 3: Fix Conditional and Operators**

Remove `fillna(col,val)` entry (`.fillna()` uses forbidden attribute access).
Remove `IN` operator entry with `.isin([])` (forbidden attribute access).

- [x] **Step 4: Manual verify**

Open expression builder, insert `YEAR(` + column, click Test — expect success not "disallowed construct".

- [x] **Step 5: Commit**

```bash
git commit -m "fix: align CalcColumnsPanel palette with supported expression functions"
```

---

## Self-Review Checklist

| Spec requirement | Task |
|---|---|
| `Dataset.measures` JSON column | Task 1 |
| CRUD + preview API | Task 2 |
| Group-aware SUM/AVG + TOTAL | Task 3 |
| shape_series + scalar KPI | Task 4 |
| MeasuresPanel UI | Task 5 |
| Fields pane Measures group | Task 6 |
| Card + crosstab + cache keys | Task 7 |
| DirectQuery 400 rejection | Task 4 |
| CalcColumnsPanel snippet fix | Task 8 |
| DirectQuery SQL pushdown | **Out of scope** — future Phase 4 spec amendment |

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-17-post-aggregation-measures.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

---

## Execution record (2026-08-17)

**Delivered:** Tasks 1, 2, 3, 4, 5, 8, plus the Fields-pane half of Task 6.
Backend 485 tests passing (+31 from this work); frontend 163 (+9).

Deviations from the plan as written, and why:

- **Task order changed to 3 → 1 → 2 → 4.** Task 2's preview endpoint calls
  `measure_eval.preview_measure`, which Task 3 creates, so the original 1 → 2 → 3 order
  could not have gone green in sequence.
- **Task 1's test file split.** As written it mixed a model test with an API test and its
  Step 4 explicitly ended on a failing route, which is not a TDD-complete task. Model
  coverage now lives in `test_measures_api.py` alongside the routes it needs.
- **Migration uses `JSON`, not `JSONB`.** Matches the existing `_migrate()` statements for
  `calculated_columns` and `column_formats`.
- **Task 3's example test was wrong.** It masked a 2-element Series indexed by region with
  a 4-element boolean taken from the source frame. Replaced with index lookups.
- **`sample_dataset` fixture does not exist.** Conftest provides `db_session`, `client`,
  `two_orgs` (a dict keyed "a"/"b") and `auth_headers`; tests build datasets inline,
  including `DatasetColumn` rows, which the name-collision check queries.
- **Measures reach shapers through config, not a new parameter.** Adding a kwarg to all 15
  shaper signatures for a Phase-1 feature was not worth it. `get_widget_data_from_df`
  overwrites `config["measure_defs"]` rather than merging, so a client cannot supply its
  own definitions through the request body.
- **`measure_eval` imports `_validate_expr_safety` lazily.** `widget_data` now imports
  `measure_eval`, so a module-level import would be circular. The safety check stays in
  `widget_data` because `sql_expr` also imports it from there.
- **Task 8 was already done.** The palette fix was present uncommitted in the working tree
  and matched all four sub-steps. No change made; the stale claim in the gap analysis was
  corrected instead.

**Not delivered:** Task 6's renderer format wiring (measure `format` is stored but not yet
applied in `WidgetRenderer`), Task 7 (card multi-measure and crosstab intersections), and
Phase 4 (DirectQuery pushdown — currently an explicit 400).
