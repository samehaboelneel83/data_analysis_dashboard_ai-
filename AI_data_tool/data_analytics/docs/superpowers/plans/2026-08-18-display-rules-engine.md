# Display-Rules Engine Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an expression-driven display-rules engine that restyles marks, cells, widget backgrounds and widget visibility from rules stored on a widget or on the report.

**Architecture:** Rules evaluate on the **shaped result**, not on the source dataframe, because a display rule refers to the aggregated value a mark shows. A new pure module `backend/app/services/display_rules.py` lifts a shaped result into a small DataFrame, evaluates each rule with the *existing* expression sandbox, and returns index-aligned styles under `rule_styles`. Renderers consume a resolved style and never see a rule. Structured conditions are compiled to expression strings **in the frontend** (the `CustomCategoryPanel`→`SWITCH()` precedent), guarded by a backend contract test.

**Tech Stack:** Python 3.12, FastAPI, pandas, pytest / pytest-asyncio (backend); React 18, TypeScript, Recharts, vitest + @testing-library/react (frontend).

**Spec:** `docs/superpowers/specs/2026-08-18-formatting-display-rules-design.md`

## Global Constraints

- **Display rules fail OPEN.** Each rule is evaluated in its own try/except; a failing rule is skipped, recorded in `rule_errors`, and every other rule still applies. This is the deliberate opposite of `apply_rls_filter` (`widget_data.py:1108`), which fails CLOSED to zero rows. Both sites must carry a comment naming the other, or a later reader will "fix" one of them.
- **Never reimplement expression evaluation.** Import `_validate_expr_safety` and `_eval_expr` from `app.services.widget_data`. A second expression path is a second thing to get wrong.
- **`evaluate_rules` never mutates its input.** It returns styles; the caller attaches them.
- **Rules are untrusted client input**, exactly like the rest of `config`. They pass through `_validate_expr_safety` on the same terms as a filter expression. A rule can only change how already-authorised data is coloured — it must never widen what data is returned.
- **Schema changes are additive only:** one line in the `ALTER TABLE … ADD COLUMN IF NOT EXISTS` list in `backend/app/main.py:15-34`. No Alembic; that is not how this repo migrates.
- **Rule columns are RESULT columns, not dataset columns.** A series result exposes `name` and `value`; a table/crosstab exposes `result["columns"]`; a gauge exposes `value` and `target`. A rule on a bar chart's measure is written `value > 1000`.
- Backend tests run from `backend/` with `pytest`. Frontend tests run from `frontend/` with `npm test`.

---

## File Structure

**Created:**
- `backend/app/services/display_rules.py` — the whole engine. Pure functions, no I/O, no ORM.
- `backend/tests/test_display_rules.py` — engine unit tests.
- `backend/tests/test_display_rules_contract.py` — frontend-emitted expressions are accepted by this engine.
- `backend/tests/test_report_display_rules_api.py` — the new report column, end to end.
- `frontend/src/lib/displayRules.ts` — structured condition → expression string, plus shared types.
- `frontend/src/lib/displayRules.test.ts` — compiler unit tests.
- `frontend/src/components/report/DisplayRulesPanel.tsx` — the rule builder UI.
- `frontend/src/components/report/DisplayRulesPanel.test.tsx` — builder tests.

**Modified:**
- `backend/app/services/widget_data.py` — attach the rule pass in `get_widget_data_from_df` (`:814-831`); add the fail-open/fail-closed cross-reference comment at `apply_rls_filter` (`:1108`).
- `backend/app/models/models.py` — `Report.display_rules`.
- `backend/app/schemas/schemas.py` — `ReportUpdate.display_rules`, `ReportOut.display_rules`.
- `backend/app/main.py` — one `ALTER TABLE` line.
- `frontend/src/types/report.ts` — `Report.display_rules`.
- `frontend/src/services/api.ts` — `reportsApi.update` accepts `display_rules`.
- `frontend/src/components/report/chartRenderers/types.ts` — `ruleStyles` on `ChartRendererProps`.
- `frontend/src/components/report/chartUtils.tsx` — `getFillFactory` third parameter.
- `frontend/src/components/report/chartRenderers/{Bar,Pie,Donut,Funnel}ChartRenderer.tsx` — pass rule styles through (these four are every current `getFillFactory` caller).
- `frontend/src/components/report/WidgetRenderer.tsx` — chrome background/visibility, and the table/crosstab/list/KPI/card branches.
- `frontend/src/components/report/WidgetConfigPanel.tsx` — mount the builder.
- `frontend/src/pages/ReportBuilder.tsx` — merge report rules ahead of widget rules; mount report-level rules UI.
- `docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md` — five rows re-scored.

---

### Task 1: Result lifting and expression rules on a series

**Files:**
- Create: `backend/app/services/display_rules.py`
- Test: `backend/tests/test_display_rules.py`

**Interfaces:**
- Consumes: `_validate_expr_safety`, `_eval_expr` from `app.services.widget_data`.
- Produces: `result_frame(result: dict) -> pd.DataFrame | None` and `evaluate_rules(result: dict, rules: list[dict]) -> dict` returning `{"rows": [...], "cells": {...}, "widget": {...}, "errors": [...]}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_display_rules.py
from app.services.display_rules import evaluate_rules, result_frame


def _series_result():
    return {
        "type": "series", "dimension": "region", "measure": "sales",
        "rows": [{"name": "US", "value": 1500}, {"name": "CA", "value": 400}],
        "total": 2,
    }


def test_result_frame_lifts_series_rows_to_name_and_value_columns():
    frame = result_frame(_series_result())

    assert list(frame.columns) == ["name", "value"]
    assert list(frame["value"]) == [1500, 400]


def test_expression_rule_styles_only_the_matching_mark():
    rules = [{
        "id": "r1", "kind": "expression", "target": "mark",
        "expression": "value > 1000", "style": {"fill": "#f87171"},
    }]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [{"fill": "#f87171"}, None]
    assert styles["errors"] == []


def test_later_rule_wins_for_the_same_mark():
    rules = [
        {"id": "report", "kind": "expression", "target": "mark",
         "expression": "value > 100", "style": {"fill": "#aaa"}},
        {"id": "widget", "kind": "expression", "target": "mark",
         "expression": "value > 1000", "style": {"fill": "#f87171"}},
    ]

    styles = evaluate_rules(_series_result(), rules)

    # Report rules are sent first, so a widget rule overriding one is just list order.
    assert styles["rows"] == [{"fill": "#f87171"}, {"fill": "#aaa"}]


def test_no_rules_produces_no_styles():
    styles = evaluate_rules(_series_result(), [])

    assert styles["rows"] == [None, None]
    assert styles["widget"] == {}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_display_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.display_rules'`

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/app/services/display_rules.py
"""Display rules: expression-driven restyling of an already-shaped widget result.

Rules evaluate AFTER shaping, never before. A rule like `value > 1000` refers to the
aggregated value a mark displays, which is what shape_series already produced — so the
engine reads the shaped result, not the dataframe. That placement is what makes rules
work identically for import and DirectQuery, and what makes them re-evaluate correctly
when a cross-filter narrows the context.

FAILURE SEMANTICS — deliberately the opposite of app.services.widget_data.apply_rls_filter,
which fails CLOSED to zero rows because a broken security control must hide data. Display
rules are cosmetic, so a broken rule must never blank or break a widget: each rule is
evaluated in isolation, failures are collected in `errors`, and every other rule still
applies. Do not "make these consistent" — the asymmetry is the point.
"""
import pandas as pd

from app.services.widget_data import _eval_expr, _validate_expr_safety


def result_frame(result: dict) -> pd.DataFrame | None:
    """Lift a shaped widget result into a frame whose columns are what a rule may name.

    Returns None when the result carries nothing a rule could address, in which case
    rules are ignored rather than erroring."""
    rtype = result.get("type")
    rows = result.get("rows") or []

    if rtype == "gauge":
        return pd.DataFrame([{"value": result.get("value"), "target": result.get("target")}])

    if rtype in ("table", "crosstab"):
        cols = result.get("columns") or []
        return pd.DataFrame(rows, columns=cols) if rows and cols else None

    # series, scalar, and shapers that return {name, value} rows without a `type`
    # (shape_card is the current example) all share the same row shape.
    if rows and isinstance(rows[0], dict):
        return pd.DataFrame(rows)

    return None


