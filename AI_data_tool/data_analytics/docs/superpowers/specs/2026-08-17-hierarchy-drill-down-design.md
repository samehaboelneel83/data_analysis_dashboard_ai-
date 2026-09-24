# Hierarchy Drill-Down + In-Panel Editing — Design

## Context

The Feature Parity Audit flags "Drill down / up on hierarchies" as partial: `HierarchyNode`
auto-generates a Year→Quarter→Month→Day chain (and the tree is already editable — rename,
delete, and the Category/Measure reclassify toggle added earlier this session), but no chart
renderer exposes interactive click-to-drill. This round closes that gap: binding a widget's
Dimension to a hierarchy node, drilling in place on click, and a shortcut back to the hierarchy
editor from the widget config panel.

## Codebase facts this design relies on

- `HierarchyNode` (`backend/app/models/models.py`) is a self-referential tree via `parent_id`.
  Auto-generate (`hierarchy.py`'s `auto_generate`) produces two distinct chain shapes:
  - **Date chains**: every level (Year/Quarter/Month/Day) shares the *same* `column_name` (the
    source datetime column) and is distinguished only by `format` (one of `year`/`quarter`/
    `month`/`day` — see `DATE_DRILL_LEVELS`). No level has its own physical column.
  - **Category chains**: not auto-generated today, but nothing stops a user from manually
    building one (e.g. Region → City) via drag/reparent in `HierarchyTree.tsx` — each level
    there *is* a distinct real column.
- `shape_series` (`widget_data.py`) groups by `config.dimension`, a literal column name — it has
  no concept of "group by Year of created_at." Date-level drilling needs a new
  `dimension_granularity` config key.
- The date-truncation logic this needs already exists, but only as closures private to
  `_build_safe_ns` (`widget_data.py:822`), the calc-column formula evaluator's namespace builder
  — `YEAR`/`QUARTER`/`MONTH`/`DAY`/`DATETRUNC` are defined there and not reusable as-is. This
  design extracts the pandas truncation logic into one new module-level function,
  `_truncate_to_granularity(series, granularity)`, that both `_build_safe_ns`'s `DATETRUNC`
  closure and the new `shape_series` code path call — no duplicated logic, no behavior change to
  the formula language.
- `WidgetRenderer.tsx`'s `onClickPoint`/`handleClick` path is already shared by every
  category-clickable chart renderer (bar, pie, donut, treemap, heatmap, line) — they all funnel
  through one handler in `WidgetRenderer`, not six separate ones. This is why drill-down can be
  added once in `WidgetRenderer` rather than touching six renderer files.
- `WidgetConfigPanel.tsx`'s role fields are driven generically by `ROLE_SPECS[wt]`; the Dimension
  (`category` role) field currently renders a plain `<select>` of `colOptions` (built from the
  `columns: DatasetColumn[]` prop). `WidgetConfigPanel` does not currently receive hierarchy data
  at all — a new `hierarchy?: HierarchyNode[]` prop is needed, passed from `ReportBuilder.tsx`
  (which already loads it for the sidebar tree).
- Cross-filtering (`CrossFilterContext`'s `emitFilter`) and click-to-drill are **not** mutually
  exclusive per the approved interaction model — a click both drills and broadcasts, matching how
  Power BI's own cross-filter and drill-down coexist today.

## Part A — Binding a widget's Dimension to a hierarchy node

`WidgetConfigPanel`'s Dimension `<select>`, when `hierarchy` is provided and non-empty, gains an
extra `<optgroup>` listing hierarchy root nodes with their full drill path as the label (e.g.
"Order Date ▸ Year"). Picking one sets `config.dimension` to that node's `column_name` (for date
chains, also `config.dimension_granularity = node.format`) and `config.hierarchyRootId` to the
*root* node's id (needed later to look up siblings/children for drilling and for the "Edit
hierarchy" shortcut). Picking a plain column (the existing behavior) clears both new keys. When
`config.hierarchyRootId` is set, a small "✎ Edit hierarchy" link appears next to the Dimension
field; clicking it opens `HierarchyTree` in a lightweight inline popover scoped to that root's
subtree, reusing the existing tree component and its rename/reclassify/delete actions verbatim —
no new editing logic, just a new place to reach it from.

## Part B — Backend: `dimension_granularity`

`shape_series` gains an optional `config.get("dimension_granularity")`. When set, before grouping,
the dimension column is replaced with `_truncate_to_granularity(df[dim], granularity)` — a new
module-level function performing the same `dt.year` / `dt.to_period(...).dt.start_time` logic
`DATETRUNC` already does, returning integers for `year`/`quarter`/`month` labels (e.g. `2024`,
`"2024-Q1"`, `"2024-01"`) and a normalized date for `day`. `_build_safe_ns`'s `DATETRUNC` closure
is refactored to call this same function (pure extraction, its own tests keep passing unchanged).
Category-chain drilling needs no backend change — the frontend simply swaps `config.dimension` to
the child node's `column_name` and re-queries, which `shape_series` already handles today.

## Part C — Frontend: drill state + breadcrumb

`WidgetRenderer` gains `drillPath: {nodeId: number; label: string}[]` state (local, not persisted
— mirrors how today's cross-filter `localSelected` already resets per session, never written to
`Widget.config`). It's only relevant when `widget.config.hierarchyRootId` is set. On a click that
would normally only call `emitFilter`, if the widget is hierarchy-bound and the current node has a
child in the hierarchy tree (passed down via a new `hierarchy?: HierarchyNode[]` prop, same data
`WidgetConfigPanel` now needs), two things happen together: (1) `emitFilter` fires exactly as
today, and (2) a new step is pushed onto `drillPath`, and the widget re-queries with the child
node's `column_name`/`dimensionGranularity` plus every ancestor step's clicked value folded into
`config.filters` as `eq` filters. A breadcrumb strip ("All ▸ 2024 ▸ Q1") renders in the widget
header only while `drillPath.length > 0`; each crumb is clickable to truncate the path back to
that depth and re-query. Reaching a leaf node (no children) leaves clicking as cross-filter-only,
unchanged from today.

## Testing

- Backend: `_truncate_to_granularity` unit tests (year/quarter/month/day against a hand-built
  datetime series); a `shape_series` test with `dimension_granularity="quarter"` grouping sales by
  calendar quarter; a regression test that `_build_safe_ns`'s `DATETRUNC` still produces identical
  output post-refactor (run the existing calc-column formula test suite unchanged).
- Frontend: `WidgetConfigPanel` — selecting a hierarchy node sets `dimension`/`dimensionGranularity`/
  `hierarchyRootId`; the Edit-hierarchy link only appears when bound. `WidgetRenderer` — clicking a
  hierarchy-bound bar both emits a cross-filter and pushes a drill step, re-queries with the merged
  filter set, and clicking a breadcrumb crumb truncates the path and re-queries; a non-hierarchy
  widget's click behavior is provably unchanged (same assertions as today's existing cross-filter
  tests, re-run against a widget with no `hierarchyRootId`).

## Explicitly out of scope

Drilling on chart types beyond the six that already share `onClickPoint` (scatter, bubble, gauge,
etc. keep today's behavior); persisting drill state across a page reload or into bookmarks (drill
position is session-local, like selection state); building new category-chain auto-generation
(only date chains auto-generate — manual category chains work once a user builds one, but this
round doesn't add UI to build one faster); a toolbar drill-up/drill-down button pair independent of
clicking a data point (deferred per the approved interaction model — click-to-drill only).
