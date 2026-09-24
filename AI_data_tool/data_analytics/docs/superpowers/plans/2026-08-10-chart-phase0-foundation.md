# Chart Type Expansion — Phase 0 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the if-chain / overloaded-config-key pattern behind the 6 existing chart types (Bar, Line, Pie, Donut, Scatter, Treemap) with a `SHAPERS` registry (backend) and `CHART_RENDERERS` registry (frontend) plus a `ROLE_SPECS`-driven config panel — with zero visible behavior change — so that Phases 1–3 (22 new chart types) can each be added as one small registry entry instead of another branch in a growing if-chain.

**Architecture:** Backend `widget_data.py` gains a `widget_type`-keyed `SHAPERS` dict (currently all entries point at the renamed `shape_series`, today's `query_widget` body, unchanged). The frontend's `WidgetBody` if-chain in `WidgetRenderer.tsx` is replaced by a `CHART_RENDERERS` dict of extracted per-chart components sharing a new `chartUtils.tsx` module. `WidgetConfigPanel.tsx`'s hardcoded field conditionals are replaced by a `ROLE_SPECS` table describing which fields each widget type needs.

**Tech Stack:** FastAPI + pandas (backend), React 18 + TypeScript + Recharts (frontend), pytest (new backend test runner), Vitest + React Testing Library (new frontend test runner).

## Global Constraints

- No visible behavior change: every existing report/widget must render, cross-filter, format, and RTL-toggle identically before and after this phase.
- No new runtime dependencies in this phase (pytest and Vitest are dev/test-only).
- Follow existing code style: this codebase uses inline styles (no CSS framework), `var(--...)` CSS custom properties for theme colors, and 2-space indentation in TypeScript.
- Existing saved widget configs (using `dimension`/`dimension2`/`measure` keys) must continue to work unchanged — no data migration.

---

## Task 1: Backend test harness

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_smoke.py`

**Interfaces:**
- Produces: a working `pytest` command runnable from the `backend/` directory.

- [ ] **Step 1: Add pytest to requirements**

Append to `backend/requirements.txt`:
```
pytest==8.2.2
```

- [ ] **Step 2: Create pytest config**

Create `backend/pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 3: Create the tests package and a smoke test**

Create `backend/tests/__init__.py` (empty file).

Create `backend/tests/test_smoke.py`:
```python
def test_smoke():
    assert True
```

- [ ] **Step 4: Install and run**

Run (from `backend/`):
```bash
pip install -r requirements.txt
pytest -v
```
Expected: `test_smoke.py::test_smoke PASSED`, 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/pytest.ini backend/tests/__init__.py backend/tests/test_smoke.py
git commit -m "test: add pytest harness for backend"
```

---

## Task 2: Thread `widget_type` through the query path + introduce the `SHAPERS` registry

**Files:**
- Modify: `backend/app/schemas/schemas.py` (`WidgetDataRequest`, ~line 202)
- Modify: `backend/app/routers/widget_data.py`
- Modify: `backend/app/services/widget_data.py` (rename `query_widget` → `shape_series`, add `SHAPERS`, update `get_widget_data`)
- Modify: `frontend/src/services/api.ts` (`widgetDataApi.query`, ~line 154)
- Modify: `frontend/src/components/report/WidgetRenderer.tsx` (`fetchData`, ~line 173)
- Test: `backend/tests/test_widget_shapers.py`

**Interfaces:**
- Produces: `shape_series(df: pd.DataFrame, config: dict) -> dict` (identical body/behavior to today's `query_widget`).
- Produces: `SHAPERS: dict[str, Callable[[pd.DataFrame, dict], dict]]` mapping `widget_type` → shaper function. Entries for `bar`, `line`, `pie`, `donut`, `treemap`, `scatter`, `kpi`, `table`, `crosstab`, `list` all point at `shape_series`.
- Produces: `get_widget_data(file_path: str, config: dict, widget_type: str = "bar", calculated_columns: list[dict] | None = None, filter_expr: str | None = None) -> dict`.
- Consumes (by later tasks): `SHAPERS` dict — Phase 1+ tasks add new keys here, e.g. `SHAPERS["waterfall"] = shape_waterfall`.

- [ ] **Step 1: Write the failing regression test**

Create `backend/tests/test_widget_shapers.py`:
```python
import pandas as pd
import pytest
from app.services.widget_data import get_widget_data_from_df, SHAPERS, shape_series


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "region": ["East", "East", "West", "West", "North"],
        "product": ["A", "B", "A", "B", "A"],
        "revenue": [100, 150, 200, 50, 300],
    })


@pytest.mark.parametrize("widget_type", ["bar", "line", "pie", "donut", "treemap", "scatter"])
def test_shapers_registry_dispatches_grouped_series(sample_df, widget_type):
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}
    direct = shape_series(sample_df, config)
    via_registry = SHAPERS[widget_type](sample_df, config)
    assert via_registry == direct
    assert via_registry["type"] == "series"
    assert {r["name"] for r in via_registry["rows"]} == {"East", "West", "North"}


def test_unknown_widget_type_falls_back_to_shape_series(sample_df):
    config = {"dimension": "region", "measure": "revenue"}
    result = get_widget_data_from_df(sample_df, config, widget_type="some_future_chart_type")
    assert result == shape_series(sample_df, config)


def test_crosstab_shape_unaffected_by_widget_type(sample_df):
    config = {"dimension": "region", "dimension2": "product", "measure": "revenue"}
    result = get_widget_data_from_df(sample_df, config, widget_type="bar")
    assert result["type"] == "crosstab"
