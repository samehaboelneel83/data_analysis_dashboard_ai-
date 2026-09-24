# Side Panes: Slicer widget, Selection pane, Sync slicers, Bookmarks — Design

## Context

The Feature Parity Audit (against Power BI's feature set) tracks category 02 "Side panes" at
1 exists · 2 partial · 3 missing: **Bookmarks pane**, **Selection pane**, and **Sync slicers
pane** are all missing. Sync slicers has a hidden dependency — it requires a **Slicer** widget
to exist, which is itself tracked separately under category 03 "Visual types" (also missing).

The user chose to close this whole category in one round, in dependency order:
**Slicer widget → cross-filter page-scoping → Selection pane → Sync slicers pane → Bookmarks.**

This round is scoped down from full Power BI parity in two deliberate ways, decided during
brainstorming:
- The Selection pane covers **visibility only**, not z-order/reordering — the app's canvas is
  grid-based (widgets placed by x/y/w/h, not freeform), so widgets essentially never overlap on
  purpose, and reordering would solve a problem this app doesn't really have.
- Bookmarks capture **page + cross-filters + prompt-filter values + widget visibility** — not
  zoom (a personal view convenience, not report state) and not report-level settings.

## Part A — Slicer widget

A new `WidgetType: 'slicer'`, added to `WIDGET_CATALOG` under the existing `'Controls'` category
alongside `kpi`/`table`/`crosstab`/`list`/`text`/`button`.

**Config shape:** `{ dimension: string }` — identical to every other dimension-only widget
(`bar`, `list`, etc.). `ROLE_SPECS.slicer = [{ role: 'category', label: 'Field to filter by',
required: true }]`, so `WidgetConfigPanel.tsx`'s existing generic role-field rendering picks it up
for free — no new config-panel code needed beyond registering the role spec.

**Data:** Reuses `widgetDataApi.query` exactly as-is — a dimension-only query already returns
`{ rows: [{ name, value }] }` where `value` is the row count per distinct value (this is the same
"count" query path already fixed to bypass the grain-invariant hazard, from the DirectQuery work
earlier this session). The slicer widget renders each `row.name` as a checkbox with `row.value`
shown as a count, exactly like Power BI's slicer list.

**Rendering** (`WidgetRenderer.tsx` → `WidgetBody`): new `wt === 'slicer'` branch — a scrollable
checkbox list. Checked state comes from `localSelected` generalized to hold an array
(`localSelected: unknown[]` instead of `unknown` — see Part B). Toggling a checkbox calls a new
`onToggleSlicerValue(value)` handler (parallel to the existing `onClickPoint`), which adds/removes
that value from the widget's local selection and re-emits the full array as one filter.

**Config UI:** No new fields beyond the role spec — reuses `WidgetConfigPanel.tsx`'s existing
dimension-role select.

## Part B — Cross-filter changes: multi-value + page scoping

Two changes to `CrossFilterContext.tsx`, needed by both the Slicer widget and Sync slicers:

**Multi-value filters.** `ActiveFilter.value: unknown` becomes `ActiveFilter.value: unknown |
unknown[]`. Downstream, `WidgetRenderer.tsx`'s `mergedConfig` builder already maps
`incomingFilters` to `{ column, op: 'eq', value }` — this becomes `{ column, op: Array.isArray(f.value)
? 'in' : 'eq', value: f.value }`, matching the backend's already-supported `in` operator
(`_apply_filters` in `widget_data.py`) with zero backend changes.

**Page scoping.** `ActiveFilter` gains `sourcePageId: number`. Both `emitFilter` and the new
`emitMultiFilter(widgetId, pageId, column, values: unknown[], label)` take the emitting widget's
page id as a parameter — call sites already have this for free via `widget.page_id` (an existing
field on every `Widget` object, no new prop threading needed). `getFiltersFor(widgetId,
currentPageId)` changes its signature to accept the current page id (also just `widget.page_id`
at the call site) and filters through: return only filters where `f.sourcePageId === currentPageId
OR interactions[f.sourceWidgetId]?.syncAllPages`. This is the one behavior change users will
notice: a chart-click filter on Page 1 no longer silently reaches Page 2 (previously accidental,
confirmed in the Layout Audit as an unintended side effect of `CrossFilterProvider` being mounted
once per report).

**`syncAllPages` flag.** A new field on `CrossFilterContext`'s per-widget `interactions` map
entry (`WidgetInteraction` gains `syncAllPages?: boolean`, default `false`) — set via
`setInteraction`, the same function `InteractionSettings.tsx` already calls. This is *not* wired
into `InteractionSettings.tsx`'s UI (that panel is about broadcast/receive, a different concept);
it's set exclusively from the new Sync Slicers pane in Part D.

## Part C — Selection pane

New component `frontend/src/components/report/SelectionPane.tsx`, rendered in the same
right-panel slot `ReportBuilder.tsx` already switches on (`showMobileEditor` → generalized to a
`rightPanelMode: 'default' | 'mobile' | 'selection' | 'sync' | 'bookmarks'` state, replacing the
single boolean). A new "👁 Selection" button sits next to "📱 Mobile layout" in the view-strip.

Lists `pageWidgets`, each row: title + widget-type icon + an eye-icon toggle button. Toggling
writes `{ hidden: !hidden }` into that widget's `config` (new optional key, same
`onUpdate(config, title)` path `WidgetConfigPanel` already uses via `updateWidgetConfig`) — no
backend/schema change, `Widget.config` is already an untyped JSON column.

