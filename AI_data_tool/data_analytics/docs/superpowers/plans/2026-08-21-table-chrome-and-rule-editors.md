# Table Chrome & Rule Editors Implementation Plan (Phase 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the last seven reachable rows of category 07 — table totals, crosstab subtotals, table cell styling, per-object chrome, per-object alt text, and authoring UIs for the two display-rule kinds whose engines already exist.

**Architecture:** Totals are computed **server-side, before the row limit truncates the frame** — a grand total taken from delivered rows would silently total only the visible page. Cell styling and object chrome are config consumed by `WidgetRenderer`, which already reads `rule_styles` and so already has the shape for per-widget presentation config. The two rule editors extend `DisplayRulesPanel`, which today only ever emits `kind: 'expression'`, even though `display_rules.py` has shipped, tested `value_map` and `interval` evaluators since phase 1.

**Tech Stack:** Python 3.12, FastAPI, pandas, pytest (backend); React 18, TypeScript, vitest + @testing-library/react (frontend).

**Spec:** `docs/superpowers/specs/2026-08-18-formatting-display-rules-design.md` (phase 3 section, as amended 2026-08-21)

## Global Constraints

- **A widget saved before this phase must render identically after it.** Every new option is opt-in and absent from existing configs. This has been the governing constraint for two phases and every prior review found at least one violation of it — assume yours will too.
- **Totals are computed before `limit` truncates the frame.** `shape_series`' raw-table branch does `df[cols].head(limit)` at `widget_data.py:204`; a total taken after that totals only the visible page. This is the entire reason totals are server-side rather than a frontend `reduce`.
- **Never offer a control a widget type cannot honour.** Table options appear only for `table`/`crosstab`/`matrix`; the capability map (`widgetCapabilities.ts`) is the established mechanism. Phase 1 shipped a rule target that painted nothing and 860 tests missed it; phase 2 found three more of the same class.
- **`_safe()` every value crossing into JSON.** `widget_data.py` uses it on every cell it emits; a `numpy.int64` or `NaN` that skips it breaks serialisation at the router, not in the shaper.
- **Display rules fail OPEN** — a malformed rule is recorded in `rule_errors` and every other rule still applies. The two new editors must not introduce a rule shape the engine rejects.
- Backend tests: `cd D:/data_analytics/backend && python -m pytest -q` (**624 passing**). Frontend: `cd D:/data_analytics/frontend`, iterate with `npx vitest run <file>` (**358 passing across 40 files**). **Do not run the full frontend `npm test`** — it has killed implementer runs on a watchdog twice; the controller runs it between tasks.

---

## Verified starting state

Read from the files, not assumed.

- **`shape_series` raw-table branch** (`widget_data.py:199-209`): returns `{type: "table", columns, rows, total}`, rows built from `sub = df[cols].head(limit)`. No totals of any kind.
- **`shape_series` crosstab branch** (`:214-229`): already computes `pivot["__total__"] = pivot[num_cols].sum(axis=1)` — an **unconditional, unlabelled row-total column** that ships today and is neither documented nor opt-in. There is no grand-total row.
- **`WidgetRenderer` table branch** (`WidgetRenderer.tsx:488-529`): normalises array-rows and object-rows, renders a plain `<table style={{fontSize: 12}}>`, already paints `ruleStyles.cells` / `ruleStyles.rows`, and shows a "Showing N of M" footer when truncated.
- **Widget chrome** (`WidgetRenderer.tsx:256-257`): border and background are hard-coded except for `ruleStyles?.widget?.background`.
- **`DisplayRulesPanel`** (200 lines): `addRule` hard-codes `kind: 'expression'`; nothing constructs `mappings` or `bands`.

---

## File Structure

**Created:**
- `frontend/src/components/report/ValueMapEditor.tsx` + `.test.tsx` — the `value_map` authoring UI.
- `frontend/src/components/report/IntervalEditor.tsx` + `.test.tsx` — the `interval` band authoring UI.
- `backend/tests/test_table_totals.py` — totals and subtotals.

**Modified:**
- `backend/app/services/widget_data.py` — totals in the table and crosstab branches (Tasks 1-2).
- `frontend/src/components/report/WidgetRenderer.tsx` — totals row, cell styling, chrome, alt text (Tasks 3-6).
- `frontend/src/components/report/DisplayRulesPanel.tsx` — mount the two editors (Tasks 7-8).
- `frontend/src/components/report/widgetCapabilities.ts` — a `tableOptions` capability (Task 9).
- `frontend/src/components/report/WidgetConfigPanel.tsx` — the table and chrome controls (Task 9).
- `docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md` (Task 10).

