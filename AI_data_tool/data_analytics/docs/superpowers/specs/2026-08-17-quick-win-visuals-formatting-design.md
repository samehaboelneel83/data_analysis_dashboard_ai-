# Quick-Win Visuals + Formatting & Layout Controls — Design

## Context

Continuing the Feature Parity Audit closure. This round covers 6 remaining gaps chosen by the
user as a bounded, next-reasonable-size round: 4 chart types (category 03) plus the Formatting &
layout controls category (05) in full — Align/distribute tools, Themes, Tab order pane, on top
of the 2 chart types that need genuinely no new backend work.

Explicitly deferred to future rounds (confirmed with the user): Maps, R/Python visual, AppSource
marketplace, the Web service layer (Workspaces/Dashboards/Apps/Lineage/Gateway/Subscriptions/
Copilot) — each is large enough, and some carry real dependency/security decisions (a mapping
library; sandboxed code execution), to warrant their own dedicated scoping round.

## Codebase facts this plan relies on

- Widget-type dispatch is a flat `SHAPERS: dict[str, Callable]` in
  `backend/app/services/widget_data.py:682`, mapping `widget_type -> shaper function`, with a
  fallback to `shape_series` for anything unregistered (`get_widget_data_from_df`,
  `widget_data.py:745-749`). Adding an alias is a one-line dict entry.
- `shape_series` already produces the exact `{rows: [{name, value}], ...}` shape that `bar`/
  `line`/etc. share — Area and Funnel need **zero new backend code**, only a frontend renderer.
- `shape_heatmap` (category + category2 + measure) is the existing shaper for a 2D grouped
  aggregate — the same shape the Ribbon chart approximation needs.
- Frontend chart types are registered in three places per type: `WidgetType` union and
  `ROLE_SPECS`/`WIDGET_CATALOG` entries in `frontend/src/types/report.ts`, and a `CHART_RENDERERS`
  entry in `frontend/src/components/report/chartRenderers/index.tsx` pointing at a new
  `<Type>Renderer.tsx` file implementing `ChartRendererProps`.
- `chartUtils.tsx` exports `export const COLORS = [...]` — a `const` binding, but the **array
  itself is mutable**. Per-category-colored renderers (`bar`, `pie`, `donut`, `treemap`, `heatmap`,
  etc.) go through `chartUtils.tsx`'s `getFillFactory(broadcasts, localSelected)` helper, which
  reads `COLORS[i % COLORS.length]` at render time — mutating the array in place (`COLORS.length =
  0; COLORS.push(...next)`) propagates to all of them with **zero renderer file changes**.
  Single-series renderers (`line`, `scatter`, `kpi`, `gauge`, …) instead hardcode the CSS custom
  property `var(--accent)` for their one stroke/fill color — a separate, light/dark-mode-driven
  mechanism, **not** wired to `COLORS` today. This round's Theme picker therefore visibly retints
  the per-category charts and the two new chart types this round build against `COLORS` directly
  (Area's fill, Ribbon's per-series bars); re-theming the existing single-accent renderers is a
  separate, larger follow-up (would need each of those files converted from `var(--accent)` to a
  `COLORS[0]` read) and is out of scope here.
- The ribbon's **Home tab has no content anywhere in the app today** (confirmed via search) — the
  natural home for the Theme picker and the Align/Distribute toolbar.
- `Widget.config` and `ReportPage`-level JSON columns are the established zero-migration place for
  new per-widget/per-page settings (used this session for `hidden`, `drillthroughPageId`,
  `tooltipPageId`, `mobile_layout`) — Tab order reuses this via `Widget.config.tabIndex`.
- `ReportBuilder.tsx` currently has one single-widget selection concept, `selectedW: Widget |
  null`, driving the right-hand config panel. Multi-select is a **new, separate** selection
  concept (`multiSelectedIds: Set<number>`) used only for alignment — clicking a widget normally
  still sets `selectedW` as today; **Shift+click** toggles multi-select membership instead.

## Part A — Area chart

