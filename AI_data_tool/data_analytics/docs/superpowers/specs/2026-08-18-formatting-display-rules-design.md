# Formatting & Display Rules — Design

**Date:** 2026-08-18
**Status:** Design approved — implementation plans to follow, one per phase
**Closes:** category 07 of `docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md`
(6 Yes / 4 Partial / 18 No of 28 rows), plus one category 13 row

## Purpose

Category 07 is the second-largest block of unshipped rows in the gap analysis and the one the
2026-08-13 roadmap named as sub-project 4, "Display Rules & Alerts". Its 22 open rows are not one
project: they split into a rule *engine*, a per-renderer *options surface*, and *table and object
chrome*. This document designs all three as one sequenced spec, with a separate implementation plan
per phase.

The engine comes first because it is the only one of the three that other categories depend on:
category 11's data-condition alerts are, in SAS's own model, an expression display rule with a
notification attached.

## Scope

### Phase 1 — Display-rules engine (5 rows)

| Gap row | Currently |
|---|---|
| Expression-based display rules | No |
| Colour-mapped-value rules by category | No |
| Gauge interval rules | No |
| Report-level display rules | No |
| Rule-driven conditional visibility | No |

### Phase 2 — Chart formatting & axis options (6 rows)

| Gap row | Currently |
|---|---|
| Fixed axis minimum / maximum | No |
| Logarithmic axis | No |
| Axis label / line / tick styling | No |
| Grid lines & wall background | Partial |
| Legend visibility & placement | Partial |
| Data labels | Partial |

### Phase 3 — Table & object chrome, plus the missing rule editors (7 rows)

| Gap row | Currently |
|---|---|
| Table totals | No |
| Crosstab subtotals | No |
| Table cell styling | No |
| Per-object background / border / padding | No |
| Per-object alternative text (also category 13) | No |
| Colour-mapped-value rules by category | **Partial** |
| Gauge interval rules | **Partial** |

**Amended 2026-08-21.** The last two rows were added after phase 1 shipped. Phase 1 built working
`value_map` and `interval` evaluators in `display_rules.py`, but nothing in the UI ever creates a
rule of either kind — `DisplayRulesPanel` only ever emits `kind: 'expression'`. Phase 1's own final
review flagged both rows as claiming capability reachable only by hand-editing JSON through the API,
and they were re-scored from Yes to Partial for exactly that reason.

Adding the two editors is therefore the cheapest pair of rows left in the category: the engine, the
result contract, the renderer painting and the error surfacing all exist and are tested. Only the
authoring surface is missing. Folding them in here also retires a standing criticism of the gap
document rather than carrying it forward another phase.

### Deliberately out of scope

Recorded as still-No rather than quietly counted:

- **Data skins / element styling** — SAS's 8 skins are a visual-design system of their own, and the
  renderers here have no styling layer to hang them on.
- **Overview / scrolling axis** — needs a second synchronised miniature chart per renderer.
- **Periodic auto-reload of object data** — belongs with scheduled refresh, not formatting.
- **Per-object data-limit override** — the global `DEFAULT_ROW_CAP` with its `sampled` flag is a
  security-adjacent control; making it per-object is a governance decision, not a formatting one.
- **Custom / imported theme JSON** — a theme *format* is a compatibility commitment; the 5 built-in
  palettes cover the need until someone asks for import.

## Phase 1 — Display-rules engine

### Where rules are evaluated, and why

Rules evaluate **after shaping, never before**. A SAS display rule such as `sales > 1000` refers to
the aggregated value the mark displays, not to any source row. `shape_series` already produces
exactly that at `widget_data.py:265` — `rows: [{name, value}, …]` — so the rule pass reads the
shaped result, not the dataframe.

This placement has three consequences worth stating:

1. **DirectQuery gets rules for free.** Shaping happens after the SQL returns, so import and
   DirectQuery reach the rule pass by the same path with no pushdown work.
2. **Cross-filtering restyles correctly.** A narrowed context reshapes the result, and the rules
   re-evaluate against the new aggregates — which is the behaviour authors expect and the reason
   client-side pre-computed styles would eventually be wrong.
3. **Cache invalidation is already handled.** Rules live inside `config`, and `config` is part of
   `_widget_data_cache_key` (`widget_data.py:1180-1192`), so editing a rule cannot serve a stale
   style.

### The evaluator