---

### Task 1: Table grand-total row, computed before the limit

**Files:**
- Modify: `backend/app/services/widget_data.py:199-209`
- Test: `backend/tests/test_table_totals.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: a `totals` key on the `table` result — `{"totals": [value|None, ...]}`, index-aligned with `columns`, present only when `config["show_totals"]` is true.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_table_totals.py
import pandas as pd

from app.services.widget_data import shape_series


def _df():
    return pd.DataFrame({
        "region": ["US", "CA", "UK", "JP", "DE"],
        "sales":  [100, 200, 300, 400, 500],
        "units":  [1, 2, 3, 4, 5],
    })


def test_no_totals_key_when_not_requested():
    result = shape_series(_df(), {"columns": ["region", "sales"]})

    assert "totals" not in result


def test_grand_total_sums_numeric_columns_and_blanks_text_ones():
    result = shape_series(_df(), {"columns": ["region", "sales"], "show_totals": True})

    assert result["columns"] == ["region", "sales"]
    assert result["totals"] == [None, 1500]


def test_grand_total_is_computed_before_the_row_limit_truncates():
    """The whole reason totals are server-side. With limit=2 the client only ever
    sees two rows, but the total must describe all five."""
    result = shape_series(_df(), {"columns": ["region", "sales"], "show_totals": True, "limit": 2})

    assert len(result["rows"]) == 2
    assert result["totals"] == [None, 1500]


def test_totals_cover_every_numeric_column():
    result = shape_series(_df(), {"columns": ["region", "sales", "units"], "show_totals": True})

    assert result["totals"] == [None, 1500, 15]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_table_totals.py -v`
Expected: FAIL — `KeyError: 'totals'` on the second test

- [ ] **Step 3: Implement**

In the raw-table branch, compute from `df` (the full frame) rather than `sub`:

```python
    if not dim and not meas:
        cols = [c for c in (explicit_cols or list(df.columns)) if c in df.columns]
        if sort_col and sort_col in df.columns:
            df = df.sort_values(sort_col, ascending=(sort == "asc"))
        sub  = df[cols].head(limit)
        result = {
            "type": "table",
            "columns": cols,
            "rows": [[_safe(v) for v in row] for row in sub.itertuples(index=False)],
            "total": len(df),
        }
        if config.get("show_totals"):
            # Computed from df, NOT sub: sub is already truncated by `limit`, and a
            # total describing only the visible page is worse than no total at all.
            result["totals"] = [
                _safe(df[c].sum()) if pd.api.types.is_numeric_dtype(df[c]) else None
                for c in cols
            ]
        return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_table_totals.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: 628 passing (624 + 4). Any pre-existing failure means the shaper changed shape for an existing caller — fix the change, not the test.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_table_totals.py
git commit -m "Add opt-in table grand totals, computed before the row limit"
```

---

### Task 2: Crosstab subtotals, and making the existing row total honest

**Files:**
- Modify: `backend/app/services/widget_data.py:214-229`
- Test: `backend/tests/test_table_totals.py`

**Interfaces:**
- Consumes: nothing from Task 1 (a different branch of the same function).
- Produces: on the `crosstab` result — `totals` (a grand-total row, same shape as Task 1) when `show_totals` is set, and the pre-existing `__total__` column now gated behind `show_subtotals`.

**The judgement call this task must make explicitly:** `__total__` currently ships **unconditionally** on every crosstab. Making it opt-in is a behaviour change for existing widgets — the column would disappear. Making it opt-out preserves them but leaves an unlabelled `__total__` in every crosstab forever. **Default it to ON (`config.get("show_subtotals", True)`)** so no existing widget loses a column, and let an author turn it off. Record that reasoning in the code comment.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_table_totals.py
def _crosstab_df():
    return pd.DataFrame({
        "region":  ["US", "US", "CA", "CA"],
        "quarter": ["Q1", "Q2", "Q1", "Q2"],
        "sales":   [10, 20, 30, 40],
    })


def _cfg(**over):
    base = {"dimension": "region", "dimension2": "quarter", "measure": "sales", "aggregation": "sum"}
    base.update(over)
    return base


def test_row_subtotal_column_ships_by_default_so_existing_widgets_keep_it():
    result = shape_series(_crosstab_df(), _cfg())

    assert "__total__" in result["columns"]


def test_row_subtotal_column_can_be_turned_off():
    result = shape_series(_crosstab_df(), _cfg(show_subtotals=False))

    assert "__total__" not in result["columns"]


