# Analytics Engine Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add time-intelligence calculation functions (YEAR/MONTH/QUARTER/DATETRUNC/YTD/SAMEPERIODLASTYEAR/YOY_GROWTH), automatic Year→Quarter→Month→Day hierarchy generation for date columns, and an in-process query-result cache for widget-data requests — three additive, independently-scoped extensions to the existing analytics engine.

**Architecture:** All three extend existing, already-shipped mechanisms rather than introducing new ones: the expression engine's `_build_safe_ns` function catalog (Part 1), the `HierarchyNode` self-referencing model via the existing `auto-generate` endpoint (Part 2), and `get_widget_data`'s single call path via a module-level in-process LRU cache (Part 3, no new infra dependency). No schema migrations, no new libraries.

**Tech Stack:** Python, FastAPI, pandas, SQLAlchemy (existing stack, unchanged).

## Global Constraints

- **Security (hard constraint):** the widget-data cache key (Part 3) MUST include `rls_filter_expr` verbatim, uninterpreted, uncombined with anything else. Two roles with different RLS restrictions must never share a cache entry for the same dataset+config — this is what prevents a cached fail-closed-empty result for one role's malformed rule leaking to a different role, and prevents an unrestricted result leaking to a restricted role.
- **No user-facing `.dt`/attribute access:** all new time-intelligence functions (Part 1) perform `.dt` attribute access only inside their own trusted Python function bodies — never introduce a function whose *user-facing expression syntax* would require attribute access, since `_validate_expr_safety` (an existing security control) rejects all `ast.Attribute` nodes in user expressions by design. Do not weaken or bypass that check.
- **No schema/migration changes anywhere in this plan** — `HierarchyNode` already has every field Part 2 needs (`parent_id`, `column_name`, `format`, `node_type`, `position`); no `_migrate()` statement is added.
- **No new dependencies** — Part 3's cache is in-process (module-level `OrderedDict` + `threading.Lock`), no Redis or caching library added to `requirements.txt`.
- **`DATETRUNC(..., 'week')`** truncates to the Monday-starting ISO week (`to_period('W').dt.start_time`) — not Sunday-start.
- **`SAMEPERIODLASTYEAR`/`YOY_GROWTH` are monthly-granularity only** — no weekly/quarterly/fiscal-calendar variants in this plan. A row whose (year−1, month) has no matching data resolves to `NaN`, never `0` (0 would be indistinguishable from "genuinely zero last year").
- **Error handling matches existing convention** — new functions raise on bad input and let it propagate through `_eval_expr` exactly like every existing function in `_build_safe_ns`; do not add try/except inside the new functions themselves.
- Test files follow existing conventions in `backend/tests/`: `_eval_expr`-direct-call style for expression-engine tests (see `test_expression_sandbox_escape.py`), fixture-based (`client`, `db_session`, `two_orgs`, `auth_headers`) for router/HTTP tests (see `test_hierarchy_widget_analysis_org_scoping.py`), `tmp_path`+real-CSV style for file-backed tests (see `test_get_widget_data_rls.py`). No mocks of the code under test.

---

### Task 1: Time-intelligence calculation functions

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_time_intelligence_functions.py`

**Interfaces:**
- Produces: `YEAR(s)`, `QUARTER(s)`, `MONTH(s)`, `DAY(s)`, `DATETRUNC(s, unit)`, `YTD(measure, date_col)`, `SAMEPERIODLASTYEAR(measure, date_col)`, `YOY_GROWTH(measure, date_col)` — all registered in `_build_safe_ns`'s `safe_globals` dict, callable from any calculated-column or filter expression exactly like the existing `SUM`/`GROUPSUM`/etc. functions. No other task depends on these directly, but they share the file Task 3 also modifies.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_time_intelligence_functions.py`:

