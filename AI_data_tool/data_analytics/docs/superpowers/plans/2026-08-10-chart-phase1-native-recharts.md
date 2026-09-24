# Chart Type Expansion — Phase 1 (Native Recharts Composition) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 10 Phase 1 chart types from `docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md` — Histogram, Dual Axis Bar/Line/Bar-Line/Time Series, Comparative Time Series, Step Plot, Dot Plot, Needle Plot, Numeric Series Plot — on top of the Phase 0 `SHAPERS`/`CHART_RENDERERS`/`ROLE_SPECS` registries, each as an additive registry entry.

**Architecture:** Two new backend shapers (`shape_histogram`, `shape_dual_series`) plus one more (`shape_xy_numeric`) cover all 10 types; several types (Step, Dot Plot, Needle) reuse the existing `shape_series`. Each type gets its own frontend renderer component registered in `CHART_RENDERERS`, a `WidgetType` union member, a `WIDGET_CATALOG` entry, and a `ROLE_SPECS` entry. Two foundational changes precede the chart-type work: `ChartRendererProps` gains `measure2Fmt` (several Phase 1 charts have a second measure needing its own format), and `WidgetConfigPanel`'s role handling is generalized from three hardcoded roles (category/category2/measure) to any role declared in `ROLE_SPECS[wt]` (Phase 1 introduces `measure2` and `start`).

**Tech Stack:** FastAPI + pandas (backend), React 18 + TypeScript + Recharts (frontend), pytest, Vitest.

## Global Constraints

- Every new chart type is purely additive: no existing chart type's shaper, renderer, or config-panel behavior changes.
- Follow the Phase 0 code patterns exactly: shapers are pure `(df, config) -> dict` functions registered in `SHAPERS`; renderers are `React.FC<ChartRendererProps>` registered in `CHART_RENDERERS`; role fields render via the generic `ROLE_SPECS[wt]` loop in `WidgetConfigPanel.tsx`.
- No new runtime dependencies (Recharts already provides `ComposedChart`, `ReferenceLine`, `ZAxis` etc. needed for this phase).
- Follow existing code style: inline styles, `var(--...)` CSS custom properties, 2-space indentation.
- `npm run build` has a baseline of 10 pre-existing TypeScript errors, unrelated to this and prior plans (in `chartUtils.tsx`, `Dashboard.tsx`, `Reports.tsx`, `api.ts`). Every task must leave this count unchanged — compare, don't expect zero.
- This host cannot run a second Docker stack (the main checkout's stack is already running on the same container/port names). Every "verify" step substitutes rigorous diff/code review plus `pytest`/`npm run test`/`npm run build` for a literal `docker compose` + browser check. Live verification happens after this branch merges, against the already-running main stack (bind-mounted, hot-reloading).
- Widget type identifiers (new `WidgetType` union members) use `snake_case`: `histogram`, `dual_axis_bar`, `dual_axis_line`, `dual_axis_bar_line`, `dual_axis_time_series`, `comparative_time_series`, `step`, `dot_plot`, `needle`, `numeric_series`.

---

## Task 1: Add `measure2Fmt` to `ChartRendererProps`

**Files:**
- Modify: `frontend/src/components/report/chartRenderers/types.ts`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Produces: `ChartRendererProps.measure2Fmt?: CalcColumnFormat` — the format for `cfg.measure2`, computed the same way `measureFmt` already is for `cfg.measure`.
- Consumes (by Tasks 7-11, 16): dual-axis and numeric-series renderers read `measure2Fmt` for their second axis/series formatting.

- [ ] **Step 1: Add the field to the props interface**

In `frontend/src/components/report/chartRenderers/types.ts`, add to the interface (after `measureFmt?: CalcColumnFormat`):
```ts
  measure2Fmt?: CalcColumnFormat
```

- [ ] **Step 2: Compute and pass it in `WidgetBody`**

In `frontend/src/components/report/WidgetRenderer.tsx`, immediately after the existing line:
```ts
  const measureFmt = allFormats?.[cfg.measure] ?? allFormats?.[cfg.dimension]
```
add:
```ts
  const measure2Fmt = allFormats?.[cfg.measure2]
```

Then in the `CHART_RENDERERS` dispatch block, add `measure2Fmt={measure2Fmt}` to the props passed:
```tsx
  const ChartRenderer = CHART_RENDERERS[wt]
  if (ChartRenderer) {
    return (
      <ChartRenderer rows={rows} cfg={cfg} rtl={rtl} broadcasts={broadcasts}
        localSelected={localSelected} onClickPoint={onClickPoint}
        measureFmt={measureFmt} measure2Fmt={measure2Fmt} allFormats={allFormats} />
    )
  }
```

- [ ] **Step 3: Verify build**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors, no new ones (this is a pure additive prop, unused by the 6 existing renderers).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/report/chartRenderers/types.ts frontend/src/components/report/WidgetRenderer.tsx
git commit -m "feat: add measure2Fmt to ChartRendererProps for dual-measure Phase 1 charts"
```

---

## Task 2: Generalize `WidgetConfigPanel` role handling to any `ROLE_SPECS[wt]` role

**Files:**
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `configKeyFor(role: string): string` — maps a role name to its config key (`category`→`dimension`, `category2`→`dimension2`, `measure`→`measure`, everything else → itself, e.g. `measure2`→`measure2`, `start`→`start`).
- Produces: `seedRoleValues(cfg: any, wt: WidgetType): Record<string, string>` — builds the initial/reset `roleValues` object from `ROLE_SPECS[wt]` instead of three hardcoded keys.
- Consumes (by Tasks 7-11, 16): once this lands, any chart type that declares a `measure2` or `start` role in `ROLE_SPECS` automatically gets a working config-panel field — no further panel changes needed per chart type, matching the Phase 0 design promise.

- [ ] **Step 1: Add the role/config-key mapping and seeding helpers**

In `frontend/src/components/report/WidgetConfigPanel.tsx`, add near the top of the component (after the `RUNNING_OPTIONS` constant, before the component function):
```ts
const ROLE_TO_CONFIG_KEY: Record<string, string> = { category: 'dimension', category2: 'dimension2', measure: 'measure' }
const configKeyFor = (role: string) => ROLE_TO_CONFIG_KEY[role] ?? role

function seedRoleValues(cfg: Record<string, unknown>, wt: WidgetType): Record<string, string> {
  const values: Record<string, string> = {}
  for (const rf of ROLE_SPECS[wt] ?? []) {
    values[rf.role] = (cfg[configKeyFor(rf.role)] as string) ?? ''
  }
  return values
}
```
(This requires `WidgetType` to be imported — add it to the existing `import type { Widget } from '../../types/report'` line, changing it to `import type { Widget, WidgetType } from '../../types/report'`.)

- [ ] **Step 2: Replace the hardcoded state initialization**

Replace:
```ts
  const [roleValues, setRoleValues] = useState<Record<string, string>>({
    category:  cfg.dimension  ?? '',
    category2: cfg.dimension2 ?? '',
    measure:   cfg.measure    ?? '',
  })
```
with:
```ts
  const [roleValues, setRoleValues] = useState<Record<string, string>>(() => seedRoleValues(cfg, wt))
```

- [ ] **Step 3: Replace the widget-change reset**

Replace:
```ts
    setRoleValues({ category: cfg.dimension ?? '', category2: cfg.dimension2 ?? '', measure: cfg.measure ?? '' })
```
with:
```ts
    setRoleValues(seedRoleValues(cfg, wt))
```

- [ ] **Step 4: Replace the dataset-change reset**

Replace:
```ts
            setRoleValues({ category: '', category2: '', measure: '' })
```
with:
```ts
            setRoleValues(Object.fromEntries((ROLE_SPECS[wt] ?? []).map(rf => [rf.role, ''])))
```

- [ ] **Step 5: Replace the config-emission logic**

Replace:
```ts
      if (roleValues.category)  config.dimension  = roleValues.category
      if (roleValues.category2) config.dimension2 = roleValues.category2
      if (roleValues.measure)   config.measure    = roleValues.measure
```
with:
```ts
      for (const rf of ROLE_SPECS[wt] ?? []) {
        const v = roleValues[rf.role]
        if (v) config[configKeyFor(rf.role)] = v
      }
```

- [ ] **Step 6: Generalize the field-picker's numeric-only-options check**

The field-rendering loop currently special-cases only `rf.role === 'measure'` for numeric column options. Find:
```tsx
            const options = rf.role === 'measure'
              ? numCols.map(c => ({ value: c.name, label: c.name }))
              : colOptions
```
Replace with:
```tsx
            const options = (rf.role === 'measure' || rf.role === 'measure2')
              ? numCols.map(c => ({ value: c.name, label: c.name }))
              : colOptions
```

- [ ] **Step 7: Verify no regression for the 6 existing chart types + kpi/table/crosstab/list**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

Trace through by hand (this is the core evidence for this task, write it in your report): for `bar` (`ROLE_SPECS.bar = [{role:'category',...},{role:'measure',...}]`), confirm `seedRoleValues` produces `{category: cfg.dimension ?? '', measure: cfg.measure ?? ''}` — identical to the old hardcoded object minus the always-present-but-unused `category2` key (previously every widget type got a `category2` entry in `roleValues` even if unused; now only types whose `ROLE_SPECS` includes `category2` get one — since `crosstab` is the only one that does, and the emission loop iterates `ROLE_SPECS[wt]` not `roleValues` keys, this has zero effect on the emitted config for any type). For `crosstab`, confirm the full 3-field seed/emit still works identically to before.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "refactor: generalize WidgetConfigPanel role handling to any ROLE_SPECS role"
```

---

## Task 3: Fix `resolve_roles()`'s two known semantic gaps

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Modify: `backend/tests/test_resolve_roles.py`

**Interfaces:**
- Modifies: `resolve_roles(config: dict) -> dict` — now treats `config["roles"]` as authoritative whenever the key is *present* (even if its value is `{}`), not merely when it's *truthy*. Docstring corrected to say roles replace (not merge with) the legacy mapping, matching the actual (unchanged) behavior.
- Consumes (by Task 6): `shape_dual_series` is the first shaper to actually call `resolve_roles`.

- [ ] **Step 1: Write the failing test for the presence-vs-truthiness fix**

Add to `backend/tests/test_resolve_roles.py`:
```python
def test_explicit_empty_roles_means_no_roles_not_legacy_fallback():
    config = {"dimension": "region", "measure": "revenue", "roles": {}}
    assert resolve_roles(config) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`):