**Rendering effect:** `ReportBuilder.tsx`'s widget-mapping loop (both the desktop grid and the
mobile stack) filters out `widget.config.hidden` widgets when `!editMode`; in `editMode` they
still render, at reduced opacity (matching the existing dimmed-hidden-page convention from
`page_type === 'hidden'`), so editors can still select and un-hide them.

## Part D — Sync slicers pane

New component `frontend/src/components/report/SyncSlicersPane.tsx`, same right-panel slot,
toggled from a new "🔗 Sync slicers" view-strip button. Lists every widget across **all pages**
of the report where `widget_type === 'slicer'` (grouped by page name), each with a toggle: "This
page only" / "All pages" — backed by `CrossFilterContext.setInteraction(widgetId, { ...current,
syncAllPages: checked })` from Part B. Requires `CrossFilterProvider`'s `interactions` map (already
report-scoped, unaffected by the Part B page-scoping change, which only touches `activeFilters`)
to be readable from this pane — already exposed via `useCrossFilter()`.

## Part E — Bookmarks

**Backend** (mirrors the `Relationship` model/router pattern from the Application Shell round):

```python
class Bookmark(Base):
    __tablename__ = "bookmarks"
    id         = Column(Integer, primary_key=True)
    report_id  = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(255), nullable=False)
    position   = Column(Integer, nullable=False, default=0)
    state      = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
```

`state` shape (frontend-defined, opaque JSON to the backend, same convention as
`ReportPage.mobile_layout`):
```ts
{
  pageId: number
  activeFilters: { column: string; value: unknown; label: string; sourceWidgetId: number; sourcePageId: number }[]
  promptValues: Record<number, string>   // keyed by page id, matches ReportBuilder's existing state shape
  hiddenWidgetIds: number[]
}
```

Router `backend/app/routers/bookmarks.py`: `GET/POST /reports/{report_id}/bookmarks`, `DELETE
/bookmarks/{id}` — org-scoped via the owning report's `org_id`, following `check_org` convention.

**Frontend:** New `BookmarksPane.tsx`, same right-panel slot, "🔖 Bookmarks" view-strip button.
"+ Add bookmark" captures current state (`activePage.id`, `activeFilters` from
`useCrossFilter()`, `promptValues`, and the current page's widgets' `hidden` flags) and posts it.
Clicking a saved bookmark: `setActivePage` to the saved page, replay each `activeFilters` entry
through `emitFilter`/`emitMultiFilter` (clearing existing filters first via `clearAllFilters()`),
restore `promptValues`, and write each `hiddenWidgetIds` entry back into its widget's config via
`updateWidgetConfig`.

## Testing

- Backend: `test_bookmark_model.py` (persistence), `test_bookmarks_org_scoping.py` (mirrors
  `test_relationships_org_scoping.py` — cross-org 404s, org-scoped list).
- Frontend: `WidgetRenderer.test.tsx` extended for the slicer widget's checkbox rendering and
  multi-value emit; `CrossFilterContext.test.tsx` (new) for page-scoping and `syncAllPages`
  bypass; `SelectionPane.test.tsx`, `SyncSlicersPane.test.tsx`, `BookmarksPane.test.tsx` (new,
  each following the `MobileLayoutEditor.test.tsx` pattern); `ReportBuilder.test.tsx` extended for
  the right-panel-mode switch and end-to-end bookmark capture/restore.

## Explicitly out of scope

Selection-pane reordering/z-order, per-user bookmarks (all bookmarks are report-shared, matching
every other piece of report state in this app), bookmark-triggered from the Button widget
(natural future follow-up once Button gets action wiring — tracked separately in the audit under
category 04), zoom/report-level-setting capture in bookmarks.