```

Note: the test imports a small helper `get_widget_data_from_df` that runs the shaping logic directly on a DataFrame (no file I/O), which doesn't exist yet — this is expected to fail.

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`):
```bash
pytest tests/test_widget_shapers.py -v
```
Expected: FAIL / ERROR — `ImportError: cannot import name 'get_widget_data_from_df'` (and `SHAPERS` doesn't exist yet either).

- [ ] **Step 3: Rename `query_widget` to `shape_series` and add the registry**

In `backend/app/services/widget_data.py`:

1. Add `from typing import Callable` to the imports at the top (after `import numpy as np`).

2. Rename the function signature at line 115 from `def query_widget(df: pd.DataFrame, config: dict) -> dict:` to `def shape_series(df: pd.DataFrame, config: dict) -> dict:` — the body (lines 116–242) is unchanged.

3. Immediately after the `shape_series` function (after line 242, before the `import math as _math` block), add:
```python
SHAPERS: dict[str, Callable[[pd.DataFrame, dict], dict]] = {
    "bar":      shape_series,
    "line":     shape_series,
    "pie":      shape_series,
    "donut":    shape_series,
    "treemap":  shape_series,
    "scatter":  shape_series,
    "kpi":      shape_series,
    "table":    shape_series,
    "crosstab": shape_series,
    "list":     shape_series,
}


def get_widget_data_from_df(df: pd.DataFrame, config: dict, widget_type: str = "bar") -> dict:
    """Dispatch to the shaper registered for widget_type, falling back to shape_series
    for any widget_type not yet registered (keeps unknown/future types working)."""
    shaper = SHAPERS.get(widget_type, shape_series)
    return shaper(df, config)
```

4. Replace the existing `get_widget_data` function (currently lines 409–415) with:
```python
def get_widget_data(file_path: str, config: dict, widget_type: str = "bar", calculated_columns: list[dict] | None = None, filter_expr: str | None = None) -> dict:
    df = load_file(file_path)
    if filter_expr:
        df = apply_filter_expr(df, filter_expr, silent=True)
    if calculated_columns:
        df = apply_calculated_columns(df, calculated_columns)
    return get_widget_data_from_df(df, config, widget_type)
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `backend/`):
```bash
pytest tests/test_widget_shapers.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Wire `widget_type` through the request schema and router**

In `backend/app/schemas/schemas.py`, modify `WidgetDataRequest` (~line 202):
```python
class WidgetDataRequest(BaseModel):
    config: dict
    calculated_columns: list[Any] = []
    widget_type: str = "bar"
```

In `backend/app/routers/widget_data.py`, change line 18 from:
```python
        return get_widget_data(ds.filename, req.config, calc_cols or None, ds.default_filter_expr or None)
```
to:
```python
        return get_widget_data(
            ds.filename, req.config, widget_type=req.widget_type,
            calculated_columns=calc_cols or None, filter_expr=ds.default_filter_expr or None,
        )
```

- [ ] **Step 6: Wire `widget_type` through the frontend API call**

In `frontend/src/services/api.ts`, change the `widgetDataApi.query` function (~line 154) from:
```ts
  query: (dsId: number, config: Record<string, unknown>, calculatedColumns: CalcColumn[] = []) =>
    api.post(`/datasets/${dsId}/widget-data`, { config, calculated_columns: calculatedColumns }).then(r => r.data),
```
to:
```ts
  query: (dsId: number, config: Record<string, unknown>, calculatedColumns: CalcColumn[] = [], widgetType = 'bar') =>
    api.post(`/datasets/${dsId}/widget-data`, { config, calculated_columns: calculatedColumns, widget_type: widgetType }).then(r => r.data),
```

In `frontend/src/components/report/WidgetRenderer.tsx`, change the `fetchData` call (~line 173) from:
```ts
      const result = await widgetDataApi.query(widgetDatasetId, mergedConfig, effectiveCalcCols)
```
to:
```ts
      const result = await widgetDataApi.query(widgetDatasetId, mergedConfig, effectiveCalcCols, wt)
```

- [ ] **Step 7: Manually verify no regression**

Start the app (from repo root):
```bash
docker compose up -d --build
```
Open `http://localhost:3000`, open an existing report containing a Bar, Line, Pie, Donut, Scatter, and Treemap widget (or create one of each against any uploaded dataset). Confirm each renders with the same data/labels as before this change, and that clicking a bar/slice/point still cross-filters other widgets.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/schemas.py backend/app/routers/widget_data.py backend/app/services/widget_data.py backend/tests/test_widget_shapers.py frontend/src/services/api.ts frontend/src/components/report/WidgetRenderer.tsx
git commit -m "refactor: introduce SHAPERS registry keyed by widget_type"
```

---

## Task 3: `resolve_roles()` compatibility helper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_resolve_roles.py`

**Interfaces:**
- Produces: `resolve_roles(config: dict) -> dict` — returns a dict with keys from `{category, category2, measure, measure2, size, color, group, start, end, label}` (only keys with a non-empty value are included). If `config["roles"]` is present, it's used directly (merged over the legacy mapping). Otherwise it's built from legacy keys: `dimension`→`category`, `dimension2`→`category2`, `measure`→`measure`.
- Consumes (by later phases): Phase 1+ shapers call `resolve_roles(config)` instead of reading `config["dimension"]` etc. directly, so both old-style and new-style (`roles`-based) configs work.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_resolve_roles.py`:
```python
from app.services.widget_data import resolve_roles


def test_legacy_keys_map_to_roles():
    config = {"dimension": "region", "dimension2": "product", "measure": "revenue"}
    assert resolve_roles(config) == {"category": "region", "category2": "product", "measure": "revenue"}


def test_missing_legacy_keys_are_omitted():
    config = {"dimension": "region"}
    assert resolve_roles(config) == {"category": "region"}


def test_explicit_roles_key_takes_precedence():
    config = {"dimension": "region", "roles": {"category": "country", "size": "population"}}
    assert resolve_roles(config) == {"category": "country", "size": "population"}


def test_empty_config_returns_empty_roles():
    assert resolve_roles({}) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`):
```bash
pytest tests/test_resolve_roles.py -v
```
Expected: FAIL — `ImportError: cannot import name 'resolve_roles'`.

- [ ] **Step 3: Implement `resolve_roles`**

In `backend/app/services/widget_data.py`, add directly below the `SHAPERS` dict definition (before `get_widget_data_from_df`):
```python
_LEGACY_ROLE_KEYS = {"dimension": "category", "dimension2": "category2", "measure": "measure"}


def resolve_roles(config: dict) -> dict:
    """Map a widget config to its role assignments.

    If config['roles'] is present, it is authoritative. Otherwise, roles are
    built from the legacy dimension/dimension2/measure keys, for backward
    compatibility with configs saved before the roles model existed.
    """
    if config.get("roles"):
        return {k: v for k, v in config["roles"].items() if v}
    roles = {}
    for legacy_key, role_name in _LEGACY_ROLE_KEYS.items():
        value = config.get(legacy_key)
        if value:
            roles[role_name] = value
    return roles
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `backend/`):
```bash
pytest tests/test_resolve_roles.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Run the full backend test suite**

```bash
pytest -v
```
Expected: all tests passed (smoke + shapers + resolve_roles).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_resolve_roles.py
git commit -m "feat: add resolve_roles() compatibility helper for future chart types"
```