New module `backend/app/services/display_rules.py`. It imports the existing expression machinery
from `widget_data` rather than reimplementing it — `_validate_expr_safety` and `_eval_expr` are the
same functions that guard calculated columns, filters and RLS, and a second expression path would be
a second thing to get wrong.

```python
def result_frame(result: dict) -> pd.DataFrame | None
def evaluate_rules(result: dict, rules: list[dict]) -> dict
```

**Compilation happens in the frontend, not here.** `frontend/src/lib/displayRules.ts` turns a
structured condition into an expression string, and the backend consumes only the compiled
`expression`. That is the `CustomCategoryPanel` → `SWITCH()` split this spec already cites, and it
comes with the same guard: a contract test holding strings copied verbatim from the compiler's own
tests, so the two sides cannot drift apart silently.

`evaluate_rules` lifts the shaped result into a small DataFrame whose columns depend on the result
type, evaluates each rule, and returns the styles. It never mutates the result it is given.

| Result `type` | Frame handed to the evaluator | Rule targets |
|---|---|---|
| `series` | one row per mark, columns `name`, `value` | per-mark |
| `table` / `crosstab` | one row per table row, columns from `result["columns"]` | per-cell and per-row |
| `scalar` | single row, columns `name`, `value` | the whole widget |
| `gauge` | single row, columns `value`, `target` | the whole widget |
| anything else | not evaluated; rules are ignored | — |

### Rule model

Three kinds behind one output contract. All three are stored as JSON; only `expression` involves the
sandbox.

```jsonc
{
  "id": "r1",
  "kind": "expression",          // "expression" | "value_map" | "interval"
  "target": "mark",              // "mark" | "background" | "visibility"
  "column": "revenue",           // which result column the rule reads
  "expression": "value > 1000",  // compiled from `condition`, or hand-written
  "condition": {                 // structured form, kept for round-trip editing
    "op": "gt", "value": 1000
  },
  "style": { "fill": "#f87171", "text": "#fff", "icon": "🔴" },
  "label": "Above target"
}
```

- **`expression`** — the config panel is a structured builder (column / operator / value → style)
  that compiles to an expression string. This is the `CustomCategoryPanel` → `SWITCH()` precedent
  from 2026-08-17: the structured form is what the author edits, the compiled expression is what the
  engine runs, and both are persisted so an author never has to reverse-engineer their own rule.
  Storing both also means a hand-written expression is representable — `condition` is simply absent,
  and the builder shows the raw expression read-only.
- **`value_map`** — `{"column": "region", "mappings": [{"value": "EMEA", "color": "#6c8fff"}]}`,
  plus SAS's **Any Category** mode, where the mapping applies to every category column in the result
  rather than one named one. Evaluated by direct comparison, never through the sandbox: a colour
  lookup does not need an expression evaluator.
- **`interval`** — ordered bands, `[{"min": 0, "max": 60, "color": "#f87171"}, …]`. This is what a
  gauge rule *is*; bands are matched lower-inclusive / upper-exclusive, with the final band's upper
  bound inclusive so the maximum value lands in a band rather than falling through.

Operators the builder offers, all compiling to the existing grammar: `eq`, `ne`, `gt`, `gte`, `lt`,
`lte`, `between`, `in`, `isnull`, `notnull`.

### Output contract

`get_widget_data_from_df` gains a rule pass after the shaper returns:

```jsonc
{
  "type": "series",
  "rows": [ … ],
  "rule_styles": {
    "rows":   [ {"fill": "#f87171"}, null, … ],   // index-aligned with rows
    "cells":  { "3": { "revenue": {"fill": "#f87171"} } },  // table/crosstab only
    "widget": { "background": "#fee", "hidden": false }
  },
  "rule_errors": [ {"id": "r2", "message": "Unknown column: revneue"} ]
}
```

Renderers consume a resolved style. No renderer ever sees a rule, an operator or an expression —
which is what keeps phase 1 from touching 31 files.

### Report-level rules

Stored on a new `reports.display_rules JSON DEFAULT '[]'` column, added to the additive
`ALTER TABLE … ADD COLUMN IF NOT EXISTS` list in `main.py:15-34` and to the Report schema. No
Alembic, matching how every column since `revision` has been added.