```python
import pandas as pd
from app.services.widget_data import _eval_expr


def test_date_part_extraction():
    df = pd.DataFrame({"d": pd.to_datetime(["2024-01-15", "2024-07-04", "2023-12-31"])})
    assert _eval_expr("YEAR(d)", df).tolist() == [2024, 2024, 2023]
    assert _eval_expr("QUARTER(d)", df).tolist() == [1, 3, 4]
    assert _eval_expr("MONTH(d)", df).tolist() == [1, 7, 12]
    assert _eval_expr("DAY(d)", df).tolist() == [15, 4, 31]


def test_datetrunc_month_and_string_dates_are_coerced():
    # date column stored as plain strings, like a freshly-read CSV column
    df = pd.DataFrame({"d": ["2024-03-17", "2024-03-02"]})
    result = _eval_expr("DATETRUNC(d, 'month')", df)
    assert list(result) == [pd.Timestamp("2024-03-01")] * 2


def test_ytd_resets_at_year_boundary():
    df = pd.DataFrame({
        "d": pd.to_datetime(["2023-12-01", "2024-01-01", "2024-02-01"]),
        "sales": [1000, 10, 20],
    })
    assert _eval_expr("YTD(sales, d)", df).tolist() == [1000, 10, 30]


def test_sameperiodlastyear_missing_prior_year_is_nan_and_yoy_growth_computes():
    df = pd.DataFrame({
        "d": pd.to_datetime(["2023-01-15", "2024-01-10", "2024-01-20"]),
        "sales": [100, 60, 90],
    })
    spy = _eval_expr("SAMEPERIODLASTYEAR(sales, d)", df)
    assert pd.isna(spy.iloc[0])       # 2023-01 has no 2022-01 to compare against
    assert spy.iloc[1] == spy.iloc[2] == 100.0

    growth = _eval_expr("YOY_GROWTH(sales, d)", df)
    assert pd.isna(growth.iloc[0])
    assert round(growth.iloc[1], 2) == 50.0   # (150 - 100) / 100 * 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_time_intelligence_functions.py -v`
Expected: FAIL — `NameError`/eval errors, since `YEAR`/`QUARTER`/etc. aren't in `safe_globals` yet.

- [ ] **Step 3: Add the functions to `_build_safe_ns`**

In `backend/app/services/widget_data.py`, inside `_build_safe_ns(df)`, add this block after the existing group-by window functions (`GROUPSUM`, `GROUPAVG`, etc., right before the `safe_globals = {` dict literal):

```python
    # ── Date / time intelligence ───────────────────────────────────────────
    def _as_datetime(s):
        """Coerce a Series to datetime64 if it isn't already; errors='coerce' turns
        unparseable values into NaT rather than raising."""
        if pd.api.types.is_datetime64_any_dtype(s):
            return s
        return pd.to_datetime(s, errors='coerce')

    def YEAR(s):     return _as_datetime(s).dt.year        # noqa: N802
    def QUARTER(s):  return _as_datetime(s).dt.quarter      # noqa: N802
    def MONTH(s):    return _as_datetime(s).dt.month        # noqa: N802
    def DAY(s):      return _as_datetime(s).dt.day          # noqa: N802

    def DATETRUNC(s, unit):  # noqa: N802
        dt = _as_datetime(s)
        unit = str(unit).lower()
        period_code = {'year': 'Y', 'quarter': 'Q', 'month': 'M', 'week': 'W', 'day': 'D'}.get(unit)
        if period_code is None:
            raise ValueError(f"DATETRUNC: unsupported unit '{unit}'")
        if period_code == 'D':
            return dt.dt.normalize()
        return dt.dt.to_period(period_code).dt.start_time

    def YTD(measure, date_col):  # noqa: N802
        """Cumulative sum within each calendar year, resetting at each year boundary.
        Uses row order (positional), matching CUMSUM/DIFF/LAG/LEAD's existing convention
        of never implicitly re-sorting the caller's dataframe."""
        year = _as_datetime(date_col).dt.year
        return measure.groupby(year).cumsum()

    def SAMEPERIODLASTYEAR(measure, date_col):  # noqa: N802
        """Monthly YoY lookup: SUM of measure in the same calendar month one year
        earlier, broadcast to every row sharing that (year, month). NaN if no data
        exists for (year-1, month)."""
        dt = _as_datetime(date_col)
        year, month = dt.dt.year, dt.dt.month
        totals = measure.groupby([year, month]).sum()
        prior_index = pd.MultiIndex.from_arrays([year - 1, month])
        result = totals.reindex(prior_index)
        result.index = measure.index
        return result

    def YOY_GROWTH(measure, date_col):  # noqa: N802
        dt = _as_datetime(date_col)
        year, month = dt.dt.year, dt.dt.month
        current = measure.groupby([year, month]).transform('sum')
        prior = SAMEPERIODLASTYEAR(measure, date_col)
        return (current - prior) / prior * 100
```