---

## Task 4: Frontend test harness (Vitest)

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/test/smoke.test.ts`

**Interfaces:**
- Produces: a working `npm run test` command in `frontend/`.

- [ ] **Step 1: Add test dependencies and script**

In `frontend/package.json`, add to `"scripts"`:
```json
    "test": "vitest run"
```
Add to `"devDependencies"`:
```json
    "vitest": "^2.0.5",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.8",
    "jsdom": "^24.1.1"
```

- [ ] **Step 2: Create Vitest config**

Create `frontend/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
```

Create `frontend/src/test/setup.ts`:
```ts
import '@testing-library/jest-dom'
```

- [ ] **Step 3: Write a smoke test**

Create `frontend/src/test/smoke.test.ts`:
```ts
import { describe, it, expect } from 'vitest'

describe('vitest harness', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2)
  })
})
```

- [ ] **Step 4: Install and run**

Run (from `frontend/`):
```bash
npm install
npm run test
```
Expected: 1 test file, 1 test passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/test/setup.ts frontend/src/test/smoke.test.ts
git commit -m "test: add Vitest + React Testing Library harness for frontend"
```

---

## Task 5: Extract shared chart utilities into `chartUtils.tsx`

**Files:**
- Create: `frontend/src/components/report/chartUtils.tsx`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Produces: `COLORS: string[]`, `SELECTED_STROKE: string`, `DIM_OPACITY: number`, `TT: React.CSSProperties`, `fmtStr(value, fmt?) => string`, `formatValue(value, fmt?) => React.ReactNode`, `EmptyState({msg}) => JSX.Element`, `getFillFactory(broadcasts, localSelected) => (name, i) => {fill, opacity, stroke?, strokeWidth?}` — all exported from `chartUtils.tsx`.
- Consumes (by Task 6+): every extracted chart renderer imports from this module instead of duplicating formatting/color logic.

- [ ] **Step 1: Create `chartUtils.tsx` with the extracted code**