The widget-data endpoint is dataset-scoped, not report-scoped, so it cannot look up the report
itself. The client merges instead: `ReportBuilder` already holds the report, and sends
`config.display_rules = [...reportRules, ...widgetRules]`. The server applies the list in order and
lets a later rule win for the same target, so widget rules override report rules by construction
rather than by a precedence flag.

Rules arriving from the client are untrusted, exactly like every other part of `config` — which is
why they go through `_validate_expr_safety` on the same terms as a filter expression. There is no
new trust boundary here: a rule can only change how already-authorised data is coloured.

### Error handling — deliberately unlike RLS

`apply_rls_filter` (`widget_data.py:1108`) fails **closed to zero rows**, because a broken security
control must hide data. Display rules must do the opposite: they are cosmetic, so a malformed rule
must never blank or break a widget.

Each rule is therefore evaluated in isolation inside its own try/except. A rule that raises is
skipped, its `id` and message are appended to `rule_errors`, and every other rule still applies. The
config panel surfaces `rule_errors` as a warning badge on the offending rule.

This inconsistency between two expression paths in the same file is intentional and must be
commented at both sites, or a later reader will "fix" one of them.

### Frontend

- `DisplayRulesPanel.tsx` — the builder, mounted in `WidgetConfigPanel` for widget rules and in the
  report settings area for report-level rules. Same component, different persistence callback.
- `WidgetRenderer` reads `data.rule_styles`, applies `widget.hidden` and `widget.background` to the
  chrome, and passes `ruleStyles` down through `ChartRendererProps`.
- `getFillFactory` in `chartUtils.tsx` gains a rule-aware overload.

  **Corrected 2026-08-20, after phase 1 shipped.** This section originally claimed mark recolouring
  would reach bar, dot, needle, butterfly, waterfall, scatter and bubble "without editing them
  individually, because the Cartesian renderers already resolve per-point fills through
  `getFillFactory`". That was false about this codebase: only **four** renderers call
  `getFillFactory` (bar, pie, donut, funnel). The rest hardcode their fills — `DotPlotRenderer` and
  `NeedlePlotRenderer` use `var(--accent)`, `ScatterChartRenderer`, `ButterflyChartRenderer` and
  `WaterfallChartRenderer` use literals, and `BubbleChartRenderer`/`TreemapChartRenderer` resolve
  `COLORS[i]` themselves.

  The whole-branch review caught this: rules were being offered on every widget type while painting
  on four. Seven more renderers were then wired individually with a
  `ruleStyles?.rows?.[i]?.fill ?? <existing colour>` fallback, taking coverage to 11 of 31. The
  remaining 20 are listed as a known gap and are folded into **phase 2**, which touches those same
  files anyway.

  The lesson worth keeping: a spec that asserts a mechanism ("they already go through X") must be
  checked against the code before it is used to size work. This one was not, and the plan inherited
  it.
- Table, crosstab, list, KPI, card and gauge branches in `WidgetRenderer` read `rule_styles`
  directly, since they do not go through `getFillFactory`.

### Testing (phase 1)

Backend, pytest, TDD:

- `compile_condition` for every operator, including `between` bounds and `in` with a list.
- Per-row matching against a `series` result; a rule matching no row yields all-`null`.
- Table/crosstab per-cell styling keyed by row index and column name.
- Interval band matching, including the top-of-range value landing in the last band.
- `value_map` Any-Category mode colouring more than one column.
- Report-then-widget ordering: the widget rule wins.
- A rule naming a missing column produces a `rule_errors` entry and leaves rows unstyled.
- A malformed rule leaves the widget's data intact — the assertion that separates this from RLS.
- An injection attempt (`value.__globals__`, backtick-and-dunder, `@df.to_csv(...)`) is rejected by
  the existing validator, reached through the rule path.

Frontend, vitest: builder round-trip (structured → expression → structured), a renderer consuming
`rule_styles`, and a visibility rule hiding a widget.

## Phase 2 — Chart formatting & axis options

### Shared options module

New `chartRenderers/axisOptions.ts`. It exports prop-builders rather than components, so each
renderer keeps its own JSX and its own layout quirks:

```ts
export function xAxisProps(cfg: any, rtl: boolean): Partial<XAxisProps>
export function yAxisProps(cfg: any, rtl: boolean, fmt?: CalcColumnFormat): Partial<YAxisProps>
export function gridProps(cfg: any): Partial<CartesianGridProps> | null
export function legendProps(cfg: any): Partial<LegendProps> | null
export function labelListProps(cfg: any, fmt?: CalcColumnFormat): Partial<LabelListProps> | null
```