```bash
pytest tests/test_resolve_roles.py::test_explicit_empty_roles_means_no_roles_not_legacy_fallback -v
```
Expected: FAIL — current code returns `{"category": "region", "measure": "revenue"}` (falls through to the legacy branch) instead of `{}`.

- [ ] **Step 3: Fix the presence check and the docstring**

In `backend/app/services/widget_data.py`, change:
```python
def resolve_roles(config: dict) -> dict:
    """Map a widget config to its role assignments.

    If config['roles'] is present, it is authoritative. Otherwise, roles are
    built from the legacy dimension/dimension2/measure keys, for backward
    compatibility with configs saved before the roles model existed.
    """
    if config.get("roles"):
        return {k: v for k, v in config["roles"].items() if v}
```
to:
```python
def resolve_roles(config: dict) -> dict:
    """Map a widget config to its role assignments.

    If the 'roles' key is present in config at all (even as an empty dict),
    it is authoritative and REPLACES the legacy mapping entirely — it is not
    merged with dimension/dimension2/measure. Only when 'roles' is absent are
    roles built from the legacy dimension/dimension2/measure keys, for
    backward compatibility with configs saved before the roles model existed.
    """
    if "roles" in config:
        return {k: v for k, v in (config["roles"] or {}).items() if v}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `backend/`):
```bash
pytest tests/test_resolve_roles.py -v
```
Expected: 5 passed (4 existing + 1 new).

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -v
```
Expected: 17 passed (13 existing + this new one; adjust if prior counts differ, but no failures).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_resolve_roles.py
git commit -m "fix: resolve_roles treats present-but-empty roles as authoritative, not a legacy fallback"
```

---

## Task 4: Backend `shape_histogram` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_histogram.py`