Create `frontend/src/components/report/chartUtils.tsx`:
```tsx
import type { CalcColumnFormat } from '../../services/api'

export const COLORS = ['#6c8fff','#a78bfa','#34d399','#fbbf24','#f87171','#38bdf8','#fb7185','#4ade80','#c084fc','#e879f9']
export const SELECTED_STROKE = '#fff'
export const DIM_OPACITY = 0.35

export const TT: React.CSSProperties = { background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }

// String-only version for Recharts axis/tooltip (cannot return JSX)
export function fmtStr(value: unknown, fmt?: CalcColumnFormat | null): string {
  if (!fmt || fmt.type === 'none') {
    if (value == null) return '—'
    return typeof value === 'number'
      ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : String(value)
  }
  const num = typeof value === 'number' ? value : parseFloat(String(value))
  const dec = fmt.decimals ?? 2
  const pre = fmt.prefix ?? ''
  const suf = fmt.suffix ?? ''
  const loc = (n: number, d = dec) =>
    n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })

  switch (fmt.type) {
    case 'number':   return isNaN(num) ? '—' : `${pre}${loc(num)}${suf}`
    case 'integer':  return isNaN(num) ? '—' : `${pre}${Math.round(num).toLocaleString()}${suf}`
    case 'currency': return isNaN(num) ? '—' : `${pre}${fmt.symbol ?? '$'} ${loc(num)}${suf}`
    case 'percent':  return isNaN(num) ? '—' : `${pre}${num.toFixed(dec)}%${suf}`
    case 'bar':      return isNaN(num) ? '—' : loc(num, 1)
    case 'badge':    return isNaN(num) ? '—' : `${pre}${loc(num)}${suf}`
    case 'trend':    return isNaN(num) ? '—'
      : `${num > 0 ? '↑' : num < 0 ? '↓' : '→'} ${pre}${Math.abs(num).toLocaleString(undefined, { maximumFractionDigits: dec })}${suf}`
    default:         return value == null ? '—' : String(value)
  }
}

// ReactNode version for table cells (can return JSX for bar/badge/trend)
export function formatValue(value: unknown, fmt?: CalcColumnFormat | null): React.ReactNode {
  if (!fmt || fmt.type === 'none') return value == null ? '—' : String(value)
  const num = typeof value === 'number' ? value : parseFloat(String(value))
  const dec = fmt.decimals ?? 2
  const pre = fmt.prefix ?? ''
  const suf = fmt.suffix ?? ''
  const fmtNum = (n: number, d = dec) =>
    n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })

  switch (fmt.type) {
    case 'number':
      return isNaN(num) ? (value ?? '—') : `${pre}${fmtNum(num)}${suf}`
    case 'integer':
      return isNaN(num) ? (value ?? '—') : `${pre}${Math.round(num).toLocaleString()}${suf}`
    case 'currency': {
      const sym = fmt.symbol ?? '$'
      return isNaN(num) ? (value ?? '—') : `${pre}${sym} ${fmtNum(num)}${suf}`
    }
    case 'percent':
      return isNaN(num) ? (value ?? '—') : `${pre}${num.toFixed(dec)}%${suf}`
    case 'bar': {
      const mn = fmt.min ?? 0; const mx = fmt.max ?? 100
      const pct = isNaN(num) ? 0 : Math.max(0, Math.min(100, ((num - mn) / (mx - mn)) * 100))
      return (
        <div style={{ display:'flex', alignItems:'center', gap:5 }}>
          <div style={{ flex:1, minWidth:50, height:7, background:'var(--border)', borderRadius:4, overflow:'hidden' }}>
            <div style={{ width:`${pct}%`, height:'100%', background: fmt.color ?? '#6c8fff', borderRadius:4 }} />
          </div>
          <span style={{ fontSize:10, color:'var(--muted)', minWidth:30, textAlign:'right' }}>
            {isNaN(num) ? '—' : num.toLocaleString(undefined, { maximumFractionDigits: 1 })}
          </span>
        </div>
      )
    }
    case 'badge': {
      const [lo, hi] = fmt.thresholds ?? [33, 66]
      const color = isNaN(num) ? 'var(--muted)' : num < lo ? '#f87171' : num > hi ? '#34d399' : '#fbbf24'
      const text = isNaN(num) ? (value ?? '—') : `${pre}${num.toLocaleString(undefined, { maximumFractionDigits: dec })}${suf}`
      return (
        <span style={{ display:'inline-block', padding:'1px 7px', borderRadius:10,
          background:color + '22', color, fontWeight:600, fontSize:11 }}>
          {text}
        </span>
      )
    }
    case 'trend': {
      const arrow = isNaN(num) ? '→' : num > 0 ? '↑' : num < 0 ? '↓' : '→'
      const color = isNaN(num) ? 'var(--muted)' : num > 0 ? '#34d399' : num < 0 ? '#f87171' : 'var(--muted)'
      const text  = isNaN(num) ? (value ?? '—')
        : `${pre}${Math.abs(num).toLocaleString(undefined, { maximumFractionDigits: dec })}${suf}`
      return <span style={{ color, fontWeight:700 }}>{arrow} {text}</span>
    }
    default:
      return value == null ? '—' : String(value)
  }
}

export function EmptyState({ msg }: { msg: string }) {
  return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12, flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 24, opacity: .4 }}>◻</span>
      <span>{msg}</span>
    </div>
  )
}

// Returns a per-point fill/opacity/stroke resolver for cross-filter highlight/dim.
export function getFillFactory(broadcasts: boolean, localSelected: unknown) {
  return (name: unknown, i: number) => {
    const color = COLORS[i % COLORS.length]
    if (!broadcasts || localSelected === null) return { fill: color, opacity: 1 }
    return localSelected === name
      ? { fill: color, opacity: 1, strokeWidth: 2, stroke: SELECTED_STROKE }
      : { fill: color, opacity: DIM_OPACITY }
  }
}
```

- [ ] **Step 2: Update `WidgetRenderer.tsx` to import from `chartUtils.tsx` instead of defining locally**

In `frontend/src/components/report/WidgetRenderer.tsx`:

1. Delete lines 12–14 (`COLORS`, `SELECTED_STROKE`, `DIM_OPACITY` consts).
2. Delete lines 16–102 (the `fmtStr` and `formatValue` functions).
3. Delete lines 120–127 (`EmptyState`).
4. Delete line 129 (`TT` const).
5. Add to the import block at the top (after the `useCrossFilter` import):
```ts
import { COLORS, TT, fmtStr, formatValue, EmptyState, getFillFactory } from './chartUtils'
```
6. In `WidgetBody`, replace the manual `getFill` closure (lines 398-405) with:
```ts
  const getFill = getFillFactory(broadcasts, localSelected)
```

- [ ] **Step 3: Verify the build still compiles**

Run (from `frontend/`):
```bash
npm run build
```
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 4: Manually verify no regression**

With the app running (`docker compose up -d`), open a report and confirm KPI/table/list value formatting (currency, percent, badge, trend styles if any are configured) looks identical to before.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/chartUtils.tsx frontend/src/components/report/WidgetRenderer.tsx
git commit -m "refactor: extract chart formatting/color utilities into chartUtils.tsx"
```

---

## Task 6: `CHART_RENDERERS` registry skeleton + dispatch wiring

**Files:**
- Create: `frontend/src/components/report/chartRenderers/types.ts`
- Create: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`
- Test: `frontend/src/components/report/chartRenderers/index.test.tsx`

**Interfaces:**
- Produces: `ChartRendererProps` interface (`rows`, `cfg`, `rtl`, `broadcasts`, `localSelected`, `onClickPoint`, `measureFmt`, `allFormats`).
- Produces: `CHART_RENDERERS: Partial<Record<WidgetType, React.FC<ChartRendererProps>>>` — starts empty.
- Consumes (by Tasks 7–12): each task adds one `CHART_RENDERERS[<type>] = <Component>` line plus the corresponding import.

- [ ] **Step 1: Define the shared props type**

Create `frontend/src/components/report/chartRenderers/types.ts`:
```ts
import type { CalcColumnFormat } from '../../../services/api'

export interface ChartRendererProps {
  rows: any[]
  cfg: any
  rtl: boolean
  broadcasts: boolean
  localSelected: unknown
  onClickPoint: (v: unknown) => void
  measureFmt?: CalcColumnFormat
  allFormats?: Record<string, CalcColumnFormat | undefined>
}
```

- [ ] **Step 2: Create the registry (initially empty)**