New `WidgetType: 'area'`, `WIDGET_CATALOG` entry (Charts category), `ROLE_SPECS.area` identical to
`line`'s (`category` + `measure`). Backend: `SHAPERS["area"] = shape_series` (one line). Frontend:
new `AreaChartRenderer.tsx` — recharts `<AreaChart>`/`<Area>`, styled consistently with
`LineChartRenderer.tsx` (same axis/tooltip/click-to-filter wiring, `fill` using `COLORS[0]` at
reduced opacity under the line).

## Part B — Funnel chart

New `WidgetType: 'funnel'`, `ROLE_SPECS.funnel` identical to `bar`'s (`category` + `measure`).
Backend: `SHAPERS["funnel"] = shape_series` (one line — funnel stages are just the sorted
dimension+measure rows, sorting/limit already handled generically by existing config). Frontend:
new `FunnelChartRenderer.tsx` using recharts' built-in `<FunnelChart>`/`<Funnel>`/`<LabelList>`.

## Part C — Card / Multi-row card

New `WidgetType: 'card'`. `ROLE_SPECS.card = [{ role: 'measures', label: 'Fields', multi: true,
required: true }]` — same multi-measure role pattern as `correlation_matrix`. Backend: new
`shape_card(df, config)` in `widget_data.py` — for each measure in `resolve_roles(config)
['measures']`, compute the single aggregate (respecting `config.get('aggregation', 'sum')`,
reusing the existing per-aggregation dispatch already used elsewhere in this file) and return
`{"rows": [{"name": measure, "value": agg_value} for each measure]}` — the same `{name, value}`
row shape the `list` widget already renders. `SHAPERS["card"] = shape_card`. Frontend: **not** a
`chartRenderers/` entry (not a recharts chart) — a new `wt === 'card'` branch in
`WidgetRenderer.tsx`'s `WidgetBody`, directly beside the existing `kpi` branch, rendering each row
as a stacked label+big-number block (same visual treatment as the `kpi` branch, repeated per row).

## Part D — Ribbon chart (scoped down, documented as an approximation)

New `WidgetType: 'ribbon'`. `ROLE_SPECS.ribbon` identical to `heatmap`'s (`category` + `category2`
+ `measure`). Backend: `SHAPERS["ribbon"] = shape_heatmap` (reuses the existing 2D-grouped shaper
verbatim — one line). Frontend: new `RibbonChartRenderer.tsx` — a **stacked bar chart ordered by
rank within each category-1 group**, using recharts' stacked `<Bar>` (one `<Bar>` per distinct
`category2` value, `stackId="ribbon"`), color-coded by `category2` via `COLORS`. This is
explicitly *not* Power BI's flowing-ribbon-connector visual (that needs hand-built SVG path
interpolation between adjacent bars — out of scope for this round) — the audit note for this row
will say so plainly.

## Part E — Themes

Backend: `Report.theme: Column(String(20), nullable=False, default="default", server_default=
"default")` + one `_migrate()` line (existing column, not a new table — needs the ALTER
statement). `ReportUpdate`/`ReportOut` schemas gain `theme: Optional[str]` / `theme: str`.

Frontend: new `frontend/src/components/report/themes.ts` exporting `THEMES: Record<string,
string[]>` — 5 named palettes (`default` = today's existing array, plus `ocean`, `sunset`,
`forest`, `mono` — each a 10-color array in the same style). `chartUtils.tsx`'s `COLORS` array is
mutated in place (`applyTheme(name)` function, exported from `chartUtils.tsx`, does
`COLORS.length = 0; COLORS.push(...(THEMES[name] ?? THEMES.default))`). `ReportBuilder.tsx` calls
`applyTheme(report.theme)` in the same effect that loads the report (before first widget render).
A small swatch-button picker (5 color-dot buttons) lives in the ribbon's Home tab content
(injected via the same `setTabContent('home', ...)` pattern already used for Insert/View/Optimize),
calling `reportsApi.update(reportId, { theme: name })` then `applyTheme(name)` immediately (so the
canvas updates without waiting for a reload) and `loadReport()` to persist the change in state.