Then add these entries to the `safe_globals` dict literal (after the existing `'GROUPMIN': GROUPMIN, 'GROUPMAX': GROUPMAX, 'GROUPPCT': GROUPPCT,` line):

```python
        # date / time intelligence
        'YEAR': YEAR, 'QUARTER': QUARTER, 'MONTH': MONTH, 'DAY': DAY,
        'DATETRUNC': DATETRUNC, 'YTD': YTD,
        'SAMEPERIODLASTYEAR': SAMEPERIODLASTYEAR, 'YOY_GROWTH': YOY_GROWTH,
```

Also add one line to the module's top-of-file docstring (in the existing function-category enumeration) noting the new "Date / time intelligence" category, matching the docstring's existing style — this is documentation only, no behavior change, and optional if the docstring's existing structure doesn't have an obvious insertion point (don't force it awkwardly).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_time_intelligence_functions.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: all existing tests still pass (255 + the 4 new ones = 259).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_time_intelligence_functions.py
git commit -m "feat: add time-intelligence functions (YEAR/MONTH/QUARTER/DATETRUNC/YTD/SAMEPERIODLASTYEAR/YOY_GROWTH)"
```

---

### Task 2: Auto date/time hierarchy generation

**Files:**
- Modify: `backend/app/routers/hierarchy.py`
- Test: `backend/tests/test_hierarchy_auto_generate_dates.py`

**Interfaces:** None consumed from Task 1. Fully independent — touches a different file.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_hierarchy_auto_generate_dates.py`:

```python
import pandas as pd
from app.models.models import Dataset


async def _seed_dataset_with_file(db_session, org_id, tmp_path, rows, name="d.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False)
    ds = Dataset(name="D", org_id=org_id, filename=str(path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_auto_generate_creates_year_quarter_month_day_chain_for_date_column(
    client, db_session, two_orgs, auth_headers, tmp_path
):
    ds = await _seed_dataset_with_file(db_session, two_orgs["a"]["org"].id, tmp_path, [
        {"order_date": "2024-01-01", "region": "East", "sales": 10},
        {"order_date": "2024-02-01", "region": "West", "sales": 20},
    ])

    resp = await client.post(f"/api/v1/datasets/{ds.id}/hierarchy/auto-generate", headers=auth_headers["a"])
    assert resp.status_code == 200
    nodes = {n["id"]: n for n in resp.json()}

    dates_folder = next(n for n in nodes.values() if n["node_type"] == "folder" and n["name"] == "Dates")
    date_col_node = next(n for n in nodes.values() if n["parent_id"] == dates_folder["id"])
    assert date_col_node["name"] == "order_date"
    assert date_col_node["column_name"] == "order_date"

    year_node = next(n for n in nodes.values() if n["parent_id"] == date_col_node["id"])
    assert year_node["name"] == "Year" and year_node["format"] == "year"
    quarter_node = next(n for n in nodes.values() if n["parent_id"] == year_node["id"])
    assert quarter_node["name"] == "Quarter" and quarter_node["format"] == "quarter"
    month_node = next(n for n in nodes.values() if n["parent_id"] == quarter_node["id"])
    assert month_node["name"] == "Month" and month_node["format"] == "month"
    day_node = next(n for n in nodes.values() if n["parent_id"] == month_node["id"])
    assert day_node["name"] == "Day" and day_node["format"] == "day"
    # every drill level points back at the same raw column, none has its own aggregation
    for n in (year_node, quarter_node, month_node, day_node):
        assert n["column_name"] == "order_date"
        assert n["aggregation"] is None


async def test_auto_generate_leaves_non_date_columns_flat(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(db_session, two_orgs["a"]["org"].id, tmp_path, [
        {"region": "East", "sales": 10}, {"region": "West", "sales": 20},
    ], name="d2.csv")

    resp = await client.post(f"/api/v1/datasets/{ds.id}/hierarchy/auto-generate", headers=auth_headers["a"])
    nodes = resp.json()

    region_node = next(n for n in nodes if n["name"] == "region")
    sales_node = next(n for n in nodes if n["name"] == "sales")
    assert not any(n["parent_id"] == region_node["id"] for n in nodes)  # still a flat leaf
    assert not any(n["parent_id"] == sales_node["id"] for n in nodes)
    assert sales_node["aggregation"] == "sum"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_hierarchy_auto_generate_dates.py -v`
Expected: FAIL — `test_auto_generate_creates_year_quarter_month_day_chain_for_date_column` fails because no children exist under the date column node yet (current behavior is a flat leaf with no drill chain). `test_auto_generate_leaves_non_date_columns_flat` should already PASS against current code (it's a regression-lock test) — if it doesn't, investigate before proceeding.

- [ ] **Step 3: Extend `auto_generate`'s datetime branch**

In `backend/app/routers/hierarchy.py`, add this constant near the top of the file (module level, after the `router = APIRouter(...)` line):

```python
DATE_DRILL_LEVELS = [("Year", "year"), ("Quarter", "quarter"), ("Month", "month"), ("Day", "day")]
```

Inside `auto_generate`, in the `for col_name, col_type in type_map.items():` loop, immediately after the existing block that creates `node` and does `counters[col_type] += 1`, add:

```python
        if col_type == "datetime":
            # Linear Year -> Quarter -> Month -> Day drill chain under this date
            # column's node. Every level shares the same underlying column_name
            # (none has its own physical column) -- `format` is what
            # distinguishes granularity. No aggregation: these are drill/grouping
            # levels, not measures.
            await db.flush()  # assign node.id so it can be used as parent_id below
            parent_id = node.id
            for pos, (label, granularity) in enumerate(DATE_DRILL_LEVELS):
                level_node = HierarchyNode(
                    dataset_id=dataset_id, parent_id=parent_id, name=label,
                    node_type="date", column_name=col_name, aggregation=None,
                    format=granularity, position=pos,
                )
                db.add(level_node)
                await db.flush()
                parent_id = level_node.id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_hierarchy_auto_generate_dates.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass, including `test_hierarchy_widget_analysis_org_scoping.py`'s existing hierarchy tests (org-scoping on hierarchy endpoints must be unaffected).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/hierarchy.py backend/tests/test_hierarchy_auto_generate_dates.py
git commit -m "feat: auto-generate Year/Quarter/Month/Day drill hierarchy for date columns"
```

---

### Task 3: Query-result cache for widget-data

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_widget_data_cache.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-2 directly, but modifies the same file as Task 1 (`widget_data.py`) — execute after Task 1 to avoid a self-inflicted merge conflict.
- Produces: `get_widget_data(..., use_cache: bool = True)` (new optional kwarg, backward compatible — every existing caller, including `backend/app/routers/widget_data.py`'s `query_widget`, is unaffected and gets caching automatically), `clear_widget_data_cache()` (test/escape-hatch utility).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_widget_data_cache.py`:

```python
import os
import time
import pandas as pd
import app.services.widget_data as wd
from app.services.widget_data import get_widget_data, clear_widget_data_cache


def _write_csv(tmp_path, rows, name="d.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def setup_function():
    clear_widget_data_cache()


def test_repeated_identical_query_hits_cache(tmp_path, monkeypatch):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])
    calls = {"n": 0}
    real_load = wd.load_file
    def counting_load(p):
        calls["n"] += 1
        return real_load(p)
    monkeypatch.setattr(wd, "load_file", counting_load)

    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}
    r1 = get_widget_data(path, config, widget_type="bar")
    r2 = get_widget_data(path, config, widget_type="bar")

    assert r1 == r2
    assert calls["n"] == 1  # second call served from cache, file never re-read


def test_different_rls_filter_expr_never_shares_a_cache_entry(tmp_path):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}

    unrestricted = get_widget_data(path, config, widget_type="bar", rls_filter_expr=None)
    restricted = get_widget_data(path, config, widget_type="bar", rls_filter_expr="region == 'North'")

    assert {r["name"] for r in unrestricted["rows"]} == {"North", "South"}
    assert {r["name"] for r in restricted["rows"]} == {"North"}


def test_file_mtime_change_invalidates_cache(tmp_path):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}])
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}
    r1 = get_widget_data(path, config, widget_type="bar")
    assert r1["rows"][0]["value"] == 100

    pd.DataFrame([{"region": "North", "sales": 999}]).to_csv(path, index=False)
    os.utime(path, (time.time() + 5, time.time() + 5))  # force a distinct mtime past fs resolution
    r2 = get_widget_data(path, config, widget_type="bar")
    assert r2["rows"][0]["value"] == 999


def test_cache_is_bounded_by_maxsize(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "widget_data_cache_maxsize", 2)
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}])

    for i in range(5):
        get_widget_data(path, {"dimension": "region", "measure": "sales", "limit": i}, widget_type="bar")

    assert len(wd._WIDGET_DATA_CACHE) <= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_widget_data_cache.py -v`
Expected: FAIL — `clear_widget_data_cache` doesn't exist, `wd._WIDGET_DATA_CACHE` doesn't exist, `use_cache` kwarg doesn't exist yet (the calls without it will still work since it's meant to be optional, but the cache-hit assertion `calls["n"] == 1` will fail since there's no caching at all yet — every call re-reads the file).

- [ ] **Step 3: Add the `widget_data_cache_maxsize` setting**

In `backend/app/core/config.py`, add this field to the `Settings` class (alongside the existing `max_upload_mb: int = 100` line):

```python
    widget_data_cache_maxsize: int = 500
```

- [ ] **Step 4: Add the cache machinery and rewrite `get_widget_data`**

In `backend/app/services/widget_data.py`, add these imports near the top of the file (alongside the existing `import pandas as pd` / `import numpy as np` block):

```python
import json
import os
import threading
from collections import OrderedDict
from ..core.config import settings
```

Then replace the existing `get_widget_data` function (currently the last function in the file) with:

```python
_WIDGET_DATA_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_WIDGET_DATA_CACHE_LOCK = threading.Lock()


def _widget_data_cache_key(
    file_path: str, file_stat: tuple | None, config: dict, widget_type: str,
    calculated_columns: list[dict] | None, filter_expr: str | None, rls_filter_expr: str | None,
) -> str:
    """Canonical, hashable (string) cache key. rls_filter_expr is included
    VERBATIM and un-normalized -- this is load-bearing for RLS isolation: two
    roles with different filter expression strings for the same
    dataset+config always land in different cache entries, so a role with
    tighter RLS can never be served a cached result computed for a role with
    looser (or no) RLS, and a fail-closed empty result for a malformed
    expression is never served to a different role whose expression is valid."""
    payload = {
        "file_path": file_path,
        "file_stat": file_stat,          # (mtime, size) or None -- invalidates on re-upload
        "config": config,
        "widget_type": widget_type,
        "calculated_columns": calculated_columns or [],
        "filter_expr": filter_expr,
        "rls_filter_expr": rls_filter_expr,
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _widget_data_cache_get(key: str):
    with _WIDGET_DATA_CACHE_LOCK:
        if key in _WIDGET_DATA_CACHE:
            _WIDGET_DATA_CACHE.move_to_end(key)  # mark most-recently-used
            return _WIDGET_DATA_CACHE[key]
    return None


def _widget_data_cache_set(key: str, value: dict) -> None:
    with _WIDGET_DATA_CACHE_LOCK:
        _WIDGET_DATA_CACHE[key] = value
        _WIDGET_DATA_CACHE.move_to_end(key)
        maxsize = settings.widget_data_cache_maxsize
        while len(_WIDGET_DATA_CACHE) > maxsize:
            _WIDGET_DATA_CACHE.popitem(last=False)  # evict least-recently-used


def clear_widget_data_cache() -> None:
    """Manual full-cache clear. Not wired into any endpoint (mtime-based
    invalidation already covers the re-upload path) -- exposed as a small
    escape hatch for tests and any future 'refresh' action."""
    with _WIDGET_DATA_CACHE_LOCK:
        _WIDGET_DATA_CACHE.clear()


def get_widget_data(
    file_path: str, config: dict, widget_type: str = "bar",
    calculated_columns: list[dict] | None = None, filter_expr: str | None = None,
    rls_filter_expr: str | None = None, use_cache: bool = True,
) -> dict:
    file_stat = None
    if use_cache:
        try:
            st = os.stat(file_path)
            file_stat = (st.st_mtime, st.st_size)
        except OSError:
            file_stat = None  # file missing/unreadable -- fall through, load_file() raises below
        key = _widget_data_cache_key(
            file_path, file_stat, config, widget_type, calculated_columns, filter_expr, rls_filter_expr,
        )
        cached = _widget_data_cache_get(key)
        if cached is not None:
            return cached

    df = load_file(file_path)
    df = apply_rls_filter(df, rls_filter_expr)
    if filter_expr:
        df = apply_filter_expr(df, filter_expr, silent=True)
    if calculated_columns:
        df = apply_calculated_columns(df, calculated_columns)
    result = get_widget_data_from_df(df, config, widget_type)

    if use_cache:
        _widget_data_cache_set(key, result)
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_widget_data_cache.py -v`
Expected: 4 passed.

- [ ] **Step 6: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass — in particular, re-check `tests/test_get_widget_data_rls.py`, `tests/test_rls_fail_closed.py`, and `tests/test_widget_data_rls_enforcement.py` pass unmodified (the cache must not change RLS enforcement behavior, only add caching around it).

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/config.py backend/app/services/widget_data.py backend/tests/test_widget_data_cache.py
git commit -m "feat: add in-process LRU cache for widget-data query results"
```

---

### Task 4: Final regression pass

**Files:** none (verification only).

- [ ] **Step 1: Run the complete backend test suite**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass, 0 failures. Total count should be 255 (pre-existing) + 4 (Task 1) + 2 (Task 2) + 4 (Task 3) = 265.

- [ ] **Step 2: Explicitly re-verify the security-sensitive test files pass**

Run: `cd backend && python -m pytest tests/test_expression_sandbox_escape.py tests/test_get_widget_data_rls.py tests/test_rls_fail_closed.py tests/test_widget_data_rls_enforcement.py tests/test_hierarchy_widget_analysis_org_scoping.py -v`
Expected: all pass — these are the exact test files exercising the RLS/security and hierarchy-CRUD paths this plan's three parts touch or run adjacent to.

---

## Post-Plan State

After Task 4, calculated columns and filter expressions can use `YEAR`/`QUARTER`/`MONTH`/`DAY`/`DATETRUNC`/`YTD`/`SAMEPERIODLASTYEAR`/`YOY_GROWTH` alongside the existing aggregation/window function catalog; `POST /datasets/{id}/hierarchy/auto-generate` builds a real Year→Quarter→Month→Day drill chain for every detected date column (rendered correctly by the existing, unmodified `HierarchyTree.tsx`); and every widget-data query is transparently cached in-process, safely isolated per RLS restriction, with mtime-based invalidation on re-upload and bounded LRU eviction. Hierarchy nodes remain a browse-only tree (not wired into chart authoring) and the AI Insights Engine / report layout engine from the original reference spec remain unscoped, per the plan's Context section.