Create `frontend/src/components/report/chartRenderers/index.tsx`:
```tsx
import type { WidgetType } from '../../../types/report'
import type { ChartRendererProps } from './types'

export type { ChartRendererProps }

export const CHART_RENDERERS: Partial<Record<WidgetType, React.FC<ChartRendererProps>>> = {}
```

- [ ] **Step 3: Write the failing dispatch test**

Create `frontend/src/components/report/chartRenderers/index.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CHART_RENDERERS } from './index'
import type { ChartRendererProps } from './types'

describe('CHART_RENDERERS registry', () => {
  it('starts empty until chart types register themselves', () => {
    expect(Object.keys(CHART_RENDERERS)).toHaveLength(0)
  })

  it('renders whatever component is registered for a widget type', () => {
    const TestRenderer: React.FC<ChartRendererProps> = ({ rows }) => (
      <div data-testid="test-chart">{rows.length} rows</div>
    )
    CHART_RENDERERS['bar'] = TestRenderer
    const Registered = CHART_RENDERERS['bar']!
    render(<Registered rows={[{ name: 'a', value: 1 }]} cfg={{}} rtl={false} broadcasts={false}
      localSelected={null} onClickPoint={() => {}} />)
    expect(screen.getByTestId('test-chart')).toHaveTextContent('1 rows')
    delete CHART_RENDERERS['bar']
  })
})
```

- [ ] **Step 4: Run test to verify it passes (registry is trivial, this proves the harness + type wiring work)**

Run (from `frontend/`):
```bash
npm run test
```
Expected: 2 passed in `chartRenderers/index.test.tsx`.

- [ ] **Step 5: Wire dispatch into `WidgetBody`**

In `frontend/src/components/report/WidgetRenderer.tsx`:

1. Add import:
```ts
import { CHART_RENDERERS } from './chartRenderers'
```
2. In `WidgetBody`, immediately after the line `const rows = data.rows ?? []` (line 396) and the `getFill` line, insert the dispatch — before the `// Bar chart` comment:
```tsx
  const ChartRenderer = CHART_RENDERERS[wt]
  if (ChartRenderer) {
    return (
      <ChartRenderer rows={rows} cfg={cfg} rtl={rtl} broadcasts={broadcasts}
        localSelected={localSelected} onClickPoint={onClickPoint}
        measureFmt={measureFmt} allFormats={allFormats} />
    )
  }
```
Since `CHART_RENDERERS` is still empty, this is a no-op — every widget type still falls through to the existing `if (wt === 'bar')` chain below it.

- [ ] **Step 6: Verify no regression**