**Interfaces:**
- Produces: `shape_histogram(df: pd.DataFrame, config: dict) -> dict` — config keys: `measure` (required), `bins` (optional int, default 10), `filters`. Returns `{"type": "series", "measure": ..., "rows": [{"name": "<lo>–<hi>", "value": <count>, "bin_start": ..., "bin_end": ...}, ...], "total": ...}`.
- Registers: `SHAPERS["histogram"] = shape_histogram`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_histogram.py`:
```python
import pandas as pd
from app.services.widget_data import shape_histogram, SHAPERS


def test_bins_numeric_data_into_default_10_bins():
    df = pd.DataFrame({"revenue": list(range(100))})
    result = shape_histogram(df, {"measure": "revenue"})
    assert result["type"] == "series"
    assert len(result["rows"]) == 10
    assert sum(r["value"] for r in result["rows"]) == 100


def test_custom_bin_count():
    df = pd.DataFrame({"revenue": list(range(100))})
    result = shape_histogram(df, {"measure": "revenue", "bins": 4})
    assert len(result["rows"]) == 4


def test_missing_measure_returns_empty():
    df = pd.DataFrame({"revenue": [1, 2, 3]})
    result = shape_histogram(df, {"measure": "nonexistent"})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_drops_nan_before_binning():
    df = pd.DataFrame({"revenue": [1.0, 2.0, None, 4.0, 5.0]})
    result = shape_histogram(df, {"measure": "revenue", "bins": 2})
    assert sum(r["value"] for r in result["rows"]) == 4


def test_registered_in_shapers():
    assert SHAPERS["histogram"] is shape_histogram
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_shape_histogram.py -v
```
Expected: FAIL — `ImportError: cannot import name 'shape_histogram'`.

- [ ] **Step 3: Implement `shape_histogram` and register it**

In `backend/app/services/widget_data.py`, add directly after the `shape_series` function (before the `SHAPERS` dict):
```python
def shape_histogram(df: pd.DataFrame, config: dict) -> dict:
    """config keys: measure (required), bins (int, default 10), filters."""
    filters = config.get("filters", [])
    meas = config.get("measure") or None
    bins = int(config.get("bins") or 10)
    df = _apply_filters(df, filters)
    if df.empty or not meas or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    s = df[meas].dropna()
    if len(s) == 0:
        return {"type": "empty", "rows": [], "total": 0}
    counts, edges = np.histogram(s, bins=bins)
    rows = []
    for i in range(len(counts)):
        lo, hi = float(edges[i]), float(edges[i + 1])
        rows.append({
            "name": f"{lo:.2f}–{hi:.2f}",
            "value": int(counts[i]),
            "bin_start": _safe(lo),
            "bin_end": _safe(hi),
        })
    return {"type": "series", "measure": meas, "rows": rows, "total": len(s)}
```
Then update the `SHAPERS` dict, adding a new entry:
```python
    "histogram": shape_histogram,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_shape_histogram.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -v
```
Expected: all passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_histogram.py
git commit -m "feat: add shape_histogram shaper for Histogram chart type"
```

---

## Task 5: Frontend Histogram chart type

**Files:**
- Create: `frontend/src/components/report/chartRenderers/HistogramRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `HistogramRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.histogram`.
- Produces: `'histogram'` added to the `WidgetType` union, `WIDGET_CATALOG`, and `ROLE_SPECS`.
- Produces: a `Bins` numeric field in `WidgetConfigPanel.tsx`, shown only for `wt === 'histogram'`.

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/HistogramRenderer.tsx`:
```tsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function HistogramRenderer({ rows, rtl }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 24, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 9 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} reversed={rtl} />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [v, 'count']} labelFormatter={(l: unknown) => `Bin: ${l}`} />
        <Bar dataKey="value" fill="var(--accent)" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import HistogramRenderer from './HistogramRenderer'
```
```tsx
  histogram: HistogramRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, and `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Change the `WidgetType` union (line 1-3) from:
```ts
export type WidgetType =
  | 'bar' | 'line' | 'pie' | 'donut' | 'scatter' | 'treemap'
  | 'kpi' | 'table' | 'crosstab' | 'list' | 'text' | 'button'
```
to:
```ts
export type WidgetType =
  | 'bar' | 'line' | 'pie' | 'donut' | 'scatter' | 'treemap'
  | 'histogram'
  | 'kpi' | 'table' | 'crosstab' | 'list' | 'text' | 'button'
```

2. Add to `WIDGET_CATALOG` (after the `treemap` entry):
```ts
  { type: 'histogram' as WidgetType, label: 'Histogram', category: 'Charts', icon: '▤', defaultW: 6, defaultH: 5 },
```

3. Add to `ROLE_SPECS` (after the `treemap` entry):
```ts
  histogram: [{ role: 'measure', label: 'Measure (numeric column)', required: true }],
```

- [ ] **Step 4: Add the Bins field and its icon**

In `frontend/src/components/report/WidgetConfigPanel.tsx`:

1. Add state (alongside the other `useState` declarations, e.g. after `tableCols`):
```ts
  const [bins, setBins] = useState<number>((cfg.bins as number) ?? 10)
```
2. Add to the widget-change reset `useEffect`:
```ts
    setBins((cfg.bins as number) ?? 10)
```
3. Add to the config-emission object (in the `else` branch that builds the generic `config` object, alongside `limit`/`sort`):
```ts
      if (wt === 'histogram') config.bins = bins
```
4. Add `bins` to the emitting `useEffect`'s dependency array.
5. Add the field JSX, gated by widget type, near the Row limit field:
```tsx
          {wt === 'histogram' && fld('Bins',
            <input type="number" value={bins} min={2} max={100} onChange={e => setBins(Number(e.target.value))} style={{ width:'100%' }} />
          )}
```
6. Add an icon entry to the `widgetIcon()` function's map: `histogram:'▤'`.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

Diff-review: confirm `HistogramRenderer` reads `rows` (from `shape_histogram`'s `{name, value}` rows) exactly like `BarChartRenderer` does, minus click-to-filter (histogram bins aren't meaningfully filterable by equality, so no `onClick`/cross-filter wiring — this is an intentional, minimal difference from Bar, not an oversight).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/HistogramRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Histogram chart type"
```

---

## Task 6: Backend `shape_dual_series` shaper (shared by 5 chart types)

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_dual_series.py`