def test_no_grand_total_row_unless_requested():
    result = shape_series(_crosstab_df(), _cfg())

    assert "totals" not in result


def test_grand_total_row_sums_each_numeric_column():
    result = shape_series(_crosstab_df(), _cfg(show_totals=True))

    cols = result["columns"]
    totals = dict(zip(cols, result["totals"]))
    assert totals[cols[0]] is None          # the dimension column has no total
    assert totals["Q1"] == 40               # 10 + 30
    assert totals["Q2"] == 60               # 20 + 40
    assert totals["__total__"] == 100
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_table_totals.py -v -k "subtotal or grand_total_row"`
Expected: FAIL — `show_subtotals` is not read and there is no `totals` key

- [ ] **Step 3: Implement**

```python
    if dim and dim2 and dim in df.columns and dim2 in df.columns:
        if meas and meas in df.columns:
            pivot = df.groupby([dim, dim2])[meas].agg(agg_fn).unstack(fill_value=0).reset_index()
        else:
            pivot = df.groupby([dim, dim2]).size().unstack(fill_value=0).reset_index()

        # Row subtotals default ON: this column shipped unconditionally before it was
        # ever configurable, so defaulting it off would silently remove a column from
        # every existing crosstab. An author can turn it off; nobody loses one by upgrading.
        if config.get("show_subtotals", True):
            num_cols = [c for c in pivot.columns if c != dim]
            pivot["__total__"] = pivot[num_cols].sum(axis=1)

        col_names = [str(c) for c in pivot.columns]
        result = {
            "type": "crosstab",
            "columns": col_names,
            "rows": [[_safe(v) for v in row] for row in pivot.itertuples(index=False)],
            "total": len(pivot),
        }
        if config.get("show_totals"):
            result["totals"] = [
                _safe(pivot[c].sum()) if pd.api.types.is_numeric_dtype(pivot[c]) else None
                for c in pivot.columns
            ]
        return result
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && python -m pytest tests/test_table_totals.py -v` then `python -m pytest -q`
Expected: PASS. 632 passing (628 + 4).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_table_totals.py
git commit -m "Add crosstab grand totals and make the row subtotal column configurable"
```

---

### Task 3: Render the totals row

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx:488-529`
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`

**Interfaces:**
- Consumes: `data.totals` from Tasks 1-2 — `(number | null)[]`, index-aligned with `data.columns`.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

```tsx
// append to WidgetRenderer.test.tsx — reuse the file's existing helpers and widgetDataApi mock
it('renders a totals row beneath the table when the server sent totals', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({
    type: 'table', columns: ['region', 'sales'],
    rows: [['US', 100], ['CA', 200]], total: 2, totals: [null, 1500],
  } as any)

  render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table' }} datasetId={1} />
    </CrossFilterProvider>
  )

  const footRow = await screen.findByTestId('table-totals-row')
  expect(footRow).toHaveTextContent('1,500')
  expect(footRow).toHaveTextContent('Total')
})

it('renders no totals row when the server sent none', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({
    type: 'table', columns: ['region', 'sales'], rows: [['US', 100]], total: 1,
  } as any)

  render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table' }} datasetId={1} />
    </CrossFilterProvider>
  )

  await screen.findByText('US')
  expect(screen.queryByTestId('table-totals-row')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/WidgetRenderer.test.tsx`
Expected: FAIL — no `table-totals-row` element exists

- [ ] **Step 3: Implement**

Add a `<tfoot>` after `</tbody>`, using the same `formatValue` the body cells use so a total is formatted like the column it totals:

```tsx
          </tbody>
          {Array.isArray(data.totals) && (
            <tfoot>
              <tr data-testid="table-totals-row"
                style={{ borderTop: '2px solid var(--border)', fontWeight: 600 }}>
                {cols.map((c: string, j: number) => (
                  <td key={j}>
                    {/* The first column carries the label rather than a number, since
                        totalling a dimension is meaningless and the row needs a name. */}
                    {j === 0 ? 'Total' : (data.totals[j] == null ? '' : formatValue(data.totals[j], allFormats?.[c]))}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/WidgetRenderer.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx
git commit -m "Render the server-computed totals row beneath tables"
```

---

### Task 4: Table cell styling

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx` (table branch)
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces: config keys `table_row_lines` (boolean), `table_row_numbers` (boolean), `table_condensed` (boolean), `table_banding` (boolean). All default off — an existing table must look unchanged.

- [ ] **Step 1: Write the failing test**

```tsx
// append to WidgetRenderer.test.tsx
async function renderTable(config: Record<string, unknown>) {
  vi.mocked(widgetDataApi.query).mockResolvedValue({
    type: 'table', columns: ['region', 'sales'],
    rows: [['US', 100], ['CA', 200]], total: 2,
  } as any)
  const r = render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table', config }} datasetId={1} />
    </CrossFilterProvider>
  )
  await screen.findByText('US')
  return r
}

