# Application Shell (Ribbon, Report/Data/Model Views, Relationship Metadata)

**Date:** 2026-08-15
**Status:** Draft

## Overview

This app was audited against Power BI's full feature surface across seven categories (application
shell, side panes, visual types, interactive controls, formatting/layout, Power Query, and the web
service layer). That audit is a decomposition exercise, not a spec — each category is its own
future sub-project, sequenced independently. This is the first: the **Application Shell** — the
ribbon, the Report/Data/Model view switcher, relationship *metadata* (not yet a query engine),
canvas page-size presets, page-navigation extensions, and a status bar.

One deliberate split shaped this spec: relationships between datasets need to support real
cross-dataset queries eventually (a widget pulling `Orders.revenue` grouped by `Customers.region`
across a join), but that query engine — spanning both import mode and DirectQuery, with RLS and
caching implications — is architecturally comparable in size to the entire DirectQuery build
(`2026-08-15-directquery-design.md`, five phases). Bundling it into a UI-chrome spec would produce
exactly the kind of sprawling, unreviewable unit that sub-project decomposition exists to prevent.
This spec defines relationships as pure metadata — the exact shape a future join engine will
consume — with a diagram to view/edit them. The join engine itself is out of scope here.

## Current State

- **Global nav** — `frontend/src/components/Layout.tsx` is a plain sidebar with page links and a
  light/dark toggle. No ribbon, no contextual command surface.
- **Report editing** — `frontend/src/pages/ReportBuilder.tsx` is the canvas: a 12-column grid with
  drag/resize/snap, widget add/config via `WidgetConfigPanel.tsx`, filters via `FilterBar.tsx`.
  There is no Report/Data/Model view switcher — it's the only view.
- **Data browsing** — `frontend/src/pages/DatasetDetail.tsx` already has a "Data" tab: paginated,
  filtered, sorted, searchable row browsing (`dataPreviewApi.query`), entirely separate from the
  report editor.
- **No relationship concept anywhere.** `Report.additional_dataset_ids` (`backend/app/models/
  models.py`) lets a report reference multiple datasets, but nothing records how they relate to
  each other — every widget query still resolves against exactly one dataset.
- **Page types already partially support this** — `ReportPage.page_type` (`models.py`) is one of
  `'normal' | 'hidden' | 'popup'`, and the frontend already omits `'hidden'` pages from the normal
  tab strip (pattern to extend, not invent).
- **The one existing cross-cutting context provider** — `frontend/src/components/report/
  CrossFilterContext.tsx` — is the precedent this spec's `RibbonContext` follows: page-level state
  that any nested component can read from and write into, provided once near the app root.
- **The admin CRUD + validation pattern to mirror** — `RowSecurityRule` in `backend/app/routers/
  admin.py`: org-scoped create/update, validated before being stored rather than failing at query
  time. `Relationship` follows the identical shape.

## Ribbon

Rendered once, replacing `Layout.tsx`'s sidebar as the app's primary chrome. Four fixed tabs —
**Home, Insert, Modeling, View** — always present; contents are contextual, not tied to a static
route table. A static per-route lookup can't express live page state (an Undo that's genuinely
disabled when there's nothing to undo, a Save button reflecting real dirty/clean state), so content
is supplied by whichever page is currently mounted:

```tsx
const { setTabContent, clearTabContent } = useRibbon()
useEffect(() => {
  setTabContent('home', <SaveStatusActions />)
  return () => clearTabContent('home')
}, [/* deps */])
```