## Part F — Tab order pane

`Widget.config.tabIndex?: number` — zero backend change (untyped JSON bag, same as `hidden`).
New `TabOrderPane.tsx` — same reorder-list UI/interface shape as `MobileLayoutEditor.tsx` (up/down
buttons per widget row), writing sequential `tabIndex` values (1, 2, 3…) matching the list's
current order into each widget's `config` via the same batched-`updateWidget` pattern
`MobileLayoutEditor`'s consumer already uses. `rightPanelMode` (already a 5-way union from the
Side Panes round: `'default' | 'mobile' | 'selection' | 'sync' | 'bookmarks'`) gains a 6th value,
`'taborder'`, with a matching "⇥ Tab order" view-strip button. Rendering: in View mode, each
widget's outer container gets `tabIndex={(widget.config as any).tabIndex ?? undefined}` — browsers
already respect explicit positive `tabIndex` for keyboard-Tab ordering over DOM order.

## Part G — Multi-select + Align/Distribute

`ReportBuilder.tsx` gains `multiSelectedIds: Set<number>` state. Each widget's `onSelect` handler
becomes: normal click → existing behavior (`setSelectedW(widget)`, clears multi-select); **Shift**
+ click → toggle `widget.id` in `multiSelectedIds` instead (leaves `selectedW`/the config panel
alone). `WidgetRenderer.tsx` gains an `isMultiSelected?: boolean` prop, rendering a distinct
outline color when true (visually distinguishable from the existing single-`selected` blue
outline). Detecting the Shift key: `WidgetRenderer`'s existing `onSelect` callback prop becomes
`onSelect?: (e: React.MouseEvent) => void` (currently `() => void` — this is the one existing
signature change) so `ReportBuilder` can branch on `e.shiftKey`.

When `multiSelectedIds.size >= 2`, the ribbon's Home tab (same `setTabContent('home', ...)`
mechanism, now also hosting the Theme picker from Part E — both render together, Theme picker
first, alignment toolbar conditionally after it) shows 8 buttons: Align Left/Center/Right,
Align Top/Middle/Bottom, Distribute Horizontally, Distribute Vertically. Each computes new `x`/`y`
grid coordinates from the selected widgets' current `layout` (bounding-box min/center/max for
align; even-spacing math for distribute — pure functions, unit-testable independent of any DOM/
React state), then fires one `reportsApi.updateWidget` call per affected widget followed by one
`loadReport()`.

## Testing

- Backend: `test_widget_data_area_funnel.py` (SHAPERS aliasing — a request with `widget_type=
  'area'`/`'funnel'` returns the same shape a `bar` request with identical config would),
  `test_shape_card.py` (multi-measure aggregation, respects per-config `aggregation`),
  `test_report_theme.py` (persistence roundtrip, mirroring `test_report_page_size.py`).
- Frontend: `AreaChartRenderer.test.tsx`, `FunnelChartRenderer.test.tsx`, `RibbonChartRenderer.test.tsx`
  (each a focused render+click-to-filter test, mirroring `chartRenderers/index.test.tsx`'s existing
  pattern), a `card` branch test in `WidgetRenderer.test.tsx`, `chartUtils.test.ts` (new — tests
  `applyTheme` mutates `COLORS` in place), `TabOrderPane.test.tsx` (mirrors
  `MobileLayoutEditor.test.tsx`), an alignment-math unit test file (pure functions, no rendering
  needed), and `ReportBuilder.test.tsx` extensions for: Home-tab theme picker persists a theme,
  Shift+click builds a multi-selection, an align button moves widgets correctly, tab-order pane
  writes sequential indices.

## Explicitly out of scope

The true Power BI ribbon-chart flow-connector visual (approximated per Part D), drag-to-select a
marquee box for multi-select (Shift+click only), any new backend aggregation beyond what
`shape_card` needs, more than 5 built-in themes, custom/uploaded theme JSON.