it('adds a row-number column only when asked', async () => {
  const { container, unmount } = await renderTable({})
  expect(container.querySelectorAll('thead th').length).toBe(2)
  unmount()

  const { container: c2 } = await renderTable({ table_row_numbers: true })
  expect(c2.querySelectorAll('thead th').length).toBe(3)
  expect(c2.querySelectorAll('tbody tr:first-child td')[0]).toHaveTextContent('1')
})

it('bands alternate rows only when asked', async () => {
  const { container, unmount } = await renderTable({})
  const plain = container.querySelectorAll('tbody tr')[1] as HTMLElement
  expect(plain.style.background).toBe('')
  unmount()

  const { container: c2 } = await renderTable({ table_banding: true })
  const banded = c2.querySelectorAll('tbody tr')[1] as HTMLElement
  expect(banded.style.background).not.toBe('')
})

it('a rule-painted cell still wins over banding', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({
    type: 'table', columns: ['region', 'sales'], rows: [['US', 100], ['CA', 200]], total: 2,
    rule_styles: { rows: [null, null], cells: { '1': { sales: { fill: '#f87171' } } }, widget: {} },
    rule_errors: [],
  } as any)
  const { container } = render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table', config: { table_banding: true } }} datasetId={1} />
    </CrossFilterProvider>
  )
  await screen.findByText('US')
  const cell = container.querySelectorAll('tbody tr')[1].querySelectorAll('td')[1] as HTMLElement
  expect(cell.style.background).toContain('247')   // rgb(247, 113, 113)
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/WidgetRenderer.test.tsx`
Expected: FAIL — no row-number column, no banding

- [ ] **Step 3: Implement**

```tsx
    const rowNumbers  = !!cfg.table_row_numbers
    const rowLines    = !!cfg.table_row_lines
    const banding     = !!cfg.table_banding
    const cellPad     = cfg.table_condensed ? '2px 6px' : undefined
```

Then in the JSX: prepend `<th>#</th>` to the header when `rowNumbers`; prepend `<td>{i + 1}</td>` to each body row; put `background: banding && i % 2 === 1 ? 'var(--surface2)' : undefined` and `borderBottom: rowLines ? '1px solid var(--border)' : undefined` on the `<tr>`; and `padding: cellPad` on each `<td>`.

**The cell style must still win over banding** — the rule fill goes on the `<td>`, banding on the `<tr>`, so a painted cell naturally covers the striped row beneath it. Do not merge banding into the cell style object.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/WidgetRenderer.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx
git commit -m "Add opt-in table cell styling: row numbers, lines, banding, condensed"
```

---

### Task 5: Per-object background, border and padding

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx:250-262`
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`

**Interfaces:**
- Consumes: `ruleStyles?.widget?.background` (already read at `:257`).
- Produces: config keys `widget_background`, `widget_border_color`, `widget_border_width` (number), `widget_radius` (number), `widget_padding` (number).

**Precedence, which the test must pin:** a display rule's background beats the static config background. A rule is a statement about the data; the config is a static choice, and the whole point of phase 1's `background` target is that it reacts.

- [ ] **Step 1: Write the failing test**

```tsx
// append to WidgetRenderer.test.tsx
it('applies a configured background and border to the widget chrome', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [{ name: 'US', value: 1 }], total: 1 } as any)
  const { container } = render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget(), config: { widget_background: '#fee2e2', widget_border_width: 3 } }} datasetId={1} />
    </CrossFilterProvider>
  )
  await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
  const chrome = container.firstElementChild as HTMLElement
  expect(chrome.style.background).toContain('254')     // rgb(254, 226, 226)
  expect(chrome.style.border).toContain('3px')
})