`RibbonContext` holds `{ home, insert, modeling, view }` JSX slots plus the setter/clear pair above,
following `CrossFilterContext`'s existing provider shape. Outside a report (Datasets, Connections,
Admin pages), Home shows page-relevant actions (Upload, New Connection) and the other three tabs
render empty. Inside a report: Home = save state; Insert = add visual/text box/button (replacing
today's inline "+ Add Widget" affordance); Modeling = calculated columns + relationships; View =
theme/layout controls (page-size presets from below live here).

**Keyboard access**, per the original ask and not a large addition on top of the component itself:
`Ctrl+F6` moves focus into the ribbon; `Tab` moves between the four tab buttons (standard button
semantics, no extra work); arrow keys move focus within the active tab's controls via a roving
`tabindex` (one control has `tabindex="0"`, the rest `-1`, arrow keys shift which one does).

**Optimize tab is excluded** — there's no real performance tooling to put in it yet (a plausible
future home once DirectQuery cache stats or query timing exist).

## Report/Data/Model Views

A left-edge icon strip — Report, Data, Model — appears **only when a report is open**; it's not
part of the global shell the way the ribbon is, since view-switching is inherently about editing
one report.

- **Report** — today's `ReportBuilder.tsx` canvas, unchanged.
- **Data** — today's `DatasetDetail.tsx` "Data" tab content, reached from inside the report editor
  instead of a separate page navigation.
- **Model** — new, described next.

## Model View — Relationship Metadata

**Data model** (new table, mirrors `RowSecurityRule`):

```python
class Relationship(Base):
    __tablename__ = "relationships"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    from_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    from_column     = Column(String(255), nullable=False)
    to_dataset_id   = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    to_column       = Column(String(255), nullable=False)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
```

Join-key only — no cardinality, no cross-filter direction. This is a deliberate simplification
(confirmed with the user), not an oversight: it's the exact shape a future join engine consumes, so
adding cardinality/direction later is a pure addition, not a migration that reshapes existing rows.

**API** — admin-scoped CRUD under `/admin/relationships`, identical validation shape to
`RowSecurityRule`: `from_column`/`to_column` must exist as real `DatasetColumn` rows on their
respective datasets (org-checked), checked at creation/update time rather than surfacing as a
confusing failure wherever the relationship is later consumed.

**Diagram scope** — shows only the datasets already attached to the open report
(`Report.dataset_id` + `Report.additional_dataset_ids`), not every dataset in the org. Boxes use a
simple auto-layout (grid arrangement by insertion order) — no persisted custom positions in v1, to
keep the data model and the interaction both genuinely simple. Lines drawn between related columns
per existing `Relationship` rows. Relationships are created via a form (pick dataset A + column,
dataset B + column, submit), not drag-to-connect — a substantially larger interaction to get right
that isn't justified for a join-key-only v1.

## Canvas Page-Size Presets

`ReportPage` gains `page_size` (`String`, `'16:9' | '4:3' | 'custom'`, default `'16:9'`) plus
nullable `custom_width`/`custom_height` used only when `page_size == 'custom'`. Surfaced in the
ribbon's View tab. Mobile layout (a distinct alternate widget arrangement per page, edited in its
own mode) is excluded — a different kind of feature than a page-size preset, deserving its own
round.

## Page Navigation Extensions

`ReportPage.page_type` gains `'tooltip'` and `'drillthrough'` alongside the existing
`'normal' | 'hidden' | 'popup'`. Both are omitted from the normal bottom tab strip (the same
treatment `'hidden'` already gets) and tagged distinctly wherever pages are managed/listed. No
triggering mechanics in this spec — right-click-to-drillthrough and hover-to-show-tooltip are real
interaction work that depends on the button/bookmark action-wiring gap identified in the audit
(currently: buttons render but have no action wiring at all). Building drillthrough triggering here
without that foundation would mean building it twice.

## Status Bar

A thin strip at the canvas bottom: `Page {n} of {total}` plus save status (`Saved` / `Saving…`, and
for DirectQuery-backed pages, a cache-freshness indicator reusing the `sampled`-badge convention
already established in `WidgetRenderer.tsx`). No zoom control — that's a real interactive
canvas-scaling mechanism distinct from the existing grid/snap, better scoped on its own.

## Testing