def _match_mask(expression: str, frame: pd.DataFrame) -> list[bool]:
    """Evaluate a boolean expression to one bool per frame row. A scalar result applies
    to every row, which is what makes `SUM(value) > 100` usable as a widget-level rule."""
    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)
    if hasattr(verdict, "__len__") and not isinstance(verdict, (str, bytes)):
        series = pd.Series(list(verdict), index=frame.index)
        return [bool(v) for v in series.fillna(False)]
    return [bool(verdict)] * len(frame)


def evaluate_rules(result: dict, rules: list[dict]) -> dict:
    """Resolve rules against a shaped result. Never mutates `result`.

    Rules apply in list order and a later rule wins for the same target, so the caller
    orders report-level rules before widget-level ones and gets widget-wins for free."""
    frame = result_frame(result)
    row_count = 0 if frame is None else len(frame)
    styles: dict = {"rows": [None] * row_count, "cells": {}, "widget": {}, "errors": []}
    if frame is None or not rules:
        return styles

    for rule in rules:
        try:
            mask = _match_mask(rule.get("expression") or "", frame)
            style = rule.get("style") or {}
            for i, matched in enumerate(mask):
                if matched:
                    styles["rows"][i] = {**(styles["rows"][i] or {}), **style}
        except Exception as e:  # noqa: BLE001 — cosmetic feature, see module docstring
            styles["errors"].append({"id": rule.get("id"), "message": str(e)})

    return styles
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_display_rules.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/display_rules.py backend/tests/test_display_rules.py
git commit -m "Add display-rules engine: expression rules over shaped results"
```

---

### Task 2: Rule failures are isolated and reported

**Files:**
- Modify: `backend/app/services/display_rules.py`
- Test: `backend/tests/test_display_rules.py`

**Interfaces:**
- Consumes: `evaluate_rules` from Task 1.
- Produces: no signature change; `styles["errors"]` is `[{"id": str, "message": str}]`.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_display_rules.py
import pytest


def test_rule_naming_a_missing_column_is_reported_and_others_still_apply():
    rules = [
        {"id": "broken", "kind": "expression", "target": "mark",
         "expression": "revneue > 1", "style": {"fill": "#000"}},
        {"id": "good", "kind": "expression", "target": "mark",
         "expression": "value > 1000", "style": {"fill": "#f87171"}},
    ]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [{"fill": "#f87171"}, None]
    assert [e["id"] for e in styles["errors"]] == ["broken"]


def test_malformed_rule_leaves_the_widget_data_intact():
    """The assertion that separates display rules from RLS: a broken cosmetic rule must
    NOT blank the widget. apply_rls_filter fails closed to zero rows; this fails open."""
    result = _series_result()
    rules = [{"id": "bad", "kind": "expression", "target": "mark",
              "expression": "value >>> ", "style": {"fill": "#000"}}]

    styles = evaluate_rules(result, rules)

    assert styles["rows"] == [None, None]
    assert len(styles["errors"]) == 1
    assert result["rows"] == [{"name": "US", "value": 1500}, {"name": "CA", "value": 400}]


@pytest.mark.parametrize("expression", [
    "value.__globals__",
    "`value`.to_csv('/tmp/x')",
    "@value",
])
def test_injection_attempts_are_rejected_through_the_rule_path(expression):
    rules = [{"id": "evil", "kind": "expression", "target": "mark",
              "expression": expression, "style": {"fill": "#000"}}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [None, None]
    assert len(styles["errors"]) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_display_rules.py -v -k "missing_column or malformed or injection"`
Expected: the injection and missing-column cases may already pass from Task 1's try/except; any that fail identify the gap. Do not skip this step — knowing which already pass tells you what Step 3 must actually change.

- [ ] **Step 3: Make them pass**

Task 1's per-rule try/except already isolates failures. The one thing to verify is that a *silently wrong* expression cannot slip through: `_eval_expr` falls back to Python `eval` when `df.eval` raises, so confirm `_validate_expr_safety` is called **before** any evaluation (it is, at the top of `_match_mask`). If `test_rule_naming_a_missing_column` fails because pandas returns something odd rather than raising, add an explicit column check at the top of `_match_mask`:

```python
    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)
    if verdict is None:
        raise ValueError(f"Rule expression produced no verdict: {expression}")
```

- [ ] **Step 4: Run the full engine test file**

Run: `cd backend && pytest tests/test_display_rules.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Add the cross-reference comment at the RLS site**

In `backend/app/services/widget_data.py`, extend the `apply_rls_filter` docstring (`:1108`):

```python
    """Apply a RowSecurityRule filter expression. Unlike apply_filter_expr(silent=True)
    used for report-level filters, this fails CLOSED: a malformed/broken RLS expression
    returns zero rows rather than the unfiltered dataframe, because a broken security
    control should hide rows, not reveal them.

    Contrast app.services.display_rules, which fails OPEN for exactly the opposite
    reason: display rules are cosmetic, so a broken one must not blank a widget. Two
    expression paths, two deliberate failure modes — do not unify them."""
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/display_rules.py backend/app/services/widget_data.py backend/tests/test_display_rules.py
git commit -m "Isolate display-rule failures and document the fail-open/fail-closed split"
```

---

### Task 3: Colour-mapped values, including SAS's Any Category mode

**Files:**
- Modify: `backend/app/services/display_rules.py`
- Test: `backend/tests/test_display_rules.py`

**Interfaces:**
- Consumes: `evaluate_rules`.
- Produces: rules of `kind: "value_map"` with `{"column": str | None, "mappings": [{"value": Any, "color": str}], "any_category": bool}`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_display_rules.py
def test_value_map_colours_marks_by_category_value():
    rules = [{
        "id": "r1", "kind": "value_map", "target": "mark", "column": "name",
        "mappings": [{"value": "US", "color": "#6c8fff"}, {"value": "CA", "color": "#34d399"}],
    }]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [{"fill": "#6c8fff"}, {"fill": "#34d399"}]


def test_value_map_leaves_unmapped_values_unstyled():
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "column": "name",
              "mappings": [{"value": "US", "color": "#6c8fff"}]}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [{"fill": "#6c8fff"}, None]


def test_any_category_mode_matches_without_naming_a_column():
    """SAS's Any Category: one mapping applies across every category column in the
    result, so a region colour stays the same colour wherever region appears."""
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "any_category": True,
              "mappings": [{"value": "CA", "color": "#34d399"}]}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [None, {"fill": "#34d399"}]


def test_value_map_needs_no_expression_and_never_errors_on_one():
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "column": "name",
              "mappings": [{"value": "US", "color": "#6c8fff"}]}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["errors"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_display_rules.py -v -k "value_map or any_category"`
Expected: FAIL — value_map rules currently fall into the expression branch with an empty expression

- [ ] **Step 3: Implement the kind dispatch**

Replace the loop body in `evaluate_rules` so each rule dispatches on `kind`:

```python
def _value_map_style(rule: dict, frame: pd.DataFrame, row_index: int) -> dict | None:
    """Direct comparison, never the sandbox — a colour lookup does not need an
    expression evaluator, and routing it through one would only add failure modes."""
    mappings = rule.get("mappings") or []
    if rule.get("any_category"):
        candidates = [c for c in frame.columns if c != "value"]
    else:
        column = rule.get("column")
        candidates = [column] if column in frame.columns else []

    for column in candidates:
        cell = frame.iloc[row_index][column]
        for mapping in mappings:
            if str(cell) == str(mapping.get("value")):
                return {"fill": mapping.get("color")}
    return None


def _rule_row_styles(rule: dict, frame: pd.DataFrame) -> list[dict | None]:
    """One resolved style per frame row for a single rule, or None where it does not match."""
    kind = rule.get("kind") or "expression"
    if kind == "value_map":
        return [_value_map_style(rule, frame, i) for i in range(len(frame))]
    style = rule.get("style") or {}
    return [style if matched else None for matched in _match_mask(rule.get("expression") or "", frame)]
```