it('lets a display rule background win over the configured one', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({
    type: 'series', rows: [{ name: 'US', value: 1 }], total: 1,
    rule_styles: { rows: [null], cells: {}, widget: { background: '#000000' } }, rule_errors: [],
  } as any)
  const { container } = render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget(), config: { widget_background: '#fee2e2' } }} datasetId={1} />
    </CrossFilterProvider>
  )
  await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
  const chrome = container.firstElementChild as HTMLElement
  expect(chrome.style.background).toContain('0, 0, 0')
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/WidgetRenderer.test.tsx`
Expected: FAIL — chrome ignores the config keys

- [ ] **Step 3: Implement**

At the container's style, keeping today's values as the fallbacks so an unconfigured widget is unchanged:

```tsx
        border: selected
          ? '2px solid var(--accent)'
          : `${cfg.widget_border_width ?? 1}px solid ${cfg.widget_border_color ?? 'var(--border)'}`,
        borderRadius: cfg.widget_radius != null ? cfg.widget_radius : 'var(--radius)',
        // A rule background beats a static one: the rule reacts to the data, which is
        // the entire point of phase 1's `background` target.
        background: ruleStyles?.widget?.background ?? cfg.widget_background ?? 'var(--surface)',
```

and apply `padding: cfg.widget_padding` to the body `<div>` when set, leaving the existing padding rule as the fallback.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/WidgetRenderer.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx
git commit -m "Make widget background, border and padding configurable per object"
```

---

### Task 6: Per-object alternative text

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx` (container element)
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces: config key `alt_text` (string). Closes a category 07 row **and** a category 13 row.

SAS's identification order is alt text → title → object name. Implement that chain exactly.

- [ ] **Step 1: Write the failing test**

```tsx
// append to WidgetRenderer.test.tsx
it('labels the widget with its alt text when set', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [], total: 0 } as any)
  render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget(), title: 'Sales', config: { alt_text: 'Quarterly sales by region' } }} datasetId={1} />
    </CrossFilterProvider>
  )
  expect(await screen.findByLabelText('Quarterly sales by region')).toBeInTheDocument()
})

it('falls back to the title, then the widget type, when no alt text is set', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [], total: 0 } as any)
  const { unmount } = render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget(), title: 'Sales' }} datasetId={1} />
    </CrossFilterProvider>
  )
  expect(await screen.findByLabelText('Sales')).toBeInTheDocument()
  unmount()

  render(
    <CrossFilterProvider>
      <WidgetRenderer widget={{ ...barWidget(), title: '' }} datasetId={1} />
    </CrossFilterProvider>
  )
  expect(await screen.findByLabelText('bar')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/WidgetRenderer.test.tsx`
Expected: FAIL — no accessible name on the container

- [ ] **Step 3: Implement**

On the container `<div>`:

```tsx
      role="figure"
      aria-label={(cfg.alt_text as string) || widget.title || wt}
```

`role="figure"` is what makes `aria-label` an accessible name on a generic container — without a role, assistive tech may ignore the label entirely.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/WidgetRenderer.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx
git commit -m "Add per-object alternative text with a title and type fallback chain"
```

---

### Task 7: The colour-mapped-value editor

**Files:**
- Create: `frontend/src/components/report/ValueMapEditor.tsx`, `frontend/src/components/report/ValueMapEditor.test.tsx`
- Modify: `frontend/src/components/report/DisplayRulesPanel.tsx`

**Interfaces:**
- Consumes: `DisplayRule` from `lib/displayRules.ts`.
- Produces: `<ValueMapEditor rule={DisplayRule} onChange={(r: DisplayRule) => void} />`, emitting `kind: 'value_map'` with `mappings: {value, color}[]` and `any_category: boolean`.

The engine has evaluated this shape since phase 1 (`display_rules.py`'s `_value_map_style`) and it is tested there — including SAS's **Any Category** mode, where the mapping applies across every category column rather than one named one. Nothing has ever created one.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/report/ValueMapEditor.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ValueMapEditor from './ValueMapEditor'

const rule = { id: 'r1', kind: 'value_map' as const, target: 'mark' as const, column: 'name', mappings: [] }

describe('ValueMapEditor', () => {
  it('adds a mapping with a value and a colour', () => {
    const onChange = vi.fn()
    render(<ValueMapEditor rule={rule} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /add mapping/i }))
    const emitted = onChange.mock.calls.at(-1)![0]
    expect(emitted.kind).toBe('value_map')
    expect(emitted.mappings).toHaveLength(1)
  })

  it('edits a mapping value and keeps the kind', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, mappings: [{ value: '', color: '#6c8fff' }] }
    render(<ValueMapEditor rule={withOne} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/mapped value/i), { target: { value: 'EMEA' } })
    const emitted = onChange.mock.calls.at(-1)![0]
    expect(emitted.mappings[0].value).toBe('EMEA')
    expect(emitted.kind).toBe('value_map')
  })

  it('toggles Any Category, which the engine reads to scan every category column', () => {
    const onChange = vi.fn()
    render(<ValueMapEditor rule={rule} onChange={onChange} />)

    fireEvent.click(screen.getByLabelText(/any category/i))
    expect(onChange.mock.calls.at(-1)![0].any_category).toBe(true)
  })

  it('removes a mapping', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, mappings: [{ value: 'EMEA', color: '#6c8fff' }] }
    render(<ValueMapEditor rule={withOne} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /remove mapping/i }))
    expect(onChange.mock.calls.at(-1)![0].mappings).toEqual([])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/ValueMapEditor.test.tsx`
Expected: FAIL — cannot resolve `./ValueMapEditor`

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/report/ValueMapEditor.tsx
import type { DisplayRule } from '../../lib/displayRules'

interface Props {
  rule: DisplayRule
  onChange: (rule: DisplayRule) => void
}

/** Authoring surface for `kind: 'value_map'`. The engine has evaluated this shape
 *  since phase 1 (services/display_rules.py::_value_map_style) — including SAS's
 *  Any Category mode — but nothing ever created one, which is why the gap row sat
 *  at Partial rather than Yes. */
export default function ValueMapEditor({ rule, onChange }: Props) {
  const mappings = rule.mappings ?? []
  const emit = (patch: Partial<DisplayRule>) => onChange({ ...rule, kind: 'value_map', ...patch })

  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
        <input type="checkbox" checked={!!rule.any_category}
          onChange={e => emit({ any_category: e.target.checked })} />
        Any category
      </label>

      {mappings.map((m, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label htmlFor={`vm-val-${rule.id}-${i}`} style={{ fontSize: 11 }}>Mapped value</label>
          <input id={`vm-val-${rule.id}-${i}`} value={String(m.value ?? '')}
            onChange={e => emit({ mappings: mappings.map((x, j) => j === i ? { ...x, value: e.target.value } : x) })} />
          <input type="color" aria-label={`Colour for mapping ${i + 1}`} value={m.color ?? '#6c8fff'}
            onChange={e => emit({ mappings: mappings.map((x, j) => j === i ? { ...x, color: e.target.value } : x) })} />
          <button onClick={() => emit({ mappings: mappings.filter((_, j) => j !== i) })}>Remove mapping</button>
        </div>
      ))}

      <button onClick={() => emit({ mappings: [...mappings, { value: '', color: '#6c8fff' }] })}>
        Add mapping
      </button>
    </div>
  )
}
```