Each renderer's existing hard-coded `<XAxis tick={…} axisLine={false} …>` is replaced by
`<XAxis {...xAxisProps(cfg, rtl)} />` with today's values as the defaults, so an untouched widget
renders byte-identically. `gridProps` and `legendProps` return `null` when the author has turned the
element off, and the renderer omits the element entirely.

**Reach: every renderer built on Recharts' Cartesian primitives.** That set is defined by capability,
not by taste, and `grep -l XAxis chartRenderers/*.tsx` says it is **20 files**, not the dozen-ish it
looks like from the widget gallery: area, bar, bubble, bubble change, butterfly, comparative time
series, dot, the four dual-axis variants, histogram, line, needle, numeric series, ribbon, scatter,
schedule/Gantt, step and waterfall.

The fully custom renderers keep their current chrome: pie, donut, treemap, funnel, gauge, heatmap,
correlation matrix, parallel coordinates, word cloud, vector and box plot.

Ribbon and schedule/Gantt are in the Cartesian set structurally but only some options mean anything
for them — a log scale on a Gantt time axis is nonsense. So `WidgetConfigPanel` offers options from
a **capability map keyed on widget type**, not from the renderer's mere membership in the set.
Showing a Log-scale toggle that silently does nothing is worse than not shipping the option.

Log scale carries one honest constraint: Recharts' `scale="log"` cannot render zero or negative
values. The config panel says so at the point of choosing it, and the axis domain falls back to
`auto` when the data contains a non-positive value, rather than rendering an empty chart.

### Testing (phase 2)

Pure functions are the point of this shape: `axisOptions.ts` gets unit tests per builder (defaults
match today's hard-coded values; min/max produce a fixed domain; log scale with a zero present falls
back to auto; RTL still flips orientation), plus one renderer-level test per behaviour proving the
props reach Recharts.

## Phase 3 — Table & object chrome

**Totals and subtotals are backend work.** A total must be computed over the full result *before*
`limit` truncates it (`widget_data.py:263`), so computing it in the browser from the delivered rows
would silently total only the visible page. `shape_series` gains `totals` on the `table` and
`crosstab` results: a row-total column (already present as `__total__` for crosstab at
`widget_data.py:222`, currently undocumented and unlabelled) and a grand-total row, each opt-in by
config. Placement before/after, matching SAS, is a render concern.

**Table cell styling** — row lines, row numbers, condensed row height, alternating row background —
is config consumed by the table branch of `WidgetRenderer`.

**Per-object chrome** — background, border colour/width, corner radius, padding — replaces the
hard-coded values at `WidgetRenderer.tsx:235-256`. Today's values become the defaults. This is also
the surface phase 1's `background` rule target writes to, so phase 3 must land after phase 1 or the
rule has nothing to set.

**Per-object alt text** — a `config.altText` field emitted as `aria-label` on the widget container,
with SAS's identification order (alt text → title → widget type) as the fallback chain. Closes a
category 13 row as well as a category 07 one.

### Testing (phase 3)

Backend: grand-total computed over the pre-limit frame (the test that would fail if someone moved it
client-side), crosstab subtotals, totals off by default. Frontend: cell-styling toggles, chrome
defaults unchanged when no config is set, `aria-label` falling back through the chain.

## Sequencing

Phase 1 → phase 3 → phase 2, or phase 1 → phase 2 → phase 3; only phase 1 is ordered, because
phase 3's per-object background is the surface phase 1's `background` rule writes to. Each phase is
independently shippable, gets its own implementation plan, and updates the gap analysis on landing
rather than all three at the end.

## Row accounting

If all three phases land as designed, 16 category-07 rows move — 13 No→Yes and 3 Partial→Yes —
taking the category from **6 / 4 / 18 to 22 / 1 / 5**, plus one row in category 13.

What is left is then exactly accounted for: the 5 remaining No rows are the five listed under
"Deliberately out of scope", and the single remaining Partial is animation playback options. No row
is left unexplained, which is the property that makes the next gap-doc update mechanical rather than
a re-audit.

Counting the category-13 alt-text row too, 17 rows move in total, taking the document from 108 to
125 Yes and overall coverage from 39% to roughly 45%.