- **Backend:** `Relationship` CRUD gets the same coverage shape as the existing
  `test_admin_row_security_rules.py` — org scoping, column-existence validation at create/update
  time, cross-org 404s. `ReportPage.page_size`/`page_type` extensions get model-level tests
  mirroring `test_dataset_mode.py`'s default-value pattern.
- **Frontend:** `RibbonContext` gets a focused test asserting content set by one mounted component
  is visible in the ribbon and cleared on unmount (same style as `WidgetRenderer.test.tsx`'s
  mock-and-assert approach, not exhaustive visual/snapshot testing — consistent with this project's
  established "diff-based review over exhaustive component tests" convention). The Model view's
  relationship form gets a test for the create-relationship flow against a mocked API.

## Explicit v1 Exclusions

- **No cross-dataset query execution.** Relationships are metadata only; no widget can pull columns
  from two datasets at once yet. That's Sub-project B (Relationship Query Engine), sequenced after
  this spec ships, built on top of the exact `Relationship` shape defined here.
- **No relationship cardinality or cross-filter direction** — join key only.
- **No custom diagram positions** — auto-layout only.
- **No mobile layout** — page-size presets only.
- **No drillthrough/tooltip triggering mechanics** — page types exist and are tagged; the
  interaction itself waits on button/bookmark action wiring.
- **No Optimize ribbon tab** — nothing real to put in it yet.
- **No canvas zoom control** in the status bar.
- **Global shell scope, confirmed with the user despite being the larger option:** the ribbon
  replaces `Layout.tsx`'s sidebar everywhere (Datasets, Connections, Admin, not just the report
  editor), with contextual per-tab content rather than per-route ribbon redefinition.

## Rollout (phases — each gets its own implementation plan)

1. **Phase 1 — Ribbon shell.** `RibbonContext`, the four-tab component, keyboard navigation,
   replacing `Layout.tsx`'s sidebar. Every existing page supplies at least empty/minimal tab
   content so nothing regresses.
2. **Phase 2 — Report/Data/Model view switcher.** The left-edge icon strip inside an open report;
   Data view relocated from `DatasetDetail.tsx` into this context; Model view scaffolded (empty
   state) ahead of relationships landing.
3. **Phase 3 — Relationship metadata.** `Relationship` model + migration + admin CRUD + validation,
   with tests, before any diagram UI consumes it.
4. **Phase 4 — Model view diagram.** Dataset boxes (auto-layout) + relationship lines + the
   create-relationship form, wired to Phase 3's API.
5. **Phase 5 — Canvas, page nav, status bar.** `page_size`/`page_type` extensions and the status
   bar, the most independent and lowest-risk pieces, sequenced last since nothing else depends on
   them.

## Files Changed (representative)

| File | Change |
|---|---|
| `frontend/src/components/RibbonContext.tsx` | New — provider + `useRibbon()`, mirrors `CrossFilterContext.tsx`'s shape |
| `frontend/src/components/Ribbon.tsx` | New — four-tab bar, keyboard nav, renders context content |
| `frontend/src/components/Layout.tsx` | Sidebar replaced by `<Ribbon />` |
| `frontend/src/pages/ReportBuilder.tsx` | Gains the Report/Data/Model view strip; Insert-tab content moves to the ribbon |
| `frontend/src/pages/DatasetDetail.tsx` | Data-tab content relocated into the report-scoped Data view |
| `frontend/src/components/report/ModelView.tsx` | New — relationship diagram + create-relationship form |
| `backend/app/models/models.py` | `Relationship`; `ReportPage.page_size`/`custom_width`/`custom_height`; `page_type` gains `'tooltip'`/`'drillthrough'` |
| `backend/app/main.py` | `_migrate()` gains the new column/table statements |
| `backend/app/routers/admin.py` | `Relationship` CRUD, validated like `RowSecurityRule` |
| `backend/app/schemas/schemas.py` | `RelationshipCreate`/`Update`/`Out` |