In `DisplayRulesPanel`, add a **Rule kind** `<select>` (Expression / Colour map / Bands) per rule, and render `ValueMapEditor` in place of the condition controls when `rule.kind === 'value_map'`.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/ValueMapEditor.test.tsx` then `npx vitest run src/components/report/DisplayRulesPanel.test.tsx`
Expected: PASS both

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/ValueMapEditor.tsx frontend/src/components/report/ValueMapEditor.test.tsx frontend/src/components/report/DisplayRulesPanel.tsx
git commit -m "Add a colour-mapped-value editor so value_map rules are authorable"
```

---

### Task 8: The interval band editor

**Files:**
- Create: `frontend/src/components/report/IntervalEditor.tsx`, `frontend/src/components/report/IntervalEditor.test.tsx`
- Modify: `frontend/src/components/report/DisplayRulesPanel.tsx`

**Interfaces:**
- Consumes: `DisplayRule`; the **Rule kind** select added in Task 7.
- Produces: `<IntervalEditor rule={DisplayRule} onChange={(r: DisplayRule) => void} />`, emitting `kind: 'interval'` with `bands: {min, max, color}[]`.

The engine matches bands **lower-inclusive / upper-exclusive, with the final band's upper bound inclusive** so a value equal to the maximum lands in a band rather than falling through. The editor must say so, because an author cannot infer it.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/report/IntervalEditor.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import IntervalEditor from './IntervalEditor'

const rule = { id: 'r1', kind: 'interval' as const, target: 'mark' as const, column: 'value', bands: [] }

