# Hierarchies across widgets — plan and results (2026-10-10)

Goal: one hierarchy (Region › Country, Year › Quarter › Month) works the same way in
every widget that can show one — slicer, crosstab rows and columns, tree, sunburst, icicle —
and a selection in any of them filters the rest of the page **exactly**.

Defaults chosen: crosstab subtotals sit **below** their group; a hierarchy selection filters
**every widget that has those columns**.

## The shared piece: the `paths` filter

```json
{"column": "region", "op": "paths",
 "value": {"columns": ["region", "country"], "granularities": [null, null],
           "paths": [["Europe"], ["North America", "Canada"]]}}
```

- OR of paths; each path is an AND of its levels; a short path is a whole branch.
- Exact: `Egypt › Alexandria` never lets in a US Alexandria (no cross-product).
- Date levels compare as bucket labels (`2025-Q2`), the labels the widgets show.
- Import data: pandas (`widget_data._apply_paths_filter`). DirectQuery: bound SQL
  `((c1 = :p AND c2 = :p) OR …)`, columns allow-listed; date buckets are applied after the
  row fetch. DuckDB falls back to pandas.

## Steps

| Step | What | Where |
|---|---|---|
| 1 | One drill model per widget in the page state (bookmarks keep it). Fixed: clicking an expanded "North › Cairo" bar filtered nothing; now filters each level. | `CrossFilterContext.tsx` (`drillOf`, `setDrill`, `restoreDrills`), `WidgetRenderer.tsx` |
| 2 | Hierarchy slicer as a tick tree: branch ticks, half-ticked parents, search at any level, counts, Select all / Clear. | `SlicerTree.tsx`, `lib/slicerTree.ts`, backend `_slicer_tree` |
| 3 | Crosstab with hierarchies on rows **and** columns: ▸/▾ on any header, subtotal per group ("Total Europe"), grand totals, every number computed from the group's own rows (an average subtotal is the group's average). Click a number → filters the page to that row and column. Columns role accepts a hierarchy (`hierarchyNodeId2`); a plain column on the other axis is a one-level chain. A level with too many values (Day across the top) is left out with a note instead of cutting off whole years. | `HierPivot.tsx`, `services/hier_pivot.py`, `WidgetConfigPanel.tsx` (`pickColumns`) |
| 4 | Tree widget tick boxes now filter (they were drawn but never wired). Sunburst and icicle zoom into a branch on click; a trail ("All › Europe") and the sunburst centre zoom back out. | `chartRenderers/HierarchyRenderer.tsx` |

Found and fixed while testing in the browser:
- Slicer tree, tree, sunburst showed "No rows match these filters" under a filter, because
  their answers carry nodes, not rows (`WidgetRenderer` row count).
- A sunburst segment that fills the whole circle (an only child) drew nothing.
- Crosstab column headers did not line up under an open group (now proper col/row spans).

## Checks

- Backend: `tests/test_hierarchy_plan.py` (19), plus widget-data, pivot, DirectQuery,
  hierarchy and slicer suites — 460 passed.
- Frontend: `lib/slicerTree.test.ts`, `WidgetRenderer.test.tsx` (steps 1–4),
  `HierarchyRenderer.test.tsx`, `hierarchyConfig.test.tsx` — full run 343 files, all pass;
  `tsc` clean; production build OK.
- Browser, English and Arabic, on "Demo — Sales" (scratch report
  **"Hierarchy check (delete me)"**): slicer tree; tree tick Europe › Germany filters the bar
  chart to Germany; crosstab opens Europe and 2025 into quarters with "Total Europe" /
  "Total 2025"; clicking Germany × 2025-Q2 filters the tree to exactly that cell's value
  ($91,361); Arabic shows RTL arrows and translated totals; sunburst zooms in and out.

## Not done / next

- DirectQuery was checked by unit tests (SQL, allow-list, injection), not in the browser.
- Zoom on sunburst/icicle is a local view (not saved in bookmarks); crosstab open branches are.
- Circle pack, dendrogram and org do not zoom yet.
- Crosstab header shows raw column names ("region › country"), not the hierarchy level names.