Run (from `frontend/`):
```bash
npm run build
npm run test
```
Expected: both succeed. Manually open the app and confirm all chart types still render (registry is empty so nothing has changed yet).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/report/chartRenderers frontend/src/components/report/WidgetRenderer.tsx
git commit -m "feat: add CHART_RENDERERS registry skeleton with dispatch wiring"
```

---

## Task 7: Migrate Bar chart to the registry

**Files:**
- Create: `frontend/src/components/report/chartRenderers/BarChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx` (delete migrated block)

**Interfaces:**
- Consumes: `ChartRendererProps` (Task 6), `TT`/`fmtStr`/`getFillFactory` (Task 5).
- Produces: `BarChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.bar`.

- [ ] **Step 1: Extract the Bar chart JSX into its own component**

Create `frontend/src/components/report/chartRenderers/BarChartRenderer.tsx`:
```tsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { TT, fmtStr, getFillFactory } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function BarChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} reversed={rtl} />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        <Bar dataKey="value" radius={[4,4,0,0]}>
          {rows.map((r: any, i: number) => {
            const s = getFill(r.name, i)
            return <Cell key={i} fill={s.fill} opacity={s.opacity} stroke={s.stroke} strokeWidth={s.strokeWidth} />
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`:
```tsx
import type { WidgetType } from '../../../types/report'
import type { ChartRendererProps } from './types'
import BarChartRenderer from './BarChartRenderer'

export type { ChartRendererProps }

export const CHART_RENDERERS: Partial<Record<WidgetType, React.FC<ChartRendererProps>>> = {
  bar: BarChartRenderer,
}
```

- [ ] **Step 3: Delete the now-dead inline Bar block from `WidgetRenderer.tsx`**

Delete the `// Bar chart` block (originally lines 407–426, the `if (wt === 'bar') return (...)` block) from `WidgetRenderer.tsx`'s `WidgetBody`. It's unreachable now (the registry dispatch above it handles `bar`), but leaving dead code around invites drift.

Also remove the now-unused `BarChart, Bar,` and (if no longer used by remaining inline blocks) `Cell` from the `recharts` import at the top of the file — check the other still-inline blocks (Line/Pie/Donut/Scatter/Treemap) before removing `Cell`, since Pie/Donut/Treemap still use it.

- [ ] **Step 4: Verify build**

Run (from `frontend/`):
```bash
npm run build
```
Expected: succeeds, no unused-import errors.

- [ ] **Step 5: Manually verify the Bar chart**

With the app running, open a report with a Bar chart widget. Confirm: bars render with the same colors/order as before, hovering shows the same tooltip, clicking a bar cross-filters other widgets and re-clicking clears it, and toggling the widget's RTL option still flips the axis.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/BarChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/components/report/WidgetRenderer.tsx
git commit -m "refactor: migrate Bar chart to CHART_RENDERERS registry"
```

---

## Task 8: Migrate Line chart to the registry

**Files:**
- Create: `frontend/src/components/report/chartRenderers/LineChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Produces: `LineChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.line`.

- [ ] **Step 1: Extract the Line chart JSX**

Create `frontend/src/components/report/chartRenderers/LineChartRenderer.tsx`:
```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function LineChartRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt }: ChartRendererProps) {
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
        <Line type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2}
          dot={{ fill: 'var(--accent)', r: 3 }}
          activeDot={{ r: 5, fill: 'var(--accent)', stroke: '#fff', strokeWidth: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add the import and registry entry:
```tsx
import LineChartRenderer from './LineChartRenderer'
```
```tsx
  line: LineChartRenderer,
```

- [ ] **Step 3: Delete the inline Line block**

Delete the `// Line chart` block (originally lines 428–445) from `WidgetRenderer.tsx`.

- [ ] **Step 4: Verify build**

```bash
npm run build
```
Expected: succeeds.

- [ ] **Step 5: Manually verify the Line chart**

Open a report with a Line chart widget. Confirm the line, dots, tooltip, click-to-filter, and RTL toggle all behave identically to before.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/LineChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/components/report/WidgetRenderer.tsx
git commit -m "refactor: migrate Line chart to CHART_RENDERERS registry"
```

---

## Task 9: Migrate Pie chart to the registry

**Files:**
- Create: `frontend/src/components/report/chartRenderers/PieChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Produces: `PieChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.pie`.

- [ ] **Step 1: Extract the Pie chart JSX**

Create `frontend/src/components/report/chartRenderers/PieChartRenderer.tsx`:
```tsx
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr, SELECTED_STROKE, getFillFactory } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function PieChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected)
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={rows} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius="70%"
            onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
            label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`}
            labelLine={false}
          >
            {rows.map((r: any, i: number) => {
              const s = getFill(r.name, i)
              return <Cell key={i} fill={s.fill} opacity={s.opacity} stroke={localSelected === r.name ? SELECTED_STROKE : 'none'} strokeWidth={s.strokeWidth ?? 0} />
            })}
          </Pie>
          <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import PieChartRenderer from './PieChartRenderer'
```
```tsx
  pie: PieChartRenderer,
```

- [ ] **Step 3: Delete the inline Pie block**

Delete the `// Pie chart` block (originally lines 447–467) from `WidgetRenderer.tsx`.

- [ ] **Step 4: Verify build**

```bash
npm run build
```

- [ ] **Step 5: Manually verify the Pie chart**

Open a report with a Pie chart widget. Confirm slices, labels, tooltip, click-to-filter (including the white selection stroke), and RTL layout are unchanged.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/PieChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/components/report/WidgetRenderer.tsx
git commit -m "refactor: migrate Pie chart to CHART_RENDERERS registry"
```

---

## Task 10: Migrate Donut chart to the registry

**Files:**
- Create: `frontend/src/components/report/chartRenderers/DonutChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Produces: `DonutChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.donut`.

- [ ] **Step 1: Extract the Donut chart JSX**

Create `frontend/src/components/report/chartRenderers/DonutChartRenderer.tsx`:
```tsx
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TT, fmtStr, getFillFactory } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function DonutChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected)
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={rows} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius="40%" outerRadius="70%"
            onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          >
            {rows.map((r: any, i: number) => {
              const s = getFill(r.name, i)
              return <Cell key={i} fill={s.fill} opacity={s.opacity} />
            })}
          </Pie>
          <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import DonutChartRenderer from './DonutChartRenderer'
```
```tsx
  donut: DonutChartRenderer,
```

- [ ] **Step 3: Delete the inline Donut block**

Delete the `// Donut chart` block (originally lines 469–488) from `WidgetRenderer.tsx`.

- [ ] **Step 4: Verify build**

```bash
npm run build
```

- [ ] **Step 5: Manually verify the Donut chart**

Open a report with a Donut chart widget. Confirm the ring, legend, tooltip, and click-to-filter behave identically.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/DonutChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/components/report/WidgetRenderer.tsx
git commit -m "refactor: migrate Donut chart to CHART_RENDERERS registry"
```

---

## Task 11: Migrate Scatter chart to the registry

**Files:**
- Create: `frontend/src/components/report/chartRenderers/ScatterChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Produces: `ScatterChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.scatter`.

**Note:** this task preserves the existing `r.x ?? r.name, r.y ?? r.value` fallback exactly as-is — this is Phase 0, a pure refactor. Giving Scatter real two-measure backend data is explicitly out of scope here (see Phase 2 in the design spec, `docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md`).

- [ ] **Step 1: Extract the Scatter chart JSX**

Create `frontend/src/components/report/chartRenderers/ScatterChartRenderer.tsx`:
```tsx
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function ScatterChartRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt, allFormats }: ChartRendererProps) {
  const scatterData = rows.map((r: any) => ({ x: r.x ?? r.name, y: r.y ?? r.value }))
  const xFmt = allFormats?.[cfg.x_axis]
  const yFmt = allFormats?.[cfg.y_axis] ?? measureFmt
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="x" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} tickFormatter={v => fmtStr(v, xFmt)} />
        <YAxis dataKey="y" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, yFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === 'x' ? xFmt : yFmt), name]} />
        <Scatter data={scatterData} fill="var(--accent)"
          onClick={broadcasts ? (d: any) => onClickPoint(d.x) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        />
      </ScatterChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import ScatterChartRenderer from './ScatterChartRenderer'
```
```tsx
  scatter: ScatterChartRenderer,
```

- [ ] **Step 3: Delete the inline Scatter block**

Delete the `// Scatter chart` block (originally lines 490–509) from `WidgetRenderer.tsx`.

- [ ] **Step 4: Verify build**

```bash
npm run build
```

- [ ] **Step 5: Manually verify the Scatter chart**

Open a report with a Scatter chart widget. Confirm points render in the same positions as before (still derived from `name`/`value` since real x/y isn't implemented yet).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/ScatterChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/components/report/WidgetRenderer.tsx
git commit -m "refactor: migrate Scatter chart to CHART_RENDERERS registry"
```

---

## Task 12: Migrate Treemap to the registry

**Files:**
- Create: `frontend/src/components/report/chartRenderers/TreemapChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Produces: `TreemapChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.treemap`.

- [ ] **Step 1: Extract the Treemap JSX**

Create `frontend/src/components/report/chartRenderers/TreemapChartRenderer.tsx`:
```tsx
import { Treemap, ResponsiveContainer } from 'recharts'
import { COLORS, SELECTED_STROKE, DIM_OPACITY } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function TreemapChartRenderer({ rows, rtl, broadcasts, localSelected, onClickPoint }: ChartRendererProps) {
  const tmData = rows.map((r: any, i: number) => ({ name: r.name, size: r.value, _i: i }))
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <Treemap data={tmData} dataKey="size" nameKey="name" aspectRatio={4/3}
          onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          content={({ x, y, width, height, name, _i }: any) => {
            const color = COLORS[(_i ?? 0) % COLORS.length]
            const isActive = localSelected === name
            const dimmed  = broadcasts && localSelected !== null && !isActive
            return width > 8 && height > 8 ? (
              <g>
                <rect x={x} y={y} width={width} height={height}
                  fill={color} opacity={dimmed ? DIM_OPACITY : 1}
                  stroke={isActive ? SELECTED_STROKE : 'var(--surface)'} strokeWidth={isActive ? 2 : 1.5} rx={4} />
                {width > 60 && height > 28 && (
                  <text x={x + width / 2} y={y + height / 2} textAnchor="middle" dominantBaseline="middle"
                    fill="#fff" fontSize={Math.min(12, width / 7)} fontWeight={600}>{name}</text>
                )}
              </g>
            ) : <g />
          }}
        />
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import TreemapChartRenderer from './TreemapChartRenderer'
```
```tsx
  treemap: TreemapChartRenderer,
```

- [ ] **Step 3: Delete the inline Treemap block and the now-unreachable fallback**

Delete the `// Treemap` block (originally lines 511–540) from `WidgetRenderer.tsx`. The final line of `WidgetBody`, `return <EmptyState msg={\`Unknown widget: ${wt}\`} />`, stays — it's now the fallback for any widget type with neither a registered renderer nor a matching non-chart branch (kpi/table/crosstab/list/text/button), which is the correct behavior for a genuinely unknown type.

At this point, `WidgetBody` should have no more `if (wt === '<chart type>')` blocks for chart types — only the non-chart branches (text, button, kpi, table/crosstab, list) plus the `ChartRenderer` dispatch and the final `EmptyState` fallback remain. Clean up now-unused `recharts` imports at the top of the file (everything except what's still used by other WidgetRenderer.tsx code, which should be nothing — `ResponsiveContainer` and friends are only used inside the extracted renderer files now).

- [ ] **Step 4: Verify build**

```bash
npm run build
```
Expected: succeeds with no unused-import warnings/errors.

- [ ] **Step 5: Manually verify the Treemap and run a full smoke pass**

Open a report with a Treemap widget — confirm rectangles, labels, click-to-filter, and dimming behave identically. Then re-open the Bar/Line/Pie/Donut/Scatter widgets checked in Tasks 7–11 once more, since this task removed the last of the legacy inline code.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/TreemapChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/components/report/WidgetRenderer.tsx
git commit -m "refactor: migrate Treemap to CHART_RENDERERS registry, remove legacy if-chain"
```

---

## Task 13: `ROLE_SPECS` table

**Files:**
- Modify: `frontend/src/types/report.ts`

**Interfaces:**
- Produces: `interface RoleField { role: string; label?: string; required: boolean; multi?: boolean }` and `ROLE_SPECS: Record<WidgetType, RoleField[]>`.
- Consumes (by Task 14): `WidgetConfigPanel.tsx` iterates `ROLE_SPECS[wt]` to render field pickers.

- [ ] **Step 1: Add `RoleField` type and `ROLE_SPECS` table**

In `frontend/src/types/report.ts`, add after the `WIDGET_CATALOG` export (after line 67):
```ts
export interface RoleField {
  role: string
  label?: string
  required: boolean
  multi?: boolean
}

// Declares which role fields WidgetConfigPanel should render for each widget type.
// Phase 0 mirrors today's dimension/dimension2/measure fields exactly — no new roles
// are introduced yet. Phase 1+ chart types add their own entries here (size/color/group/
// start/end roles) as they're built.
export const ROLE_SPECS: Record<WidgetType, RoleField[]> = {
  bar:      [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  line:     [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  pie:      [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  donut:    [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  scatter:  [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  treemap:  [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  kpi:      [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  table:    [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  crosstab: [{ role: 'category',  label: 'Dimension (Group / X-axis)', required: true },
             { role: 'category2', label: 'Column Pivot',               required: false },
             { role: 'measure',   label: 'Measure (numeric column)',   required: false }],
  list:     [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  text:     [],
  button:   [],
}
```

- [ ] **Step 2: Verify build**

Run (from `frontend/`):
```bash
npm run build
```
Expected: succeeds (this is a pure addition, nothing consumes `ROLE_SPECS` yet).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/report.ts
git commit -m "feat: add ROLE_SPECS table describing widget config fields per type"
```

---

## Task 14: Refactor `WidgetConfigPanel` to render fields from `ROLE_SPECS`

**Files:**
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Consumes: `ROLE_SPECS`, `RoleField` (Task 13).

- [ ] **Step 1: Add role-value state keyed by role name instead of separate `dimension`/`dimension2`/`measure` state**

In `frontend/src/components/report/WidgetConfigPanel.tsx`:

1. Add the import:
```ts
import { AGGREGATIONS, ROLE_SPECS } from '../../types/report'
```
(replacing the existing `import { AGGREGATIONS } from '../../types/report'` at line 3).

2. Replace the three separate state declarations (lines 27–29):
```ts
  const [dimension,  setDimension]  = useState(cfg.dimension  ?? '')
  const [dimension2, setDimension2] = useState(cfg.dimension2 ?? '')
  const [measure,    setMeasure]    = useState(cfg.measure    ?? '')
```
with a single role-keyed map:
```ts
  const [roleValues, setRoleValues] = useState<Record<string, string>>({
    category:  cfg.dimension  ?? '',
    category2: cfg.dimension2 ?? '',
    measure:   cfg.measure    ?? '',
  })
  const setRole = (role: string, value: string) => setRoleValues(prev => ({ ...prev, [role]: value }))
```

3. In the widget-change `useEffect` (lines 58–75), replace:
```ts
    setDimension(cfg.dimension ?? '')
    setDimension2(cfg.dimension2 ?? '')
    setMeasure(cfg.measure ?? '')
```
with:
```ts
    setRoleValues({ category: cfg.dimension ?? '', category2: cfg.dimension2 ?? '', measure: cfg.measure ?? '' })
```

4. In the dataset-change handler (inside the `datasets && Object.keys(datasets).length > 1` block, ~lines 134–142), replace:
```ts
            setDimension('')
            setDimension2('')
            setMeasure('')
```
with:
```ts
            setRoleValues({ category: '', category2: '', measure: '' })
```

5. In the config-emitting `useEffect` (lines 78–96), replace:
```ts
      if (dimension)  config.dimension  = dimension
      if (dimension2) config.dimension2 = dimension2
      if (measure)    config.measure    = measure
```
with:
```ts
      if (roleValues.category)  config.dimension  = roleValues.category
      if (roleValues.category2) config.dimension2 = roleValues.category2
      if (roleValues.measure)   config.measure    = roleValues.measure
```
and update the effect's dependency array (line 96) — replace `dimension, dimension2, measure,` with `JSON.stringify(roleValues),`.

Note: role values still serialize to the exact same legacy config keys (`dimension`/`dimension2`/`measure`) — this keeps every existing saved widget config, and the backend `resolve_roles()` compatibility mapping from Task 3, working unchanged.

- [ ] **Step 2: Replace the hardcoded Dimension/Column Pivot/Measure fields with a `ROLE_SPECS`-driven loop**

Replace this block (lines 168–182):
```tsx
        {wt !== 'text' && wt !== 'button' && (<>
          {/* Dimension */}
          {fld('Dimension (Group / X-axis)',
            sel(dimension, setDimension, colOptions, '— select column —')
          )}

          {/* Second dimension for crosstab */}
          {wt === 'crosstab' && fld('Column Pivot',
            sel(dimension2, setDimension2, colOptions)
          )}

          {/* Measure */}
          {fld('Measure (numeric column)',
            sel(measure, setMeasure, numCols.map(c => ({ value:c.name, label:c.name })), '— count rows —')
          )}
```
with:
```tsx
        {wt !== 'text' && wt !== 'button' && (<>
          {/* Role fields — driven by ROLE_SPECS so each widget type declares its own fields
              instead of this component hardcoding a conditional per type. */}
          {(ROLE_SPECS[wt] ?? []).map(rf => {
            const options = rf.role === 'measure'
              ? numCols.map(c => ({ value: c.name, label: c.name }))
              : colOptions
            const placeholder = rf.role === 'measure' ? '— count rows —' : '— select column —'
            return (
              <div key={rf.role}>
                {fld(rf.label ?? rf.role, sel(roleValues[rf.role] ?? '', v => setRole(rf.role, v), options, placeholder))}
              </div>
            )
          })}
```

The rest of the `(<>...</>)` block (Aggregation, Running metric, column selector, Sort, Row limit — lines 184–252) is unchanged.

- [ ] **Step 3: Verify build**

Run (from `frontend/`):
```bash
npm run build
```
Expected: succeeds.

- [ ] **Step 4: Manually verify the config panel for every widget type**

With the app running, open the widget config panel (edit mode) for one widget of each type: bar, line, pie, donut, scatter, treemap, kpi, table, crosstab, list. For each, confirm:
- The same fields appear in the same order as before (Dimension, [Column Pivot for crosstab only], Measure, Aggregation, ...).
- Changing a field still updates the widget's rendered output after the 600ms debounce.
- Switching between widgets still correctly resets the panel to that widget's saved values (no stale state bleeding across widgets — this was the purpose of the `mounted` ref guard, unchanged by this task).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "refactor: drive WidgetConfigPanel field rendering from ROLE_SPECS"
```

---

## Task 15: Full regression pass and Phase 0 close-out

**Files:** none (verification only)

- [ ] **Step 1: Run the full automated test suite**

Backend (from `backend/`):
```bash
pytest -v
```
Expected: all tests pass (smoke, `test_widget_shapers.py`, `test_resolve_roles.py`).

Frontend (from `frontend/`):
```bash
npm run build
npm run test
```
Expected: build succeeds, all Vitest tests pass.

- [ ] **Step 2: Full manual regression in the browser**

Start the stack:
```bash
docker compose up -d --build
```
Open `http://localhost:3000`. For each of the 6 chart types (bar, line, pie, donut, scatter, treemap) plus kpi, table, crosstab, and list:
1. Open (or create) a report widget of that type against a real uploaded dataset.
2. Confirm it renders with correct data.
3. Confirm cross-filter click-to-filter and clear-on-repeat-click still work.
4. Confirm the RTL toggle in the config panel still flips the widget correctly.
5. Confirm value formatting (currency/percent/badge/trend, if configured via Column Formats) still displays correctly.

- [ ] **Step 3: Update the design spec status**

In `docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md`, change the `**Status:**` line from `Approved` to `Phase 0 Complete`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md
git commit -m "docs: mark chart-type-expansion Phase 0 complete"
```

**Phase 0 is now done.** The `SHAPERS` and `CHART_RENDERERS` registries plus `ROLE_SPECS` are in place with zero behavior change. Phase 1 (Histogram, Dual Axis Bar/Line/Bar-Line/Time Series, Comparative Time Series, Step Plot, Dot Plot, Needle Plot, Numeric Series Plot — 10 chart types) gets its own plan document, written fresh against this foundation, before implementation starts.