describe('IntervalEditor', () => {
  it('adds a band with numeric bounds', () => {
    const onChange = vi.fn()
    render(<IntervalEditor rule={rule} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /add band/i }))
    const emitted = onChange.mock.calls.at(-1)![0]
    expect(emitted.kind).toBe('interval')
    expect(emitted.bands).toHaveLength(1)
  })

  it('stores bounds as numbers, not strings', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, bands: [{ min: 0, max: 0, color: '#f87171' }] }
    render(<IntervalEditor rule={withOne} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/band 1 minimum/i), { target: { value: '60' } })
    expect(onChange.mock.calls.at(-1)![0].bands[0].min).toBe(60)
  })

  it('explains the boundary convention, which an author cannot infer', () => {
    render(<IntervalEditor rule={rule} onChange={vi.fn()} />)
    expect(screen.getByText(/last band/i)).toBeInTheDocument()
  })

  it('removes a band', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, bands: [{ min: 0, max: 60, color: '#f87171' }] }
    render(<IntervalEditor rule={withOne} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /remove band/i }))
    expect(onChange.mock.calls.at(-1)![0].bands).toEqual([])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/IntervalEditor.test.tsx`
Expected: FAIL — cannot resolve `./IntervalEditor`

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/report/IntervalEditor.tsx
import type { DisplayRule } from '../../lib/displayRules'

interface Props {
  rule: DisplayRule
  onChange: (rule: DisplayRule) => void
}

/** Authoring surface for `kind: 'interval'` — what a gauge rule actually is.
 *  The engine (services/display_rules.py::_interval_style) matches bands
 *  lower-inclusive / upper-exclusive, EXCEPT the last band's upper bound, which is
 *  inclusive so a value equal to the maximum lands in a band instead of falling
 *  through unstyled. An author cannot infer that, so the UI states it. */
export default function IntervalEditor({ rule, onChange }: Props) {
  const bands = rule.bands ?? []
  const emit = (patch: Partial<DisplayRule>) => onChange({ ...rule, kind: 'interval', ...patch })
  const setBand = (i: number, k: 'min' | 'max' | 'color', v: string) =>
    emit({ bands: bands.map((b, j) => j === i ? { ...b, [k]: k === 'color' ? v : Number(v) } : b) })

  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {bands.map((b, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label htmlFor={`bd-min-${rule.id}-${i}`} style={{ fontSize: 11 }}>Band {i + 1} minimum</label>
          <input id={`bd-min-${rule.id}-${i}`} type="number" value={String(b.min ?? '')}
            onChange={e => setBand(i, 'min', e.target.value)} />
          <label htmlFor={`bd-max-${rule.id}-${i}`} style={{ fontSize: 11 }}>Band {i + 1} maximum</label>
          <input id={`bd-max-${rule.id}-${i}`} type="number" value={String(b.max ?? '')}
            onChange={e => setBand(i, 'max', e.target.value)} />
          <input type="color" aria-label={`Colour for band ${i + 1}`} value={b.color ?? '#f87171'}
            onChange={e => setBand(i, 'color', e.target.value)} />
          <button onClick={() => emit({ bands: bands.filter((_, j) => j !== i) })}>Remove band</button>
        </div>
      ))}

      <button onClick={() => emit({ bands: [...bands, { min: 0, max: 0, color: '#f87171' }] })}>
        Add band
      </button>

      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>
        A band includes its minimum and excludes its maximum, so bands can sit end to end.
        The <strong>last band</strong> also includes its maximum, so a value equal to the
        top of the range is still coloured.
      </p>
    </div>
  )
}
```

Render it from `DisplayRulesPanel` when `rule.kind === 'interval'`, using the Rule kind select from Task 7.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/IntervalEditor.test.tsx` then `npx vitest run src/components/report/DisplayRulesPanel.test.tsx`
Expected: PASS both

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/IntervalEditor.tsx frontend/src/components/report/IntervalEditor.test.tsx frontend/src/components/report/DisplayRulesPanel.tsx
git commit -m "Add an interval band editor so gauge-style rules are authorable"
```

---

### Task 9: Offer the new options in the config panel

**Files:**
- Modify: `frontend/src/components/report/widgetCapabilities.ts`, `frontend/src/components/report/WidgetConfigPanel.tsx`
- Test: `frontend/src/components/report/widgetCapabilities.test.ts`, `frontend/src/components/report/WidgetConfigPanel.test.tsx`

**Interfaces:**
- Consumes: `formattingCapabilities(wt)` and `FormattingCapability` from `widgetCapabilities.ts`.
- Produces: a new capability `'tableOptions'`, granted only to `table`, `crosstab` and `matrix`.

- [ ] **Step 1: Write the failing test**

```typescript
// append to widgetCapabilities.test.ts
it('offers table options only to the table-shaped types', () => {
  for (const wt of ['table', 'crosstab', 'matrix'] as const) {
    expect(formattingCapabilities(wt)).toContain('tableOptions')
  }
  for (const wt of ['bar', 'line', 'pie', 'kpi', 'gauge'] as const) {
    expect(formattingCapabilities(wt)).not.toContain('tableOptions')
  }
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/widgetCapabilities.test.ts`
Expected: FAIL — `'tableOptions'` is not a capability