and in `evaluate_rules`:

```python
    for rule in rules:
        try:
            for i, style in enumerate(_rule_row_styles(rule, frame)):
                if style:
                    styles["rows"][i] = {**(styles["rows"][i] or {}), **style}
        except Exception as e:  # noqa: BLE001 — cosmetic feature, see module docstring
            styles["errors"].append({"id": rule.get("id"), "message": str(e)})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_display_rules.py -v`
Expected: PASS (all tests, including Task 1 and 2's)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/display_rules.py backend/tests/test_display_rules.py
git commit -m "Add colour-mapped-value display rules with Any Category mode"
```

---

### Task 4: Interval band rules (gauge rules)

**Files:**
- Modify: `backend/app/services/display_rules.py`
- Test: `backend/tests/test_display_rules.py`

**Interfaces:**
- Consumes: `_rule_row_styles`.
- Produces: rules of `kind: "interval"` with `{"column": str, "bands": [{"min": float, "max": float, "color": str}]}`. `column` defaults to `"value"`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_display_rules.py
def _gauge_result():
    return {"type": "gauge", "measure": "attainment", "value": 72, "target": 100, "total": 5}


def test_interval_rule_picks_the_band_containing_the_gauge_value():
    rules = [{"id": "r1", "kind": "interval", "target": "mark", "column": "value", "bands": [
        {"min": 0,  "max": 60,  "color": "#f87171"},
        {"min": 60, "max": 85,  "color": "#fbbf24"},
        {"min": 85, "max": 100, "color": "#34d399"},
    ]}]

    styles = evaluate_rules(_gauge_result(), rules)

    assert styles["rows"] == [{"fill": "#fbbf24"}]


def test_bands_are_lower_inclusive_and_upper_exclusive():
    rules = [{"id": "r1", "kind": "interval", "column": "value", "target": "mark", "bands": [
        {"min": 0,  "max": 60, "color": "#f87171"},
        {"min": 60, "max": 85, "color": "#fbbf24"},
    ]}]
    result = {"type": "gauge", "measure": "m", "value": 60, "target": 100, "total": 1}

    styles = evaluate_rules(result, rules)

    assert styles["rows"] == [{"fill": "#fbbf24"}]


def test_top_of_range_lands_in_the_last_band_rather_than_falling_through():
    """The final band's upper bound is inclusive, so a value equal to the maximum is
    coloured instead of rendering unstyled — the same closed-top-interval choice the
    numeric binning generator already makes."""
    rules = [{"id": "r1", "kind": "interval", "column": "value", "target": "mark", "bands": [
        {"min": 0,  "max": 60,  "color": "#f87171"},
        {"min": 60, "max": 100, "color": "#34d399"},
    ]}]
    result = {"type": "gauge", "measure": "m", "value": 100, "target": 100, "total": 1}

    styles = evaluate_rules(result, rules)

    assert styles["rows"] == [{"fill": "#34d399"}]


def test_value_outside_every_band_is_unstyled():
    rules = [{"id": "r1", "kind": "interval", "column": "value", "target": "mark",
              "bands": [{"min": 0, "max": 50, "color": "#f87171"}]}]
    result = {"type": "gauge", "measure": "m", "value": 90, "target": 100, "total": 1}

    styles = evaluate_rules(result, rules)

    assert styles["rows"] == [None]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_display_rules.py -v -k "interval or band or top_of_range"`
Expected: FAIL — `kind: "interval"` currently falls through to the expression branch

- [ ] **Step 3: Implement interval matching**

```python
def _interval_style(rule: dict, frame: pd.DataFrame, row_index: int) -> dict | None:
    """Bands are lower-inclusive / upper-exclusive, except the last band's upper bound,
    which is inclusive so a value equal to the maximum lands in a band rather than
    falling through unstyled."""
    column = rule.get("column") or "value"
    if column not in frame.columns:
        raise ValueError(f"Interval rule names a column that is not in the result: {column}")
    cell = frame.iloc[row_index][column]
    if pd.isna(cell):
        return None
    value = float(cell)

    bands = rule.get("bands") or []
    for i, band in enumerate(bands):
        low, high = float(band.get("min")), float(band.get("max"))
        is_last = i == len(bands) - 1
        if low <= value < high or (is_last and value == high):
            return {"fill": band.get("color")}
    return None
```

and add the branch to `_rule_row_styles`:

```python
    if kind == "interval":
        return [_interval_style(rule, frame, i) for i in range(len(frame))]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_display_rules.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/display_rules.py backend/tests/test_display_rules.py
git commit -m "Add interval-band display rules, closing the gauge-rules gap"
```

---

### Task 5: Per-cell styling for table and crosstab results

**Files:**
- Modify: `backend/app/services/display_rules.py`
- Test: `backend/tests/test_display_rules.py`

**Interfaces:**
- Consumes: `evaluate_rules`.
- Produces: `styles["cells"]` as `{row_index_str: {column_name: style}}`. A rule **with** `column` styles that cell; a rule **without** `column` styles the whole row via `styles["rows"]`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_display_rules.py
def _table_result():
    return {
        "type": "table",
        "columns": ["region", "sales", "margin"],
        "rows": [["US", 1500, 0.4], ["CA", 400, 0.1]],
        "total": 2,
    }


def test_rule_with_a_column_styles_that_cell_only():
    rules = [{"id": "r1", "kind": "expression", "target": "mark", "column": "sales",
              "expression": "sales > 1000", "style": {"fill": "#f87171"}}]

    styles = evaluate_rules(_table_result(), rules)

    assert styles["cells"] == {"0": {"sales": {"fill": "#f87171"}}}
    assert styles["rows"] == [None, None]


def test_rule_without_a_column_styles_the_whole_row():
    rules = [{"id": "r1", "kind": "expression", "target": "mark",
              "expression": "sales > 1000", "style": {"fill": "#f87171"}}]

    styles = evaluate_rules(_table_result(), rules)

    assert styles["rows"] == [{"fill": "#f87171"}, None]
    assert styles["cells"] == {}


def test_crosstab_columns_are_addressable_by_name():
    result = {"type": "crosstab", "columns": ["region", "Q1", "Q2", "__total__"],
              "rows": [["US", 10, 90, 100], ["CA", 5, 5, 10]], "total": 2}
    rules = [{"id": "r1", "kind": "expression", "target": "mark", "column": "Q2",
              "expression": "Q2 > 50", "style": {"fill": "#34d399"}}]

    styles = evaluate_rules(result, rules)

    assert styles["cells"] == {"0": {"Q2": {"fill": "#34d399"}}}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_display_rules.py -v -k "cell or whole_row or crosstab"`
Expected: FAIL — everything currently lands in `styles["rows"]`

- [ ] **Step 3: Route styles to cells when the rule names a column**

In `evaluate_rules`, replace the accumulation loop:

```python
    for rule in rules:
        try:
            column = rule.get("column")
            # A column-scoped rule paints one cell; an unscoped rule paints the row.
            # value_map/interval rules use `column` to READ from, not to paint, so they
            # only ever paint cells on table-shaped results where cells exist.
            cell_scoped = bool(column) and column in frame.columns and _is_tabular(result)
            for i, style in enumerate(_rule_row_styles(rule, frame)):
                if not style:
                    continue
                if cell_scoped:
                    key = str(i)
                    styles["cells"].setdefault(key, {})
                    styles["cells"][key][column] = {**styles["cells"][key].get(column, {}), **style}
                else:
                    styles["rows"][i] = {**(styles["rows"][i] or {}), **style}
        except Exception as e:  # noqa: BLE001 — cosmetic feature, see module docstring
            styles["errors"].append({"id": rule.get("id"), "message": str(e)})
```

and add:

```python
def _is_tabular(result: dict) -> bool:
    """Only table-shaped results have addressable cells; a bar chart's mark is its row."""
    return result.get("type") in ("table", "crosstab")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_display_rules.py -v`
Expected: PASS (all tests — confirm the Task 3 `value_map` tests on series results still pass, since `_is_tabular` now gates cell routing)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/display_rules.py backend/tests/test_display_rules.py
git commit -m "Route column-scoped display rules to individual table cells"
```

---

### Task 6: Widget-level targets — background and conditional visibility

**Files:**
- Modify: `backend/app/services/display_rules.py`
- Test: `backend/tests/test_display_rules.py`

**Interfaces:**
- Consumes: `evaluate_rules`.
- Produces: `styles["widget"]` as `{"background": str}` and/or `{"hidden": bool}`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_display_rules.py
def test_background_target_sets_a_widget_level_style_not_a_row_style():
    rules = [{"id": "r1", "kind": "expression", "target": "background",
              "expression": "value > 1000", "style": {"background": "#fee2e2"}}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["widget"] == {"background": "#fee2e2"}
    assert styles["rows"] == [None, None]


def test_visibility_target_hides_the_widget_when_the_rule_matches():
    rules = [{"id": "r1", "kind": "expression", "target": "visibility",
              "expression": "value > 1000", "style": {}}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["widget"]["hidden"] is True


def test_visibility_rule_that_matches_nothing_leaves_the_widget_visible():
    rules = [{"id": "r1", "kind": "expression", "target": "visibility",
              "expression": "value > 99999", "style": {}}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["widget"].get("hidden", False) is False


def test_widget_level_rules_use_any_row_matching():
    """A widget-level rule is a statement about the widget, so one qualifying mark is
    enough. Scalar and gauge results have exactly one row, making this a no-op there."""
    result = {"type": "series", "rows": [{"name": "A", "value": 1}, {"name": "B", "value": 5000}],
              "total": 2}
    rules = [{"id": "r1", "kind": "expression", "target": "background",
              "expression": "value > 1000", "style": {"background": "#fee2e2"}}]

    styles = evaluate_rules(result, rules)

    assert styles["widget"] == {"background": "#fee2e2"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_display_rules.py -v -k "background_target or visibility or any_row"`
Expected: FAIL — `target` is currently ignored and everything paints rows

- [ ] **Step 3: Branch on target inside the accumulation loop**

```python
_WIDGET_TARGETS = ("background", "visibility")
```

and at the top of the per-rule `try`:

```python
            target = rule.get("target") or "mark"
            if target in _WIDGET_TARGETS:
                row_styles = _rule_row_styles(rule, frame)
                matched = any(s is not None for s in row_styles)
                if target == "visibility":
                    styles["widget"]["hidden"] = styles["widget"].get("hidden", False) or matched
                elif matched:
                    styles["widget"].update(rule.get("style") or {})
                continue
```

Note the visibility branch always writes the key, so a non-matching rule yields an explicit `False` rather than an absent key — the renderer then never has to distinguish "no rule" from "rule said visible".

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_display_rules.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/display_rules.py backend/tests/test_display_rules.py
git commit -m "Add widget-level display-rule targets: background and visibility"
```

---

### Task 7: Attach the rule pass to the widget-data pipeline

**Files:**
- Modify: `backend/app/services/widget_data.py:814-831`
- Test: `backend/tests/test_widget_data_display_rules.py` (create)

**Interfaces:**
- Consumes: `evaluate_rules` from `app.services.display_rules`.
- Produces: every widget-data result gains `rule_styles` and `rule_errors` when `config["display_rules"]` is non-empty, and is untouched otherwise.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_widget_data_display_rules.py
import pandas as pd

from app.services.widget_data import get_widget_data_from_df


def _df():
    return pd.DataFrame({"region": ["US", "CA"], "sales": [1500, 400]})


def test_result_carries_rule_styles_when_rules_are_configured():
    config = {
        "dimension": "region", "measure": "sales", "aggregation": "sum",
        "display_rules": [{"id": "r1", "kind": "expression", "target": "mark",
                           "expression": "value > 1000", "style": {"fill": "#f87171"}}],
    }

    result = get_widget_data_from_df(_df(), config, "bar")

    assert result["rule_styles"]["rows"] == [{"fill": "#f87171"}, None]
    assert result["rule_errors"] == []


def test_result_is_untouched_when_no_rules_are_configured():
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}

    result = get_widget_data_from_df(_df(), config, "bar")

    assert "rule_styles" not in result
    assert "rule_errors" not in result


def test_a_broken_rule_never_costs_the_widget_its_data():
    config = {
        "dimension": "region", "measure": "sales", "aggregation": "sum",
        "display_rules": [{"id": "bad", "kind": "expression", "target": "mark",
                           "expression": "nope >", "style": {"fill": "#000"}}],
    }

    result = get_widget_data_from_df(_df(), config, "bar")

    assert len(result["rows"]) == 2
    assert len(result["rule_errors"]) == 1


def test_rules_do_not_run_on_an_error_result():
    config = {"measure": "missing_measure", "display_rules": [
        {"id": "r1", "kind": "expression", "target": "mark",
         "expression": "value > 1", "style": {"fill": "#000"}}]}

    result = get_widget_data_from_df(_df(), config, "bar")

    assert "rule_styles" not in result or result["rule_styles"]["rows"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_widget_data_display_rules.py -v`
Expected: FAIL — `KeyError: 'rule_styles'`

- [ ] **Step 3: Wire the pass into the dispatcher**

In `get_widget_data_from_df`, after the shaper returns:

```python
    shaper = SHAPERS.get(widget_type, shape_series)
    config = {**config, "measure_defs": measures or []}
    try:
        result = shaper(df, config)
    except ValueError as e:
        # Measure evaluation failed. Surfacing the error beats falling back to a base
        # column, which would render a plausible-looking but wrong number.
        return {"type": "error", "message": str(e), "rows": [], "total": 0}

    # Display rules are resolved against the SHAPED result, because a rule refers to the
    # aggregated value a mark shows. Attached here rather than inside each of the 15
    # shapers, so every widget type gets rules without touching a shaper.
    rules = config.get("display_rules") or []
    if rules and result.get("type") != "error":
        from app.services.display_rules import evaluate_rules  # local: avoids an import cycle

        styles = evaluate_rules(result, rules)
        result["rule_errors"] = styles.pop("errors")
        result["rule_styles"] = styles
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_widget_data_display_rules.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the whole backend suite for regressions**

Run: `cd backend && pytest -q`
Expected: PASS. `display_rules` rides inside `config`, which is already part of `_widget_data_cache_key` (`:1180-1192`), so editing a rule invalidates its cache entry with no extra work — but confirm the cache tests still pass rather than assuming it.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_widget_data_display_rules.py
git commit -m "Resolve display rules in the widget-data pipeline"
```

---

### Task 8: Report-level rule storage

**Files:**
- Modify: `backend/app/models/models.py:66-84`, `backend/app/schemas/schemas.py:198-219`, `backend/app/main.py:15-34`
- Test: `backend/tests/test_report_display_rules_api.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Report.display_rules` (JSON list, default `[]`), readable on `ReportOut` and writable via `PATCH /reports/{id}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_report_display_rules_api.py
import pytest

from app.models.models import Report


@pytest.mark.asyncio
async def test_new_report_defaults_to_no_display_rules(client, auth_headers):
    created = await client.post("/reports", json={"name": "R"}, headers=auth_headers["a"])

    assert created.status_code == 200
    assert created.json()["display_rules"] == []


@pytest.mark.asyncio
async def test_report_display_rules_round_trip_through_patch(client, auth_headers):
    created = await client.post("/reports", json={"name": "R"}, headers=auth_headers["a"])
    report_id = created.json()["id"]
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "any_category": True,
              "mappings": [{"value": "US", "color": "#6c8fff"}]}]

    patched = await client.patch(f"/reports/{report_id}", json={"display_rules": rules},
                                 headers=auth_headers["a"])

    assert patched.status_code == 200
    assert patched.json()["display_rules"] == rules
    fetched = await client.get(f"/reports/{report_id}", headers=auth_headers["a"])
    assert fetched.json()["display_rules"] == rules


@pytest.mark.asyncio
async def test_editing_display_rules_bumps_the_report_revision(client, auth_headers):
    """Report-level rules restyle every page, so another open session must be told."""
    created = await client.post("/reports", json={"name": "R"}, headers=auth_headers["a"])
    report_id = created.json()["id"]
    before = created.json()["revision"]

    await client.patch(f"/reports/{report_id}", json={"display_rules": []},
                       headers=auth_headers["a"])

    fetched = await client.get(f"/reports/{report_id}", headers=auth_headers["a"])
    assert fetched.json()["revision"] > before
```

Check `backend/tests/conftest.py` for the exact shape of the `auth_headers` fixture before writing these — it yields per-org header dicts, and the existing `tests/test_bookmarks_org_scoping.py` shows the calling convention.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_report_display_rules_api.py -v`
Expected: FAIL — `KeyError: 'display_rules'`

- [ ] **Step 3: Add the column, the schema fields, and the startup ALTER**

`models.py`, in `Report` after `theme`:

```python
    # Report-level display rules: applied to every object on every page, ahead of any
    # widget-level rules, which override them by list order. See services/display_rules.py.
    display_rules          = Column(JSON, default=list)
```

`schemas.py`:

```python
class ReportUpdate(BaseModel):
    ...
    display_rules: Optional[list[dict]] = None


class ReportOut(BaseModel):
    ...
    display_rules: list[dict] = []
```

`main.py`, appended to the `ALTER TABLE` list:

```python
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS display_rules JSON DEFAULT '[]'",
```

Confirm the report PATCH handler in `backend/app/routers/reports.py` applies unset-aware updates (`exclude_unset=True`) so an omitted `display_rules` is not silently cleared. If it uses a field allowlist, add `display_rules` to it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_report_display_rules_api.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/models.py backend/app/schemas/schemas.py backend/app/main.py backend/app/routers/reports.py backend/tests/test_report_display_rules_api.py
git commit -m "Store report-level display rules on the report"
```

---

### Task 9: The frontend condition compiler

**Files:**
- Create: `frontend/src/lib/displayRules.ts`, `frontend/src/lib/displayRules.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `compileCondition(column: string, cond: RuleCondition): string`, plus exported types `RuleOperator`, `RuleCondition`, `DisplayRule`, `RuleStyle`, `RuleStyles`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/displayRules.test.ts
import { describe, it, expect } from 'vitest'
import { compileCondition } from './displayRules'

describe('compileCondition', () => {
  it('compiles comparison operators against a plain column', () => {
    expect(compileCondition('value', { op: 'gt', value: 1000 })).toBe('value > 1000')
    expect(compileCondition('value', { op: 'gte', value: 1000 })).toBe('value >= 1000')
    expect(compileCondition('value', { op: 'lt', value: 10 })).toBe('value < 10')
    expect(compileCondition('value', { op: 'lte', value: 10 })).toBe('value <= 10')
    expect(compileCondition('value', { op: 'eq', value: 10 })).toBe('value == 10')
    expect(compileCondition('value', { op: 'ne', value: 10 })).toBe('value != 10')
  })

  it('quotes string operands with double quotes', () => {
    expect(compileCondition('name', { op: 'eq', value: 'US' })).toBe('name == "US"')
  })

  it('backtick-quotes column names that are not bare identifiers', () => {
    expect(compileCondition('net sales', { op: 'gt', value: 1 })).toBe('`net sales` > 1')
  })

  it('compiles between to an inclusive pair', () => {
    expect(compileCondition('value', { op: 'between', value: 10, value2: 20 }))
      .toBe('(value >= 10) and (value <= 20)')
  })

  it('compiles in to a list membership test', () => {
    expect(compileCondition('name', { op: 'in', value: ['US', 'CA'] }))
      .toBe('name in ["US", "CA"]')
  })

  it('compiles null checks without using `not`, which is ambiguous on a Series', () => {
    expect(compileCondition('value', { op: 'isnull' })).toBe('isnull(value) == True')
    expect(compileCondition('value', { op: 'notnull' })).toBe('isnull(value) == False')
  })

  it('escapes embedded double quotes rather than emitting broken syntax', () => {
    expect(compileCondition('name', { op: 'eq', value: 'a"b' })).toBe('name == "a\\"b"')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- displayRules`
Expected: FAIL — cannot resolve `./displayRules`

- [ ] **Step 3: Write the compiler**

```typescript
// frontend/src/lib/displayRules.ts
/**
 * Compiles a structured display-rule condition into an expression string for the
 * backend engine (backend/app/services/display_rules.py).
 *
 * This mirrors lib/customCategories.ts: the author edits the structured form, the
 * compiled string is what runs, and both are persisted so a rule stays editable.
 * Nothing here stops us emitting syntax the engine rejects — that is exactly how the
 * expression palette once shipped `.str.upper()` snippets that could never run — so
 * backend/tests/test_display_rules_contract.py asserts these strings verbatim.
 */
export type RuleOperator =
  | 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'between' | 'in' | 'isnull' | 'notnull'

export interface RuleCondition {
  op: RuleOperator
  value?: unknown
  value2?: unknown
}

export interface RuleStyle {
  fill?: string
  text?: string
  icon?: string
  background?: string
}

export interface DisplayRule {
  id: string
  kind: 'expression' | 'value_map' | 'interval'
  target: 'mark' | 'background' | 'visibility'
  label?: string
  column?: string
  expression?: string
  condition?: RuleCondition
  style?: RuleStyle
  mappings?: { value: unknown; color: string }[]
  any_category?: boolean
  bands?: { min: number; max: number; color: string }[]
}

export interface RuleStyles {
  rows: (RuleStyle | null)[]
  cells: Record<string, Record<string, RuleStyle>>
  widget: { background?: string; hidden?: boolean }
}

const BARE_IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/

function col(name: string): string {
  return BARE_IDENTIFIER.test(name) ? name : `\`${name}\``
}

function literal(value: unknown): string {
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return `"${String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
}

const COMPARISONS: Partial<Record<RuleOperator, string>> = {
  eq: '==', ne: '!=', gt: '>', gte: '>=', lt: '<', lte: '<=',
}

export function compileCondition(column: string, cond: RuleCondition): string {
  const c = col(column)

  if (cond.op === 'between') return `(${c} >= ${literal(cond.value)}) and (${c} <= ${literal(cond.value2)})`
  if (cond.op === 'in') {
    const items = (Array.isArray(cond.value) ? cond.value : [cond.value]).map(literal)
    return `${c} in [${items.join(', ')}]`
  }
  // `not isnull(x)` would evaluate `not` on a Series, which raises "truth value is
  // ambiguous". Comparing to a boolean keeps it elementwise.
  if (cond.op === 'isnull') return `isnull(${c}) == True`
  if (cond.op === 'notnull') return `isnull(${c}) == False`

  const operator = COMPARISONS[cond.op]
  if (!operator) throw new Error(`Unsupported display-rule operator: ${cond.op}`)
  return `${c} ${operator} ${literal(cond.value)}`
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- displayRules`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/displayRules.ts frontend/src/lib/displayRules.test.ts
git commit -m "Add the display-rule condition compiler"
```

---

### Task 10: Contract test between the compiler and the engine

**Files:**
- Create: `backend/tests/test_display_rules_contract.py`

**Interfaces:**
- Consumes: `compileCondition`'s output strings (copied verbatim from Task 9's tests), `evaluate_rules`.
- Produces: nothing; this is a guard.

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_display_rules_contract.py
"""Contract test between the frontend display-rule compiler and this engine.

The compiler in `frontend/src/lib/displayRules.ts` turns structured conditions into
expression strings. Nothing stops it emitting syntax the engine rejects — that is exactly
how the old expression palette ended up advertising `.str.upper()` snippets that
_validate_expr_safety refuses. These strings are copied verbatim from that compiler's own
tests, so if either side drifts, one of these fails.
"""
import pandas as pd
import pytest

from app.services.display_rules import evaluate_rules
from app.services.widget_data import _eval_expr, _validate_expr_safety


@pytest.mark.parametrize("expression,expected", [
    ("value > 1000",                       [True, False]),
    ("value >= 1500",                      [True, False]),
    ("value < 500",                        [False, True]),
    ("value <= 400",                       [False, True]),
    ("value == 1500",                      [True, False]),
    ("value != 1500",                      [False, True]),
    ('name == "US"',                       [True, False]),
    ("(value >= 10) and (value <= 500)",   [False, True]),
    ('name in ["US", "CA"]',               [True, True]),
    ("isnull(value) == False",             [True, True]),
    ("isnull(value) == True",              [False, False]),
])
def test_compiler_output_is_accepted_and_evaluates_elementwise(expression, expected):
    frame = pd.DataFrame([{"name": "US", "value": 1500}, {"name": "CA", "value": 400}])

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == expected


def test_backtick_quoted_column_from_the_compiler_reaches_the_engine():
    result = {"type": "table", "columns": ["net sales"], "rows": [[1500], [400]], "total": 2}
    rules = [{"id": "r1", "kind": "expression", "target": "mark",
              "expression": "`net sales` > 1000", "style": {"fill": "#f87171"}}]

    styles = evaluate_rules(result, rules)

    assert styles["errors"] == []
    assert styles["rows"] == [{"fill": "#f87171"}, None]
```

- [ ] **Step 2: Run the test**

Run: `cd backend && pytest tests/test_display_rules_contract.py -v`
Expected: PASS. If the `isnull(...) == True` cases fail, the compiler's null handling is wrong, not the test — fix `compileCondition` and rerun both suites.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_display_rules_contract.py
git commit -m "Guard the compiler/engine contract for display rules"
```

---

### Task 11: Send rules with the query and type the response

**Files:**
- Modify: `frontend/src/types/report.ts`, `frontend/src/services/api.ts`, `frontend/src/components/report/WidgetRenderer.tsx`
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`

**Interfaces:**
- Consumes: `DisplayRule`, `RuleStyles` from `lib/displayRules.ts`.
- Produces: `WidgetRenderer` accepts a `reportDisplayRules?: DisplayRule[]` prop and merges it ahead of `config.display_rules`; `Report.display_rules` exists on the type.

- [ ] **Step 1: Write the failing test**

```typescript
// append to frontend/src/components/report/WidgetRenderer.test.tsx
it('sends report rules ahead of widget rules so the widget rule wins', async () => {
  const widget = {
    id: 1, page_id: 1, widget_type: 'bar' as const, title: 'T',
    config: { dimension: 'region', measure: 'sales',
              display_rules: [{ id: 'w', kind: 'expression', target: 'mark',
                                expression: 'value > 1000', style: { fill: '#f87171' } }] },
    layout: { x: 0, y: 0, w: 6, h: 4 }, created_at: '',
  }
  const reportRules = [{ id: 'r', kind: 'expression' as const, target: 'mark' as const,
                         expression: 'value > 0', style: { fill: '#aaa' } }]

  render(
    <CrossFilterProvider>
      <WidgetRenderer widget={widget} datasetId={1} reportDisplayRules={reportRules} />
    </CrossFilterProvider>
  )

  await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
  const sentConfig = vi.mocked(widgetDataApi.query).mock.calls[0][1] as any
  expect(sentConfig.display_rules.map((r: any) => r.id)).toEqual(['r', 'w'])
})
```

Follow the existing mocking setup at the top of `WidgetRenderer.test.tsx` — it already mocks `widgetDataApi`; reuse that rather than adding a second mock.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- WidgetRenderer`
Expected: FAIL — `display_rules` is `undefined` on the sent config

- [ ] **Step 3: Implement**

In `types/report.ts`, add to `Report`:

```typescript
  /** Applied to every object on every page, ahead of any widget-level rules. */
  display_rules?: DisplayRule[]
```

with `import type { DisplayRule } from '../lib/displayRules'`.

In `services/api.ts`, widen the `reportsApi.update` parameter type with `display_rules: DisplayRule[]`.

In `WidgetRenderer.tsx`, add `reportDisplayRules?: DisplayRule[]` to `Props`, and inside the `mergedConfig` `useMemo`:

```typescript
    // Report rules first, widget rules second: the engine lets a later rule win for the
    // same target, so widget-over-report precedence is list order, not a flag.
    const widgetRules = (cfg.display_rules as DisplayRule[] | undefined) ?? []
    const allRules = [...(reportDisplayRules ?? []), ...widgetRules]
    if (allRules.length > 0) cfg.display_rules = allRules
```

Add `JSON.stringify(reportDisplayRules)` to the `useMemo` dependency array, or a report-rule edit will not refetch.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- WidgetRenderer`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/report.ts frontend/src/services/api.ts frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx
git commit -m "Merge report and widget display rules into the widget query"
```

---

### Task 12: Renderers consume resolved styles

**Files:**
- Modify: `frontend/src/components/report/chartUtils.tsx:151-159`, `frontend/src/components/report/chartRenderers/types.ts`, `frontend/src/components/report/chartRenderers/{Bar,Pie,Donut,Funnel}ChartRenderer.tsx`, `frontend/src/components/report/WidgetRenderer.tsx`
- Test: `frontend/src/components/report/chartUtils.test.ts`, `frontend/src/components/report/WidgetRenderer.test.tsx`

**Interfaces:**
- Consumes: `RuleStyles` from `lib/displayRules.ts`; `data.rule_styles` from the API.
- Produces: `getFillFactory(broadcasts, localSelected, ruleRowStyles?)`; `ChartRendererProps.ruleStyles?: RuleStyles`.

- [ ] **Step 1: Write the failing tests**

```typescript
// append to frontend/src/components/report/chartUtils.test.ts
import { getFillFactory } from './chartUtils'

describe('getFillFactory with rule styles', () => {
  it('uses the rule fill instead of the palette colour', () => {
    const getFill = getFillFactory(false, null, [{ fill: '#f87171' }, null])

    expect(getFill('US', 0).fill).toBe('#f87171')
  })

  it('falls back to the palette where no rule matched', () => {
    const getFill = getFillFactory(false, null, [{ fill: '#f87171' }, null])
    const plain = getFillFactory(false, null)

    expect(getFill('CA', 1).fill).toBe(plain('CA', 1).fill)
  })

  it('keeps cross-filter dimming on top of a rule fill', () => {
    const getFill = getFillFactory(true, 'US', [{ fill: '#f87171' }, null])

    expect(getFill('CA', 1).opacity).toBeLessThan(1)
  })
})
```

```typescript
// append to frontend/src/components/report/WidgetRenderer.test.tsx
it('hides the widget body when a visibility rule matched', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({
    type: 'series', rows: [{ name: 'US', value: 5 }], total: 1,
    rule_styles: { rows: [null], cells: {}, widget: { hidden: true } }, rule_errors: [],
  } as any)

  render(
    <CrossFilterProvider>
      <WidgetRenderer widget={barWidget} datasetId={1} />
    </CrossFilterProvider>
  )

  expect(await screen.findByTestId('widget-hidden-by-rule')).toBeInTheDocument()
})

it('paints a table cell with the style the engine resolved', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({
    type: 'table', columns: ['region', 'sales'], rows: [['US', 1500]], total: 1,
    rule_styles: { rows: [null], cells: { '0': { sales: { fill: '#f87171' } } }, widget: {} },
    rule_errors: [],
  } as any)

  render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget, widget_type: 'table' }} datasetId={1} />
    </CrossFilterProvider>
  )

  const cell = await screen.findByText('1500')
  expect(cell).toHaveStyle({ background: '#f87171' })
})
```

Reuse whatever `barWidget`-style fixture the file already defines; if there is none, lift the widget literal from the Task 11 test.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- "chartUtils|WidgetRenderer"`
Expected: FAIL — `getFillFactory` takes two arguments; no hidden/cell handling exists

- [ ] **Step 3: Implement**

`chartUtils.tsx`:

```typescript
// Returns a per-point fill/opacity/stroke resolver for cross-filter highlight/dim.
// A display-rule fill overrides the palette colour but not the selection treatment:
// a rule says what a mark means, selection says what the user is looking at.
export function getFillFactory(
  broadcasts: boolean,
  localSelected: unknown,
  ruleRowStyles?: (RuleStyle | null)[],
) {
  return (name: unknown, i: number) => {
    const color = ruleRowStyles?.[i]?.fill ?? COLORS[i % COLORS.length]
    if (!broadcasts || localSelected === null) return { fill: color, opacity: 1 }
    return localSelected === name
      ? { fill: color, opacity: 1, strokeWidth: 2, stroke: SELECTED_STROKE }
      : { fill: color, opacity: DIM_OPACITY }
  }
}
```

`chartRenderers/types.ts`: add `ruleStyles?: RuleStyles`.

In each of `BarChartRenderer`, `PieChartRenderer`, `DonutChartRenderer`, `FunnelChartRenderer` (the complete set of `getFillFactory` callers — verify with `grep -l getFillFactory chartRenderers/*.tsx`), destructure `ruleStyles` from props and pass it:

```typescript
  const getFill = getFillFactory(broadcasts, localSelected, ruleStyles?.rows)
```

In `WidgetRenderer.tsx`:

- Read `const ruleStyles = data?.rule_styles as RuleStyles | undefined`.
- Before rendering the body, when `ruleStyles?.widget?.hidden` is true, render a placeholder instead of `WidgetBody`. In view mode return `null` from the container; in edit mode render `<div data-testid="widget-hidden-by-rule">Hidden by a display rule</div>` so an author can still select and edit the widget they just hid.
- Apply `ruleStyles?.widget?.background` to the container's `background` style, falling back to `var(--surface)`.
- Pass `ruleStyles` into `WidgetBody` and on to `<ChartRenderer ... ruleStyles={ruleStyles} />`.
- In the table/crosstab branch, style each cell from `ruleStyles?.cells?.[String(i)]?.[cols[j]]`:

```tsx
                {row.map((v, j) => {
                  const cellStyle = ruleStyles?.cells?.[String(i)]?.[cols[j]]
                  const rowStyle = ruleStyles?.rows?.[i]
                  const painted = cellStyle ?? rowStyle ?? undefined
                  return (
                    <td key={j} style={painted ? { background: painted.fill, color: painted.text } : undefined}>
                      {formatValue(v, allFormats?.[cols[j]])}
                    </td>
                  )
                })}
```

- In the KPI and card branches, use `ruleStyles?.rows?.[0]?.fill` (KPI) and `ruleStyles?.rows?.[i]?.fill` (card) as the value colour, falling back to `var(--accent)`.
- In the list branch, use `ruleStyles?.rows?.[i]?.fill` as the row background.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS across the suite — confirm the existing `getFillFactory` tests still pass with the new optional third parameter.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/chartUtils.tsx frontend/src/components/report/chartUtils.test.ts frontend/src/components/report/chartRenderers frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx
git commit -m "Paint display-rule styles in renderers, tables and widget chrome"
```

---

### Task 13: The rule builder UI

**Files:**
- Create: `frontend/src/components/report/DisplayRulesPanel.tsx`, `frontend/src/components/report/DisplayRulesPanel.test.tsx`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Consumes: `compileCondition`, `DisplayRule` from `lib/displayRules.ts`.
- Produces: `<DisplayRulesPanel rules={DisplayRule[]} columns={string[]} onChange={(rules: DisplayRule[]) => void} errors={{id, message}[]} />`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/report/DisplayRulesPanel.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DisplayRulesPanel from './DisplayRulesPanel'

describe('DisplayRulesPanel', () => {
  it('stores the compiled expression alongside the structured condition', () => {
    const onChange = vi.fn()
    render(<DisplayRulesPanel rules={[]} columns={['value', 'name']} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))
    fireEvent.change(screen.getByLabelText(/column/i), { target: { value: 'value' } })
    fireEvent.change(screen.getByLabelText(/operator/i), { target: { value: 'gt' } })
    fireEvent.change(screen.getByLabelText(/^value$/i), { target: { value: '1000' } })

    const saved = onChange.mock.calls.at(-1)![0][0]
    expect(saved.expression).toBe('value > 1000')
    expect(saved.condition).toEqual({ op: 'gt', value: 1000, value2: undefined })
  })

  it('round-trips an existing rule back into the builder controls', () => {
    const rule = {
      id: 'r1', kind: 'expression' as const, target: 'mark' as const, column: 'value',
      expression: 'value > 1000', condition: { op: 'gt' as const, value: 1000 },
      style: { fill: '#f87171' },
    }
    render(<DisplayRulesPanel rules={[rule]} columns={['value']} onChange={vi.fn()} />)

    expect((screen.getByLabelText(/operator/i) as HTMLSelectElement).value).toBe('gt')
    expect((screen.getByLabelText(/^value$/i) as HTMLInputElement).value).toBe('1000')
  })

  it('shows a warning on the rule the engine could not evaluate', () => {
    const rule = { id: 'bad', kind: 'expression' as const, target: 'mark' as const,
                   column: 'value', expression: 'nope >', style: {} }
    render(
      <DisplayRulesPanel rules={[rule]} columns={['value']} onChange={vi.fn()}
        errors={[{ id: 'bad', message: 'Expression is not valid' }]} />
    )

    expect(screen.getByText(/Expression is not valid/i)).toBeInTheDocument()
  })

  it('removes a rule', () => {
    const onChange = vi.fn()
    const rule = { id: 'r1', kind: 'expression' as const, target: 'mark' as const,
                   column: 'value', expression: 'value > 1', style: {} }
    render(<DisplayRulesPanel rules={[rule]} columns={['value']} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /remove/i }))

    expect(onChange).toHaveBeenCalledWith([])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- DisplayRulesPanel`
Expected: FAIL — cannot resolve `./DisplayRulesPanel`

- [ ] **Step 3: Build the panel**

```tsx
// frontend/src/components/report/DisplayRulesPanel.tsx
import { compileCondition } from '../../lib/displayRules'
import type { DisplayRule, RuleCondition, RuleOperator } from '../../lib/displayRules'

const OPERATORS: { value: RuleOperator; label: string }[] = [
  { value: 'gt', label: 'is greater than' }, { value: 'gte', label: 'is at least' },
  { value: 'lt', label: 'is less than' },    { value: 'lte', label: 'is at most' },
  { value: 'eq', label: 'equals' },          { value: 'ne', label: 'does not equal' },
  { value: 'between', label: 'is between' }, { value: 'in', label: 'is one of' },
  { value: 'isnull', label: 'is blank' },    { value: 'notnull', label: 'is not blank' },
]

interface Props {
  rules: DisplayRule[]
  columns: string[]
  onChange: (rules: DisplayRule[]) => void
  errors?: { id?: string; message: string }[]
}

// Numbers must survive as numbers: `value > "1000"` compares a Series to a string.
const coerce = (raw: string): unknown =>
  raw !== '' && !isNaN(Number(raw)) ? Number(raw) : raw

export default function DisplayRulesPanel({ rules, columns, onChange, errors }: Props) {
  const update = (i: number, patch: Partial<DisplayRule>) => {
    const next = rules.map((r, j) => (j === i ? { ...r, ...patch } : r))
    const rule = next[i]
    // Recompile on every edit so the stored expression can never drift from the
    // structured condition an author is looking at.
    if (rule.condition && rule.column) {
      rule.expression = compileCondition(rule.column, rule.condition)
    }
    onChange(next)
  }

  const addRule = () => onChange([...rules, {
    id: crypto.randomUUID(), kind: 'expression', target: 'mark',
    column: columns[0] ?? 'value', condition: { op: 'gt', value: 0 },
    expression: compileCondition(columns[0] ?? 'value', { op: 'gt', value: 0 }),
    style: { fill: '#f87171' },
  }])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {rules.map((rule, i) => {
        const error = errors?.find(e => e.id === rule.id)
        const cond: RuleCondition = rule.condition ?? { op: 'gt' }
        // A hand-written expression has no structured form to render controls from.
        if (!rule.condition) return (
          <div key={rule.id}>
            <label htmlFor={`expr-${rule.id}`}>Expression</label>
            <input id={`expr-${rule.id}`} value={rule.expression ?? ''} readOnly />
            {error && <span role="alert">{error.message}</span>}
            <button onClick={() => onChange(rules.filter((_, j) => j !== i))}>Remove</button>
          </div>
        )
        return (
          <div key={rule.id} style={{ display: 'grid', gap: 6 }}>
            <label htmlFor={`col-${rule.id}`}>Column</label>
            <select id={`col-${rule.id}`} value={rule.column ?? ''}
              onChange={e => update(i, { column: e.target.value })}>
              {columns.map(c => <option key={c} value={c}>{c}</option>)}
            </select>

            <label htmlFor={`op-${rule.id}`}>Operator</label>
            <select id={`op-${rule.id}`} value={cond.op}
              onChange={e => update(i, { condition: { ...cond, op: e.target.value as RuleOperator } })}>
              {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>

            {cond.op !== 'isnull' && cond.op !== 'notnull' && (
              <>
                <label htmlFor={`val-${rule.id}`}>Value</label>
                <input id={`val-${rule.id}`} value={String(cond.value ?? '')}
                  onChange={e => update(i, { condition: { ...cond, value: coerce(e.target.value) } })} />
              </>
            )}
            {cond.op === 'between' && (
              <>
                <label htmlFor={`val2-${rule.id}`}>To</label>
                <input id={`val2-${rule.id}`} value={String(cond.value2 ?? '')}
                  onChange={e => update(i, { condition: { ...cond, value2: coerce(e.target.value) } })} />
              </>
            )}

            <label htmlFor={`target-${rule.id}`}>Applies to</label>
            <select id={`target-${rule.id}`} value={rule.target}
              onChange={e => update(i, { target: e.target.value as DisplayRule['target'] })}>
              <option value="mark">The mark</option>
              <option value="background">Widget background</option>
              <option value="visibility">Hide the widget</option>
            </select>

            <label htmlFor={`fill-${rule.id}`}>Fill</label>
            <input id={`fill-${rule.id}`} type="color" value={rule.style?.fill ?? '#f87171'}
              onChange={e => update(i, { style: { ...rule.style, fill: e.target.value } })} />

            {error && <span role="alert" style={{ color: 'var(--danger)', fontSize: 11 }}>{error.message}</span>}
            <button onClick={() => onChange(rules.filter((_, j) => j !== i))}>Remove</button>
          </div>
        )
      })}
      <button onClick={addRule}>Add rule</button>
    </div>
  )
}
```

Styling is deliberately minimal above — match it to `ColumnFormatsPanel.tsx` once the tests pass. What must not change is the behaviour the tests pin:

- An **Add rule** button appending a rule with `id: crypto.randomUUID()`, `kind: 'expression'`, `target: 'mark'`.
- Per rule: a **Column** `<select>` from the `columns` prop, an **Operator** `<select>` over the ten `RuleOperator` values, a **Value** input (and a second **To** input shown only for `between`), a **Fill** colour input, and a **Target** `<select>` over mark / background / visibility.
- Every control has an associated `<label htmlFor>`, so the tests address them by name rather than by DOM position.
- On any change, recompute `expression: compileCondition(column, condition)` and call `onChange` with the full rule array. Numeric-looking input is stored as a number, not a string, so `value > "1000"` never reaches the engine.
- When `errors` contains the rule's id, render the message next to that rule.
- A rule whose `condition` is absent (hand-written expression) shows the raw expression in a read-only field instead of the builder controls, as the spec requires.

Mount it in `WidgetConfigPanel.tsx` in a "Display rules" section, passing the result columns for the widget type: `['name', 'value']` for series-shaped widgets, and the configured `columns` for table/crosstab. This is the point the Global Constraints call out — a rule addresses **result** columns, so offering dataset columns here would produce rules that never match.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- DisplayRulesPanel`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/DisplayRulesPanel.tsx frontend/src/components/report/DisplayRulesPanel.test.tsx frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "Add the display-rules builder to the widget config panel"
```

---

### Task 14: Report-level rules in the builder

**Files:**
- Modify: `frontend/src/pages/ReportBuilder.tsx`
- Test: `frontend/src/pages/ReportBuilder.test.tsx` if it exists; otherwise extend `DisplayRulesPanel.test.tsx` with the wiring assertion

**Interfaces:**
- Consumes: `DisplayRulesPanel`, `reportsApi.update`.
- Produces: report rules persisted via `PATCH /reports/{id}` and passed to every `WidgetRenderer` as `reportDisplayRules`.

- [ ] **Step 1: Write the failing test**

```typescript
it('persists report-level rules and passes them to every widget', async () => {
  render(<ReportBuilder />)   // follow the file's existing render/route harness

  fireEvent.click(await screen.findByRole('button', { name: /report rules/i }))
  fireEvent.click(screen.getByRole('button', { name: /add rule/i }))

  await waitFor(() => expect(reportsApi.update).toHaveBeenCalledWith(
    expect.any(Number),
    expect.objectContaining({ display_rules: expect.any(Array) }),
  ))
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- ReportBuilder`
Expected: FAIL — no such control

- [ ] **Step 3: Implement**

- Add a **Report rules** entry to the side-pane switcher alongside Bookmarks / Selection / Sync slicers, rendering `<DisplayRulesPanel>` bound to `report.display_rules`.
- On change, call `reportsApi.update(report.id, { display_rules })` and update local report state — this matches how theme changes already persist, so follow that call site exactly rather than inventing a new one.
- Pass `reportDisplayRules={report.display_rules}` to every `WidgetRenderer` render site in this file, including the mobile-layout and view-mode paths. Missing one is the likeliest bug in this task: `grep -n "<WidgetRenderer" src/pages/ReportBuilder.tsx` and confirm each call site.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS across the suite

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReportBuilder.tsx frontend/src/pages/ReportBuilder.test.tsx
git commit -m "Add report-level display rules to the report builder"
```

---

### Task 15: Verify end to end and update the gap analysis

**Files:**
- Modify: `docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md`

**Interfaces:**
- Consumes: everything above.
- Produces: five re-scored rows and a corrected headline.

- [ ] **Step 1: Run both suites and record the actual output**

Run: `cd backend && pytest -q` then `cd frontend && npm test`
Expected: PASS. Do not proceed on a partial pass — a re-scored gap row is a factual claim about shipped behaviour.

- [ ] **Step 2: Exercise the feature in the running app**

Start the app, add a bar chart, add a rule `value > <something in range>`, and confirm the matching bars recolour and that a cross-filter re-evaluates them. Then break the rule deliberately (`nope >`) and confirm the chart still renders with a warning rather than going blank — the fail-open guarantee is the one behaviour a unit test cannot fully vouch for in the real stack.

- [ ] **Step 3: Re-score the five category-07 rows**

In the category 07 table, change each row's datalytics column to `Yes` and rewrite its note to say what shipped and how it is narrower than SAS. Cover, honestly: rules address result columns rather than arbitrary source expressions; there are no parameters to reference, since parameters do not exist in this app; and report-level rules apply to every object without SAS's data-source-independence caveat. Follow the note style of the rows re-scored on 2026-08-17 — a `**Shipped 2026-08-18.**` prefix, the mechanism, then the honest limitation.

- [ ] **Step 4: Update the tally and the headline**

Update the category 07 row in the Tally table (6/4/18 → 11/4/13) and the total (108 → 113 Yes, 140 → 135 No). Also fix the stale **"The three gaps that matter most"** section: text functions shipped in `766dbae`, so that entry is wrong and should be replaced by the next-ranked gap, with the closed items moved into the "Closed since this document was first written" note.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md
git commit -m "Update gap analysis: display-rules engine shipped"
```

---

## Verification checklist

- [ ] `cd backend && pytest -q` passes
- [ ] `cd frontend && npm test` passes
- [ ] A widget with no rules produces a result with no `rule_styles` key (no wasted payload)
- [ ] A broken rule leaves the widget rendering, with an error badge in the config panel
- [ ] A widget rule beats a report rule targeting the same mark
- [ ] Editing a rule refetches rather than serving a cached style
- [ ] Both `apply_rls_filter` and `display_rules.py` carry the cross-referencing failure-mode comment