**Interfaces:**
- Produces: `shape_dual_series(df: pd.DataFrame, config: dict) -> dict` — uses `resolve_roles(config)` to read `category` OR `start` (whichever is present — both are just "the grouping column" for this shaper; `start` is used for date-based variants) plus `measure` and/or `measure2`. Returns `{"type": "dual_series", "category": ..., "measure": ..., "measure2": ..., "rows": [{"name": ..., "value": ..., "value2": ...}, ...], "total": ...}` — `value`/`value2` are omitted from a row's dict when the corresponding role isn't set.
- Registers: `SHAPERS["dual_axis_bar"] = SHAPERS["dual_axis_line"] = SHAPERS["dual_axis_bar_line"] = SHAPERS["dual_axis_time_series"] = SHAPERS["comparative_time_series"] = shape_dual_series`.
- Consumes: `resolve_roles` (Task 3's fixed version).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_dual_series.py`:
```python
import pandas as pd
from app.services.widget_data import shape_dual_series, SHAPERS


def sample_df():
    return pd.DataFrame({
        "month": ["Jan", "Jan", "Feb", "Feb", "Mar"],
        "revenue": [100, 50, 200, 100, 300],
        "cost": [60, 20, 90, 40, 120],
    })


def test_both_measures_grouped_by_category():
    config = {"roles": {"category": "month", "measure": "revenue", "measure2": "cost"}}
    result = shape_dual_series(sample_df(), config)
    assert result["type"] == "dual_series"
    assert result["category"] == "month"
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["Jan"]["value"] == 150
    assert by_name["Jan"]["value2"] == 80
    assert by_name["Feb"]["value"] == 300
    assert result["total"] == 5


def test_start_role_used_as_grouping_column_like_category():
    config = {"roles": {"start": "month", "measure": "revenue"}}
    result = shape_dual_series(sample_df(), config)
    assert result["category"] == "month"
    assert all("value" in r and "value2" not in r for r in result["rows"])


def test_only_measure2_no_measure():
    config = {"roles": {"category": "month", "measure2": "cost"}}
    result = shape_dual_series(sample_df(), config)
    assert all("value2" in r and "value" not in r for r in result["rows"])


def test_missing_category_returns_empty():
    config = {"roles": {"measure": "revenue"}}
    result = shape_dual_series(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_missing_both_measures_returns_empty():
    config = {"roles": {"category": "month"}}
    result = shape_dual_series(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_aggregation_config():
    config = {"roles": {"category": "month", "measure": "revenue"}, "aggregation": "avg"}
    result = shape_dual_series(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["Jan"]["value"] == 75.0


def test_all_five_widget_types_registered_to_same_shaper():
    for wt in ["dual_axis_bar", "dual_axis_line", "dual_axis_bar_line", "dual_axis_time_series", "comparative_time_series"]:
        assert SHAPERS[wt] is shape_dual_series
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_shape_dual_series.py -v
```
Expected: FAIL — `ImportError: cannot import name 'shape_dual_series'`.

- [ ] **Step 3: Implement `shape_dual_series` and register it**

In `backend/app/services/widget_data.py`, add directly after `shape_histogram` (before the `SHAPERS` dict — note `SHAPERS` and `resolve_roles` are currently defined further down the file, after `shape_series`; move this new function so it's defined before the `SHAPERS` dict literal, and note `resolve_roles`/`_LEGACY_ROLE_KEYS` must already be defined above this point — if they aren't yet (they currently sit after the `SHAPERS` dict in the file), move the `_LEGACY_ROLE_KEYS` dict and `resolve_roles` function definition to appear directly after `_apply_filters` and before `shape_series`, so both `shape_series`-family functions and `SHAPERS` can reference `resolve_roles` without forward-reference issues — Python doesn't require this for module-level functions calling each other, since `SHAPERS` is only evaluated after every function above it is defined, but keep the file's read order logical: filters → shapers (using resolve_roles) → resolve_roles → SHAPERS dict does NOT work if shape_dual_series is placed before resolve_roles's definition in a way that matters at runtime — it doesn't, Python resolves names at call time not definition time, so placement doesn't affect correctness, only readability; place `shape_dual_series` right after `shape_histogram` as instructed and leave `resolve_roles`'s existing position after `SHAPERS` alone):
```python
def shape_dual_series(df: pd.DataFrame, config: dict) -> dict:
    """config roles: category OR start (grouping column), measure, measure2.
    At least one of measure/measure2 must be set. Used by dual-axis and
    comparative time-series chart types, which differ only in rendering."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category") or roles.get("start")
    meas = roles.get("measure")
    meas2 = roles.get("measure2")
    agg = (config.get("aggregation") or "sum").lower()
    limit = int(config.get("limit") or 50)
    df = _apply_filters(df, filters)
    if df.empty or not cat or cat not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    agg_fn = _pandas_agg_fn(agg)
    agg_cols = [c for c in (meas, meas2) if c and c in df.columns]
    if not agg_cols:
        return {"type": "empty", "rows": [], "total": 0}
    grouped = df.groupby(cat)[agg_cols].agg(agg_fn).reset_index()
    grouped = grouped.sort_values(cat).head(limit)
    rows = []
    for _, row in grouped.iterrows():
        r = {"name": _safe(row[cat])}
        if meas and meas in agg_cols:
            r["value"] = _safe(row[meas])
        if meas2 and meas2 in agg_cols:
            r["value2"] = _safe(row[meas2])
        rows.append(r)
    return {"type": "dual_series", "category": cat, "measure": meas, "measure2": meas2, "rows": rows, "total": len(df)}
```
Then update the `SHAPERS` dict, adding:
```python
    "dual_axis_bar":           shape_dual_series,
    "dual_axis_line":          shape_dual_series,
    "dual_axis_bar_line":      shape_dual_series,
    "dual_axis_time_series":   shape_dual_series,
    "comparative_time_series": shape_dual_series,
```

Since `shape_dual_series` calls `resolve_roles`, and `resolve_roles` is currently defined textually *after* the `SHAPERS` dict in the file (Phase 0 placed it there), this works correctly at runtime regardless of textual order (Python only resolves the name when `shape_dual_series` is actually called, by which point the whole module has finished loading) — no code movement is required, just be aware of it when reading the file.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_shape_dual_series.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -v
```
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_dual_series.py
git commit -m "feat: add shape_dual_series shaper for the 5 dual-measure chart types"
```

---

## Task 7: Frontend Dual Axis Bar Chart

**Files:**
- Create: `frontend/src/components/report/chartRenderers/DualAxisBarChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`

**Interfaces:**
- Produces: `DualAxisBarChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.dual_axis_bar`.
- Produces: `'dual_axis_bar'` added to `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` (roles: `category`, `measure` label "Bars (left axis)", `measure2` label "Line/Bars (right axis)" — both required since a dual-axis chart needs two measures to be meaningful).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/DualAxisBarChartRenderer.tsx`:
```tsx
import { ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function DualAxisBarChartRenderer({ rows, cfg, rtl, measureFmt, measure2Fmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} reversed={rtl} />
        <YAxis yAxisId="left" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <YAxis yAxisId="right" orientation={rtl ? 'left' : 'right'} tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => fmtStr(v, measure2Fmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === (cfg.measure2 ?? 'value2') ? measure2Fmt : measureFmt), name]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar yAxisId="left" dataKey="value" name={cfg.measure ?? 'value'} fill="var(--accent)" radius={[3, 3, 0, 0]} />
        <Bar yAxisId="right" dataKey="value2" name={cfg.measure2 ?? 'value2'} fill="#a78bfa" radius={[3, 3, 0, 0]} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import DualAxisBarChartRenderer from './DualAxisBarChartRenderer'
```
```tsx
  dual_axis_bar: DualAxisBarChartRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'dual_axis_bar'` to the `WidgetType` union (next to `'histogram'`).
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'dual_axis_bar' as WidgetType, label: 'Dual Axis Bar', category: 'Charts', icon: '▥', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  dual_axis_bar: [{ role: 'category', label: 'Dimension (X-axis)', required: true },
                  { role: 'measure',  label: 'Bars (left axis)',   required: true },
                  { role: 'measure2', label: 'Bars (right axis)',  required: true }],
```

- [ ] **Step 4: Add the icon to `WidgetConfigPanel.tsx`'s `widgetIcon()` map**

Add `dual_axis_bar:'▥'` to the map in `widgetIcon()`.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

Confirm in your report: `rows` from `shape_dual_series` are `{name, value, value2}` objects — this renderer reads `dataKey="value"` / `dataKey="value2"` directly, matching that shape.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/DualAxisBarChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Dual Axis Bar chart type"
```

---

## Task 8: Frontend Dual Axis Line Chart

**Files:**
- Create: `frontend/src/components/report/chartRenderers/DualAxisLineChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `DualAxisLineChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.dual_axis_line`.

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/DualAxisLineChartRenderer.tsx`:
```tsx
import { ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function DualAxisLineChartRenderer({ rows, cfg, rtl, measureFmt, measure2Fmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" reversed={rtl} />
        <YAxis yAxisId="left" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <YAxis yAxisId="right" orientation={rtl ? 'left' : 'right'} tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => fmtStr(v, measure2Fmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === (cfg.measure2 ?? 'value2') ? measure2Fmt : measureFmt), name]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line yAxisId="left" type="monotone" dataKey="value" name={cfg.measure ?? 'value'} stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} />
        <Line yAxisId="right" type="monotone" dataKey="value2" name={cfg.measure2 ?? 'value2'} stroke="#a78bfa" strokeWidth={2} dot={{ r: 3 }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import DualAxisLineChartRenderer from './DualAxisLineChartRenderer'
```
```tsx
  dual_axis_line: DualAxisLineChartRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'dual_axis_line'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'dual_axis_line' as WidgetType, label: 'Dual Axis Line', category: 'Charts', icon: '⤢', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  dual_axis_line: [{ role: 'category', label: 'Dimension (X-axis)', required: true },
                    { role: 'measure',  label: 'Line (left axis)',   required: true },
                    { role: 'measure2', label: 'Line (right axis)',  required: true }],
```

- [ ] **Step 4: Add the icon**

Add `dual_axis_line:'⤢'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/DualAxisLineChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Dual Axis Line chart type"
```

---

## Task 9: Frontend Dual Axis Bar-Line Chart

**Files:**
- Create: `frontend/src/components/report/chartRenderers/DualAxisBarLineChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `DualAxisBarLineChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.dual_axis_bar_line`. Renders `measure` as bars on the left axis and `measure2` as a line on the right axis (the defining difference from Task 7's all-bars and Task 8's all-lines variants).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/DualAxisBarLineChartRenderer.tsx`:
```tsx
import { ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function DualAxisBarLineChartRenderer({ rows, cfg, rtl, measureFmt, measure2Fmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} reversed={rtl} />
        <YAxis yAxisId="left" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <YAxis yAxisId="right" orientation={rtl ? 'left' : 'right'} tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => fmtStr(v, measure2Fmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === (cfg.measure2 ?? 'value2') ? measure2Fmt : measureFmt), name]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar yAxisId="left" dataKey="value" name={cfg.measure ?? 'value'} fill="var(--accent)" radius={[3, 3, 0, 0]} />
        <Line yAxisId="right" type="monotone" dataKey="value2" name={cfg.measure2 ?? 'value2'} stroke="#fbbf24" strokeWidth={2} dot={{ r: 3 }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import DualAxisBarLineChartRenderer from './DualAxisBarLineChartRenderer'
```
```tsx
  dual_axis_bar_line: DualAxisBarLineChartRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'dual_axis_bar_line'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'dual_axis_bar_line' as WidgetType, label: 'Dual Axis Bar-Line', category: 'Charts', icon: '▧', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  dual_axis_bar_line: [{ role: 'category', label: 'Dimension (X-axis)', required: true },
                        { role: 'measure',  label: 'Bars (left axis)',  required: true },
                        { role: 'measure2', label: 'Line (right axis)', required: true }],
```

- [ ] **Step 4: Add the icon**

Add `dual_axis_bar_line:'▧'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/DualAxisBarLineChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Dual Axis Bar-Line chart type"
```

---

## Task 10: Frontend Dual Axis Time Series Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/DualAxisTimeSeriesRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `DualAxisTimeSeriesRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.dual_axis_time_series`. Visually a two-line composed chart like Task 8, but its `ROLE_SPECS` uses a `start` role (date column) instead of `category`, and `shape_dual_series` (Task 6) already treats `start` as the grouping column — no backend change needed.

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/DualAxisTimeSeriesRenderer.tsx`:
```tsx
import { ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function DualAxisTimeSeriesRenderer({ rows, cfg, rtl, measureFmt, measure2Fmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" reversed={rtl} />
        <YAxis yAxisId="left" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <YAxis yAxisId="right" orientation={rtl ? 'left' : 'right'} tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => fmtStr(v, measure2Fmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === (cfg.measure2 ?? 'value2') ? measure2Fmt : measureFmt), name]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line yAxisId="left" type="monotone" dataKey="value" name={cfg.measure ?? 'value'} stroke="var(--accent)" strokeWidth={2} dot={false} />
        <Line yAxisId="right" type="monotone" dataKey="value2" name={cfg.measure2 ?? 'value2'} stroke="#a78bfa" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
```
(`dot={false}` distinguishes a "time series" reading — many points, no per-point markers — from Task 8's smaller-N Dual Axis Line, which shows dots.)

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import DualAxisTimeSeriesRenderer from './DualAxisTimeSeriesRenderer'
```
```tsx
  dual_axis_time_series: DualAxisTimeSeriesRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'dual_axis_time_series'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'dual_axis_time_series' as WidgetType, label: 'Dual Axis Time Series', category: 'Charts', icon: '⟿', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  dual_axis_time_series: [{ role: 'start',    label: 'Date',              required: true },
                           { role: 'measure',  label: 'Line (left axis)',  required: true },
                           { role: 'measure2', label: 'Line (right axis)', required: true }],
```

- [ ] **Step 4: Add the icon**

Add `dual_axis_time_series:'⟿'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

Confirm in your report: the `start` role (not `category`) is what `WidgetConfigPanel` will render for this type, via Task 2's generalized `ROLE_SPECS[wt]` loop — no config-panel code changes needed here, only the `ROLE_SPECS` data entry.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/DualAxisTimeSeriesRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Dual Axis Time Series chart type"
```

---

## Task 11: Frontend Comparative Time Series Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/ComparativeTimeSeriesRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `ComparativeTimeSeriesRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.comparative_time_series`. Per the design spec, this is for "identifying anomalies between two separate time series" — same visual family as Task 10 but framed as comparing two independent series rather than one metric's dual scale; distinguished in the UI by its own label/role labels, not by different rendering logic.

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/ComparativeTimeSeriesRenderer.tsx`:
```tsx
import { ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function ComparativeTimeSeriesRenderer({ rows, cfg, rtl, measureFmt, measure2Fmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" reversed={rtl} />
        <YAxis yAxisId="left" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <YAxis yAxisId="right" orientation={rtl ? 'left' : 'right'} tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => fmtStr(v, measure2Fmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === (cfg.measure2 ?? 'series B') ? measure2Fmt : measureFmt), name]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line yAxisId="left" type="monotone" dataKey="value" name={cfg.measure ?? 'series A'} stroke="var(--accent)" strokeWidth={2} dot={false} />
        <Line yAxisId="right" type="monotone" dataKey="value2" name={cfg.measure2 ?? 'series B'} stroke="#f87171" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import ComparativeTimeSeriesRenderer from './ComparativeTimeSeriesRenderer'
```
```tsx
  comparative_time_series: ComparativeTimeSeriesRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'comparative_time_series'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'comparative_time_series' as WidgetType, label: 'Comparative Time Series', category: 'Charts', icon: '⇄', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  comparative_time_series: [{ role: 'start',    label: 'Date',     required: true },
                             { role: 'measure',  label: 'Series A', required: true },
                             { role: 'measure2', label: 'Series B', required: true }],
```

- [ ] **Step 4: Add the icon**

Add `comparative_time_series:'⇄'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/ComparativeTimeSeriesRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Comparative Time Series chart type"
```

---

## Task 12: Frontend Step Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/StepPlotRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `StepPlotRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.step`. Reuses `shape_series` (single category + single measure, exactly like `bar`/`line`) — no new backend shaper needed, only `SHAPERS["step"] = shape_series` (already covered by Phase 0's fallback-to-`shape_series` default behavior for any unregistered type, but registered explicitly here for clarity and consistency with the rest of `SHAPERS`).

- [ ] **Step 1: Register `step` in `SHAPERS`**

In `backend/app/services/widget_data.py`, add to the `SHAPERS` dict:
```python
    "step": shape_series,
```

- [ ] **Step 2: Create the renderer**

Create `frontend/src/components/report/chartRenderers/StepPlotRenderer.tsx`:
```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function StepPlotRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" reversed={rtl} />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        <Line type="stepAfter" dataKey="value" stroke="var(--accent)" strokeWidth={2} dot={{ fill: 'var(--accent)', r: 3 }}
          activeDot={{ r: 5, fill: 'var(--accent)', stroke: '#fff', strokeWidth: 2 }} />
      </LineChart>
    </ResponsiveContainer>
  )
}
```
Step Plot uses one continuous stroke color, not per-point `Cell` coloring, so `getFillFactory` is not imported (unlike Bar/Pie/Donut).

- [ ] **Step 3: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import StepPlotRenderer from './StepPlotRenderer'
```
```tsx
  step: StepPlotRenderer,
```

- [ ] **Step 4: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'step'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'step' as WidgetType, label: 'Step Plot', category: 'Charts', icon: '⊓', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  step: [{ role: 'category', label: 'Dimension (X-axis)',       required: true },
         { role: 'measure',  label: 'Measure (numeric column)', required: false }],
```

- [ ] **Step 5: Add the icon**

Add `step:'⊓'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 6: Verify**

Run backend and frontend checks:
```bash
cd backend && .venv/Scripts/python.exe -m pytest -v
cd frontend && npm run build
```
Expected: all backend tests pass; frontend build shows exactly the 10 pre-existing errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/widget_data.py frontend/src/components/report/chartRenderers/StepPlotRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Step Plot chart type"
```

---

## Task 13: Frontend Dot Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/DotPlotRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`
- Modify: `backend/app/services/widget_data.py`

**Interfaces:**
- Produces: `DotPlotRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.dot_plot`. Reuses `shape_series` — a dot plot is a bar chart's `{name, value}` data rendered as one dot per category on a horizontal axis instead of a bar.

- [ ] **Step 1: Register `dot_plot` in `SHAPERS`**

In `backend/app/services/widget_data.py`, add to the `SHAPERS` dict:
```python
    "dot_plot": shape_series,
```

- [ ] **Step 2: Create the renderer**

Create `frontend/src/components/report/chartRenderers/DotPlotRenderer.tsx`:
```tsx
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function DotPlotRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" dataKey="value" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} tickFormatter={v => fmtStr(v, measureFmt)} />
        <YAxis type="category" dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} width={90} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        <Scatter data={rows} fill="var(--accent)" shape="circle"
          onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        />
      </ScatterChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 3: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import DotPlotRenderer from './DotPlotRenderer'
```
```tsx
  dot_plot: DotPlotRenderer,
```

- [ ] **Step 4: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'dot_plot'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'dot_plot' as WidgetType, label: 'Dot Plot', category: 'Charts', icon: '⁚', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  dot_plot: [{ role: 'category', label: 'Dimension (Y-axis)',       required: true },
             { role: 'measure',  label: 'Measure (numeric column)', required: false }],
```

- [ ] **Step 5: Add the icon**

Add `dot_plot:'⁚'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 6: Verify**

```bash
cd backend && .venv/Scripts/python.exe -m pytest -v
cd frontend && npm run build
```
Expected: all backend tests pass; frontend build shows exactly the 10 pre-existing errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/widget_data.py frontend/src/components/report/chartRenderers/DotPlotRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Dot Plot chart type"
```

---

## Task 14: Frontend Needle Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/NeedlePlotRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`
- Modify: `backend/app/services/widget_data.py`

**Interfaces:**
- Produces: `NeedlePlotRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.needle`. Reuses `shape_series`. Adds a `baseline` numeric config field (default `0`) rendered via a Recharts `ReferenceLine`.

- [ ] **Step 1: Register `needle` in `SHAPERS`**

In `backend/app/services/widget_data.py`, add to the `SHAPERS` dict:
```python
    "needle": shape_series,
```

- [ ] **Step 2: Create the renderer**

Create `frontend/src/components/report/chartRenderers/NeedlePlotRenderer.tsx`:
```tsx
import { ComposedChart, Bar, ReferenceLine, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function NeedlePlotRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt }: ChartRendererProps) {
  const baseline = Number(cfg.baseline ?? 0)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} reversed={rtl} />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        <ReferenceLine y={baseline} stroke="var(--muted)" strokeDasharray="3 3" />
        <Bar dataKey="value" fill="var(--accent)" barSize={3}>
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  )
}
```

Recharts renders a thin `Bar` (`barSize={3}`) from the baseline (0 by default, since Recharts bars always start at the axis's own zero unless a `ReferenceArea`/custom shape is used — for a true needle-from-arbitrary-baseline effect when `baseline !== 0`, the Y axis domain must include the baseline and the bar visually reads as "from axis 0" not "from baseline" for non-zero baselines; this is an accepted simplification for Phase 1 given the `ReferenceLine` still visually marks the baseline for comparison). Note this limitation explicitly in your report; a true offset-baseline needle (bar spans `[baseline, value]` rather than `[0, value]`) is a candidate refinement for a later phase.

- [ ] **Step 3: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import NeedlePlotRenderer from './NeedlePlotRenderer'
```
```tsx
  needle: NeedlePlotRenderer,
```

- [ ] **Step 4: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'needle'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'needle' as WidgetType, label: 'Needle Plot', category: 'Charts', icon: '↕', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  needle: [{ role: 'category', label: 'Dimension (X-axis)',       required: true },
           { role: 'measure',  label: 'Measure (numeric column)', required: false }],
```

- [ ] **Step 5: Add the Baseline field and icon**

In `frontend/src/components/report/WidgetConfigPanel.tsx`:

1. Add state:
```ts
  const [baseline, setBaseline] = useState<number>((cfg.baseline as number) ?? 0)
```
2. Add to the widget-change reset `useEffect`:
```ts
    setBaseline((cfg.baseline as number) ?? 0)
```
3. Add to the config-emission object:
```ts
      if (wt === 'needle') config.baseline = baseline
```
4. Add `baseline` to the emitting `useEffect`'s dependency array.
5. Add the field JSX, gated by widget type:
```tsx
          {wt === 'needle' && fld('Baseline',
            <input type="number" value={baseline} onChange={e => setBaseline(Number(e.target.value))} style={{ width:'100%' }} />
          )}
```
6. Add `needle:'↕'` to the `widgetIcon()` map.

- [ ] **Step 6: Verify**

```bash
cd backend && .venv/Scripts/python.exe -m pytest -v
cd frontend && npm run build
```
Expected: all backend tests pass; frontend build shows exactly the 10 pre-existing errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/widget_data.py frontend/src/components/report/chartRenderers/NeedlePlotRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Needle Plot chart type"
```

---

## Task 15: Backend `shape_xy_numeric` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_xy_numeric.py`

**Interfaces:**
- Produces: `shape_xy_numeric(df: pd.DataFrame, config: dict) -> dict` — roles `measure` (x) and `measure2` (y), both required, row-level (no grouping/aggregation). Returns `{"type": "xy_series", "x": ..., "y": ..., "rows": [{"x": ..., "y": ...}, ...], "total": ...}`, sorted by `x`, NaN rows dropped, capped at `config["limit"]` (default 500).
- Registers: `SHAPERS["numeric_series"] = shape_xy_numeric`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_xy_numeric.py`:
```python
import pandas as pd
from app.services.widget_data import shape_xy_numeric, SHAPERS


def test_returns_sorted_xy_pairs():
    df = pd.DataFrame({"month_offset": [3, 1, 2], "unemployment_rate": [5.5, 4.0, 5.0]})
    result = shape_xy_numeric(df, {"roles": {"measure": "month_offset", "measure2": "unemployment_rate"}})
    assert result["type"] == "xy_series"
    assert result["x"] == "month_offset"
    assert result["y"] == "unemployment_rate"
    assert [r["x"] for r in result["rows"]] == [1, 2, 3]
    assert [r["y"] for r in result["rows"]] == [4.0, 5.0, 5.5]


def test_drops_rows_with_nan_in_either_column():
    df = pd.DataFrame({"x": [1, 2, None, 4], "y": [10, None, 30, 40]})
    result = shape_xy_numeric(df, {"roles": {"measure": "x", "measure2": "y"}})
    assert len(result["rows"]) == 2
    assert result["total"] == 4


def test_missing_measure2_returns_empty():
    df = pd.DataFrame({"x": [1, 2, 3]})
    result = shape_xy_numeric(df, {"roles": {"measure": "x"}})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    df = pd.DataFrame({"x": list(range(10)), "y": list(range(10))})
    result = shape_xy_numeric(df, {"roles": {"measure": "x", "measure2": "y"}, "limit": 3})
    assert len(result["rows"]) == 3


def test_registered_in_shapers():
    assert SHAPERS["numeric_series"] is shape_xy_numeric
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_shape_xy_numeric.py -v
```
Expected: FAIL — `ImportError: cannot import name 'shape_xy_numeric'`.

- [ ] **Step 3: Implement `shape_xy_numeric` and register it**

In `backend/app/services/widget_data.py`, add directly after `shape_dual_series`:
```python
def shape_xy_numeric(df: pd.DataFrame, config: dict) -> dict:
    """config roles: measure (x), measure2 (y). Row-level, no aggregation."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    x = roles.get("measure")
    y = roles.get("measure2")
    limit = int(config.get("limit") or 500)
    df = _apply_filters(df, filters)
    if df.empty or not x or not y or x not in df.columns or y not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    sub = df[[x, y]].dropna().sort_values(x).head(limit)
    rows = [{"x": _safe(r[x]), "y": _safe(r[y])} for _, r in sub.iterrows()]
    return {"type": "xy_series", "x": x, "y": y, "rows": rows, "total": len(df)}
```
Then update the `SHAPERS` dict, adding:
```python
    "numeric_series": shape_xy_numeric,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_shape_xy_numeric.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -v
```
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_xy_numeric.py
git commit -m "feat: add shape_xy_numeric shaper for Numeric Series Plot"
```

---

## Task 16: Frontend Numeric Series Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/NumericSeriesPlotRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `NumericSeriesPlotRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.numeric_series`. Reads `{x, y}` rows from `shape_xy_numeric` (Task 15) — different row shape from every other Phase 1 chart, which all use `{name, value[, value2]}`.

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/NumericSeriesPlotRenderer.tsx`:
```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function NumericSeriesPlotRenderer({ rows, rtl, measureFmt, measure2Fmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="x" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} tickFormatter={v => fmtStr(v, measureFmt)} />
        <YAxis dataKey="y" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measure2Fmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === 'x' ? measureFmt : measure2Fmt), name]} />
        <Line type="monotone" dataKey="y" stroke="var(--accent)" strokeWidth={2} dot={{ fill: 'var(--accent)', r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import NumericSeriesPlotRenderer from './NumericSeriesPlotRenderer'
```
```tsx
  numeric_series: NumericSeriesPlotRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'numeric_series'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'numeric_series' as WidgetType, label: 'Numeric Series Plot', category: 'Charts', icon: '∿', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  numeric_series: [{ role: 'measure',  label: 'X axis (numeric)', required: true },
                    { role: 'measure2', label: 'Y axis (numeric)', required: true }],
```

- [ ] **Step 4: Add the icon**

Add `numeric_series:'∿'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

Confirm in your report: unlike every other Phase 1 renderer, this one reads `row.x`/`row.y` (not `row.name`/`row.value`) — this is intentional, matching `shape_xy_numeric`'s distinct row shape, and both axes use `type="number"` (not a categorical `dataKey="name"` axis).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/NumericSeriesPlotRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Numeric Series Plot chart type"
```

---

## Task 17: Full regression pass and Phase 1 close-out

**Files:** none (verification only), plus the spec doc status line.

- [ ] **Step 1: Run the full automated test suite**

Backend (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest -v
```
Expected: all tests pass (Phase 0's 17 + this phase's new ones: 5 histogram + 7 dual_series + 5 xy_numeric + 1 resolve_roles fix = 18 new, ~35 total — exact count isn't the point, zero failures is).

Frontend (from `frontend/`):
```bash
npm run build
npm run test
```
Expected: build shows exactly the 10 pre-existing errors; all Vitest tests pass.

- [ ] **Step 2: Full manual regression read**

Read through the final `frontend/src/components/report/chartRenderers/index.tsx` and confirm all 16 chart types (6 from Phase 0 + 10 from this phase) are registered with no duplicate keys, no typos in widget-type strings (cross-check each against the corresponding `WidgetType` union member and `WIDGET_CATALOG`/`ROLE_SPECS` entries).

Read through `backend/app/services/widget_data.py`'s `SHAPERS` dict and confirm all 16 chart types plus `kpi`/`table`/`crosstab`/`list` are present, each mapped to a real, defined function.

- [ ] **Step 3: Update the design spec status**

In `docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md`, change the `**Status:**` line from `Phase 0 Complete` to `Phase 1 Complete`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md
git commit -m "docs: mark chart-type-expansion Phase 1 complete"
```

**Phase 1 is now done — 16 of 28 target chart types are live.** Phase 2 (Bubble Plot, Bubble Change Plot, Correlation Matrix, Heat Map, Fit Lines, Parallel Coordinates — 6 items) gets its own plan document, written fresh against this foundation, before implementation starts. Phase 2 is also where `ChartRendererProps` will need widening beyond `rows` (per the Phase 0 final review's forward-looking note) since Correlation Matrix and Parallel Coordinates don't fit a flat rows array.