- [ ] **Step 3: Implement**

Add `'tableOptions'` to the `FormattingCapability` union and grant it to `table`, `crosstab`, `matrix` — note those three currently map to `[]`, so this gives them their first entry and makes the Formatting group appear for them.

In `WidgetConfigPanel`, inside the existing Formatting `ExpandableGroup`:
- when `caps.includes('tableOptions')`: **Show totals** (`show_totals`), **Show row subtotals** (`show_subtotals`), **Row numbers** (`table_row_numbers`), **Row lines** (`table_row_lines`), **Banded rows** (`table_banding`), **Condensed** (`table_condensed`).
- for every widget type, in a new `ExpandableGroup id="appearance" title="Appearance" defaultOpen={false}`: **Background** (`widget_background`), **Border colour** (`widget_border_color`), **Border width** (`widget_border_width`), **Corner radius** (`widget_radius`), **Padding** (`widget_padding`), **Alt text** (`alt_text`).

Every control gets an associated `<label htmlFor>`. **Follow the tri-state rule established in phase 2:** seed each state from `cfg.<key>` with no `??` fallback, and write a key only when its state is not `undefined`, so an untouched control leaves no key behind. `show_subtotals` in particular must stay absent unless touched — the backend defaults it to `true`, and writing `false` from an untouched panel would silently drop a column from every existing crosstab.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/widgetCapabilities.test.ts` then `npx vitest run src/components/report/WidgetConfigPanel.test.tsx`
Expected: PASS. A pre-existing panel test that fails because a control moved behind the new collapsed group is a real finding — fix it by opening the group, never by weakening the assertion.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/widgetCapabilities.ts frontend/src/components/report/widgetCapabilities.test.ts frontend/src/components/report/WidgetConfigPanel.tsx frontend/src/components/report/WidgetConfigPanel.test.tsx
git commit -m "Offer table and appearance options in the widget config panel"
```

---

### Task 10: Update the gap analysis

**Files:**
- Modify: `docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md`

**Interfaces:**
- Consumes: everything above.
- Produces: seven re-scored rows across two categories, and a corrected tally.

- [ ] **Step 1: Run both suites and record the output**

Run: `cd backend && python -m pytest -q` and `cd frontend && npm test`
Expected: PASS. Do not re-score on a red suite — a gap row is a factual claim.

- [ ] **Step 2: Re-score the rows**

Category 07, five No→Yes: Table totals, Crosstab subtotals, Table cell styling, Per-object background/border/padding, Per-object alternative text.
Category 07, two Partial→Yes: Colour-mapped-value rules by category, Gauge interval rules.
Category 13, one No→Yes: Alternative text per object.

Use a `**Shipped 2026-08-21.**` prefix, mechanism then honest limitation, matching the rows re-scored on 2026-08-17, -18 and -20. Limitations that must appear:

- Totals are a **grand total only** — SAS also offers per-group subtotals within a crosstab's row axis, and placement before or after the group. Ours is one row at the foot.
- The crosstab row-subtotal column defaults ON because it shipped unconditionally before it was configurable; turning it off is opt-in.
- Cell styling covers row numbers, row lines, banding and condensed height. SAS also offers vertical lines and per-column alignment.
- Object chrome is background, border, radius and padding. **Data skins remain out of scope** — SAS's eight skins are a visual design system of their own.
- The two rule editors close the authoring gap phase 1's review identified; the engines were already shipped and tested.

- [ ] **Step 3: Update the tally and verify by counting**

Category 07 goes from **14/4/10** to **21/2/5** (five No-to-Yes and two Partial-to-Yes: 14+7 Yes, 4-2 Partial, 10-5 No, summing to 28). Category 13 goes from **2/2/7** to **3/2/6**. The Total goes from **116/28/132** to **124/26/126**.

Verify by counting the actual table rows — every category must sum to its declared row count and the total must sum to 276. Do not trust this arithmetic.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md
git commit -m "Update gap analysis: table chrome and rule editors shipped"
```

---

## Verification checklist

- [ ] `cd backend && python -m pytest -q` passes
- [ ] `cd frontend && npm test` passes
- [ ] A table saved before this phase renders with no totals row, no row numbers, no banding
- [ ] A crosstab saved before this phase still shows its `__total__` column
- [ ] A grand total on a limited table describes every row, not the visible page
- [ ] A rule-painted cell still wins over a banded row
- [ ] A display-rule background still beats a configured one
- [ ] Table options appear only on table-shaped widget types
- [ ] The gap-analysis tally sums to 276
