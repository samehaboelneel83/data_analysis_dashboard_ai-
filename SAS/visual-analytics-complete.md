# Visual Analytics Tool — Complete Reverse-Engineering Deliverable

All fifteen documents of the deliverable merged into one file, in the reading order the README recommends (overview → recommendations → specs → blueprint → raw findings). Each original file is a top-level section; its headings have been shifted down one level. References like `visualizations.md` §G.2 now point to the section of that name below.

## Contents

1. [Visual Analytics Tool — reverse-engineering deliverable](#visual-analytics-tool--reverse-engineering-deliverable) — `README.md`
2. [Recommendations — what to build, in what order, and what to leave behind](#recommendations--what-to-build-in-what-order-and-what-to-leave-behind) — `RECOMMENDATIONS.md`
3. [Implementation Specification — for an AI coding agent](#implementation-specification--for-an-ai-coding-agent) — `implementation-spec.md`
4. [UI/UX Specification — analytics platform](#uiux-specification--analytics-platform) — `UI_UX_SPECIFICATION.md`
5. [Platform blueprint — building a professional data analytics product](#platform-blueprint--building-a-professional-data-analytics-product) — `PLATFORM_BLUEPRINT.md`
6. [Application Map — overview, sitemap and routes](#application-map--overview-sitemap-and-routes) — `application-map.md`
7. [Screen Inventory](#screen-inventory) — `screens.md`
8. [Activity Inventory and User Journeys](#activity-inventory-and-user-journeys) — `activities.md`
9. [Component Inventory](#component-inventory) — `components.md`
10. [Visualization Inventory](#visualization-inventory) — `visualizations.md`
11. [Data Model and State Model](#data-model-and-state-model) — `data-model.md`
12. [Interaction Model](#interaction-model) — `interaction-model.md`
13. [Design System and Responsive Behaviour](#design-system-and-responsive-behaviour) — `design-system.md`
14. [Observed system architecture — session 17](#observed-system-architecture--session-17) — `observed-architecture.md`
15. [Closing the UNKNOWN register — session 19](#closing-the-unknown-register--session-19) — `unknowns-closed.md`

---

<!-- ===== Source: README.md ===== -->

## Visual Analytics Tool — reverse-engineering deliverable

A complete implementation specification for building a new analytics product with similar functionality, workflows, information architecture, interaction patterns and visual language — **without copying proprietary source code, brand assets, wordmarks, icons or product naming.**

**Subject:** SAS Visual Analytics, "Explore and Visualize" module (SAS Viya for Learners deployment).
**Method:** nineteen live observation sessions driving the running application through a browser, plus one cross-check against vendor training material. No vendor source code was read. Fourteen sessions worked in blank, never-saved sandbox reports on a 2.34M-row sample table. Two sessions (6 and 10) observed **saved, production, multi-page reports read-only in View mode** — nine reports in all, covering parameters, forecasting, network, path and decision-tree objects and a custom graph template. Nothing was saved, modified, exported, shared, copied, commented on or deleted in any session, and no confirmation dialog was ever accepted.
**Observed:** 22–23 Sep 2026.

### Files

| File | Contents |
|---|---|
| `application-map.md` | What the product does · complete sitemap · routing model (observed and proposed) |
| `screens.md` | Every significant screen, pane, dialog, and the empty/loading/error/confirmation state catalogue |
| `activities.md` | 20 user activities (entry, preconditions, inputs, steps, result, alternates, validation, errors, dependencies) and 6 end-to-end journeys |
| `components.md` | Reusable UI component inventory with variants, states, inputs, outputs and interactions |
| `visualizations.md` | All 78 object types with required and optional roles, per-chart detail, and capability boundaries |
| `data-model.md` | Observed and inferred entities, attributes, relationships, lifecycles; state machines |
| `interaction-model.md` | Pointer semantics, selection, undo, progressive disclosure, the three-layer filtering model, keyboard |
| `design-system.md` | Typography, colour, layout and component tokens measured from live computed styles; responsive behaviour |
| `implementation-spec.md` | **Start here to build.** Architecture, state, data model, visualization config, routing, components, interactions, responsive, design system, P0–P4 priorities, patterns to copy, 84 defects to fix, acceptance criteria, vendor-documentation cross-check, and the UNKNOWN list |
| `UI_UX_SPECIFICATION.md` | **The design deliverable.** A build-ready UI/UX spec: principles, information architecture, layout system, the full token set, a component library with anatomy/variants/states/a11y, interaction patterns, the nine-state catalogue, microcopy rules, accessibility, responsive and theming, and a definition of done |
| `PLATFORM_BLUEPRINT.md` | **Read this third.** The full-stack engineering design: data plane, semantic layer, query protocol, document service, dual-path rendering, client architecture, platform services, security, and a five-phase build plan |
| `observed-architecture.md` | The runtime and network evidence behind the blueprint — payload budget, the WASM rendering engine, service topology, the query protocol and the autosave mechanism |
| `RECOMMENDATIONS.md` | **Read this second.** The judgement layer: the three ideas the product rests on, a P0–P4 build order, patterns worth copying, the seven failure habits behind all 76 defects, and what not to copy |
| `screenshots/` | Capture manifests by area. **No image files** — see the note in any manifest for why, and what to re-capture |

### Change log

| Date | Change |
|---|---|
| 22 Sep 2026 | Sessions 1–5: object library, right panes, data preparation, interactivity. Initial ten-file split. |
| 23 Sep 2026 | Session 6 folded in (first saved production report, read-only): viewer side pane (`screens.md` §C.3b), drill-down (`interaction-model.md` §H.2b), viewer undo (§H.3), asymmetric filter disclosure (§H.6, defect 11 narrowed), banded display rules (`visualizations.md` §G.2b), Stacking Container component (`components.md`), patterns 11–13 and defects 36–38, UNKNOWN list refreshed. |
| 23 Sep 2026 | Sessions 7–9 folded in: exhaustive option sweeps, automatic-chart decision table (defects 34–35). |
| 23 Sep 2026 | **Session 19** (closing the UNKNOWN register): three more ML objects fitted and all six role schemas re-verified; **Create pipeline fully resolved** — it creates a real Model Studio project and a four-node runnable pipeline, hijacks the tab and crashes on arrival; the platform application map added to `application-map.md` §B.4; defects 82–84. Esri left unanswered by instruction. |
| 23 Sep 2026 | **Session 18** (design tokens and UI/UX synthesis): spacing scale, the single 100ms motion token, layering and focus treatment measured and added to `design-system.md` §L.4b; **`UI_UX_SPECIFICATION.md` added** — the consolidated, build-ready design specification. |
| 23 Sep 2026 | **Session 17** (system architecture): client payload measured at **63.4 MB** incl. a **12.9 MB WebAssembly rendering engine**; service topology, the executor/job/results query protocol, `PUT`-per-change autosave, dual service workers and empty client storage recorded in `observed-architecture.md`; defects 77–81; **`PLATFORM_BLUEPRINT.md` added**. |
| 23 Sep 2026 | **Session 16** (two real models fitted and compared): **Model comparison output resolved** — dialog-configured, three-panel verdict with the winner colour-coded (`visualizations.md` §G.2i); fitted-model headers and **Create pipeline**; Parallel coordinates and Vector plot roles; defects 75–76; **`RECOMMENDATIONS.md` added**. Four UNKNOWNs closed. |
| 23 Sep 2026 | **Session 15** (statistical objects and statistics-flavoured charts, blank sandbox on RETAILDEMO_2): §G.1's Statistics and ML role tables re-verified and confirmed; placeholder rendering, Cluster's two-panel output and row disclosures, Model comparison's precondition, and the Box plot / Histogram / Fit Line option catalogues added as `visualizations.md` §G.2h; Geo group corrected to a **layer stack**; a seventh undo grammar; defects 69–74. |
| 23 Sep 2026 | **Session 14** (geography items and the geo-map family, blank sandbox on RETAILDEMO_2): the New Geography Item dialog in full (`screens.md` §C.4b), the seven map layers and their roles (`visualizations.md` §G.2g), basemap services, `GeographyItem` added to the data model, patterns 18–20, defects 64–68. Two standing UNKNOWNs closed; an Esri terms dialog was left unanswered by choice. |
| 23 Sep 2026 | **Session 13** (Data pane, multi-select and drag-and-drop, blank sandbox on PRODUCTS): the multi-item drop resolver and the three-zone drop-target model (`visualizations.md` §G.2e–G.2f), Data-pane selection corrected in `components.md` and `interaction-model.md` §H.3b, defects 58–63, and the vendor's four-measure correlation rule confirmed on the drop path (§P.3). Two earlier selection claims retracted. |
| 23 Sep 2026 | **Session 12** (Suggestions follow-up, second sandbox with a second data source): slot-1 chart type shown to be a **random draw**, multi-source scoping resolved, and the session-11 verdict on the vendor's correlation claim **corrected** — the correlation mechanism is real, the missing piece is a semantic veto. Defects 19 and 53 re-scoped; two UNKNOWNs closed, one opened. |
| 23 Sep 2026 | **Session 11** (Suggestions pane, blank sandbox on RETAILDEMO_2): the engine characterised as a fixed four-slot template rotation (`visualizations.md` §G.2d), pane and card anatomy (`screens.md`, `components.md`), activity A19 rewritten, defects 48–57, defects 19 and 35 sharpened, and a first pass at the vendor-documentation claims (§P.3, revised by session 12). |
| 23 Sep 2026 | **Session 10** (favorites crawl, nine saved reports, read-only): analytic and custom objects (`visualizations.md` §G.2c), viewer pane corrections and the four filter section kinds (`screens.md` §C.3c), report prompt bar (§C.3d), four new dialogs, six new components, control cascades and the first disclosed keyboard shortcuts (`interaction-model.md` §H.6b, §H.7), narrow-width behaviour (`design-system.md` §M), patterns 14–17, defects 39–47, defect 29 widened to four causes, UNKNOWN list refreshed (parameters, analytic objects and custom templates resolved). |

### Evidence labelling

- **OBSERVED** — seen directly in the running UI.
- **INFERRED — confidence: High / Medium / Low** — deduced from observed behaviour.
- **DOCUMENTED** — from vendor training material, not re-verified in the app.
- **UNKNOWN** — could not be determined from the UI. Listed explicitly rather than guessed.

### Originality constraints

1. Do not copy the vendor's name, logo, icon set, licensed typeface, theme names or any screenshot.
2. The design tokens describe proportions and roles — reproduce the *system*, not the brand hue.
3. Vendor-flavoured terminology ("Crosstab", "Key value", "Data roles", "Lattice") has a neutral mapping in `implementation-spec.md`.
4. No proprietary source was read; everything here is black-box behaviour.


---

<!-- ===== Source: RECOMMENDATIONS.md ===== -->

## Recommendations — what to build, in what order, and what to leave behind

Drawn from sixteen hands-on sessions against SAS Visual Analytics. This is the judgement layer on top of `va-spec/`: the spec says what the product does, this says what you should do about it.

---

### 1. The three things that actually make the product work

Strip away 78 object types and the product rests on three ideas. Get these right and the rest is surface area.

**1. Typed roles with filtered pickers.** Every object declares a role schema; every picker offers only type-compatible columns; required roles are enforced. A user cannot put a date on a measure axis. This is why a novice can build a working chart in four clicks, and it is the single highest-leverage thing to copy.

> **But make role schemas data, not code.** Custom graph templates ship their own object type name and their own author-named roles (`Shared Category`, `Shared Measure`, `Line Grouping`). The 78-object catalogue is a shipped default set, not a closed universe. If you hardcode role sets per chart class you will have to rewrite the layer the first time someone wants a custom template.

**2. Auto-fill the required measure.** Drop a category, get a bar chart counting rows. The object renders *immediately*, and the user edits from something rather than assembling from nothing. Every empty-state in the product follows the same instinct — objects draw example data before they have any.

**3. Descriptive undo on everything.** "Undo: Change Benchmark Country Selector from Russian Federation to China." Users explore fearlessly because every step is named and reversible. **Then unify the grammar** — the product has seven different sentence patterns for one operation family and the worst one is `Change option "fitLineType"`. One pattern: verb, item, role, object, new value.

---

### 2. Build order

#### P0 — the spine (nothing else works without it)
Data source → data items with a **label / physical-column split** → typed role schemas loaded as data → object instances → one query executor per data session → canvas layout → descriptive undo. Single-object reports end to end: bar, line, list table, crosstab.

#### P1 — the loop that makes it a product
Filters (object, page, report), the three-layer filtering model, controls as first-class filter sources, cross-object actions, and **one merged, inspectable filter stack per object** shown identically to author and reader. Page and report prompt bars.

#### P2 — the things users ask for on day two
Calculated items and an expression editor; display rules including banded ranges; ranks; totals and subtotals **recomputed from source rows at their own level**; export.

#### P3 — the differentiators
Geography items with a live validation panel; the geo layer stack; forecasting with scenario analysis and goal seeking; the statistical object family with model headers and `Model comparison`.

#### P4 — assistive, once the core is trustworthy
Suggestions, automatic chart selection, outlier insights, the report linter. **Do these last.** Every one of them in the subject product is actively misleading today, and an assistive feature that recommends nonsense costs more trust than it earns.

---

### 3. Patterns worth stealing outright

| Pattern | Where it appears | Why it matters |
|---|---|---|
| **Validate a mapping before committing it** | New Geography Item: `86% mapped`, *"1 of 1 unmapped values: England"*, live map preview | The single best interaction in the product. Apply it to every mapping step — geography, joins, custom categories, imports |
| **Disclose the population, always** | `Observations: 646K of 2.3M`, `Polylines: 72`, `Observations: 100 of 100` | Every object that drops, caps or truncates should say so in its header, in the same words |
| **Say when you invented something** | Path analysis: *"An artificial sequence order was generated for 6 paths that contains simultaneous events"* | Where the engine breaks a tie or fabricates ordering, tell the reader |
| **Colour the verdict** | Model comparison: winning model's bar in accent, loser's in grey | Make comparisons legible before a number is read |
| **Theme-aware basemaps** | Map service `Automatic` swaps to a High Contrast tileset under the high-contrast theme | Cheap, and the difference between an accessible map and an unusable one |
| **Classify sensitivity at the column and propagate it** | A PII badge on `City` inherited by the geography item derived from it | One classification, enforced down the derivation chain |
| **Split the reader's filter list by origin** | Viewer pane: `Permanent Filters` vs `Interactive Filters` | Readers can audit why they are seeing what they see |
| **Undo in the viewer** | *"Undo: Change Continent Selector from North America to Europe"* | Readers explore instead of rebuilding state by hand |
| **Self-documenting reports** | Overview page as table of contents; "View details about this page" opening a pop-up page | Needs no feature you won't already have |
| **Promote a model to the real workbench** | `Create pipeline → Add to new project` | Offer the seam on the object, not buried in a menu |

---

### 4. The seven failure patterns to design out

Seventy-six catalogued defects collapse into seven habits. Fix the habit, not the instance.

**1. Silent refusal.** A body drop the resolver can't place, a type-mismatched drop, a Hierarchy dialog whose OK does nothing, a pie "Other" of 101%, a forecast horizon of 0. Nothing happens and nothing is said. **Rule: every refusal states a reason, and every disabled control says which of its causes applies** — the subject has five distinct causes (no content, not saved, no permission, not in this deployment, nothing selected) behind one undifferentiated grey.

**2. Silent substitution.** Scatter becomes a heat map at 748K points; a layer switch discards an incompatible geography item; converting an object re-maps roles; `Frequency` is dropped from a correlation set. **Rule: never change what the user asked for without naming the change in the object.**

**3. Aggregation without semantics.** Everything defaults to Sum, including latitudes, years and identifiers. The suggestion engine's slot 1 is filled with the most *correlated* measure pair — which on any table with coordinates is a latitude pair, perfectly correlated and perfectly meaningless. **Rule: exclude coordinate, year, identifier and code columns from measure pools before any statistic is computed. Infer a safe default aggregation per column and warn before summing a non-additive one.**

**4. Undisclosed truncation.** 3,000-row caps behind a tiny ⓘ, 100-row word clouds, text objects that clip mid-sentence with no affordance, axis labels thinned to four of forty. **Rule: truncation is a first-class state with a visible explanation and a one-click alternative.**

**5. Inconsistent disclosure of the same fact.** The histogram states `Bin count (2-100)` in its label; the forecast horizon silently rejects 0 and 9999 with no range anywhere. Two objects fit the same two columns over populations differing by 1.7M rows without either saying so. **Rule: one disclosure vocabulary, applied everywhere.**

**6. Accessibility as an afterthought.** Canvas rendering with no data values in the DOM; suggestion cards as nameless `<canvas>`; selection state that vanishes when virtualised rows scroll away; two inconsistent naming rules for object accessible names; shortcuts disclosed only inside one pane. **Rule: every canvas object ships a real accessible representation, and the accessible name is generated by the same function that writes the title.**

**7. Non-determinism without recovery.** The suggestion engine returns a different set on every refresh — different columns *and* a different chart type for identical inputs — with no pinning, no history, and Refresh discarding what you had. **Rule: assistive output is reproducible and explainable, or it doesn't ship.**

---

### 5. Five decisions I'd make differently from the subject

1. **One chart-choosing resolver, not four.** The subject has a canvas auto-chart resolver, a Suggestions template rotation, a viewer "(recommended)" conversion ranking, and a multi-item drop resolver — and they disagree. Build one, call it from all four surfaces, and have it explain its choice.
2. **Addressable URLs.** The subject has a single route; no deep links, no browser history. Report, page, object and view mode should all be addressable — it costs little early and is near-impossible to retrofit.
3. **A reflow mode for the canvas.** Nothing in the subject ever stacks: at phone width the prompt strip scrolls sideways and the canvas keeps its absolute layout. Give authors absolute placement *and* a reflow mode, and let them choose per page.
4. **Merge the author's and reader's filter views.** The asymmetry — readers see the full filter stack, authors don't — is the strangest defect in the product. One model, two skins.
5. **Ship the statistics family early, not late.** The model objects are the subject's strongest work: a header stating event, fit statistic and population; sub-tabs for alternative views of one fit; `Model comparison` as a three-panel verdict. They are also where competitors are weakest.

---

### 6. Two things to explicitly not copy

- **The 78-object catalogue as a menu.** Users cannot choose between "Needle plot" and "Dot plot" from a list. Lead with the role assignment and let the resolver propose the form, with the catalogue as an override.
- **Assistive features that guess.** Suggestions, automatic charts and outlier insights are the subject's weakest surfaces precisely because they act without explaining. Either make them reproducible and accountable, or leave them out of v1 — a blank Suggestions pane costs nothing; a pane that confidently proposes summed latitudes costs credibility.

---

### 7. Where the evidence is thin

Treat these as unverified in the spec, not as gaps in the product: the Esri basemap catalogue (a consent gate I did not answer), five of six Machine Learning objects, `Create pipeline`'s output, export and sharing output, mid-drag visual feedback, custom geography provider authoring, and real device rendering. The bundle marks each one UNKNOWN rather than guessing, and that labelling is worth preserving as you build — it tells you which parts of the spec you can rely on and which you should re-check against the live product.


---

<!-- ===== Source: implementation-spec.md ===== -->

## Implementation Specification — for an AI coding agent

> **Evidence labels:** OBSERVED · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.
> **Evidence base:** nineteen hands-on sessions against `vfl-026.engage.sas.com` — fourteen in never-saved sandbox reports, and two (sessions 6 and 10) read-only in View mode on **saved, production, multi-page reports** built by report authors, nine reports in all. Nothing was saved, exported, shared, deleted or overwritten in any session, and no confirmation dialog was ever accepted. Section P alone is documentation rather than observation.


### APPLICATION ARCHITECTURE

#### Frontend

**Recommended architecture.** A single-page client with four separable layers, mirroring how the subject actually behaves:

```
┌──────────────────────────────────────────────────────────┐
│ Shell            banner · toolbar · rails · modal host    │
├──────────────────────────────────────────────────────────┤
│ Document         ReportDefinition (pages → objects →      │
│                  roles → filters/ranks/rules/actions)     │
│                  the single source of truth for authoring │
├──────────────────────────────────────────────────────────┤
│ Query engine     role assignment → QueryDefinition →      │
│                  job queue (one executor per source) →    │
│                  columnar results, cached per object      │
├──────────────────────────────────────────────────────────┤
│ Renderers        canvas chart renderer · canvas grid ·    │
│                  DOM controls · accessible table fallback │
└──────────────────────────────────────────────────────────┘
```

Keep the document free of results. The subject separates the report *definition* from the runtime data (DOCUMENTED: the vendor calls the definition artefact BIRD), and this is the single most important structural decision — it makes save, undo, templates and server-side rendering all tractable.

**Page structure.**

```
/                          shell
├── HomeView               folder tree · search · sort · card grid · New report
├── EditorView             the authoring surface
│   ├── LeftRail           Data · Objects · Outline · Suggestions · Review
│   ├── CanvasView         report-control strip · page tabs · page-control strip ·
│   │                      filter breadcrumb · object grid
│   └── RightRail          Options · Roles · Actions · Rules · Filters · Ranks
├── ViewerView             toolbar · page tabs · objects · optional side pane
└── ModalHost              one dialog at a time; stacking only for pickers
```

**Component hierarchy.** `App → Shell → (HomeView | EditorView | ViewerView) → Pane* → Section* → Control*`, with `ObjectFrame → Renderer` as the only branch that touches the query engine. The full component list is in `components.md`.

#### State

| Scope | Holds | Notes |
|---|---|---|
| **Global** | Current user, theme, open documents (multi-document switcher), notifications, feature flags | The subject keeps several reports open at once; model documents as a collection, not a singleton |
| **Document** | The whole `ReportDefinition`: pages, objects, roles, filters, ranks, rules, actions, controls, calculated items, parameters | Undo/redo is a stack of typed, labelled mutations over this tree — see Interaction requirements below |
| **Session / local** | Selection (object, marks), active pane per rail, pin state, expanded sections, maximized object, edit vs view mode | Selection must survive a mode switch (OBSERVED) |
| **Server** | Table metadata, column profiles, query results, saved reports, templates, common filters | Cache results per (object, query hash); invalidate on role, filter, rank or aggregation change |
| **Ephemeral** | In-flight jobs, toasts, dialog state, drag payload | Cancel in-flight jobs when a new one supersedes them for the same object |

**Autosave vs save.** The subject persists unsaved editor state server-side for crash recovery while keeping an explicit Save for the document itself (INFERRED — confidence: Medium-High, from a `POST` then `PATCH` to a files service and a "Restore previous session" affordance). Copy that split: recover work without silently publishing it.

#### Data Model

Entities and relationships are specified in `data-model.md`. The short form:

```
User → Report → Page → Object → RoleAssignment → DataItem
                 │        ├── Filter · Rank · DisplayRule
                 │        └── Action (ObjectLink | PageLink | ReportLink | UrlLink | ParameterLink)
                 ├── Control (report- or page-scoped)
                 ├── DataSource → DataItem (Category | Measure | AggregatedMeasure | Date |
                 │                Geography | Hierarchy | CustomCategory | CalculatedItem |
                 │                Parameter | Partition)
                 │       ├── DataView          (reusable item customizations)
                 │       └── DataSourceMapping (item ↔ item across sources)
                 ├── CommonFilter
                 └── Theme
```

#### Visualization

**Chart architecture.** One renderer per mark family (bar/column, line/step, point, area, arc, rect/heat, text, geo), not one per chart name. The subject exposes 78 object types but they collapse into far fewer mark families differing mainly by role schema and options — build the schema, not 78 components.

**Configuration model.** Every object is:

```jsonc
{
  "id": "obj-1",
  "type": "bar",
  "name": "Bar - Region 1",          // auto-derived from the first role item
  "title": { "mode": "automatic" },   // automatic | custom | none
  "roles": {                          // validated against the type's role schema
    "category": ["region"],
    "measure":  ["frequency"],
    "group":    []
  },
  "options": { "direction": "horizontal", "dataLabels": false },
  "filters": [], "ranks": [], "rules": [], "actions": [],
  "layout":  { "extendWidth": true, "shrinkWidth": true, "specifyHeight": false },
  "dataLimit": { "override": false, "rows": 3000 }
}
```

The **role schema** is the contract: each role declares `{ name, required, minItems, maxItems, acceptedTypes }`. `visualizations.md` gives the complete schema for all 78 types.

**Filter model.** Three layers, which the subject never unifies and a rebuild should:

```jsonc
{
  "effectiveFilters": [                 // computed, always inspectable
    { "source": "object",  "item": "promotionId", "op": "in", "values": ["Coupon"], "includeMissing": true },
    { "source": "control", "item": "department",  "op": "in", "values": ["kids"],   "controlId": "ctl-2" },
    { "source": "link",    "item": "region",      "op": "in", "values": ["ASIA"],   "fromObject": "obj-3" }
  ]
}
```

Every layer carries an explicit `includeMissing`, defaulting to `true`, and the merged list is what the UI shows. This single change fixes the subject's worst semantic inconsistency.

#### Routing

The subject has **one route** (OBSERVED) — nothing is addressable. Give the rebuild real routes:

| Route | Screen | Parameters | Required state |
|---|---|---|---|
| `/dashboard` | Home | `?tab=recent\|favorites\|shared\|trash` | Authenticated |
| `/projects` | Project list | `?q=&sort=&view=grid\|list` | Authenticated |
| `/projects/:projectId` | Project detail | — | Read on project |
| `/projects/:projectId/datasets` | Dataset list | `?q=` | Read on project |
| `/projects/:projectId/datasets/:datasetId` | Dataset explorer | `?column=` | Dataset loaded |
| `/projects/:projectId/datasets/new` | Import wizard | `?step=source\|map\|confirm` | Write on project |
| `/projects/:projectId/analytics` | Analytics home (reports + explorations) | `?q=&sort=&type=` | Read on project |
| `/projects/:projectId/analytics/new` | Start from dataset or template | `?dataset=&template=` | Write on project |
| `/projects/:projectId/analytics/:reportId` | **Report editor** | `?page=&object=&pane=options\|roles\|filters\|ranks\|rules\|actions` | Write on report |
| `/projects/:projectId/analytics/:reportId/view` | **Viewer** | `?page=&filters=<encoded>&popup=:pageId` | Read on report |
| `/projects/:projectId/analytics/:reportId/objects/:objectId` | Maximized object | `?pane=` | Report loaded |
| `/settings/*` | Account, theme, connections | — | Authenticated |

Two rules: create the report record on "New" so `:reportId` always exists (the subject's unsaved-document state is why so many commands sit greyed), and encode viewer filter state in the query string so a filtered view is shareable.

#### Reusable Components

Full inventory with states, inputs and interactions in `components.md`. Minimum set to build:

`AppBanner · Toolbar · IconRail · SidePane · PaneHeaderMenu · SearchField · DataItemRow · InlinePropertyEditor · ObjectLibraryList · Canvas · PageTabStrip · ObjectFrame · ChartRenderer · DataGrid · RoleGroup · TypeFilteredPicker · DualListPicker · FilterCard · RankCard · ControlWidget (dropdown | buttonbar | list | slider | textinput) · FilterBreadcrumb · PropertySection · Dropdown · ColorPicker · PlacementPicker · ExpressionEditor · ResultsPreviewGrid · Modal · Toast · Tooltip · HoverCard · ContextMenu · SeverityCounter · ThumbnailCard · AssistantPanel`

Not needed (the subject has none): breadcrumb navigation, pagination, command palette.

#### Interactions

Requirements, all traceable to observed behaviour (`interaction-model.md`):

1. Single click selects; **double-click drills** — never overload single click with navigation.
2. Right-click opens a context menu on objects, data items, page tabs and column headers.
3. Drag a data item onto an object, a role, the canvas or a control strip.
4. Hover reveals affordances (edit pencil, object ⋮, maximize) and data tips.
5. Every mutation is undoable with a **descriptive label** naming the object and the setting.
6. No mode switch or configuration change may destroy other configuration — the subject deletes manual links when automatic actions are enabled, and that is a bug to avoid.
7. Esc closes only the innermost layer.
8. Rejections are always explained; silent reverts are forbidden.
9. Truncation, tie caps and dropped rows are disclosed in the object, not in a 12px icon.
10. Keyboard: full tab order, a documented shortcut map, and an accessible table alternative for every canvas-rendered visual.

#### Responsive

Breakpoints observed in the subject's stylesheets: **768 / 992 / 1200**, plus a print stylesheet. Actual sub-desktop layouts were never observed (UNKNOWN).

| Range | Layout behaviour |
|---|---|
| ≥1200px | Full authoring: rail + left pane + canvas + right pane |
| 992–1199px | Collapse one pane to overlay; canvas keeps priority |
| 768–991px | Viewer-oriented: rails become sheets; editing degraded or blocked |
| <768px | **Read-only viewer only.** Stack objects one per row; controls become sheets |
| Print | Page-per-page layout; honour the report's fixed-size setting |

Author-controlled sizing is part of the model, not just CSS: per-object specify/extend/shrink width and height, page-level "avoid scrollbars", report-level fixed size, and an absolute-positioning container. Reproduce these as document properties.

#### Design System

Tokens and component metrics in `design-system.md`. The system in one paragraph: dense and flat, one saturated brand colour used only for the banner and links, near-black text, **2px radii**, hairline 1px borders instead of shadows, grey surfaces separating rails from canvas, a 6+ colour mid-saturation categorical palette, and dedicated palette slots for **missing** and **other** values. Build tokens as `--color-*`, `--space-*`, `--radius-*`, `--font-*`; ship light, dark and high-contrast themes from day one, since the subject's theme switch is report-level and users expect it.

---

### Implementation Priority

| Priority | Scope | Contents |
|---|---|---|
| **P0** | Core application | Shell (banner, toolbar, rails, modal host) · document model + undo/redo · data source loading with column classification · object insert with placeholder rendering · role schema + type-filtered pickers · query engine (executor, job queue, cached columnar results) · bar/line/pie/table renderers · save, close-with-confirmation, single-document routing |
| **P1** | Main analytics workflow | Options/Roles/Filters/Ranks panes · object filters with an explicit unified missing-value policy · Top/Bottom N in true rank order · aggregation menu with a safe default per column type · crosstab with source-level totals and subtotals · pages, page types, page tabs · viewer mode with an accessible table fallback · addressable routes for report/page/object/mode |
| **P2** | Advanced visualization | Remaining mark families and the full 78-type role catalogue · geo maps with the provider/lat-long prerequisite surfaced in the picker · calculated items and the expression editor with edit-time validation · custom categories, hierarchies, parameters · display rules · cell visualizations · data labels, axis and legend options |
| **P3** | Secondary features | Controls/prompts at report, page and body scope · object/page/report/URL links and cross-filter modes · filter breadcrumb · page templates · common filters · data views and data-source mapping · export (PDF, package) · comments and sharing · report linter with quick fixes |
| **P4** | Polish | Auto chart-type inference · suggestion engine filtered by column semantics · AI assistant · insights and outlier detection · forecasting and statistical/ML objects · playback/slideshow · localization · PWA and a separate mobile viewer |

**Sequencing note.** P0 and P1 together deliver the product's actual value proposition — a person who cannot write a query builds a correct, filtered, cross-linked report. Everything in P2–P4 is breadth. The subject's own weaknesses cluster in P1 semantics (missing values, totals, ranks, aggregation defaults), so that is where the rebuild earns its advantage.

---

### Traceability

Every requirement above is traceable to observed behaviour:

| Requirement | Evidence | Where documented |
|---|---|---|
| Role schema per object type | 78 objects' role tables read from the Roles pane | `visualizations.md` §G.1 |
| Query engine shape | Network observation: one executor, jobs with incrementing sequence, CSV + string-index results | below, "Observed query protocol" |
| Canvas rendering | DOM and accessibility-tree queries return no cell text; a single `<canvas>` carries the pixels | `components.md`, `interaction-model.md` |
| Single route | URL unchanged across every navigation | `application-map.md` §K |
| Design tokens | Live computed styles and sampled canvas pixels | `design-system.md` §L |
| Filter semantics | Four different missing-value behaviours reproduced in the app | `interaction-model.md` §H.6 |
| Totals correctness | Independent crosstab reproduced the subtotal values exactly | `visualizations.md` §G.2 |
| Every defect in the fix list | Reproduced in the running app | below, "Defects to fix" |

---

### Supporting detail (observed behaviour behind the requirements above)

#### Observed query protocol (OBSERVED at the network layer; no credentials or tokens recorded)

**Query protocol (OBSERVED at the network layer, no credentials or tokens recorded):**
- One **executor** is created per data session: `POST /reportData/executors` → 201.
- Every object's query is a **job** posted to that executor: `POST /reportData/jobs?indexStrings=true&embeddedData=true|limited&executorId=<id>&wait=30&jobId=<executorId>_c<N>&sequence=<n>&dataDefinitions=dd<N>` → 201. `wait=30` indicates long-polling.
- Results are fetched as files: `GET /reportData/results/<jobId>/files/dd<N>.csv` and a companion `dd<N>index.csv` (string index — consistent with `indexStrings=true` dictionary-encoding category values).
- Supporting services observed: `/dataTables/dataSources/{source}/tables/{table}` and `/casManagement/…` (table metadata), `/visualAnalyticsAdministration/defaultReportDataViews?filter=eq(dataTableUri,…)`, `/catalog/instances?filter=eq(resourceId,…)` (asset catalogue), `/annotations/annotations?resourceUri=…`, `/folders/folders/@myHistory/histories` (recently used), `/notifications/notifications?…`, `/files/files` (`POST` then `PATCH` — **INFERRED: unsaved-state autosave powering session recovery, confidence: Medium-High**).
- Auth is per-service silent OAuth: a first call returns an auth challenge, the client is bounced through `/SASLogon/oauth/authorize?client_id=sas.<service>` and the call is retried. **Do not replicate this pattern** — use one session token across your services.

**Build it as:** a single-page client with a **query engine per data source**, a **job queue with sequence numbers**, **columnar/dictionary-encoded result transport**, and **canvas-rendered charts and grids**. Charts and data grids alike are drawn to `<canvas>`: DOM and accessibility-tree queries for cell text return nothing, while a single `<canvas>` element carries the rendered pixels (**OBSERVED** by DOM inspection; the performance motive is **INFERRED — confidence: High**). The cost is that no cell text exists in the DOM, so pair canvas rendering with an accessible table or ARIA summary, which the subject lacks.

#### Build order (superseded by the P0–P4 table above; kept for rationale)
1. **Data layer** — table metadata, column classification (category/measure/date), distinct counts, aggregation engine, row caps.
2. **Object model** — object types with typed role schemas; the role schema *is* the product's contract (Section G.1 is a complete specification of 78 of them).
3. **Canvas and pages** — layout with extend/shrink flags, page types, templates.
4. **Property panes** — Options / Roles / Filters / Ranks / Rules / Actions, each scoped by selection.
5. **Interaction layer** — controls, links, modes, breadcrumb.
6. **Authoring aids** — expression editor, calculated items, custom categories, hierarchies.
7. **Viewer** — read-only mode, side pane, drill, export.
8. **Assistive** — suggestions, review/lint, AI panel.

#### Patterns to copy (these are the product's real strengths)
1. **Typed role assignment with filtered pickers** — the user cannot put a date on a measure axis. Single-item roles grey out once filled.
2. **Auto-fill the required measure with a row count** so an object renders the moment a category is dropped.
3. **Descriptive undo labels** naming the object and the option changed.
4. **Non-additive-safe totals** — always recompute totals and subtotals from source rows at their own level, never from displayed cells. Verified for averages on both axes, and for a distinct-count grand total on a single-level crosstab.
5. **Models that disclose dropped rows** ("646K of 2.3M").
6. **Viewer-visible filter logic** (`… OR Missing(x)`), so readers can audit what they are seeing.
7. **A dedicated "Missing" colour and an "Other" colour** in the theme.
8. **A lint pane** that flags unused data sources, accessibility and performance issues with one-click fixes.
9. **Objects render placeholder sample data** before configuration, so the canvas is never blank and empty.
10. **Object names that follow their data** ("Bar 1" → "Bar - Region 1").
11. **Viewer-side filter disclosure, split by origin** — the reader's pane separates `Permanent Filters` (built into the report) from `Interactive Filters` (arriving from controls, links and selections), each written out in full. Readers can audit exactly why they are seeing what they are seeing. Copy this, then fix the asymmetry by giving the author the same view.
12. **Undo extended to the viewer**, with the same descriptive labels — "Undo: Change Continent Selector from North America to Europe". Readers can step back through their own exploration instead of rebuilding a filter state by hand. Most BI viewers do not offer this.
13. **Self-documenting reports** — the production report carried an overview page acting as a table of contents with page links, and every analysis page had a "View details about this page" text link opening a **pop-up page** that explained the page's contents. This needs no feature a rebuild wouldn't already have (text objects, page links, pop-up page type), and it is the difference between a dashboard and a readable one.
14. **Proactive outlier disclosure for readers** — a viewer-side "View insights" surface that runs on demand, reports *"One or more objects is impacted by outliers"*, and quantifies the impact per group (`Outdoors: 56.22%, including $1,687,084.95 vs excluding $738,539.67`). Most BI tools let a reader stare at an outlier-driven average with no hint. Copy the idea; fix the execution (defects 42, 43).
15. **Disclosing fabricated ordering** — the path object states *"An artificial sequence order was generated for 6 paths that contains simultaneous events."* Whenever the engine has to break a tie or invent an order, say so in the object.
16. **Role schemas as data** — custom graph templates ship their own object type name and their own **author-named roles** ("Shared Category", "Shared Measure", "Line Grouping"). Build the role system so a template can declare a schema; do not hardcode role sets per chart class.
17. **What-if in the viewer, not just the studio** — scenario analysis and goal seeking on a forecast, with per-factor reset and per-factor solver bounds, available to a reader without an edit right.
18. **Validate a mapping before committing it** — the New Geography Item dialog reports `N% mapped`, previews the result on a map, and **names the values that failed** (`England` against ISO country names) while you are still configuring. The same notice reappears on the rendered object. Every mapping step in a rebuild — geography, joins, custom categories — should show its match rate and its failures before the user presses OK.
19. **Theme-aware basemaps** — the *Automatic* map service swaps in a High Contrast tileset when the high-contrast theme is active. Cheap to reproduce, and it is the difference between an accessible map and an unusable one.
20. **Classify sensitivity once, at the column, and propagate it** — a quasi-identifier badge on `City` was inherited by the geography item derived from it, with a plain-language explanation on hover.

#### Defects to fix (observed failure modes, each a product opportunity)
| # | Observed behaviour | Required behaviour in the rebuild |
|---|---|---|
| 1 | Every measure defaults to **Sum**, including ages, latitudes and years, with no warning | Infer a safe default per column (Average or Count for bounded/identifier-like numerics); warn before summing a non-additive column |
| 2 | Missing values handled four different ways across filters, list controls, sliders and groupings; a **full-range slider silently drops them** | One explicit, consistent missing-values policy surfaced identically in every filtering surface, defaulting to *include* and always visible |
| 3 | Row caps (3,000 / 100) disclosed only by a tiny ⓘ | Prominent, explained truncation with a one-click "rank top N instead" |
| 4 | Data-limit override accepted 999,999,999 and **froze the browser** | Hard ceiling with validation and a cancellable query |
| 5 | Ranked results render **alphabetically**, not in rank order; rank count 0 accepted silently | Sort by rank; reject 0 with a message |
| 6 | Ties capped at count + 100 with an opaque notice | State the true tie count and offer to include all |
| 7 | Year-to-date anchored to **today's calendar date**, silently understating historical years | Anchor period-to-date to the data's own period, or make the anchor an explicit, labelled choice |
| 8 | Partial periods compared to full periods with no flag | Mark incomplete periods in the visual and the tooltip |
| 9 | No relative date filters anywhere | First-class relative ranges in filters and controls |
| 10 | Enabling automatic actions **deletes manual links**; disabling doesn't restore them | Never destroy configuration to change a mode; make modes additive and reversible |
| 11 | Filters from controls and links are invisible in the **editor's** Filters pane — though the **viewer's** pane does disclose them, split into Permanent and Interactive. The disclosure is backwards: the person configuring the report is the one kept in the dark | One merged, inspectable filter stack per object, identical in authoring and consumption |
| 12 | Text input prompt is exact and case-sensitive despite offering prefix suggestions | Match what the autocomplete implies; offer contains/starts-with |
| 13 | Single click highlights but does not select in template and list dialogs | Single click selects |
| 14 | **Esc inside a dropdown closes the whole dialog and discards the work** | Esc closes only the innermost layer |
| 15 | Silent rejections (pie "Other" 101%, forecast horizon 0/9999, Hierarchy OK with no name, Geography OK with no provider) | Always explain a refusal |
| 16 | Display rule with no colour accepted and does nothing | Require a visual effect or warn |
| 17 | Duplicate data-item names accepted silently | Warn and disambiguate |
| 18 | Converting an object to an incompatible type silently re-maps roles (a date became a *Color*) | Preview the mapping and require confirmation |
| 19 | Suggestions propose meaningless charts (summed latitudes, summed years). **Mechanism established (sessions 11–12):** slot 1 of the template rotation is filled with the table’s **most strongly correlated measure pair** — `Country_Lat`/`State_Lat` on one table, `Cost`/`Retail Price` on another. Correlation is a reasonable generator; it is computed **with no semantic veto**, so on any table carrying coordinates the coordinate pair wins every time | **Exclude latitude, longitude, year, identifier and code columns from the measure pool before correlation is computed.** Re-ranking afterwards does not fix it |
| 20 | Object library scrolls back to the top after every insert; search text persists across dialogs. (A separate, **intermittent** input defect drops the letters "e" and "g" in the Data pane filter — seen in session 2, did not reproduce in session 8) | Preserve scroll position; scope search state; fix the input handler |
| 21 | Two-way filter mode makes a list control filter itself to one value | Exclude a control from its own filter scope |
| 22 | Clicking the "All Other" bar clears the filter instead of filtering to its members | Filter to the bundled members |
| 23 | Everything renders to canvas with no accessible equivalent; no keyboard shortcut surface | Provide an accessible table view, ARIA summaries and a documented, discoverable shortcut map |
| 24 | Single route; no deep links, no browser history | Addressable routes for report, page, object and view mode |
| 25 | Fonts inconsistent by default (report font vs crosstab rule font) | One type system |
| 26 | Applying a lattice silently re-sorts a chart from value order to alphabetical | Preserve sort across reconfiguration, or announce the change |
| 27 | Containers accept objects only by drag; double-click appends to the page instead, with no affordance explaining it | Support both, and show a drop target |
| 28 | Reference lines accept only a constant or a parameter — no mean, median or percentile | Offer statistical reference lines |
| 29 | Disabled menu items never say why, and there are **four** different reasons. *Content* (an empty report greys almost everything), *save* (About this report needs stored metadata), *permission* (on a course report owned by someone else, Save a copy and Copy link were greyed) and *deployment* — **Share report is greyed on the account's own saved report too**, where Save a copy, Copy link and Copy embeddable markup are all enabled, so that capability is switched off for the whole deployment | Give every disabled control a reason, and distinguish "not yet" from "not yours" from "not here" |
| 30 | Objects expose an accessible name and role (`role="application"`) but **no data values** in the DOM or accessibility tree | Pair every canvas object with a real accessible representation and publish a keyboard map |
| 31 | A shared axis across measures of different magnitudes renders one series as invisible slivers, with no warning | Detect incompatible magnitudes; refuse, warn, or offer a log scale |
| 32 | A custom sort is invisible from the object, applies only when sorting by that category, and silently sends unlisted members to alphabetical order | Name the custom order in the sort menu and state the fallback |
| 33 | Changing an axis-range setting inverted the category order and reverting did not restore it (observed once) | Treat ordering as explicit state that survives unrelated setting changes |
| 34 | The automatic chart ignores cardinality — a 748K-distinct identifier column becomes an unreadable bar chart capped at 3,000 rows | Resolve on classification **and** cardinality **and** column semantics; rank, bucket or refuse, and explain the choice |
| 35 | **Four** chart-choosing code paths coexist and disagree: the canvas auto-chart resolver (deterministic, session 9), the Suggest pane (**not a resolver at all — a randomised template rotation**, session 11), the viewer’s "Change \<type\> to" **(recommended)** marker (session 10), and the Suggest pane’s own slot-to-type mapping. The naive one sits on the primary gesture | One resolver, consistently applied, and one explanation of why it chose what it chose |
| 36 | Text objects **clip without any indication** — a production overview page stopped mid-sentence ("…and sales representatives to"). The full text is in the DOM; there is no scrollbar, ellipsis or overflow affordance, so a reader cannot tell text is missing | Detect overflow; show an affordance and make the object scrollable or auto-fit |
| 37 | Cross-filtering has **no page-level disclosure** — clicking a treemap tile re-filtered three objects and rescaled their axes, with a thin border on the clicked tile as the only on-canvas evidence (the filter breadcrumb is opt-in and was off). A reader arriving mid-session cannot tell the page is filtered | Always show active interactive filters at page level, with a one-click clear |
| 38 | **Axis label thinning hides most categories** — roughly 40 bars rendered with four labelled; the rest are unidentifiable without hovering | Rotate, wrap, or switch orientation before dropping labels; never thin below a readable minimum without saying so |
| 39 | **A virtualised list silently drops most of its rows.** The favorites grid declares `aria-rowcount=97`, reserves the full scroll height, renders placeholder rows for all of them — and **never loads past 70**. Two passes over the same list returned partially disjoint sets | Load what you declare; render an explicit loading state in the row rather than a blank that reads as data |
| 40 | **Content search ignores the identifier people actually use.** `160_151` returns a relevance-ranked list of unrelated reports; `210_111` returns the entire library as if it were a result set; the words `Color-Mapped` find it instantly. Digit/underscore tokens are dropped and the query degrades to "everything" | Match literal substrings of the name; never return a full listing as a result set; say when a query matched nothing |
| 41 | **Text inputs drop specific printable characters.** In the Open dialog's search box, `Analyzing a Forecast` became `aAnalyinaForcast`; `Forecast` became `Forcast` three times running, including when **e** was sent as its own discrete key press; a stray leading `a` was prepended each time; and a second entry appended instead of replacing (`Network AnalysisNtwork An`). Logged as intermittent in session 2; **reproducible** here | Fix the input handler; never let a shortcut layer swallow printable characters |
| 42 | **A generated insight ships an unfilled authoring placeholder to the reader.** Under the heading *"What are the Details of these Outliers?"* the Outliers dialog renders the literal string `<Double-click to enter text here>` | Never render an unbound template slot; omit the section or fill it |
| 43 | **A generated table mixes formatted and raw numbers.** In the same dialog, *Including/Excluding Outliers* are currency-formatted (`$429,751.38`) while *Difference* is raw (`425537.045`) | One format resolution for every numeric column in generated output |
| 44 | **Accessible names are inconsistent between object types.** Side by side: *"+/- vs Benchmark by Customer Country, Bar chart"* and *"List table - Customer Country 1"* — the second is the internal object name, with no data description and no type suffix | One naming rule — description plus type — for every object |
| 45 | **A colour-mapped display rule is invisible in the Display Rules pane.** A report built to demonstrate one shows visibly mapped, consistent colours across three objects while the viewer's Display Rules pane shows an empty `Report` scope | List every rule that affects rendering, value-to-colour mappings included, in the pane named after them |
| 46 | **Narrow layouts scroll sideways instead of stacking.** At ~405px effective width the report prompt strip scrolls horizontally, the banner title truncates, and the canvas keeps its absolute layout unchanged | Stack the prompt bar, wrap the button bar, give the canvas a reflow mode |
| 47 | **A forecast silently discards assigned factors.** Two underlying factors were assigned; only one appears as a panel, in Reset and in Bounds. The model's selection is never stated | Name the factors used and the ones dropped, with the reason |
| 48 | **The empty Suggestions pane says nothing** — a disabled combobox, two disabled icons and blank space, while the Data pane beside it says *"To begin, add or import data."* | Every pane states what it needs and what it will do |
| 49 | **Suggestion cards are invisible to assistive technology.** Each is a `<canvas>` inside `role="application"` with an **empty `aria-label`** — a nameless application region with no chart type, no caption, no data items. Report objects at least carry a descriptive name | Give every card an accessible name stating type and data items; offer a text list view |
| 50 | **Dismissing a suggestion is irreversible and silent.** Right-click ▸ Delete removes the card with no toast and **no undo entry** — the undo label still reads the previous action | Make dismissal undoable, and remember it so the suggestion is not re-offered |
| 51 | **The suggestion engine re-suggests what is already on the page.** Three consecutive Refreshes re-offered `Department by Frequency` after it had been inserted. The vendor guide claims the opposite (§P.3) | Exclude or demote charts already present |
| 52 | **Suggestions ignore the user’s selection.** With `Brand Name` selected in the Data pane, ten generated suggestions used it zero times | Bias suggestions toward the selection — that is the moment the user is asking a question |
| 53 | **Suggestion generation is non-deterministic with no way back, and the randomness reaches the chart type.** Seven Refreshes on unchanged inputs gave seven different column sets; separately, the same category and measure pair produced **Butterfly, Dual axis bar and Dual axis bar-line on different attempts** (13 samples, three categories each yielding two types). Refresh discards the current list, and there is no pinning or history | Make generation reproducible and the encoding choice explainable; let the user pin and return to a batch |
| 54 | **A suggestion card and the object it creates use opposite naming grammars.** `Department by Frequency` → object titled `Frequency of Department`; `MDY, Country_Lat by State_Lat` → `Country_Lat, State_Lat by MDY` | One naming function shared by the card, the object title and the accessible name |
| 55 | **A caption names a role the object does not use.** `ChannelType, Year by Category` produced a word cloud with an empty Color role, and `Category` is not a column in the table but the Data pane’s group heading | Captions describe only what the object will contain |
| 56 | **A suggestion that renders nothing is still offered.** `Transaction Date/Time by 12 week RFM Bucket` drew both axis titles and no marks | Validate the query before showing the card |
| 57 | **Batch size is undisclosed and variable** (4 or 5), and "Add more suggestions" never says how many remain or whether the well is dry | State the count; disable the control when exhausted |
| 58 | **A body drop is silently ignored when the resolver's preferred role is full, even though an empty compatible role exists.** The same item dropped on the role slot is accepted immediately | Fall through to the next compatible empty role, or refuse with a reason and highlight the eligible targets |
| 59 | **Scatter is substituted for a heat map or a correlation matrix without disclosure, and the undo entry names the object that was *not* created** — three of four multi-measure drops | Disclose the substitution in the object ("binned: 748K points"); write the undo entry from the object that exists |
| 60 | **`Frequency` is silently dropped from a correlation set** — five selected measures produced a four-measure matrix with no note | Name the items excluded and why |
| 61 | **Two categories plus a measure produce a List table that demotes the measure to a plain column**, with no indication a chart was possible | Offer the chart alternative, or state why a table was chosen |
| 62 | **Data-pane selection is invisible to assistive technology once scrolled.** `aria-selected` lives only on rendered rows in the virtualised list, so a live three-item selection can report as zero | Maintain an accessible selection summary independent of virtualisation |
| 63 | **Six different undo grammars for one operation family** (`interaction-model.md` §H.3b) | One sentence pattern: verb, item, role, object |
| 64 | **Switching a map's layer type silently discards an incompatible Geography assignment**, leaving a blank object and no message — lat/long → Region and lookup → Line both verified | Refuse the switch with a reason, or offer to convert the geography item; never delete a required role silently |
| 65 | **A geography item whose provider is unavailable takes its whole object down silently** — the object renders nothing, is absent from the accessibility tree, and its roles cannot be inspected even in the viewer pane | Render a named error placeholder stating the missing provider |
| 66 | **`Based on` in the New Geography Item dialog is not type-filtered** — all 57 columns including measures and dates, in the same dialog whose lat/long pickers *are* filtered. Choosing a measure yields `0% mapped` and a list of integers | Apply the product's own typed-picker discipline consistently |
| 67 | **Selecting a Custom coordinate space reports "Invalid value" before anything has been typed** | Do not mark an untouched required field invalid; show the syntax example as help text |
| 68 | **The geography-provider authoring commands (New / Edit / Delete provider) are greyed with no explanation** — a fifth distinct cause of greying alongside content, save, permission and deployment | Say which cause applies |
| 69 | **Model comparison's "No Comparable Models" modal re-fires on every selection** and blocks the properties pane, so the object can be deleted but never inspected or configured. Its content is good — four named, checkable conditions | State the precondition **in** the object's placeholder; never re-raise an informational dialog on selection |
| 70 | **Box plots hide outliers by default** — computed but not drawn, with nothing on the object saying so — and the `Ignore` vs `Hide` distinction (excluded from the statistics vs merely not drawn) is never explained | Show outliers by default; label the three modes by what they do to the statistics |
| 71 | **Option-change undo entries expose raw internal option keys** (`Change option "fitLineType"`) and drop the object name and the new value | Name the setting in the user's words, plus the object and the new value |
| 72 | **Four effect roles each carry a required asterisk on the regression objects while only one need be filled** | Use a distinct marker for "one of these", and say which are still outstanding |
| 73 | **Numeric limits are disclosed inconsistently** — the histogram states `Bin count (2-100)` in its label while the forecast horizon silently rejects 0 and 9999 with no range shown (defect 15) | State every numeric range in the control |
| 74 | **A scatter plot offers no fit line by default** and the setting sits four sections down the Options pane | Offer the fit line where the chart is |
| 75 | **Two objects on one page fit the same two columns over different populations without saying so** — Cluster used 646K of 2.3M rows, Decision tree and Forest used all 2.3M | State the missing-value policy per object, and warn when two objects on a page disagree about the population |
| 76 | **The Model comparison dialog shows Data, Response and Event level as bare labels** with no indication they are inherited from the candidate models and cannot be changed | Say where a fixed value came from |
| 77 | **A 63.4 MB client payload** — 45.5 MB of JavaScript in 135 files plus a 12.9 MB WebAssembly rendering engine, all before a single query | Budget the initial bundle (≤ 2 MB JS); lazy-load the renderer on first object and analytics chunks on demand |
| 78 | **HTTP `449` used as a retry signal** on data-session creation — a non-standard status a compliant client may abandon on | `409 Conflict` or `503` with `Retry-After` |
| 79 | **A chatty job stream** — one job per object per change, a client counter past `c430` in one session, many jobs producing no fetched result | Batch a page's queries into one request; coalesce changes within a frame |
| 80 | **`limit=32767` on a collection fetch** instead of paging | Page every collection; make page size a server concern |
| 81 | **2.7 MB of localization bundles loaded up front** for a single locale | One locale, split by route |
| 82 | **Promoting a model hijacks the tab and crashes the destination.** *Create pipeline → Add to new project* replaced the Visual Analytics session with Model Studio, which rendered *"The application has encountered a serious error and must be reloaded."* — the project had been created, and one Reload recovered it | Open the destination in a new tab; never replace unsaved authoring context; do not ship a handoff whose landing page fails |
| 83 | **The model handoff loses the predictor set** — `Customer Age`, an assigned predictor in the source object, arrived **Rejected** in the generated pipeline | Carry every role assignment across, and report anything the destination cannot represent |
| 84 | **Two missing-value policies across the model family, never disclosed** — Cluster and Bayesian network use 646K of 2.3M rows while Decision tree, Forest and Gradient boosting use all 2.3M (strengthens defect 75 from two objects to five) | State the policy per object and warn when two objects on a page disagree about the population |

> **See also `PLATFORM_BLUEPRINT.md`** — the full-stack engineering design (data plane, semantic layer with semantic typing, query protocol, document service, dual-path rendering, client, platform services, security, and a five-phase build plan), and **`observed-architecture.md`** for the raw runtime and network evidence behind it.
>
> **See also `RECOMMENDATIONS.md`** — the judgement layer on top of this spec: the three ideas the product actually rests on, a P0–P4 build order, ten patterns worth copying outright, the seven failure habits behind all 76 defects, five decisions to make differently, and two things not to copy.

#### Terminology map (avoid vendor-flavoured names)
| Subject term | Neutral equivalent |
|---|---|
| Crosstab | Pivot table |
| Key value | KPI tile |
| Data roles | Field wells / encodings |
| Display rules | Conditional formatting |
| Lattice rows/columns | Small multiples / trellis |
| Data tip values | Tooltip fields |
| Report Review | Report linter |
| Automatic actions | Cross-filtering mode |
| Common filter | Shared filter |
| Objects With Data | Saved component |

#### Acceptance criteria (verifiable against this document)
1. A user can go from an empty report to a rendered, filtered, cross-linked two-page report **without writing a query** (Journey J1).
2. Every object type declares a role schema; pickers offer only type-compatible columns; required roles are enforced (Section G.1).
3. Totals, subtotals and "other" buckets are recomputed from source rows at their own level — proven for Average on both axes, and for a distinct-count grand total (Section G.2).
4. Missing values behave identically in every filtering surface and are always disclosed (Defect 2).
5. Truncation, tie caps and dropped rows are always visible and explained (Defects 3, 6; Strength 5).
6. Undo covers every configuration change with a descriptive label, and no mode switch destroys configuration (Strength 3, Defect 10).
7. Report, page, object and mode are addressable by URL (Defect 24).
8. The viewer is keyboard-navigable and exposes an accessible equivalent of every canvas-rendered visual (Defects 23, 49).
9. No suggestion, automatic chart or conversion recommendation is ever produced by a code path other than the single resolver, and each one can state why it was chosen (Defects 19, 35, 53).
10. Every destructive or dismissive action — including dismissing a suggestion — produces a descriptive, reversible undo entry (Defects 10, 50).

---

### P. Cross-check against vendor training material

**Source:** a user-supplied structured guide derived from the vendor's own training course (EYVA152, *SAS Visual Analytics 1 for SAS Viya: Basics*, stated release LTS 2025.09). **This is documentation, not observation.** Sections A–O were produced under a no-documentation rule; nothing below has been re-verified in the running app, and the training release differs from the observed deployment. Claims from it are labelled **DOCUMENTED**. Where the two disagree, the observed behaviour in Sections A–O governs, because it came from the build in front of us.

#### P.1 Where the documentation confirms what was observed
| Observed (A–O) | Documented corroboration |
|---|---|
| Landing page with folder list, search, Tile/Table (grid/list) toggle, "New report", session recovery | Home page described as the launch point with the same folders, faceted search, Tile/Table views, New Report and **Restore Previous Session** |
| Left rail: Data, Objects, Outline, Suggestions, Report Review | Same five, named **Suggest** and **Review** |
| Right rail: Options, Data Roles, Actions, Display Rules, Filters, Ranks | Same six, named **Roles** and **Rules** |
| Panes pin/unpin, auto-collapse, overflow ⋮ menus, collapsible prompt strips | Same interaction model described explicitly |
| Role-based configuration with required vs optional roles, assignable via "Assign data" or the Roles pane | Same, and the guide draws the same conclusion for implementers: keep a structured role schema rather than a bespoke form per chart |
| Client renders the visuals; the server returns structured data | Stated as the architectural split: the analytic engine returns structured results, the browser renders — consistent with the observed CSV-result transport and canvas rendering |
| Common filters are reusable across objects | Adds that a common filter is **tied to its data source** and can be applied to any object using that source **even if the object has none of those items in its roles** |
| Four measures produce a correlation matrix | **Reproduces on the drop path (OBSERVED, session 13):** four measures dragged together onto an empty canvas build a Correlation matrix; 2–3 build a heat map. A session-9 note that this "did not reproduce" was testing the single-item automatic-chart path and was stated too broadly |
| Suggestions can be statistically poor | Explains the engine: suggestions are driven by **cardinality and measure correlations**, and items already used are not reused in newly generated suggestions. **Split verdict after re-testing on a second table (OBSERVED, sessions 11–12).** The **correlation** half is *supported*: slot 1 of the template rotation is filled with the table’s most strongly correlated measure pair — `Country_Lat`/`State_Lat` on `RETAILDEMO_2`, `Cost`/`Retail Price` on `PRODUCTS` — and column position is ruled out. The **reuse** half *fails*: `Department by Frequency` was re-offered in three consecutive Refreshes after being inserted (defect 51). The **cardinality** half is *undetermined*: the favoured category was `Department` (6) on one table and `Product Category` (12) on the other, neither the lowest nor the highest. A session-11 note recording that both claims failed was too broad and is superseded here |

#### P.2 New facts that resolve items previously marked UNKNOWN
| Previously UNKNOWN | DOCUMENTED answer | Consequence for the rebuild |
|---|---|---|
| Saved-report persistence format | The report **definition** is a separate artefact from the runtime result — the vendor calls it **BIRD** (Business Intelligence Report Definition) and treats it as the recipe the browser renders, with query results embedded into it | Confirms the Section O.1 split. Model the document as `ReportDefinition` JSON (pages → objects → roles → filters/actions) and keep results entirely out of it |
| What "data views" are | A reusable, shareable set of data-item customizations bound to a data source — explicitly **not** a database view | Add a `DataView` entity: classification, format, aggregation and naming overrides that travel with the source across reports |
| What "Map data" does | **Data-source mapping** connects corresponding items across two sources so one action can filter both; mapped items' **formats must match** | Add `DataSourceMapping` (source item ↔ target item) and validate format compatibility at mapping time |
| Whether a tablet/phone layout exists | Consumption is via browser, an installable **PWA**, and a separate **mobile app** with its own discovery/connection flow | Section M's recommendation stands and is strengthened: build a desktop authoring surface and a distinct mobile viewer, rather than reflowing the editor |
| Why the Geography role offered nothing | Geographic items need either latitude/longitude columns or a **geographic data provider**; custom polygon shapes require a provider, and defining providers is permission-gated | The empty picker was a missing prerequisite, not a bug. In a rebuild, say so in the picker and link to the fix |
| How the automatic chart picks a type | Documented as "number and type of items". **Session 9 derived the actual table by experiment** (see `visualizations.md`); the guide's four-measures→correlation-matrix example did not reproduce | Resolve on classification, cardinality and column semantics; show the user why it chose what it chose |
| Source-table viewing limits | Viewing a source table is restricted past roughly **150K rows, 10K columns or 5M cells**, with a message when exceeded; viewing/editing are permission-gated capabilities | Set explicit, stated limits for any raw-data browser instead of silent truncation |
| Rank count flexibility | The rank count **can be a numeric parameter**, enabling e.g. a rolling window driven by a control | Makes the Section O.4 #5 fix cheaper: parameterised counts plus correct rank ordering |
| Custom-category intervals | A "generate groups" action divides values into equal groups; interval bounds are **manually entered and cannot be dynamic** | Offer both: auto-binning *and* data-driven bounds, which the subject lacks |
| Nested aggregation rules | Nested aggregations are constrained except through a dedicated table-aggregation mechanism | Matches the observed `AggregateTable` / `AggregateCells` / `Table` functions; design the expression grammar to reject nesting with a clear message |

#### P.3 Divergences and cautions
1. **Different build.** The guide targets LTS 2025.09; the observed deployment is a "Viya for Learners" environment whose pane labels differ slightly ("Suggestions" / "Report Review" vs "Suggest" / "Review"). Treat documented specifics as version-dependent.
2. **Documentation describes intent; observation captured behaviour.** The guide does not mention any of the 25 defects in Section O.4 — the Sum-by-default hazard, the four inconsistent missing-value policies, the `ToToday` year-to-date anchoring, ranks rendering alphabetically, or automatic actions deleting manual links. A rebuild driven only by the documentation would reproduce those faults.
3. **Page ranges in the guide's lesson index are unreliable** by its own admission, and several lessons resolved to no range, so it is not a complete map of the course.
4. **Copyright:** the guide quotes vendor slide notes verbatim in places. Those passages are the vendor's text — use the *facts* in a rebuild, not the wording, and do not carry that material into shipped documentation.

#### P.4 Net effect on this specification
Sections A–O are unchanged in substance. The documentation adds **four entities** (`DataView`, `DataSourceMapping`, a first-class `ReportDefinition` artefact, and the geographic-provider concept) and **one architectural confirmation** (definition-versus-result separation, client-side rendering). Section I's data model should gain `DataView` and `DataSourceMapping`; Section O.1's architecture recommendation is corroborated rather than revised.

---

### UNKNOWN / NOT OBSERVABLE

- Saved-report storage format — **partially resolved (DOCUMENTED, Section P.2):** the definition is a separate artefact from query results. Versioning, concurrency and the full permission model remain unknown.
- What "Copy link…" and "Copy embeddable markup…" emit (gated behind saving).
- Export output (PDF, report package), Share, Distribute and Localize behaviour — never exercised.
- Tablet and mobile layouts — **partially resolved.** DOCUMENTED (Section P.2): consumption uses a PWA and a separate mobile app rather than a reflowed editor. OBSERVED (session 10, `design-system.md` §M): at narrow effective widths the chrome re-lays-out — title to its own row, button bars overflow with arrows, the prompt strip scrolls sideways — while the report canvas never reflows, and `matchMedia` never fires, so the behaviour is container-measured rather than media-query driven. Real device rendering and the PWA are still unobserved.
- Full keyboard shortcut map. Help exposes no shortcut reference; the **only** shortcuts the product discloses anywhere are `Ctrl+Enter` and `F2`, printed inline at the foot of the Comments pane (OBSERVED, session 10).
- Semantic success / warning / error colours — none appeared in any observed state.
- AI assistant behaviour once a prompt is sent; AI custom-category group generation.
- Join editor (the join query timed out before the editor opened) and Import data. **Map data and data views are now explained (DOCUMENTED, Section P.2)** but were never exercised.
- ~~Creating a geography item from scratch~~ — **RESOLVED (OBSERVED, session 14):** all three source types exercised — name/code lookup (ten vocabularies), registered provider, and latitude/longitude with five coordinate spaces including a custom PROJ string. See `screens.md` §C.4b and `visualizations.md` §G.2g.
- ~~Geo map rendering with real geography~~ — **RESOLVED (OBSERVED, session 6):** a geo coordinate map with a geography item in the Geography role and an aggregated measure on Color renders correctly, and exposes its own hover control cluster (search, expand, layer selector, locate, zoom). The empty Geography picker in the sandbox is explained by the missing lat/long or provider prerequisite (DOCUMENTED, Section P.2).
- ~~Comments~~ — **RESOLVED (OBSERVED, session 6):** per-object scope with its own object selector, a 1,000-character limit with live remaining count, search, and the empty state "No comments are available." Posting a comment was not attempted; session 10 confirmed threaded **replies** exist. **Alert subscriptions** is a sub-tab of the viewer Rules pane (not a pane of its own, and absent for control objects) and was never exercised.
- The 79th object counted by the Show/Hide Objects dialog but absent from the tree.
- Server-side effects of any action, and all backend implementation details.
- ~~**Parameters**~~ — **RESOLVED (OBSERVED, session 10):** a character parameter driving a benchmark comparison, exposed through a **required** drop-down control whose value list is itself cascaded from a second control. Changing it repriced a calculated column, re-sorted and rescaled a chart, and produced one descriptive undo entry. The parameter's **expression** is still unseen — it lives in the editor, which was deliberately not entered.
- ~~Model comparison / analytic objects with real data~~ — **RESOLVED for forecasting, network analysis, path analysis and decision tree (OBSERVED, session 10)**; see `visualizations.md` §G.2c. *Model comparison with two compatible models* and *"Create pipeline"* remain unexercised.
- ~~Custom graph templates~~ — **RESOLVED (OBSERVED, session 10):** a custom template ships its own type name and author-named roles. The **Graph Builder** that authors them was not opened.
- **Apply** in scenario analysis and goal seeking — never pressed, because it changes the viewer's model state.
- **Fit ▾** on the decision tree, and the *Variable Importance* / *Assessment* sub-views' contents.
- **Play report / Edit playback**, **Authorization…**, **Manage this content** — never opened.
- ~~**Model comparison output**~~ — **RESOLVED (OBSERVED, session 16):** configured by an **Add Model Comparison** dialog rather than roles, and rendering a three-panel verdict (Fit Statistic with the winner in the accent colour, Confusion Matrix faceted by model, Relative Importance Plot). See `visualizations.md` §G.2i.
- ~~**Parallel coordinates** / **Vector plot**~~ — **RESOLVED (OBSERVED, session 16):** `Variables*` and `X axis*/Y axis*/X Origin*/Y Origin*` respectively.
- ~~**"Create pipeline"**~~ — **FULLY RESOLVED (OBSERVED, session 19, with the user's explicit authorisation):** the handoff navigates the tab to **SAS Model Studio**, creates a project (`Interactive Project`, type *Data Mining and Machine Learning*) and generates a **complete four-node runnable pipeline** — `Data → Visual Data Preparation → <the promoted model> → Model Comparison` — plus a variable grid in which the VA **Response becomes the Target**, other columns become **Input**, a generated `_dmIndex_` becomes **Key**, and some columns arrive **Rejected** (including an assigned predictor — defect 83). Model Studio **crashed on arrival** and needed one Reload (defect 82). The project it creates is real and must be deleted by hand.
- **Machine Learning — partly resolved (OBSERVED, session 19).** All six role schemas re-verified against the live objects and confirmed. **Three fitted and rendered:** Forest (KS 0.1000, 2.3M of 2.3M), **Bayesian network** (KS 0.2855, **646K of 2.3M**; panels Network · Variables in Network (BIC Score) · **Model Selection** with a green star on the chosen structure · Confusion Matrix) and **Gradient boosting** (KS 0.3986, 2.3M of 2.3M; Variable Importance · Iteration Plot · Confusion Matrix). **Factorization machine, Neural network and Support vector machine were not fitted.**
- **The Esri ArcGIS basemap catalogue** — **UNKNOWN by choice.** The third-party consent dialog was deliberately left unanswered on the user's instruction, so no response is stored. Without it the catalogue is *Automatic* + *OpenStreetMap {Standard · Light · Dark · High Contrast}*.
- **Export / Share / Copy link / embeddable markup output, and Play report / Edit playback** — still unopened. These can be opened and cancelled without downloading, sharing or saving; they are safely doable.
- The **Esri ArcGIS Online** basemap catalogue — gated behind a third-party terms dialog (Accept / Decline, stored under *Settings → Geographic Mapping*) that was deliberately left unanswered.
- The **custom geography provider** authoring flow (New / Edit / Delete provider are greyed in this deployment), and **Geo line** rendering with a real path geography.
- **Mid-drag visual feedback** — drop-target highlighting, insertion indicators and cursor states. The app uses HTML5 drag-and-drop; synthesised pointer events do not start a drag and a real one cannot be paused with the available tooling (`visualizations.md` §G.2f).
- Dropping data items onto a **container**, between two existing objects, or dragging an assigned item back **out** of a role.
- ~~The rule that picks slot 1's chart type~~ — **RESOLVED (OBSERVED, session 12): there is no rule.** Thirteen samples; three categories each produced two different types from identical inputs. It is a uniform random draw from the three two-measure comparison types (`visualizations.md` §G.2d).
- ~~Whether the Suggestions pane behaves differently with more than one data source~~ — **RESOLVED (OBSERVED, session 12):** per-source, never mixed, auto-switches to a newly added source, and its selector is the **same selection** as the Data pane's.
- What picks the **category** that dominates slot 2 (`Department` on one table, `Product Category` on another — stable per table, and neither the lowest nor the highest cardinality). The vendor's cardinality claim neither reproduces nor is refuted.
- Authoring a report from the *author's* side of the features only visible in the viewer (comments, alerts, the Permanent/Interactive filter split) — observed only as a reader.


---

<!-- ===== Source: UI_UX_SPECIFICATION.md ===== -->

## UI/UX Specification — analytics platform

A build-ready design specification. Every measurement is from the live subject product; every *rule* is the one I would write for your platform, which in places is deliberately not what the subject does. Where the two differ, the subject's behaviour is shown as **Observed** and the rule as **Spec**.

Companion documents: `RECOMMENDATIONS.md` (product judgement) · `PLATFORM_BLUEPRINT.md` (engineering) · `screens.md`, `components.md`, `interaction-model.md`, `design-system.md` (raw findings).

---

### 1. Design principles

Eight principles, each earned from something that worked or failed across seventeen sessions.

1. **Typed, not free-form.** The user picks a column; the system decides where it can go. A date cannot land on a measure axis. This is what lets a novice build a correct chart in four clicks.
2. **Render immediately, refine after.** Drop one field and something appears — a measure auto-fills with a row count, an unconfigured object draws example data. Never show an empty frame and a form.
3. **Say the number behind the picture.** Every object that samples, caps, bins or drops rows declares it in its header, in the same words, every time.
4. **Never act silently.** Every refusal has a reason. Every substitution is announced. Every disabled control says which of its causes applies.
5. **Everything is reversible, and the reversal is a sentence.** One undo grammar — *verb, item, role, object, value* — across the whole product, including for readers.
6. **Disclosure is symmetric.** Whatever a reader can learn about why a number looks the way it does, an author can learn too. And vice versa.
7. **Density with air.** This is a professional tool used for hours. Small type, hairline borders, 8px rhythm, no decorative chrome — but never crowded to the point of misreading.
8. **One model, two renderings.** Every visual emits pixels and an accessible projection from the same scene graph, so they cannot drift.

---

### 2. Information architecture

#### 2.1 Top-level surfaces
```
Landing  ──▶  Report (Edit)  ⇄  Report (View)
   │              │
   │              ├── Page 1..n   (Basic | Hidden | Pop-up)
   │              └── Object 1..n
   └── Content browser (Recent · Favorites · My Folder · Shared · Recycle Bin · Recommendations)
```

#### 2.2 The two-mode model
| | Edit | View |
|---|---|---|
| Purpose | construct | consume |
| Left rail | Data · Objects · Outline · Suggestions · Review | — |
| Right pane | Options · Roles · Actions · Rules · Filters · Ranks | Roles · Rules · Filters · Ranks · Comments (read-only) |
| Undo | full | **yes — reader interactions are undoable too** |

**Spec:** one mode switch, always visible, always one click, and state (selections, drill, prompts) survives the switch in both directions.

#### 2.3 Navigation rules
- **Spec:** every surface is addressable — `/reports/{id}/pages/{pageId}?mode=view&filters=…`. Back and forward work. Deep links open exactly what was shared.
- **Observed (defect 24):** the subject has one route for the entire application, no history, no deep links. This cannot be retrofitted; decide it on day one.
- Page tabs appear above the canvas; hide the strip in View mode when a report has one Basic page.
- Pop-up pages open as modals from links, never as navigation.

---

### 3. Layout system

#### 3.1 Application shell
```
┌──────────────────────────────────────────────────────────┐
│ Banner                                            38px   │
├──────────────────────────────────────────────────────────┤
│ Report toolbar                                    44px   │
├────┬──────────────┬──────────────────────┬───────────────┤
│Rail│  Left pane   │       Canvas         │  Right pane   │
│34px│    338px     │        fluid         │     384px     │
└────┴──────────────┴──────────────────────┴───────────────┘
```

| Region | Size | Behaviour |
|---|---|---|
| Banner | 38px | fixed; identity, global search, notifications, help, account |
| Toolbar | 44px | document actions; title left, actions right |
| Icon rail | 34px | 5 tabs, ~53px hit height; a **»** toggle reveals labels |
| Left pane | 338px | pinned or auto-collapse on canvas click |
| Right pane | 384px | same |
| Canvas | fluid | ~16px gutter around objects |
| AI / assistant panel | ~460px | overlay, not a pane |

**Spec:** panes are resizable and their width persists per user. The subject's are fixed — a 338px data pane truncates most real column names.

#### 3.2 Canvas layout
- Objects fill the page in a flex/grid layout; page direction vertical by default.
- Per object: *Specify / Extend if available / Shrink if necessary* for width and height.
- Page: *Avoid scrollbars*. Report: *Set fixed report size*. Plus a **Precision container** for absolute placement.

**Spec:** keep these author-controlled flags — layout behaviour should be an authoring decision — and add a page-level **reflow mode** for narrow viewports (§11).

---

### 4. Design tokens

Measured at 1214×731, light theme. Substitute your own hues; copy the *system*.

#### 4.1 Type
| Token | Value |
|---|---|
| `font.family.ui` | one humanist sans throughout (Inter / Source Sans 3 / system-ui) |
| `font.size.xs` | 12px — small control text, captions |
| `font.size.sm` | 14px — **base body, buttons, inputs, list rows** |
| `font.size.md` | 16px — pane titles, rail labels |
| `font.lineHeight.default` | 1.4 (22.4px at 16px) |
| `font.weight.regular` / `.bold` | 400 / 700 — **no light weights** |
| `font.family.chart` | must equal `font.family.ui` |

> **Observed defect 25:** crosstab display-rule text defaults to a different family from the report font. One type system, no exceptions.

#### 4.2 Colour
| Token | Value | Use |
|---|---|---|
| `color.brand` | `#0664D0` | banner, links, primary actions |
| `color.text.primary` | `#1B1D22` | |
| `color.text.secondary` | `#6D7585` | axis and legend labels |
| `color.text.disabled` | `#C3C8D0` | |
| `color.surface` | `#FFFFFF` | panes, cards, menus |
| `color.surface.subtle` | `#F9FAFB` | rail |
| `color.background` | `#F4F4F6` | canvas surround |
| `color.border` | `#DDDFE4` | 1px hairlines — **elevation comes from borders, not shadows** |
| `color.accent.single` | `#4398F9` | default single-series mark |
| `color.categorical[0..7]` | `#EC80CE` · `#54B6A4` · `#F28D44` · `#97C03F` · `#A570E8` · `#4398F9` · (+2 unsampled) | assignment order; each mark outlined ~10% darker than its fill |
| `color.data.missing` | reserved slot | **a dedicated Missing colour — copy this** |
| `color.data.other` | grey | the "Other" bucket |
| `color.gradient.continuous` | 2-stop light → brand | continuous colour roles |
| `color.status.success/warning/danger` | **UNKNOWN in subject** | **Spec: define all three.** The subject has none; validation is red text plus a red outline and severity counters are monochrome |

#### 4.3 Spacing
Base **4px**, rhythm **8px**. Observed distribution: `8px` dominant, then `16`, `6`, `4`, `2`, `32`.

`space.1`=4 · `space.2`=8 · `space.3`=12 · `space.4`=16 · `space.6`=24 · `space.8`=32

#### 4.4 Shape, border, elevation
| Token | Value |
|---|---|
| `radius.default` | **2px** everywhere — buttons, inputs, cards |
| `border.width` | 1px |
| `elevation.flat` | none — panes and cards use borders |
| `elevation.overlay` | light drop shadow — menus, modals, popovers only |

#### 4.5 Motion
**Observed:** only 18 of 375 sampled elements have any transition, and all use the same one:

```
duration: 100ms
easing:   cubic-bezier(0, 0.5, 0.2, 1)
property: background-color, border-color
```

No entrance, exit or layout animation anywhere.

**Spec — keep this discipline.** Motion exists to soften state change, not to narrate. Token set:
`motion.fast` 100ms (hover, active, focus) · `motion.default` 160ms (disclosure, pane collapse) · `motion.slow` 240ms (modal in/out). Same easing. **Respect `prefers-reduced-motion`** and drop to 0ms.

#### 4.6 Layering
Observed z-indices are shallow — `0`, `1`, `2`, `4`, `5` — with stacking handled by DOM order and portals.

**Spec — name the layers:** `base` 0 · `sticky` 100 · `dropdown` 200 · `overlayPane` 300 · `modal` 400 · `toast` 500 · `tooltip` 600. Never write a raw z-index.

#### 4.7 Sizing
| Token | Value |
|---|---|
| `size.control.height` | 28px (buttons, inputs, selects) |
| `size.control.padding` | 4px 8px |
| `size.icon.glyph` | 16px |
| `size.icon.target` | 22–24px |
| `size.checkbox` | 16px |
| `size.row.condensed` | list and grid rows, condensed by default |

> **Spec:** 24px is below the 44px comfortable touch target. Under the touch breakpoint, scale `size.icon.target` to 44px.

---

### 5. Component library

Each entry: **anatomy → variants → states → behaviour → accessibility**. Components marked ★ are the ones that carry the product.

#### 5.1 Application chrome

**App banner** — identity · global search · notifications · help · account avatar. Fixed 38px. *Spec:* at narrow widths the product title truncates with an ellipsis; never wrap the banner.

**Report toolbar** — title (left) · action cluster (right) · overflow ⋮. 44px.
*States:* every action is enabled, or disabled **with a reason** (§7.5).
*Spec:* at narrow widths the title moves to its own row above the toolbar (the subject does this and it is the right call).

**Icon rail** ★ — 5 tabs, 34px wide, ~53px hit height, **»** toggles labels.
*States:* selected (left accent bar + tint), hover, focus ring.
*A11y:* `role="tablist"`, arrow-key navigation, `aria-selected`.

**Side pane** — header (title + ⋮) · body · pin/unpin · collapse chevron.
*Variants:* left (338px), right (384px), overlay (~460px).
*Behaviour:* auto-collapse on canvas click unless pinned.
*Spec:* resizable, width persisted per user.

#### 5.2 Data

**Data item row** ★ — icon (classification) · label · distinct count · badges (sensitivity, outlier) · hover affordances.
*Variants:* category · measure · aggregated measure · date · geography · hierarchy.
*States:* default · hover (reveals edit) · **selected (checkbox appears on every row once anything is selected)** · badged · dragging.
*Behaviour:* click selects one; **Ctrl/Cmd+click toggles; Shift+click ranges**; selection spans classification groups and **survives virtualised scrolling**; right-click opens a 20+ item menu; drag — single or multi-item.
*A11y:* **Spec — the selection must survive virtualisation in the accessibility tree.** The subject's `aria-selected` exists only on rendered rows, so a live three-item selection can report as zero (defect 62). Maintain a live region announcing "*3 items selected*".

**Hover card** — name · distinct values · **name in data** (physical column) · format · sensitivity explanation in plain language.
*Spec:* this is the mapping surface. Show both halves of the mapping always.

**Selection summary** — `Clear selection (n)` at the foot of the pane.
*Spec:* also expose the count as a live region.

#### 5.3 Objects

**Object frame** ★ — title · hover ⋮ · maximize · resize handles · body · footer notices.
*States:* default · selected (border + handles) · hover · maximized · **loading** · **error** · **truncated** · **placeholder (example data)**.
*Behaviour:* click selects; double-click drills; right-click menu; drag to move; drop target for data items (§6.2).

**Object header line** ★ — for analytic objects: `<Title> · Event: <level> ▾ · Fit: <statistic> <value> ▾ · Observations: <used> of <total> · <Action> ▾`.
*Spec:* **generalise this to every object.** Any object that samples, caps, bins or drops rows prints `Rows: <used> of <total>` in the same slot, in the same words. This single pattern retires defects 3, 6, 59, 60, 75.

**Chart canvas** — the drawing surface.
*Spec:* emits **both** a painter pass and an ARIA projection from one scene graph (§10).

**Data grid** — crosstab (nested headers) or list table. Column header menu: sort · replace · remove · aggregation · format · new calculation · cell visualization · indent · totals · row numbers.
*Behaviour:* virtualised scroll, column resize, fit-to-width.

**In-object tab strip** — for analytic objects with several views of one fit (*Tree · Icicle · Variable Importance · Assessment*). ‹ › arrows when it overflows.

**Viewport control cluster** — fit · pan · zoom in · zoom out, on hover, for objects laid out in free 2-D space (map, network, path). Not for category/value grids.

#### 5.4 Configuration

**Role group** ★ — label · required marker · items · `+ Add`.
*States:* required-unfilled · filled · greyed (single-item role at capacity) · **drop target**.
*Spec:* a required marker means *this role*. For "any one of these N", use a bracketed group marker and say which are outstanding — the subject puts `*` on four roles when one suffices (defect 72).

**Typed picker** — single (`Add Data Item`) or multi (`Add Data Items` + checkboxes + Apply). Empty state: *"No data items available for role."*
*Spec:* filter by type **and** semantic type. Never offer a latitude as a summable measure.

**Property section** — collapsible group in the Options pane, with a settings search box spanning the pane.

**Filter card** — category (checkbox list + frequency bars) · numeric (histogram slider) · date (range slider) · per-card ⋮.

**Rank card** — subset · count · rank-by · ties · All Other.

**Expression editor** — toolbar of skeletons · text area · inline error count · red squiggle · gutter marker · resizable results preview.
*Spec:* validate per keystroke, report position, keep the last valid result visible while invalid.

#### 5.5 Controls (reader-facing)

**Drop-down · List · Button bar · Slider · Text input.**
*States:* empty · selected · **required** · cleared · overflowing.
*Behaviour:* an optional control's list opens with **`Clear filter`**; a **required** control omits it. Button bars overflow with ‹ › arrows.
*Spec:* controls are ordinary filter sources and may cascade — and the cascade must be visible in the filter stack.

**Report / page prompt bar** — controls in a row above the page tabs, collapsible by a ▲ chevron.
*Spec:* **stacks** below the breakpoint. The subject scrolls it sideways (defect 46).

#### 5.6 Feedback

**Toast** — bottom-left, transient, with **Undo**. Used for reversible side effects.

**Modal** — small · large · blocking notice. Esc closes **only the innermost layer**.
> **Observed defect 14:** Esc inside a dropdown closes the whole dialog and discards the work.

**Tooltip / data tip** — hover, one row per assigned role plus data-tip values.

**Inline notice (ⓘ)** — object-level disclosure: truncation, unmapped values, fabricated ordering.
*Spec:* promote these from a tiny ⓘ to a visible line in the object header.

**Empty state** — icon · one sentence saying what this surface needs · a primary action.
> **Observed defect 48:** the Suggestions pane renders a disabled control and blank space.

---

### 6. Interaction patterns

#### 6.1 Selection
| Gesture | Result |
|---|---|
| Click | select one |
| Ctrl/Cmd + click | toggle one in or out |
| Shift + click | select a range |
| Click a chart mark | select that mark (single-select) |
| Click a control value | apply a filter |

Selections persist across mode switches and across virtualised scrolling.

#### 6.2 Drag and drop ★
A **three-zone target model**:

| Target | Result |
|---|---|
| Empty canvas | create an object (resolver, §6.3) |
| **Gutter around an object** | create an object, split in that direction |
| **Object body** | assign to a compatible role — replace a filled single role, append to a multi role |
| **Role slot** | assign to that role directly |
| **Chip inside a role** | reorder within the role |

*Spec additions:*
- **Fall through to the next compatible empty role** rather than no-op. The subject ignores a drop when its preferred role is full even though an empty compatible role exists (defect 58).
- **Show the drop target.** Highlight the receiving zone, name the role it will fill, and show an insertion indicator for reorder. *(The subject's mid-drag feedback could not be captured; specify it rather than copy it.)*
- Keyboard equivalent: focus a data item, `Space` to pick up, arrow to a role, `Space` to drop.

#### 6.3 Automatic object selection
One resolver, called from every surface (canvas drop, object conversion, suggestions).

| Dropped set | Object |
|---|---|
| 1 category | bar (measure auto-filled with row count) |
| 1 category + n measures | bar, measures stacked into the measure role |
| 1 date + measure | time series |
| ≥2 categories | table, everything as columns |
| 2–3 measures | binned scatter / heat map |
| ≥4 measures | correlation matrix |

*Spec:* the resolver must (a) consult **semantic type**, never offering coordinates, years or identifiers as measures; (b) **explain its choice** on request; (c) be **deterministic** for the same input.

#### 6.4 Undo ★
A command log over the document. **One sentence grammar:**

```
<Verb> <item> <preposition> <role> of <object> [from <old> to <new>]
```

Examples: `Assign Supplier Continent to Group of Bar – Supplier Country` · `Replace Frequency with Cost in Measure of Bar – Supplier Country` · `Change Fit line type of Scatter 1 from None to Linear`.

> **Observed:** seven competing grammars, the worst being `Change option "fitLineType"` — a raw internal key with no object and no value (defect 71).

Rules: every mutation produces exactly one entry; rejected input produces none; **dismissals are undoable too** (the subject's suggestion-card delete is not — defect 50); undo works in View mode.

#### 6.5 Progressive disclosure
Panes auto-collapse unless pinned · property sections collapse · advanced settings behind ⋮ · the expression editor as the escape hatch behind every filter and calculation · a settings search spanning the Options pane.

#### 6.6 Confirmation and refusal
- **Confirm** only destructive-and-irreversible actions and closing unsaved work.
- **Everything else** uses a toast with Undo.
- **Never no-op.** A refused action states why, in the object or beside the control.

---

### 7. State catalogue

Every object and pane implements all nine.

| State | Rule |
|---|---|
| **Empty (unconfigured)** | draw **example data** plus a central `Assign data` action, so the layout teaches the object |
| **Empty (no data matches)** | *"No data matches the current filters."* + a clear-filters action |
| **Loading** | spinner over the greyed placeholder; never a blank frame |
| **Partial** | first results drawn, remainder loading, stated |
| **Truncated** ★ | **visible header line**: `Rows: 3,000 of 748,213 — row limit`, plus a one-click *rank top N instead* |
| **Substituted** ★ | `Binned: 748K points rendered as a heat map` — never silent |
| **Error** | what failed, why, what to try; keep the object's identity and roles inspectable |
| **Refused** | reason beside the control: `not saved` · `no permission` · `not licensed` · `no content` · `nothing selected` |
| **Disabled** | as refused — **the cause is always named**. The subject has five causes behind one grey (defect 29) |

---

### 8. Content and microcopy

**Voice:** plain, specific, second person for actions, no exclamation marks, no blame.

**One naming function** produces the object title, the accessible name and any undo label. The subject has at least three and they disagree — a card reading `Department by Frequency` creates an object titled `Frequency of Department` (defect 54).

| Surface | Pattern | Example |
|---|---|---|
| Object title (auto) | `<measure> by <category>[ grouped by <group>]` | `Cost by Supplier Country grouped by Supplier Continent` |
| Accessible name | `<title>, <object type>` | `Cost by Supplier Country, Bar chart` |
| Undo | §6.4 grammar | |
| Truncation | `<used> of <total> — <reason>` | `646K of 2.3M — rows with missing values excluded` |
| Validation | `The value must be …` with the bound | `Bin count must be between 2 and 100.` |
| Empty pane | what it needs, then what it does | `Add data to see suggested charts.` |
| Refusal | reason first, then remedy | `Share is turned off for this deployment.` |

**Numeric limits are always stated in the control.** The subject states `Bin count (2-100)` in one place and silently rejects `0` and `9999` in another (defect 73).

---

### 9. Iconography

One line-weight set, 16px glyph on a 22–24px target, 1.5px strokes, square terminals to match the 2px radius. Classification icons (category · measure · date · geography · hierarchy) are the highest-traffic glyphs in the product — they appear on every data row, every role chip and every picker — so design those five first and test them at 16px on a `#FFFFFF` and a `#F9FAFB` surface.

---

### 10. Accessibility specification

This is where the subject is weakest and where a newcomer can win outright.

| Requirement | Spec |
|---|---|
| **Charts** ★ | every visual emits a painter pass **and** an ARIA projection from one scene graph: a real `<table>` of the plotted values, a one-sentence summary, and focusable marks in visual order. Non-negotiable, and cheap only if designed in on day one |
| Accessible names | one naming function (§8); never fall back to an internal object id |
| Selection | announced in a live region and correct under virtualisation |
| Keyboard | full operation without a pointer, including drag (§6.2), and a **discoverable shortcut map** — the subject discloses exactly two shortcuts, inside one pane (defect 23) |
| Focus | 3px `:focus-visible` outline, 2px offset, contrast ≥ 3:1 against both adjacent surfaces. *(Observed: the subject defines a 3px outline and applies it on `:focus-visible` — correct.)* |
| Contrast | text ≥ 4.5:1, UI and graphical objects ≥ 3:1. Verify the categorical palette against `#FFFFFF` **and** the subtle surface |
| Colour independence | never encode meaning in hue alone — pair with shape, pattern or a label. The subject's Model comparison greys the losing bar, which is good, but it is the only signal |
| Motion | honour `prefers-reduced-motion` |
| Theme | a genuine High Contrast theme, including a high-contrast basemap for maps |
| Targets | 44px under the touch breakpoint |

---

### 11. Responsive specification

**Observed:** the subject re-lays-out its chrome by **measured container width in JavaScript, not CSS media queries** (`matchMedia` never fired while the layout visibly changed). The report canvas **never reflows** at any width; the prompt strip scrolls sideways and the banner title truncates.

**Spec — container queries, and a real reflow mode.**

| Breakpoint | Shell | Canvas |
|---|---|---|
| ≥1200px | rail + left pane + canvas + right pane | as authored |
| 992–1199px | panes overlay instead of push | as authored |
| 768–991px | rail collapses to icons; one pane at a time | **reflow: single column, objects at minimum legible height** |
| <768px | View mode only; toolbar becomes an overflow menu; **prompt bar stacks** | reflow, vertical scroll |

Authors choose per page between **as-authored** (absolute placement preserved, pan/zoom below the breakpoint) and **reflow**. Print gets its own stylesheet and uses the export path.

---

### 12. Theming

Light (default) · Dark · High Contrast · custom brand.

- All tokens resolve through CSS custom properties on a single root scope; components never hardcode a hex.
- **Charts read the same tokens** — the theme must reach the drawing layer, not just the DOM.
- The **basemap follows the theme** (a high-contrast tileset under High Contrast). The subject does this and it is excellent.
- A theme editor exposes: report font, 8 fill swatches, 8 line/marker swatches, plus the reserved **Missing** and **Other** colours.
- Theme is a report-level property so a shared report looks the same for every reader.

---

### 13. Definition of done

A component ships when:

1. All nine states in §7 are implemented and screenshotted.
2. It uses only tokens — no literal colours, sizes or z-indices.
3. Keyboard operation is complete, and the focus ring passes contrast on every surface it sits on.
4. Its accessible name comes from the shared naming function.
5. Every refusal and every disabled state names its cause.
6. Every mutation emits one undo command in the §6.4 grammar.
7. If it renders data: truncation, substitution and population are disclosed in the header, and an ARIA projection exists.
8. It behaves at 360px, 768px and 1440px, and under `prefers-reduced-motion`.
9. Microcopy matches §8, including the numeric bound in any validation message.
10. Nothing in it fails silently.


---

<!-- ===== Source: PLATFORM_BLUEPRINT.md ===== -->

## Platform blueprint — building a professional data analytics product

An original full-stack design, informed by seventeen sessions of observing a mature commercial BI product. Nothing here is copied from that product: the observations told us which problems are real and which solutions earn their keep; the design below is the one I would build.

Read `RECOMMENDATIONS.md` first for the product judgement. This is the engineering.

---

### 0. The one-paragraph architecture

A **semantic layer** turns physical tables into typed data items. A **query compiler** turns an object's role assignment into a query plan and pushes aggregation to the warehouse. A **session-scoped executor** runs plans, dictionary-encodes strings, and returns results inline when small and by reference when large. A **document service** stores report definitions as versioned JSON, separate from results. A **thin client** holds the document, asks for one result per object, and renders through a single drawing layer that also serves export and mobile. Everything else — identity, authorization, content, preferences, localization, fonts — is a small service behind one gateway.

---

### 1. Layer map

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLIENTS         web app · embedded SDK · PWA/mobile · export worker │
├─────────────────────────────────────────────────────────────────────┤
│  EDGE            gateway · authn · rate limit · tenant routing       │
├─────────────────────────────────────────────────────────────────────┤
│  APP SERVICES    documents · query · exports · thumbnails            │
│                  content · identity · authorization · preferences    │
│                  localization · fonts · maps · notifications         │
├─────────────────────────────────────────────────────────────────────┤
│  SEMANTIC        data sources · data items · relationships · policy  │
├─────────────────────────────────────────────────────────────────────┤
│  QUERY ENGINE    plan compiler · cache · executor pool · governor    │
├─────────────────────────────────────────────────────────────────────┤
│  DATA PLANE      warehouse / lakehouse · in-memory tier · object store│
└─────────────────────────────────────────────────────────────────────┘
```

Build the **document service, semantic layer, query engine and one client** first. Everything else is replaceable.

---

### 2. Data plane

**Do not build a storage engine.** Sit on DuckDB (single-node and embedded), ClickHouse (self-hosted scale) or the customer's Snowflake/BigQuery/Databricks. Your value is the semantic layer and the interaction model, not another columnar store.

**Three tiers, chosen per data source:**

| Tier | When | Mechanism |
|---|---|---|
| **Live** | source is fast, or data must be current | compile to SQL, push everything down |
| **Accelerated** | dashboards over a slow source | materialise a columnar extract on a schedule; keep the semantic layer identical |
| **In-memory** | interactive exploration over ≤ a few hundred million rows | load into DuckDB/Arrow per session, hash-encode strings once |

The subject's headline capability is sub-second interaction over 2.3M rows; that is unremarkable for a columnar engine today. **Choose the tier per source and make the choice visible to the author**, because it determines whether a filter is instant or takes ten seconds.

**Row-level security belongs here, not in the client.** Every compiled query carries the caller's identity and the policy predicates get `AND`-ed into the `WHERE` clause server-side. A filter the client can remove is not security.

---

### 3. Semantic layer

This is the heart of the product. Two rules decide whether the rest works:

> **Rule 1 — a data item is a mapping, and both halves are visible.** Label and physical column are distinct fields. Users rename freely; queries never break.
>
> **Rule 2 — role schemas are data, not code.** Objects declare their roles in a registry. A custom template can add an object type with its own named roles without a deploy.

```jsonc
// DataItem
{
  "id": "di_7f3",
  "label": "Customer Age",           // what the user sees and renames
  "columnName": "CUST_AGE",          // physical, never shown in titles
  "sourceId": "ds_retail",
  "classification": "measure",       // category | measure | date | geography | hierarchy
  "semanticType": "age",             // ← see §3.1. drives aggregation + veto
  "defaultAggregation": "average",   // inferred, never blindly "sum"
  "format": {"type":"number","decimals":0},
  "sensitivity": "quasi-identifier", // propagates to derived items
  "cardinality": 74,                 // cached, refreshed on profile
  "nullCount": 1694312,
  "derivation": null                 // set for calculated items, hierarchies, geography
}
```

#### 3.1 Semantic typing is the highest-value thing you will build
Every serious defect in the subject traces back to one missing concept: **the system knows a column is numeric but not what it means.** It sums latitudes, sums years, sums identifiers, and recommends charts built from them.

On profile, classify each column into a `semanticType`: `latitude`, `longitude`, `year`, `identifier`, `code`, `postal`, `currency`, `count`, `ratio`, `percentage`, `duration`, `age`, `score`, `unknown`. Derive it from name patterns, value range, cardinality-to-row ratio, uniqueness and format. Then enforce:

| Semantic type | Default aggregation | Sum allowed? | Eligible as a measure in auto-selection? |
|---|---|---|---|
| `latitude` / `longitude` | none — it is a coordinate | **never** | **no** |
| `identifier` / `code` | `distinctCount` | **never** | **no** |
| `year` | none — it is a date part | **never** | **no** |
| `age` / `score` / `ratio` | `average` | warn | yes |
| `currency` / `count` | `sum` | yes | yes |
| `percentage` | `average` (weighted if a weight exists) | **never** | yes |

**This one table removes roughly a third of the subject's catalogued defects** — the summed latitudes, the summed years, the nonsense suggestions, the meaningless auto-charts.

#### 3.2 Aggregation is a first-class expression
Store `{ column, aggregation, filterContext, scope }`, not a string. Non-additive aggregations (`distinctCount`, `median`, percentiles) must be **recomputed at each level**, never summed from displayed cells — subtotals, grand totals and "other" buckets all query at their own grain. The subject gets this right and it is worth the cost.

#### 3.3 Calculated items
An expression AST, not a string, with a small typed function library. Store the AST; render the text. Validate on every keystroke, and report errors with a position. Let an item declare a `scope` (`row`, `groupBy`, `fixed`, `grandTotal`) — the "fixed group-by context" idea is genuinely useful and most tools lack it.

---

### 4. Query engine

#### 4.1 Compilation
```
Object + RoleAssignment + FilterStack + RankStack
  → logical plan (dimensions, measures, filters, ranks, limits)
  → physical plan (SQL or DuckDB relation)
  → result set + string dictionary
```

Compile **per object**, not per page: objects have different filter stacks. But **execute a page's plans in one request** — the subject's one-job-per-object stream is its clearest protocol mistake.

#### 4.2 The wire protocol

Copy the shape, fix the details.

```http
POST /v1/sessions                          → 201 {sessionId, expiresAt}
DELETE /v1/sessions/{id}                   → 204

POST /v1/sessions/{id}/query               → 200
{
  "requests": [                            // ← batch: a whole page in one call
    {"ref":"obj_a","plan":{…},"maxRows":5000},
    {"ref":"obj_b","plan":{…},"maxRows":5000}
  ],
  "stringEncoding": "dictionary",
  "inlineLimit": 262144,                   // bytes; larger results spill
  "waitMs": 30000                          // long-poll, not a poll loop
}

→ {
  "results":[
    {"ref":"obj_a","status":"ok","inline":{"columns":[…],"rows":[…],"dictionary":[…]},
     "truncation":{"applied":false},"rowsScanned":2339245,"rowsReturned":6,"elapsedMs":412},
    {"ref":"obj_b","status":"ok","href":"/v1/results/r_88f1","expiresAt":"…",
     "truncation":{"applied":true,"limit":5000,"total":748213,"reason":"rowLimit"}}
  ]
}
```

Non-negotiables in that payload:

- **`truncation` is always present**, with the limit, the true total and the reason. Never a tiny ⓘ.
- **`rowsScanned` vs `rowsReturned`** — so an object can honestly print *"646K of 2.3M"*, and so two objects on one page can be detected as describing different populations.
- **Dictionary-encoded strings** — the subject's `indexStrings=true`, and it is the right call.
- **Inline when small, by reference when large** — the subject's `embeddedData=limited`, also right.
- **Long-poll with an explicit `waitMs`**, and `202 + Retry-After` when the work outlives it. **Never a non-standard status**; the subject's `449` on session creation is a trap.
- **Idempotency key per request** so a retry cannot double-run an expensive plan.

#### 4.3 Caching, at three levels
1. **Plan cache** — identical logical plan + identical policy context → reuse the result id.
2. **Result cache** — keyed by plan hash and data-source version; invalidated by a version bump, never by TTL alone.
3. **Dictionary cache** — string dictionaries are stable per column and per session; send them once.

#### 4.4 Governor
Per-tenant and per-user concurrency caps, a wall-clock budget per query, a scanned-bytes budget, and a **cancel** endpoint wired to the client so navigating away kills the work. Surface the budget in the error: *"stopped after 30 s and 4.2 GB scanned"* beats *"query failed"*.

---

### 5. Document service

Report definitions are **versioned JSON documents**, completely separate from results.

```jsonc
{
  "id":"rep_9k2","version":47,"schemaVersion":3,
  "title":"Q3 Retail Review",
  "dataSources":[{"id":"ds_retail","ref":"…","items":[…]}],
  "parameters":[…],
  "commonFilters":[…],
  "pages":[{
    "id":"pg_1","type":"basic","layout":{"mode":"grid","cells":[…]},
    "prompts":[…],
    "objects":[{
      "id":"obj_a","type":"bar","title":{"mode":"auto"},
      "roles":{"category":["di_dept"],"measure":["di_sales"]},
      "filters":[…],"ranks":[…],"displayRules":[…],"options":{…}
    }]
  }],
  "actions":[{"source":"obj_a","target":"obj_b","mode":"filter"}]
}
```

- **Separate definition from results, always.** The subject does this and it is why one definition can render in a browser, a PDF and a phone.
- **Version every save**; keep a bounded history; make restore one click.
- **Autosave by diff, not by whole-document PUT.** The subject PUTs the entire content on essentially every change. Send a JSON patch, debounce at ~750 ms, and keep a local mirror so a network blip is invisible.
- **Migrate on read** with `schemaVersion`. You will change this schema ten times in year one.

---

### 6. Rendering

The subject's single most consequential decision is a 13 MB WebAssembly engine drawing every visual to a 2D canvas. It buys one renderer for browser, export and mobile — and costs it the accessibility layer entirely.

**Take the benefit, refuse the cost. Render twice from one scene graph:**

```
Data + encoding spec → scene graph → ├── canvas/WebGL painter   (pixels, fast, exportable)
                                     └── DOM/ARIA projector     (a real accessible table)
```

The scene graph is the contract. The painter handles millions of marks; the projector emits a `<table>`, a summary, and focusable marks in the same order. **Both are generated from one model, so they cannot drift.** This is the accessibility answer the subject never found, and it is cheap if you design for it on day one and impossible to retrofit later.

Practical guidance: SVG up to ~2k marks (crisp, inspectable, free accessibility), canvas beyond, WebGL beyond ~100k. Bin before you draw — and when you bin, **say so on the object** ("binned: 748K points"), which the subject does not.

**One naming function** produces the object title, the accessible name and any undo label. The subject has at least three and they disagree.

---

### 7. Client architecture

| Concern | Choice |
|---|---|
| Framework | anything mainstream — React or Svelte. Do **not** write a component framework; the subject did and it shows in the payload |
| State | one normalised document store + a separate results cache keyed by plan hash. Never mix definition and data in one tree |
| Undo | a **command log** over the document, not state snapshots. Every command carries a human sentence: **verb, item, role, object, value**. One grammar — the subject has seven |
| Budget | **≤ 2 MB initial JS**, route-split, renderer lazy-loaded on first object, analytics chunks on demand. The subject ships 45 MB of JS and a 13 MB WASM before a single query |
| Localization | one locale, split by route. The subject loads 2.7 MB of bundles up front |
| Offline | a service worker for the shell; an IndexedDB mirror of the open document |
| Routing | **real URLs** — `/reports/{id}/pages/{pageId}?mode=view&filters=…`. The subject has a single route and no history, and it cannot be retrofitted |

#### 7.1 Responsive, properly
Absolute placement *and* a reflow mode, chosen per page by the author. Below the breakpoint: stack the prompt bar, wrap control bars, give each object a minimum legible size and let the page scroll vertically. The subject scrolls its prompt strip sideways at phone width and never reflows the canvas — do the opposite.

---

### 8. Platform services

Keep them small, boring and behind one gateway.

| Service | Notes |
|---|---|
| **Identity** | OIDC. `@currentUser` convenience routes are a good idea |
| **Authorization** | **`POST /v1/authorization/decisions:batch`** — the single best API idea observed. A toolbar asks once for fifty decisions. Every decision returns a **reason code** (`not_saved`, `no_permission`, `not_licensed`, `no_content`, `no_selection`) so the UI can say *why* a control is disabled. The subject has five distinct causes behind one undifferentiated grey |
| **Content** | folders, favorites, recents, shortcuts, recycle bin, search facets. One RQL-ish grammar (`filter=and(eq(a,b))`, `sortBy=f:desc`, `start`/`limit`) — but **page everything**; never `limit=32767` |
| **Preferences** | per-user, read and written back |
| **Localization** | message bundles per locale per route |
| **Fonts** | a font service keeps browser, PDF and mobile typography identical |
| **Maps** | basemap catalogue; **make the default theme-aware** (swap to a high-contrast tileset under the high-contrast theme — the subject does this and it is excellent). Third-party providers behind explicit, revocable consent stored per user |
| **Thumbnails / Exports** | async job services with a poll-or-webhook contract, rendering through the **same** scene graph |
| **Notifications / Alerts** | subscriptions on an object plus a threshold, evaluated server-side |

---

### 9. Security and tenancy

- **Row-level policy in the compiler**, never in the client.
- **Column-level sensitivity** on the data item, inherited by every derived item, surfaced as a badge with a plain-language explanation, and enforceable as a redaction policy. The subject shows the badge but does not enforce anything.
- **Tenant isolation** at the connection and the cache key. A plan hash without a tenant id is a data leak waiting to happen.
- **Audit** every query with user, plan hash, rows scanned, policies applied.
- **Embedding**: signed, scoped, short-lived tokens for a single report and a single filter context.

---

### 10. Build plan

| Phase | Ships | Done when |
|---|---|---|
| **1. Spine** (6–10 wks) | semantic layer with semantic typing · plan compiler · session/query API with truncation contract · document service with versioned autosave · one client: bar, line, table, crosstab · typed roles with filtered pickers · command-log undo | a user builds a four-object page over a real warehouse table without writing SQL |
| **2. The loop** (6–8 wks) | filter stack (object/page/report) · controls as filter sources · cross-object actions · prompt bars · **one inspectable filter stack shown identically to author and reader** | a reader can answer *why am I seeing this?* without asking |
| **3. Depth** (8–12 wks) | calculated items + expression editor · display rules · ranks · non-additive totals at grain · export via the shared scene graph · real URLs | a finance team replaces a spreadsheet |
| **4. Differentiators** (ongoing) | geography with a **live mapping validation panel** · map layer stack · forecasting with scenario/goal-seek · the statistical family with model headers and model comparison | an analyst stops exporting to Python |
| **5. Assistive** (last) | suggestions · automatic chart selection · outlier advisor · linter — **one resolver, reproducible, explainable, with a semantic veto** | a recommendation can always answer *why this chart?* |

**Do phase 5 last and gate it.** Every assistive surface in the subject is its weakest work, for one reason: they act without explaining. An assistive feature that cannot justify itself costs more trust than it earns.

---

### 11. Ten invariants to enforce in code review

1. No aggregation without a `semanticType` check.
2. Every result carries `rowsScanned`, `rowsReturned` and a `truncation` object.
3. Every refusal returns a reason code; no silent no-ops.
4. Every disabled control renders a reason.
5. No substitution of what the user asked for without a visible note on the object.
6. Every mutation produces one undo command with the shared sentence grammar.
7. Every visual emits both a painter pass and an ARIA projection from one scene graph.
8. Every mapping step (geography, join, category) reports a match rate and names its failures before commit.
9. Every collection endpoint pages; no unbounded `limit`.
10. Object title, accessible name and undo label all come from one naming function.

---

### 12. What this blueprint does not know

Honest gaps, carried forward from `observed_architecture.md`:

- **Request and response bodies were never read** — how a role assignment becomes a query on the wire is inferred from behaviour, not observed. The §4.2 protocol is my design, not a transcription.
- **Authentication internals are unknown** — token exchange, lifetimes and refresh were deliberately not captured.
- **No performance instrumentation** — the latency figures quoted anywhere in this bundle are wall-clock observations, not measurements.
- **Export, sharing and embedding output** were never produced, so §8's export contract is designed from first principles.

Treat these four as design decisions you own, not as facts to copy.


---

<!-- ===== Source: application-map.md ===== -->

## Application Map — overview, sitemap and routes

> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

### A. Application Overview

**What it is:** a browser-based, single-page, WYSIWYG **report authoring and consumption tool** for business intelligence. A user picks an in-memory data table, drags visual objects onto a paged canvas, assigns data columns to typed *roles* on each object, and wires objects together with interactions. The result is a multi-page interactive report that other people open in a read-only viewer mode.

**Core proposition (OBSERVED):** the author never writes a query. Every object issues its own aggregated query against the source table; the UI's job is to make role assignment, filtering, ranking and cross-object interaction safe and fast.

**Two modes of the same document (OBSERVED):**
| Mode | Who | UI |
|---|---|---|
| Editing | Author | Left icon rail (5 panes), canvas with page tabs, right property rail (6 panes), toolbar with undo/redo/save |
| Viewing | Consumer | Rails hidden; optional slim right pane (Data Settings, Display Rules, Filters, Ranks, Comments); playback/slideshow; insights |

**Feature pillars (OBSERVED):**
1. **Data preparation in-report** — calculated items, custom categories, hierarchies, geography items, parameters, partitions, aggregated sources, joins.
2. **A large object library** — 78 visible object types across tables, graphs, geo maps, controls, analytics, statistics, machine learning, containers and content embeds.
3. **Role-based visual configuration** — each object declares required/optional roles; pickers only offer type-compatible columns.
4. **Interactivity** — filters, ranks, prompts (controls), object links, page links, report links, URL links, display rules.
5. **Assistive features** — auto chart suggestions, automated explanation/prediction, forecasting, an AI side-panel assistant, and a lint-style "Report Review" panel.

**Scale characteristics (OBSERVED):** the app is built for tables in the millions of rows. Objects cap displayed rows (bar 3,000; word cloud 100) and disclose the cap only through a small ⓘ affordance.

---

### B. Sitemap

Discovered structure. Indentation = containment, not URL depth (see Section K: there is effectively **one route**).

```
Visual Analytics (Explore and Visualize)
├── Landing / Home  ("Explore and Visualize")
│   ├── Content browser (left list)
│   │   ├── Recent
│   │   ├── My Favorites
│   │   ├── My Folder
│   │   ├── SAS Content
│   │   ├── Shared with Me
│   │   ├── Recycle Bin
│   │   └── Recommendations          (default landing selection)
│   ├── Search box
│   ├── Sort by (Relevance …) + sort-direction toggle + grid/list toggle
│   ├── Item cards (thumbnail, name, date)
│   ├── "New report" (primary action, top right)
│   ├── "Recovery available for previous session" → Restore previous session
│   └── What's New / Learn More links (external)
│
├── Report Editor  (Editing mode)
│   ├── Application banner (global, persistent)
│   │   ├── Applications menu (suite launcher: Analytics Life Cycle, Administration)
│   │   ├── Product title
│   │   ├── AI assistant side panel  ("Copilot")
│   │   ├── Global search
│   │   ├── Notifications
│   │   ├── Help  → Learning Center / Help Center / FAQ (all external)
│   │   └── Account avatar
│   ├── Report toolbar
│   │   ├── Edit/View toggle
│   │   ├── Report name
│   │   ├── Undo / Redo (descriptive labels)
│   │   ├── Save
│   │   ├── More (⋮) report menu
│   │   │   ├── Home / New / Open / Save / Save as / Reopen / Close
│   │   │   ├── View report
│   │   │   ├── Export ▸ (PDF, Report package)
│   │   │   ├── Share report / Copy link / Copy embeddable markup / Distribute
│   │   │   ├── Localize report
│   │   │   ├── Import pages from report → content browser dialog
│   │   │   ├── Interface options ▸ (auto-refresh, object overlays, layout guides)
│   │   │   ├── Expand report controls (+ all page controls)
│   │   │   ├── Edit administration settings
│   │   │   └── About this report
│   │   ├── Insights popover (appears once objects have data)
│   │   └── Opened reports (N) — multi-document switcher
│   ├── Left icon rail
│   │   ├── Data pane           (data source, item tree, item menus, + New data item)
│   │   ├── Objects pane        (object library, 10 groups)
│   │   ├── Outline pane        (page/object tree, New Page, delete)
│   │   ├── Suggestions pane    (auto-generated chart thumbnails)
│   │   └── Report Review pane  (lint findings by severity, Evaluate Performance)
│   ├── Canvas
│   │   ├── Report control strip (collapsed by default)
│   │   ├── Page tab strip (+ add page, per-page ⋮ menu)
│   │   ├── Page control strip
│   │   ├── Filter breadcrumb bar (when enabled)
│   │   └── Object area (empty state → "Select a template")
│   └── Right property rail
│       ├── Options       (Report / Page / Object settings, searchable)
│       ├── Data Roles
│       ├── Actions       (Object / Page / Report / URL links, automatic actions)
│       ├── Display Rules
│       ├── Filters
│       └── Ranks
│
├── Report Viewer  (Viewing mode)
│   ├── View toolbar (insights, fullscreen, side pane, ⋮ with Play report / Edit playback)
│   ├── Page tabs (Basic pages only)
│   ├── Pop-up page (modal overlay)
│   └── Side pane: Data Settings / Display Rules / Filters / Ranks / Comments
│
└── Modal dialogs (see Section C.3)
    Choose Data · Import data · New Calculated Item · Expression editors · New Hierarchy ·
    New Custom Category · New Geography Item · New Parameter · New Partition ·
    New Interaction/Spline Effect · Custom sort · Format · New Scope · Advanced Filter ·
    New Display Rule · Add URL Link · Open (content browser) · Select a Template ·
    Manage Page Templates · Show or Hide Objects/Data Items · Edit Playback · Save confirmation
```

---

### K. Routing Model

**Finding (OBSERVED): the application has effectively one route.** `https://<host>/SASVisualAnalytics/` never changed while creating a report, loading data, adding objects, switching pages, opening dialogs, entering view mode or closing a report. No path segments, no query string, no hash fragment.

| Route | Screen | Parent | Entry | Parameters | Required state |
|---|---|---|---|---|---|
| `/SASVisualAnalytics/` | Landing, editor and viewer alike | — | direct navigation | none observed | authenticated session |
| `/SASLogon/oauth/authorize?client_id=sas.<service>&redirect_uri=…` | Silent per-service OAuth | — | triggered by first call to each backend service | client_id, redirect_uri, response_type, state | — |

**Consequences for a reimplementation (and an improvement to make):** report, page, object selection and view mode are **not addressable**, so no deep links, no browser Back/Forward within the app, and no bookmarkable state. The product compensates with in-app "Copy link…" commands (**UNKNOWN** what URL they emit — the action is gated behind saving). **Recommendation:** give the rebuild real routes, e.g. `/reports/:reportId/pages/:pageId?mode=view&object=:objectId&filters=…`.

#### B.4 Where this application sits in its platform (OBSERVED, session 19)

The suite's Applications menu enumerates the whole platform, which is the clearest available answer to *"where does a reporting tool sit in an analytics suite?"*:

| Group | Applications |
|---|---|
| **Favorites** | Explore and Visualize · Build Custom Graphs |
| **Analytics Life Cycle** | Discover Information Assets · Manage Data · **Explore and Visualize** · Build Models · Manage Models · Build Decisions · Develop Code and Flows |
| **Administration** | Build Custom Graphs · Manage Themes · Explore Lineage · Manage Environment · Manage Workflows |

The reporting tool is **one station of seven** on an explicit life cycle, with the model workbench immediately downstream — which is why a fitted model in a report offers **Create pipeline** at all (`visualizations.md` §G.2i, and the UNKNOWN register).


---

<!-- ===== Source: screens.md ===== -->

## Screen Inventory

> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

### C. Screen Inventory

#### C.1 Primary screens

| # | Screen | Purpose | Key regions | Empty state | Notes |
|---|---|---|---|---|---|
| S1 | Landing / Home | Find or create a report | Folder list, search, sort + view toggles, result grid, "New report", What's New rail | Folder with no items shows the grid empty | Session recovery card appears when an unsaved session exists |
| S2 | Report Editor — blank | Start a report | Rail, empty canvas, right pane | Canvas: illustration + "Design a Report" + "Drag objects or data items onto the page, or start from a page template" + **Select a template** button | Data pane empty state: "To begin, add or import data." + Add data / Import data + Recently Used Data (5 links) |
| S3 | Report Editor — populated | Build and configure | Same, with objects on canvas | — | Object selection drives every right-pane tab |
| S4 | Report Editor — object maximized | Focus one object | Canvas fills; rails restricted | Data pane: "The Data pane is not available when an object is maximized" | Restore view via context menu |
| S5 | Report Viewer | Consume | Toolbar, page tabs, objects, optional side pane | Empty report: "No content to display." | Rails hidden; AI assistant icon disappears |
| S6 | Pop-up page (viewer) | Drill target | Modal with page name, ×, Close, Export as PDF, resize grip | — | Opened by **double-click** on a linked object |
| S7 | AI assistant side panel | Conversational help | Welcome, 3 starter chips (Add a data source / Add a visual / Help me get started), prompt box with attach, disclaimer | Welcome state is the empty state | "AI-generated content. Evaluate accuracy and suitability before use." |

#### C.2 Rail panes (left)

| Pane | Contents | Empty / special states |
|---|---|---|
| Data | Source dropdown + source-actions menu, search, **+ New data item**, tree grouped Category / Measure / Aggregated Measure with distinct counts and badges (sensitive-data shield, outlier dots), per-item hover **Edit properties** and right-click menus | No data → Add data / Import data + recent list. Maximized object → unavailable message |
| Objects | 10 groups: Tables (2), Graphs (30), Geo Maps (10), Controls (5), Analytics (6), Containers (5), Content (5), Statistics (8), Machine Learning (6), Objects With Data (1) = 78 + search; ⋮ → Expand/Collapse, Show or hide objects, Sort (Name ✓ / Recent), Show object groups, Reorder groups, Import custom graph | List scrolls back to top after each insert |
| Outline | Tree of pages → objects, **+ New Page**, delete (greyed with one page), filter, "Clear selection" | Single page → delete greyed |
| Suggestions | Live-rendered chart previews with captions, a **data-source combobox** (one source at a time), **Refresh** and **Add more suggestions** — both disabled until data is loaded. **No ⋮ pane menu** (the only pane without one). Batches of **4 or 5**, not the documented 4. Right-click a card: **Add to current page · Add to new page · Delete** | **Empty state is literally blank** (defect 48). Cards are nameless `<canvas>` to assistive tech (defect 49). See `visualizations.md` §G.2d for the generation engine |
| Report Review | Severity counters (High / Medium / Low), findings with per-item quick-fix ⋮, **Evaluate Performance** link, filter box, ⋮ (sort/filter/export) | "No issues need to be reviewed. However, some issues can be found only after evaluating the report's performance." |

#### C.3 Property panes (right)

| Pane | Scope selector | Sections |
|---|---|---|
| Options | Report / Page / each object, plus a **settings search box** | Report: General, Style (theme + palettes), Layout, Viewer Capabilities, Report Controls. Page: General, Style, Layout, Page Controls. Object: Object, Style, Layout, Graph Frame, type-specific (Bar, Crosstab, Pie, Slider…), Axes, Reference Lines, Legends, Cells, Cell Visualizations, Totals and Subtotals |
| Data Roles | object | Role groups with typed "+ Add" pickers; per-item right-click (Remove, Move to, Aggregation, Format, View data details) |
| Actions | page or object | Automatic actions on all objects (mode: One-way ✓ / Two-way / Linked selection), Object Links, Page Links, Report Links, URL Links, Parameter Links |
| Display Rules | object | Rule list grouped by scope; New rule dialog |
| Filters | object | Filter cards with per-filter ⋮ menu |
| Ranks | object | Rank cards (subset, count, rank-by, ties, All Other) |
| **Empty states** | — | Data Roles / Filters / Ranks with nothing selected: "Select an object to see its roles/filters/ranks." |

**Gating of toolbar commands — three independent causes (OBSERVED):** *content* (an empty report greys almost everything; adding data and one object enables Export, Copy link, embeddable markup, Distribute and Localize even while unsaved), *save* (About this report needs stored metadata), and *permission* (Share report was disabled in every state; on a saved report Copy link and Save a copy were disabled too). The UI never says which applies.

#### C.3b Viewer side pane, as seen on a production report (OBSERVED, session 6)

The viewer has its own reduced property pane, opened per object. It is **not** the editor's pane with controls removed — the disclosure differs, and in one respect it tells the reader more than it tells the author.

| Viewer pane | Contents observed | Notes |
|---|---|---|
| Data Settings | The object's role assignments, read-only (e.g. geo map: *Geography* = Supplier Country, *Color* = Average Products per Supplier, *Data tips* = three items) | Confirms the role catalogue holds in production: a geography item, a hierarchy in a category role, and an aggregated period calculation in a measure role all appear here |
| Display Rules | Doubles as the **legend** for the rule set; shows bands and placement ("Right of text, with Profit as x") | See `visualizations.md` §G.2b for the banded three-colour rule |
| Alert subscriptions | Present as a pane; not exercised | — |
| Filters | Split into two labelled groups: `Permanent Filters: None` and `Interactive Filters: Product Category = 'Clothes'` | **Asymmetric disclosure** — the editor's Filters pane hides filters arriving from controls and links; the viewer discloses them. The author is the one kept in the dark. See `interaction-model.md` §H.6 |
| Ranks | Plain sentence form ("Top 10 of City by Profit"), not the editor's card UI | — |
| Comments | Per-object (the pane carries its own object selector), **1,000-character limit** with a live remaining count, search affordance, empty state "No comments are available." | Not posted |

**Viewer toolbar undo is live and descriptive** — "Undo: Change Continent Selector from North America to Europe". Undo is not an authoring-only feature; the same mechanism and the same label grammar extend to consumption.

**Geo maps carry their own on-hover control cluster** — search, expand, layer selector, locate, zoom in / zoom out. This is the only object type observed with built-in zoom and pan; no other chart exposes viewport controls.

#### C.3c Viewer side pane, corrected across nine reports (OBSERVED, session 10)

| Fact | Detail |
|---|---|
| Tab names | The rail reads **Roles · Rules · Filters · Ranks · Comments**; the first pane's own header reads **"Data Settings"** — two names for one surface |
| Object selector | Hierarchical: report → group → objects. The group is the **data source** in one report (`Products`) and the **page** in others (`Page 1`, `Ungrouped Network Analysis`). The grouping level is not consistent |
| Report-level selection | Roles: *"Select an object to see its roles."* · Rules: a `Report` scope row |
| Rules tab | Holds **two sub-tabs**: **Display Rules** and **Alert subscriptions**. For **control objects only Display Rules appears** — alert subscriptions is object-type-conditional (corrects the session-6 note that it is a pane of its own) |
| Comments | Per object, **1,000-character limit** with live remaining count, search, empty state *"No comments are available."*, and **threaded replies** |

**The Filters pane has four kinds of section, not two (OBSERVED).**

| Section | Example |
|---|---|
| `Permanent Filters` | `None` on every object observed |
| `Interactive Filters` | `Continent Name = 'Asia'`, `Year = 2015` |
| One section **named after the data item**, holding the object's own filter | `Iris Species` → `In(Iris Species, 'Setosa', 'Virginica') OR Missing(Iris Species)` |
| An **object-type-specific** section | `Path Filter` → `PathContains(Grouped Pages, 'Buy')` |

The `… OR Missing(x)` form documented from the editor is confirmed verbatim in the viewer.

#### C.3d Report prompt bar (OBSERVED, session 10)

A report-scoped prompt strip sits **above the page tab strip**, with a **▲ chevron that collapses the whole strip**. One report carried three controls in a single row: a **button bar** (six continents, none selected), a **drop-down** showing the greyed placeholder `Facility Country`, and a **text input** with placeholder `Enter Facility City...`.

A drop-down control's value list carries **`Clear filter`** as its first entry — and a control marked **(required)** does **not** offer it. That is the cleanest expression of `required` in the product.

#### C.4 Dialog inventory (all observed; every one was cancelled)

| Dialog | Trigger | Required fields | Refusal behaviour observed |
|---|---|---|---|
| Choose Data | Add data / role "+ Add" with no source | table selection | "You must select an item." when a table is previewed but not selected |
| New Calculated Item | + New data item | Name*, valid expression | OK greyed until expression parses |
| Expression editor (also Advanced Filter, Apply data filter, Parameter value) | several | expression | Inline error count "(n)", red squiggle, gutter marker, messages such as "Unexpected >", type mismatch, "Division by zero is undefined." |
| New Hierarchy | + New data item | Name and items are marked required | **OK stays enabled with nothing entered and then does nothing, silently** |
| New Custom Category | + New data item | Name, groups | AI "Generate value groups" available for categories only |
| New Geography Item | + New data item | Name*, Based on*, Geography data source* | Fully exercised in session 14 — see below. With *Geographic data provider* chosen and none selected, **OK is visibly disabled** (not silently refused) |
| New Parameter | + New data item | Name, Type | — |
| New Partition | + New data item | Name*, percentages | Training 100 → "The value must be less than 100." |
| Custom sort | category right-click | ≥1 item | OK greyed at 0; **partial order accepted** |
| Format | Format ▸ / pencil | — | Width > 32 → "The value cannot be greater than 32." |
| New Scope | Calculated item Scope + | scope type | Custom intersection (default) / Grand total |
| New Display Rule | Display Rules + | operator + value | **Rule with no colour accepted, does nothing** |
| Add URL Link | Actions | URL | "Open URL" greyed until a URL is typed |
| **Open** (report browser) | ⋮ ▸ Open | a report selection | Left tree (Recent · My Favorites · My Folder · SAS Content · Shared with Me · Recycle Bin), results grid, right details panel with **Details / Comments** tabs and collapsible **Thumbnails · Properties · More**, Name field, Type selector. Empty state *"Select an item to see its information."* Refusal: **"You cannot select a folder for this operation."** Properties exposes a folder URI (`/folders/folders/<uuid>`) and a "modified by" line carrying the signed-in email address |
| **Outliers of \<measure\>** | View insights ▸ Analyze Objects for Impact ▸ Details | — | A generated narrative report in a modal: a headline count, a distribution strip with the outlier band highlighted, and an impact table **Product Line \| Including Outliers \| Excluding Outliers \| Outlier Impact \| Difference**. Ships an unfilled authoring placeholder (defect 42) and mixes formatted and raw numbers (defect 43) |
| **Scenario Analysis** | forecasting object ▸ What if ▸ | — | chart/table toggle · History cutoff slider · Adjust ▾ · Reset ▾ · Undo/Redo · **Apply** disabled until changed · resizable |
| **Goal Seeking** | forecasting object ▸ What if ▸ | — | as above plus **Bounds ▾** (Factor \| Lower Bound \| Upper Bound, default *Unbounded*) |
| Select a Template | empty page | template selection | **Single click does not select** → "You must select a template."; double-click applies |
| Manage Page Templates | template dialog | — | Vendor templates locked (badge); custom ones have Edit/Delete |
| Edit Playback | view ⋮ | seconds | min 3 / max 3,600 with explicit messages |
| Save confirmation | Close with unsaved changes | — | "Do you want to save '<name>' before it is closed?" → Save / Don't save / Cancel |
| Evaluate Performance gate | Report Review | saved report | "You must save a report before you can analyze its performance." |
| No Comparable Models | insert Model comparison | two comparable models | Blocking explanatory dialog on insert |

#### C.4b New Geography Item, in full (OBSERVED, session 14)

| Field | Detail |
|---|---|
| **Name\*** | prefilled `Geographic Item 1` |
| **Based on\*** | **all 57 columns** — categories, measures and dates alike, **not type-filtered** (defect 66). Note: *"The new geography item will be a duplicate of this item."* |
| **Geography data source\*** | three radios: *Geographic name or code lookup* · *Geographic data provider* · *Latitude and longitude in data* |
| Right panel | a **live validation panel**: `N% mapped`, a **Preview** selector (**Scatter** centroids / **Region** polygons), a rendered map, and the unmapped values |

**Name or code lookup** offers exactly ten vocabularies: Country or Region Names · ISO 2-Letter · ISO 3-Letter · ISO Numeric · SAS Map ID Values · Subdivision (State, Province) Names · Subdivision SAS Map ID Values · US State Names · US State Abbreviations · US ZIP Codes. **There is no city-level lookup and no non-US postal lookup** — city geography must come from coordinates or a custom provider.

**Geographic data provider** adds a provider dropdown (one entry in this deployment, *US County Data*), an **ID column** picker and a *Latitude/Longitude in data* checkbox; its ⋮ menu offers **New / Edit / Delete provider**, all greyed (defect 68), and the panel reads *"Mapping information not available."*

**Latitude and longitude in data** adds **Latitude (y)**, **Longitude (x)** — both **type-filtered** to the 37 numeric columns — and **Coordinate space**: **Web Mercator · World Geodetic System (WGS84) · British National Grid (OSGB36) · Singapore Transverse Mercator · Custom**. *Custom* exposes a **PROJ string** field with the inline example `+proj=longlat +datum=WGS84 +no_defs`, shown as an error before any input (defect 67).

**The validation panel is the best thing in the dialog** and is worth copying verbatim:

| Configuration | Result |
|---|---|
| `Based on` = a measure, lookup = Country Names | **0% mapped**, *"5 of 13 unmapped values: 10, 11, …"* |
| `Based on` = `Country`, lookup = Country Names | **86% mapped**, *"1 of 1 unmapped values: **England**"* |
| `Based on` = `City`, lat/long = `City_Lat`/`City_Long`, WGS84 | **100% mapped**, the unmapped list disappears |

On OK: `Undo: New geography item Geographic Item 1 on data RETAILDEMO_2`, and the Data pane grows a **third group, `Geography`**, alongside Category and Measure.

#### C.5 State catalogue (empty / loading / error / confirmation / selection)

| State | Where | Exact presentation |
|---|---|---|
| Empty page | Canvas | Illustration, "Design a Report", instruction line, Select a template |
| Empty object (no roles) | Any chart | **Renders synthetic placeholder data** ("Measure by Category", Category 1–3, axis 0–40) behind an "Assign data" button |
| Empty pane | Right rail | "Select an object to see its …" |
| Empty role picker | Geography role | "No data items available for role." |
| Loading — object | Object body | Centred spinner + "Loading…" |
| Loading — modal | Data operations | Blocking "Loading data…" overlay (outlived its own error during a failed join) |
| Row cap | Bar / word cloud | Tiny ⓘ bottom-right: "Only 3,000 rows of the data appear." / "Only 100 rows…" |
| Tie cap | Rank with ties | "Only some of the data appears because there are too many ties associated with the rank." |
| No data after filter | Any object | Axis frame retained + "No data matches the current filters." |
| Validation error | Text fields | Red field + message ("Required field", "The value must be at least 3.") |
| Silent rejection | Pie "Other" % = 101, forecast horizon 0/9999 | Field reverts, **no message, no undo entry** |
| Toast | Automatic actions on | "Actions were removed because they are not allowed with action mode One-way filters" + Undo |
| Selection | Chart mark | Mark highlighted; others dimmed; chip added to filter breadcrumb when enabled |
| Hover | Chart mark | Tooltip card with role/value pairs (e.g. "Region: ASIA / Frequency: 970") |
| Disabled | Menus, buttons | Greyed text `#C3C8D0`, no opacity change, still focusable |


---

<!-- ===== Source: activities.md ===== -->

## Activity Inventory and User Journeys

> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

### D. Activity Inventory

Each activity: purpose · entry · preconditions · inputs · steps · result · alternates · validation · errors · dependencies. All OBSERVED unless marked.

#### A1 — Create a report
- **Purpose:** start a new authoring document.
- **Entry:** Landing → "New report"; or editor ⋮ → New.
- **Preconditions:** authenticated session.
- **Inputs:** none.
- **Steps:** 1) Click New report. 2) Editor opens with an untitled report ("Report N", N increments per session) and one empty page.
- **Result:** unsaved report; Save enabled but Export/Share/Copy link/Evaluate Performance greyed until saved.
- **Alternates:** open an existing report; restore a recovered session.
- **Validation / errors:** none.
- **Dependencies:** none.

#### A2 — Add a data source
- **Purpose:** bind a table to the report.
- **Entry:** Data pane → Add data, or a "Recently Used Data" link, or any role picker when no source exists.
- **Preconditions:** a report is open.
- **Inputs:** table selection.
- **Steps:** 1) Open Choose Data. 2) Filter by Available (default) / Favorites / Recent, or search. 3) Select a table (checkbox). 4) Add.
- **Result:** Data pane lists columns grouped **Category / Measure**, each category showing its distinct count; the system adds **Frequency** (measure) and **Frequency Percent** (aggregated measure); sensitive-data shields and outlier dots appear.
- **Alternates:** Import data (upload); New data from join; New data from aggregation.
- **Validation / errors:** "You must select an item." if a table is only previewed. Search is slow and briefly shows "Results: 0".
- **Dependencies:** A1.

#### A3 — Add a visualization object
- **Purpose:** put a visual on the page.
- **Entry:** Objects pane (double-click or drag); Data pane item → "Add to current page"/"Add to new page"; **a multi-item drag from the Data pane** (select with Ctrl/Cmd+click or Shift+click, then drag — the resolver and its decision table are in `visualizations.md` §G.2e); Suggestions pane card; page template.
- **Preconditions:** a page exists. A data source is **not** required.
- **Inputs:** object type.
- **Steps:** 1) Double-click object. 2) Object appears with placeholder sample data + "Assign data".
- **Result:** object named `<Type> N`; after roles are filled the name becomes `<Type> - <first role item> N`; title follows data ("Frequency of Region").
- **Alternates:** "Change <type> to ▸" converts an existing object (43 targets offered, none greyed).
- **Validation / errors:** Model comparison refuses on insert with an explanatory dialog.
- **Dependencies:** A1. Real rendering needs A2.

#### A4 — Assign data to roles
- **Purpose:** bind columns to the object's visual channels.
- **Entry:** object "Assign data" button, or right rail → Data Roles.
- **Preconditions:** A2 + A3.
- **Inputs:** column per role.
- **Steps:** 1) Open Data Roles. 2) Click "+ Add" on a role. 3) Pick from a **type-filtered** list. 4) Repeat.
- **Result:** object queries and renders. Assigning only a category **auto-fills the required measure with Frequency**. Adding a real measure afterwards *sometimes* silently replaces Frequency and sometimes keeps it alongside — both were observed, so the rule is **UNKNOWN**; a rebuild should make the replacement explicit.
- **Alternates:** drag a data item onto the object; role item right-click → Remove / Move to / Aggregation / Format.
- **Validation:** single-item roles grey out "+ Add" after one item; multi-item roles use checkboxes. Pickers exclude incompatible types (Time axis = dates only; Measure roles = measures only).
- **Errors:** Geography role shows "No data items available for role." with no remedy offered.
- **Dependencies:** A2, A3.

#### A5 — Change a measure's aggregation
- **Purpose:** switch Sum to Average, Min, etc.
- **Entry:** Data pane item right-click → Aggregation ▸ (global default), or Data Roles item right-click, or column-header menu (object-level override).
- **Inputs:** one of 20 aggregations (Default (Sum) ✓, Sum, Average, Std dev, Std error, Variance, Count, Number missing, Minimum, Q1, Median, Q3, Maximum, Skewness, Kurtosis, CV, Uncorrected SS, Corrected SS, t statistic, p-value).
- **Result:** every dependent object, filter header and display rule follows the new aggregation.
- **Constraint:** **no distinct count** in this menu — only via the `Distinct()` function in a calculated item.
- **Dependencies:** A2.

#### A6 — Create a calculated item
- **Purpose:** derive a new column or aggregated measure.
- **Entry:** Data pane → + New data item → Calculated item.
- **Inputs:** Name*, expression.
- **Steps:** 1) Name it. 2) Build an expression from Operators / Functions / Data / New parameter (double-click inserts a skeleton). 3) Optionally add a **Scope** (aggregated items only). 4) OK.
- **Result:** item appears under Measure or Aggregated Measure; format auto-detected; **it is not added to any object automatically**.
- **Validation:** live error count "(n)", red squiggles, messages for syntax, type mismatch, aggregated-vs-row mixing and literal division by zero. OK greyed until valid.
- **Errors:** Results preview unavailable for aggregated measures; preview keeps the **last valid** result while text is invalid.
- **Dependencies:** A2.

#### A7 — Filter an object
- **Purpose:** restrict the rows an object sees.
- **Entry:** right rail → Filters → + New filter.
- **Inputs:** a column, then values/range.
- **Steps:** 1) Pick item (Advanced filter, object's own items, common filters, then all items). 2) Adjust checkboxes / range slider / histogram. 3) Optionally open ⋮ for condition type, missing-value handling, invert, sort, promote to common filter.
- **Result:** object re-queries; other objects untouched unless linked.
- **Defaults:** **Include missing values ✓**; condition "Is between (inclusive)" for numerics; detail (not aggregated) values; continuous for numerics, discrete for categories.
- **Alternates:** "Filter aggregated values" retargets the filter at the aggregate (header renames to "Sales (Average)"); Advanced edit writes the expression form.
- **Errors:** an inverted full selection yields "No data matches the current filters." with no warning.
- **Dependencies:** A4.

#### A8 — Rank (Top/Bottom N)
- **Purpose:** show only the leading or trailing members.
- **Entry:** right rail → Ranks → + New rank.
- **Inputs:** category, subset type, count, rank-by measure, ties, All Other.
- **Defaults:** Top count, **10**, rank-by = the object's measure, Ties ☐, All Other ☐.
- **Result:** applies immediately.
- **Observed quirks:** ranked bars are drawn **alphabetically, not in rank order**; **count 0 is accepted** and the chart silently keeps the previous result; Ties caps at **count + 100 tied rows** with a notice. Tie-breaking when Ties is off appeared to follow descending member name (**INFERRED — confidence: Medium**, from two samples).
- **Dependencies:** A4.

#### A9 — Add a prompt (control)
- **Purpose:** let a reader filter interactively.
- **Entry:** drop a category on the **report control strip** (filters all pages), the **page control strip** (filters the page), or the page body (filters nothing until linked).
- **Inputs:** a category (or measure/date for Slider).
- **Steps:** 1) Place the control. 2) Configure Options (Required, Initial value, multi-select, search, missing-values option). 3) For a body control, open Actions and tick target objects.
- **Result:** report/page controls filter automatically and **cascade into each other**; body controls need explicit links.
- **Types:** Drop-down list, Button bar, List, Slider, Text input. "Change to" converts between Drop-down, Button bar, Text input and Slider (List is not offered).
- **Validation:** Text input matches **exactly and case-sensitively** despite offering prefix suggestions; Slider **excludes missing values even at full range** unless its "Missing values option" is enabled.
- **Dependencies:** A2 + at least one target object.

#### A10 — Link objects (cross-filtering)
- **Purpose:** make one object drive others.
- **Entry:** right rail → Actions.
- **Two mechanisms:** (a) **Automatic actions on all objects** — page-wide mode: One-way filters ✓ / Two-way filters / Linked selection; (b) **Object Links** — per-target checkbox, each link typed Filter (default) or Linked selection.
- **Result:** selecting a mark filters or highlights targets; a breadcrumb bar shows removable chips when enabled.
- **Destructive side effect:** enabling automatic actions **deletes existing manual object links** (toast + Undo); disabling does not restore them. Page links survive.
- **Quirks:** Two-way mode makes a List control filter itself down to the chosen value; clicking the "All Other" bar **clears** the filter instead of filtering to the excluded members; linked filtering drops empty categories rather than showing zeros.
- **Dependencies:** ≥2 objects on a page.

#### A11 — Drill to another page (page link)
- **Purpose:** detail-on-demand.
- **Entry:** Actions → Page Links → tick a target page.
- **Preconditions:** ≥2 pages.
- **Result:** in **view mode**, a **double-click** on a mark opens the target; a single click only selects. A Pop-up page opens as a modal; a Basic page switches tabs.
- **Options:** per-link ⋮ → "Set prompt bar values of target page" ☐.
- **Dependencies:** A12.

#### A12 — Manage pages
- **Entry:** page tab "+", page tab ⋮, or Outline pane.
- **Actions:** Rename, Page type (Basic ✓ / Hidden / Pop-up), Limit visibility to users, Delete, Duplicate, Export as PDF, Copy link, Copy embeddable markup, Collapse/Expand controls, Save as page template, Manage page templates.
- **Constraints:** **Hidden and Pop-up are greyed when only one page exists**; Delete greyed likewise; export/link/template items greyed on an unsaved report. Both Hidden and Pop-up undo as "Hide page".
- **Dependencies:** A1.

#### A13 — Apply a page template
- **Entry:** empty page → Select a template; or page ⋮ → Manage page templates.
- **Steps:** 1) Open dialog (list ✓ / grid toggle, filter). 2) **Double-click** a template.
- **Result:** inserts a laid-out section of placeholder objects; a dashboard template also turns on the filter breadcrumb. Undo label "Add section with template".
- **Validation:** single click highlights only → "You must select a template."
- **Dependencies:** A1.

#### A14 — Style an object / report
- **Entry:** right rail → Options.
- **Inputs:** theme (Dark / Light ✓ / High Contrast / custom), font (38 families), fill and line palettes, **dedicated Missing colour**, **Other colour**, padding, borders, axis settings, legend placement (9-point), data skins, abbreviation scale and precision.
- **Result:** applied live.
- **Quirk:** crosstab display-rule text defaults to a different font from the report font.
- **Dependencies:** A3.

#### A15 — Add a display rule (conditional formatting)
- **Entry:** right rail → Display Rules → + New rule.
- **Inputs:** target item, operator (=, <>, ≤x≤, <, <=, > ✓, >=, Missing, NotMissing), value (constant **or another measure**), style.
- **Result:** colours marks/cells; in view mode the Display Rules pane doubles as the legend.
- **Quirks:** **a rule with no colour is accepted and does nothing**; rules test the **displayed aggregated value**; with no intersections chosen a crosstab rule also colours subtotal rows.
- **Dependencies:** A4.

#### A16 — Switch to view mode / consume
- **Entry:** pencil toggle or ⋮ → View report.
- **Result:** rails hidden; only Basic pages get tabs; selections made in edit mode carry over; AI assistant icon disappears; ⋮ gains Play report and Edit playback.
- **Side pane tabs:** Data Settings (read-only roles), Display Rules (legend + Alert subscriptions), Filters (**Permanent** and **Interactive**, showing real logic such as `BetweenInclusive(x, MIN, MAX) OR Missing(x)`), Ranks (plain sentence), Comments.
- **Errors:** Comments refuse until the report is saved.
- **Dependencies:** A1.

#### A17 — Save / close
- **Entry:** Save button, ⋮ → Save / Save as / Close.
- **Result:** closing an unsaved report raises a three-way confirmation (Save / Don't save / Cancel).
- **Gated by save:** Export, Share, Copy link, Copy embeddable markup, Distribute, Localize, Comments, Evaluate Performance, page Export/Copy link/Save as template, About this report.
- **Dependencies:** A1.

#### A18 — Review report quality
- **Entry:** rail → Report Review.
- **Result:** findings by severity (High / Medium / Low counters) with per-finding quick fixes ("Remove the data source …"); filter by Accessibility / Performance; sort by severity; export as PDF.
- **Gate:** Evaluate Performance requires a saved report.
- **Dependencies:** A1.

#### A19 — Use auto-suggestions
- **Entry:** rail → Suggestions. Requires a data source; both controls are disabled until one is loaded, and the empty pane shows **no text** (defect 48).
- **Steps:** pick a data source in the pane's combobox → a batch of **4 or 5** cards generates automatically → **Refresh** replaces the batch, **Add more suggestions** appends another → insert by **double-click**, drag, or right-click ▸ *Add to current page* / *Add to new page*; dismiss with right-click ▸ *Delete*.
- **Result:** an object with its required roles and data tips filled, its optional grouping/colour role empty, and a descriptive undo entry. The inserted card leaves the list and is replaced; a deleted card is not replaced and **cannot be undone** (defect 50).
- **Validation:** none. Cards that render nothing are still offered (defect 56).
- **Risk:** the engine is a fixed slot rotation with randomised columns (`visualizations.md` §G.2d) — statistically meaningless suggestions are structural, not occasional. It also ignores the Data pane selection and the report's existing content (defects 51, 52).
- **Dependencies:** A2.

#### A20 — Ask the AI assistant
- **Entry:** banner icon (edit mode only).
- **Result:** side panel with starter chips, prompt box with attachment, AI disclaimer. First open shows an English-only notice with "Don't show this message again".
- **Dependencies:** A1. Effect of prompts: **UNKNOWN** (never sent).

---

### E. User Journeys

**J1 — First report, end to end (OBSERVED)**
```
Landing → New report → Data pane → Add data / Recently Used → choose table
  → Objects pane → double-click object (renders placeholder sample)
  → Assign data → role "+ Add" → pick column (measure auto-fills as Frequency)
  → Options → title, style, axes        → Filters → + New filter
  → Ranks → Top N                        → Actions → link objects
  → page tabs "+" → second page → page type Pop-up → Page Links
  → pencil toggle → view mode → verify → Save
```

**J2 — Analyse without authoring (OBSERVED):** `Landing → open report → view mode → controls/prompts → click marks → breadcrumb chips → double-click to drill into pop-up → side pane Filters to read the logic`.

**J3 — Prepare data inside a report (OBSERVED):** `Data pane → + New data item → Calculated item → expression editor → (Scope) → OK → item appears in Data pane → drag to object`. Variants: Custom category (with AI group generation), Hierarchy, Date hierarchy (instant, no dialog), Geography item, Parameter, Partition, New aggregated data (instant, creates a second source), New data from join (timed out in testing).

**J4 — Model a target (OBSERVED):** `Objects → Statistics/ML object → Response + Predictors → model runs immediately → read Fit Summary / Residual / Odds Ratio / Confusion Matrix → (Create pipeline, not exercised)`. Models disclose dropped rows ("Observations: 646K of 2.3M").

**J5 — Build an interactive dashboard (OBSERVED):** `New page → Select a template (Dashboard) → placeholders → assign data to each → add report/page controls → Actions → Automatic actions on all objects → choose mode → verify breadcrumb`.

**J6 — Recover an interrupted session (OBSERVED):** `Landing shows "Recovery available for previous session" → Restore previous session`. Unsaved editor state is persisted server-side (see Section N/K: `POST /files/files` then `PATCH`). **INFERRED — confidence: High.**


---

<!-- ===== Source: components.md ===== -->

## Component Inventory

> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

### F. Component Inventory

| Component | Purpose | Location | Variants | States | Inputs | Outputs | Interactions | Responsive |
|---|---|---|---|---|---|---|---|---|
| App banner | Global identity + system actions | Top, full width, 38px | one | static | — | menu opens | click; opens side panels | Fixed height (UNKNOWN below 768px) |
| Report toolbar | Document-level actions | Below banner, 44px | edit / view variants | enabled, disabled (unsaved report) | — | commands | click; ⋮ opens menu | Fixed |
| Icon rail | Switch left panes | Left, 34px | 5 tabs; labels can be shown | selected, hover, focus ring | — | pane change | click; "»" toggles labels | Fixed |
| Side pane (left/right) | Hold panes | 338px left, 384px right | pinned / unpinned | pinned, auto-collapse | — | — | pin icon; collapse chevron; auto-collapse on canvas click | Fixed widths |
| Pane header + ⋮ | Pane-level config | Top of each pane | — | — | — | menu | click | — |
| Search / filter box | Narrow lists | Data, Objects, Options, Filters, dialogs | plain | empty, typing, cleared | text | filtered list | live filter; **text can persist across dialogs (defect)** | — |
| Data item row | Represent a column | Data pane | category / measure / aggregated / date / geography | default, hover (reveals Edit properties), **selected (a checkbox appears on every row once anything is selected, and the pane grows a `Clear selection (n)` link stating the count)**, badged (sensitive, outlier) | — | selection | click selects one; **Ctrl/Cmd+click toggles; Shift+click ranges**; selections span the Category/Measure groups and survive virtualised scrolling; right-click (20+ actions); hover card; **drag — single or multi-item** | `aria-selected` is lost for rows scrolled out of the virtualised list (defect 62) |
| Inline property editor | Rename/reclassify | Data pane | measure / category / date variants | expanded | name, classification, format, aggregation | item update | pencil toggles | — |
| Object library list | Insert objects | Objects pane | grouped, sortable | — | — | insert | double-click, drag | Scrolls to top after insert (defect) |
| Canvas | Host objects | Centre | page-scoped | empty, populated, maximized | drops | layout | drag, drop, resize handles, right-click | Scrolls; "Avoid scrollbars" option |
| Page tab strip | Switch pages | Above canvas | Basic / Hidden / Pop-up (eye-slash icon) | active, inactive | — | page change | click, ⋮ menu, "+" | Disappears in view mode when only one Basic page |
| Object frame | Wrap a visualization | Canvas | any object type | default, selected (border + handles), hover (⋮ + maximize), maximized, loading, error, capped | roles | queries | click, double-click, right-click, drag, resize, maximize | Extend/shrink width and height flags |
| Chart canvas | Render marks | Inside object frame | 30 graph types + 10 geo | placeholder, rendered, empty, capped | query result | pixels | hover tooltip, click select, double-click drill; **rendered to `<canvas>`**: the wrapper carries `role="application"` and a descriptive `aria-label` ("Frequency of Region, Bar chart"), but **no data values reach the DOM or the accessibility tree** | Redraws on resize |
| Data grid (crosstab / list table) | Tabular display | Inside object frame | crosstab (nested) / list table | with/without totals, row numbers, cell visualizations | rows | — | header menu (sort, aggregation, format, calculation), column resize, scroll | Fit columns to width ✓ |
| Role group | Bind columns | Data Roles | single-item / multi-item | required (red *), filled, greyed after limit | picks | assignment | "+ Add", right-click, drag | — |
| Type-filtered picker | Choose a column | Role "+ Add" | "Add Data Item" (single) / "Add Data Items" (multi, checkboxes) | empty ("No data items available for role.") | selection | assignment | click / check + Apply | — |
| Filter card | Constrain data | Filters pane | category (checkbox list + frequency bars), numeric (histogram slider), date (range slider) | default, edited, inverted, empty-result | values | filter | drag handles, check, ⋮ menu | — |
| Rank card | Top/Bottom N | Ranks pane | count / percent | — | count, measure | subset | selects + numeric entry | — |
| Control (prompt) | Reader-facing filter | Report strip / page strip / body | Drop-down, Button bar, List, Slider, Text input | required, empty, selected, cleared | user choice | filter or parameter | click, type, drag handles | Button bar overflows with arrows |
| Filter breadcrumb | Show active filters | Top of page | — | none / chips | — | remove filter | click chip ×, expand range chip | — |
| Property section | Group settings | Options pane | collapsible | expanded, collapsed, greyed | — | setting | chevron, controls | — |
| Dropdown / combobox | Choose a value | Everywhere | plain select, editable combo, colour picker, 9-point placement picker, dual-list picker | open, closed, typing, greyed | — | value | click; **Esc inside a dialog's dropdown closes the whole dialog (defect)** | — |
| Dual-list picker | Move items | Hierarchy, Custom sort, Show/Hide, Scope | — | — | selections | ordered list | arrows, double-click, reorder buttons | — |
| Expression editor | Author logic | Calculated items, filters, parameters | full / single-line | valid, invalid (count + squiggle), empty | text | expression | toolbar inserts skeletons; ⓘ popovers (**don't auto-close**) | Resizable split with Results grid |
| Results preview grid | Validate an expression | Expression editor | — | shows last valid result while invalid; "not available for aggregated measures" | — | rows | scroll | — |
| Modal dialog | Focused task | Overlay | small / large / blocking notice | — | fields | commit | OK/Cancel; × ; Esc | Centred, resizable (pop-up page) |
| Toast | Report a side effect | Bottom-left | with Undo | transient | — | undo | click Undo | — |
| Tooltip / hover card | Explain | Charts, data items, ⓘ icons | data tip / lineage card / help popover | — | — | — | hover or click | — |
| Context menu | Object/item actions | Right-click | object, data item, page tab, column header, canvas | items enabled/greyed, submenus | — | command | right-click; hover for submenu | Long menus scroll |
| Counter chips | Severity summary | Report Review | High / Medium / Low | 0..n | — | filter | click | — |
| Thumbnail card | Suggest or open | Suggestions, Landing | **suggestion card** (live `<canvas>` preview + caption + `••••` drag handle) / report card | no hover affordance at all — no ⋮, no insert button, no tooltip; caption truncates with no title | — | insert or open | **double-click inserts**; drag; right-click → Add to current page / Add to new page / Delete | Grid reflows |
| Container | Group objects in one frame | Canvas | Precision, Stacking (button-bar navigated), Tab, Prompt | empty (drop target), populated, one child visible (stacking/tab) | dropped objects | layout + navigation | **accepts objects by drag only** — double-click appends to the page instead (defect 27); the navigation control switches which child is visible | Children inherit the container box |
| In-object tab strip | Switch views of one analytic model | Inside an analytic object's frame | Decision tree: Decision Tree / Icicle / Variable Importance / Assessment | selected, scrollable | — | view change | click; ‹ › arrows scroll the strip | Arrows appear when the strip overflows |
| Model header line | State what the model fitted | Top of an analytic object | — | — | — | — | **Fit ▾** opens a criterion selector | Wraps |
| Viewport control cluster | Zoom and pan a free 2-D object | On hover, under ⋮ and maximize | map / network / path | shown on hover | — | viewport | fit, pan, zoom in, zoom out | — |
| Report prompt bar | Report-scoped controls | Above the page tab strip | any control types, in one row | expanded, **collapsed via ▲**, horizontally scrolled when narrow | user choices | report filters/parameters | click, type; ‹ › on an overflowing button bar | **Scrolls sideways; never stacks** |
| Insight popover | Flag outlier-driven numbers | Anchored to the viewer toolbar | — | idle, analysing (determinate bar), result | — | per-measure impact list | "Analyze Objects for Impact", then Details | — |
| What-if modal | Explore a forecast | Overlay | Scenario analysis / Goal seeking | Apply disabled until changed | dragged points, Adjust values, Bounds | revised forecast | drag points, Adjust ▾, Reset ▾, Bounds ▾ | Resizable |
| AI panel | Assistive chat | Right overlay | — | welcome, conversation | prompt | response | chips, type, attach | ~460px overlay |

**Stacking Container as the sanctioned "same chart, different measure" pattern (OBSERVED, session 6).** A production report offered an "Orders | Profit" toggle that looked like a parameter swapping a measure. It is a Stacking Container holding **two complete bar charts**, with a button bar navigating between them. Cost: one whole object per variant, each with its own roles and its own rank. A rebuild that supports a measure parameter directly would undercut this.

**Not present (OBSERVED absence):** breadcrumb navigation for pages, pagination controls (grids scroll virtually), a command palette, and any documented keyboard-shortcut surface (Help has no shortcut reference).


---

<!-- ===== Source: visualizations.md ===== -->

## Visualization Inventory

> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

### G. Visualization Inventory

#### G.1 Full role catalogue (78 objects; `*` = required)

**Tables**

| Object | Required | Optional |
|---|---|---|
| Crosstab | Measures* | Columns, Rows |
| List table | *(none — the only object with no required role)* | Columns, Hidden |

**Graphs (30)**

| Object | Required | Optional |
|---|---|---|
| Bar chart | Category*, Measure* | Group, Lattice columns, Lattice rows, Data tip values, Animation, Hidden |
| Box plot | Measures* | Category, Lattice columns, Lattice rows |
| Bubble change plot | X start*, X end*, Y start*, Y end*, Size start*, Size end*, Group* | — |
| Bubble plot | X axis*, Y axis*, Size* | Group, Color, Lattice ×2, Data tip values, Animation, Hidden |
| Butterfly chart | Category*, Measure (bar)*, Measure (bar 2)* | Data tip values, Hidden |
| Comparative time series | Time axis*, Measure (TS1)*, Measure (TS2)* | Data tip values, Hidden |
| Correlation matrix | Measures* | option: within one set (default) / between two sets |
| Dot plot | Category*, Measure* | Lattice ×2, Data tip values, Hidden |
| Dual axis bar | Category*, Measure (bar)*, Measure (bar 2)* | Lattice ×2, Data tip values, Animation, Hidden |
| Dual axis bar-line | Category*, Measure (bar)*, Measure (line)* | as above |
| Dual axis line | Category*, Measure (line)*, Measure (line 2)* | as above |
| Dual axis time series | Time axis*, Measure (line)*, Measure (line 2)* | Data tip values, Hidden |
| Gauge | Measure* | Target, Group, Data tip values, Hidden |
| Heat map | Axis Items*, Color* | — |
| Histogram | Measure*, Frequency* | — |
| Key value | Measure* | Lattice category, Data tip values, Hidden |
| Line chart | Category*, Measure* | Group, Lattice ×2, Data tip values, Animation, Hidden |
| Needle plot | X axis*, Y axis* | Group, Lattice ×2, Data tip values, Hidden |
| Numeric series plot | X axis*, Y axis* | Group, Label, Lattice ×2, Data tip values, Hidden |
| Parallel coordinates | Variables* | — |
| Pie chart | Category*, Measure* | Group, Lattice ×2, Data tip values, Animation, Hidden |
| Scatter plot | Measures* | Color, Lattice ×2, Data tip values, Data labels, Hidden |
| Schedule chart | Task*, Start*, Finish* | Group, Label, Lattice ×2, Data tip values, Hidden |
| Step plot | X axis*, Y axis* | Group, Label, Lattice ×2, Data tip values, Hidden |
| Targeted bar | Category*, Measure*, Target* | Lattice ×2, Data tip values, Animation, Hidden |
| Time series plot | Time axis*, Measure* | Group, Data tip values, Hidden |
| Treemap | Tile*, Size* | Color, Data tip values, Hidden |
| Vector plot | X axis*, Y axis*, X Origin*, Y Origin* | Color, Group, Lattice ×2, Data tip values, Hidden |
| Waterfall | Category*, Measure* | Lattice ×2, Data tip values, Hidden |
| Word cloud | Word*, Size* | Color, Data tip values, Hidden |

**Geo maps (10)** — roles are grouped per map layer. The ten library entries are **Geo bubble · cluster · contour · coordinate · line · line-coordinate · network · pie · region · region-coordinate**, while the object’s own *Change type* dialog offers **seven** layer types — the two extra entries (`line-coordinate`, `region-coordinate`) are **composites**, so a geo object carries a **layer stack**, not a single layer (OBSERVED, session 15; refines §G.2g).

| Object | Required | Optional |
|---|---|---|
| Geo bubble | Geography*, Size* | Color, Data tip values, Data label, Hidden, Animation |
| Geo cluster | Geography* | Size, Color, tips, label, Hidden |
| Geo contour | Geography*, Color* | — |
| Geo coordinate | Geography* | Size, Color, tips, label, Hidden, Animation |
| Geo line | Geography* | Width, Color, Pattern, tips, label, Hidden, Animation |
| Geo line-coordinate | Line layer Geography*, Scatter layer Geography* | per-layer extras |
| Geo network | Source*, Target* | Size, Color, Link width, Link color, Label, tips |
| Geo pie | Geography*, Measure*, Category* | Size, tips, label, Hidden, Animation |
| Geo region | Geography*, Color* | tips, label, Data values, Hidden, Animation |
| Geo region-coordinate | Region layer Geography*+Color*, Scatter layer Geography* | per-layer extras |

**Controls (5)** — Button bar / Drop-down list / List: Category* (+ Measure, Hidden). Slider: Measure or Date* (single). Text input: Category* (+ Measure, Hidden).

**Analytics (6)** — Automated explanation (Response*, Underlying factors*, +Time); Automated prediction (Response*, Underlying factors*); Forecasting (Time axis*, Measure*, +Underlying factors); Network analysis (Source*, Target* + 6 optional); Path analysis (Event*, Sequence order*, Transaction identifier*, Weight*); Text topics (Document collection*, +Document details).

**Statistics (8)** — optional roles differ per object, so do not apply a blanket list:

| Object | Required | Optional |
|---|---|---|
| Cluster | Variables* | *(none)* |
| Decision tree | Response*, Predictors* | Partition ID, Frequency, Weight, Node details |
| Generalized additive model | Response*, Spline effects* | Continuous effects, Classification effects, Interaction effects, Partition ID, Frequency, Weight, Offset |
| Generalized linear model | Response* + at-least-one-of Continuous*/Classification*/Interaction* effects | Partition ID, Group by, Frequency, Weight, Offset |
| Linear regression | Response* + at-least-one-of the three effect roles* | Partition ID, Group by, Frequency, Weight |
| Logistic regression | Response* + at-least-one-of the three effect roles* | Partition ID, Group by, Frequency, Weight, Offset |
| Model comparison | *(refuses on insert without two comparable models)* | — |
| Nonparametric logistic regression | Response*, Spline effects* | Continuous, Classification, Interaction effects, Partition ID, Frequency, Weight, Offset |

**Machine Learning (6)** — all require **Response* + Predictors***; optional roles differ:

| Object | Optional |
|---|---|
| Bayesian network | Partition ID |
| Factorization machine | *(none)* |
| Forest | Partition ID, Frequency, Weight |
| Gradient boosting | Partition ID, Frequency, Weight |
| Neural network | Partition ID, Weight |
| Support vector machine | Partition ID |

**Containers (5)** and **static Content (Image, Job content, Web content)** — "Roles are not supported for the selected object." **Data-driven content:** Variables*, Parameters. **Text:** Measures, Parameters (both optional).

**Objects With Data (1)** — a saved, pre-built component ("customized loyality template" in the test environment): inserts a whole laid-out container with its own bound data source. **Caution observed:** inserting it silently removed the report's unused existing data source, and undoing it left the report with no data at all. A rebuild should never mutate other data bindings when inserting a saved component.

*Group totals: 2 + 30 + 10 + 5 + 6 + 5 + 5 + 8 + 6 + 1 = **78** visible objects. The Show/Hide Objects dialog counts 79; the extra one was never located in the tree.*

#### G.2 Per-visualization detail (the ones exercised with real data)

**Bar chart** — geometry: rectangles from a fixed baseline; horizontal by default with Y reversed so the first category sits at the top. Axes: measure axis auto-scales and relabels ("Sales (millions)"); category axis thins labels via "Fitting steps: Drop some". Legend: only with Group; 9-point placement, default Bottom. Tooltip: one row per assigned role plus Data tip values. Data labels and segment labels off by default. Colour: single accent when ungrouped, categorical palette by Group. Sort: descending by measure when the measure is Frequency; **reverts to alphabetical if the sorted measure is removed**. Filtering: own filters + incoming links. Zoom/pan: none; an optional **Overview axis** adds a brushable mini-chart. Selection: click toggles a mark; double-click triggers page links. Aggregation: per measure. Cap: **3,000 rows** with ⓘ. Empty: "No data matches the current filters."

**Crosstab** — nested row and column headers; borders on; alternating row background; condensed rows; fit columns to width. Totals and Subtotals off by default, placed **Before** (above) their group when enabled, scoped Rows/Columns/Both, per measure. **All totals and subtotals are recomputed from source rows at their own level, never from displayed cells.** Verified for **Average on both axes** (row subtotals and nested column subtotals each matched an independently computed source-level average). A distinct-count **grand total** was verified separately on a single-level rows-only crosstab (213 true distinct cities, versus 218 if the per-region counts were summed); distinct count in *nested column* subtotals was **not** tested. Cell visualizations (bar or heat map, left/right/replace) **are not drawn on total rows**. Column-header menu: sort, replace, remove, explain, aggregation, format, create calculation, cell visualization, indent, hide totals, row numbers, abbreviate.

**Pie chart** — donut by default (ring width 30%, start 90°, counterclockwise), centre total label. **Automatically buckets small members into a grey "Other" slice below 4%**; setting 0% draws every member with repeating colours; 101 is silently rejected.

**Word cloud** — caps at **100 rows** with ⓘ.

**Time series plot** — binning interval Automatic / Fixed count / **Use format** ✓; optional logarithmic scale and overview axis; no period-over-period options on the object itself.

**Forecasting** — confidence interval 95%, horizon 6 periods, shaded band after a divider; horizon 0 and 9999 are silently rejected.

**Logistic regression** — runs when any one starred effect role is filled; auto-picks an event level (chose a 10.38% class, neither majority nor rarest); fit statistic default KS (Youden) from a list of ~20, each with an inline definition; panels: Fit Summary, Residual Plot, Odds Ratio Plot, Confusion Matrix; **discloses dropped rows** ("Observations: 646K of 2.3M").

**Slider control** — range (default) or single value; horizontal or vertical; snaps to integers; **excludes missing values even at full range** unless "Missing values option" is on; its bounds are silently clamped when a cross-filter narrows the data.

#### G.2b Roles and options exercised in session 7 (OBSERVED)

**Lattice columns / rows** — a multi-item role (checkbox picker + Apply). Turns the object into a panel grid, one panel per value, sharing the category axis; panel headers truncate without a tooltip; the lattice item is auto-added to Data tip values. **Applying a lattice silently re-sorts the chart from value order to alphabetical.**

**Reference lines** — Options → Reference Lines → + New reference line creates one instantly with a computed default value. Settings: Label, Value, Axis (fixed to the measure axis), Line style (pattern, width 1–6, colour). **Value accepts only a typed constant or a parameter** — there is no mean/median/percentile option. Lines are drawn in every lattice panel.

**Parameters** — created from the Data pane or inline from any control that accepts one. The dialog is context-sensitive: created from a reference line it **locks Type to Numeric and disables "Multiple values"**; created from the Data pane it offers Character / Numeric / Date / Datetime. A control writes to a parameter through **Actions → Parameter Links** (a slider exposes *range start* and *range end* separately). Verified loop: slider → parameter → reference line, updating live.

**Containers** — Stacking renders its children as a tab strip with ‹ › arrows (the mechanism behind a "same chart, different measure" switcher). **Objects must be dragged in; double-click appends to the page instead.** Containers cannot be action sources ("Actions cannot be created from the selected object").

**Geography items** — the prerequisite for all 10 geo maps. The creation dialog previews a map with a **match rate ("86% mapped")** and names the failures ("1 of 1 unmapped values: England"); the rendered map repeats the warning in an ⓘ ("No matches were found for supplied geography data items: England."). Once created, the item appears in the Geography picker and the map renders.

**Multiple measures and axis ranges (OBSERVED)** — a second measure produces side-by-side panels, each independently scaled. **X Axis Range**: *Different per cell* (default) / *Same within each column* / *Same for all cells*. A shared scale across measures of different magnitudes makes the smaller series invisible without warning.

**Custom sort (OBSERVED)** — defined on the data item, but applied only when the object sorts **by that category**. Listed values come first in the defined order; unlisted values fall back to alphabetical. The object's sort menu gives no indication that a custom order exists.

**Insights (OBSERVED)** — the toolbar's "Insights were found" opens an **Outliers** advisor naming the measures that may be skewed, with an "Analyze Objects for Impact" action. It is a data-quality advisor, not narrative insight.

**View source table (OBSERVED)** — raw row-level viewer with column-type icons, a row/column count, and an explicit banner when the table exceeds the in-memory threshold: "Some features are not available due to the large size of the table."

**Automatic chart selection (OBSERVED, session 9)** — dropping items on the canvas resolves to a type by classification alone:

| Items | Result |
|---|---|
| 1 category (any cardinality) | Bar chart |
| 1 measure | Histogram |
| 1 date | Time series plot |
| 1 category + 1 measure | Bar chart |
| 2, 3 or 4 measures | Scatter plot — **read from the undo entry; see the caution below** |

Cardinality is **not** considered: a 748K-distinct identifier column produced a bar chart truncated at the row cap.

> **Caution on the multi-measure rows (added session 13).** The undo entry for a multi-measure drop names **Scatter** even when the object built is something else — verified three times (2 measures → *Heat map*, 3 measures → *Heat map*, 4 measures → *Correlation matrix*), each confirmed from the object's own name in the Data Roles pane. If the original reading of this row came from the undo label rather than the object, "Scatter plot" is wrong here too (INFERRED — confidence Medium; the original trial was not repeated). The verified multi-item drop behaviour is in §G.2e.

**The vendor guide's "four measures → correlation matrix" example does reproduce — on the drop path (OBSERVED, session 13).** Four measures dragged together onto an empty canvas build a **Correlation matrix**. The earlier "did not reproduce" note applied to the single-item automatic-chart path and was stated too broadly; see §G.2e and §P.3.

**Display rules as banded ranges (OBSERVED on a production report, session 6)** — beyond single-operator conditions, a rule set can be a series of value bands, each with its own colour, rendered as a **miniature gauge inside the cell**:

| Band | Colour | Placement |
|---|---|---|
| −600,000 ≤ x < 0 | red | "Right of text, with Profit as x" |
| 0 ≤ x < 400,000 | yellow | same |
| 400,000 ≤ x ≤ 900,000 | green | same |

In the viewer, the Display Rules pane doubles as the **legend** for these bands. A negative value renders red within the same left-anchored track rather than extending left of a zero baseline.

#### G.2c Analytic and custom objects, read from production reports (OBSERVED, session 10)

Eight favorited reports were opened read-only in the viewer and every object's roles were read from the side pane. These are the first observations of the analytics group with real data.

| Object | Roles as configured | Notes |
|---|---|---|
| **Geo network** | Source `from_loc` · Target `to_loc` · Size `MaxWind` · Color `Category` | A network drawn **on a map**: nodes are geographic points, links follow the Source→Target pair. Carries the map's own viewport controls |
| **Network analysis** (hierarchy form) | **Levels** `Type - DriveTrain - Make` (a hierarchy) · Color `Origin` | The role catalogue lists Source*/Target* as required. A **second form takes a hierarchy in a single `Levels` role** and derives the edges from it — the catalogue entry is incomplete |
| **Path analysis** | Event `Grouped Pages` · Sequence order `time` · Transaction identifier `id` · Weight `purchase` | Renders as a multi-column flow diagram. Has viewport controls |
| **Decision tree** | Response `Iris Species` · Predictors (4 measures) | See the in-object tab strip below |
| **Forecasting** | Time axis `Transaction Date` · Measure `Sales Rep Actual` · Underlying factors `Market Penetration`, `Order Marketing Cost` | **Two factors assigned, one used.** Only `Order Marketing Cost` appears as a panel, in the Reset menu and in the Bounds table — the model selects its own factors and the UI shows only those, without saying so (INFERRED — confidence Medium) |
| **Custom graph** (`Custom Bar Line Graph_solution`) | **Shared Category** `Transaction Month` · **Shared Measure** `Profit` · **Line Grouping** `Product Brand` | See below — the most structural finding in the bundle |

**Custom templates extend the role catalogue at runtime (OBSERVED).** A custom graph's object type *is the template's name*, and its roles are *author-named* — "Shared Category", "Shared Measure", "Line Grouping" appear in no built-in object. It rendered as a two-cell stack: an upper cell of two dotted series lines sharing one axis, a lower cell of bars, one shared category axis, independent value axes, one merged legend.

> **Consequence for the rebuild: role schemas must be data, loaded per object type, never hardcoded per chart class.** The 78-object catalogue in G.1 is a shipped default set, not a closed universe.

**Analytic objects nest their own tab strip (OBSERVED).** The decision tree renders a model header —

> **Decision Tree of Iris Species** · Event: **Virginica** · Fit: **False Positive Rate 0.020 ▾** · Observations: **100 of 100**

— above an in-object tab strip with ‹ › scroll arrows: **Decision Tree · Icicle · Variable Importance · Assessment**, each a different rendering of the same fitted model. No other object type nests tabs inside its frame. The `Observations: 100 of 100` line is the clearest row-count disclosure anywhere in the product (compare Strength 5).

**Forecasting is a what-if environment, available to readers (OBSERVED).** The object renders actual points, a model line and a **confidence band past a vertical forecast divider**, with each underlying factor in its own stacked panel below. Its top-right carries **What if ▾**:

| Mode | Surface |
|---|---|
| **Scenario analysis** | Modal: chart/table view toggle · **History cutoff** slider · **Adjust ▾** · **Reset ▾** · Undo/Redo · **Apply** (disabled until something changes). Editable points sit on the **factor** series |
| **Goal seeking** | The same, plus **Bounds ▾**. Editable points sit on the **target** series instead — you set the goal, it solves for the factor |

*Adjust* offers **Set all to constant value · Add value to all · Add percentage to all · Progressively add value**, with a numeric Value field. *Reset* offers **Factor: \<name\>** and **Reset all**. *Bounds* is a table **Factor | Lower Bound | Upper Bound**, both defaulting to **Unbounded**. Apply was never pressed.

**Viewport controls are not a map exclusive (OBSERVED — corrects session 6).** Path analysis exposes the same on-hover cluster (fit · pan · zoom in · zoom out) under its ⋮ and maximize. The rule is geometric, not type-specific: objects laid out in a **free 2-D space** (map, network, path) get viewport controls; objects on a **category/value grid** do not.

**Path analysis discloses fabricated ordering (OBSERVED).** A footer ⓘ reads *"An artificial sequence order was generated for 6 paths that contains simultaneous events."* The product tells the reader it invented ordering where the data had ties — the disclosure discipline the rest of the product lacks (compare defects 2, 3, 7, 8). The sentence is also ungrammatical.

**An object can be re-typed from the viewer, and one target is marked recommended (OBSERVED).** The viewer object menu carries **"Change \<type\> to ▸"**. For a treemap with a (1 category, 1 measure) signature the targets were: **Bar chart (recommended)**, Butterfly chart, Crosstab, Dot plot, Dual axis bar chart, Dual axis bar-line chart, Dual axis line chart, Gauge, Key value, Line chart, List table, Needle plot, Numeric series plot, Pie chart, Scatter plot, Step plot, Targeted bar chart, Waterfall chart, Word cloud — 19 targets, the current type excluded. The **"(recommended)"** marker is a third surface for the chart-choosing resolver found in session 9 (canvas auto-chart, Suggest pane, and now conversion ranking), reinforcing defect 35.

#### G.2d The Suggestions engine, characterised (OBSERVED, session 11)

Ten batches were generated in a blank sandbox on `RETAILDEMO_2` (2.34M rows × 57 columns) — the initial load, seven Refreshes and three "Add more suggestions". Every batch had the same shape. **The pane is a fixed slot rotation with randomised column picks, not a ranked recommender.**

| Slot | Caption template | Object type produced | Frequency |
|---|---|---|---|
| **1** | `<varying category>, Country_Lat by State_Lat` (or the `_Long` pair) | a **two-measure comparison** — Butterfly, Dual axis bar, or Dual axis bar-line | **10 of 10** |
| **2** | `<category> by Frequency` / `<category>, Frequency by Category` | **Treemap** | **10 of 10** (filled by `Department` in 9 of 10) |
| **3** (and 4 in five-card batches) | free-form: `ChannelType by Cost`, `Age Bucket by Storeage`, `<x> of Frequency Percent` | varies (Word cloud observed) | varies |
| **last** | `<date column> by <varying measure>` | **Time series plot** | **10 of 10** |

Batch size is **4 or 5** and is never disclosed.

**Slot 1 is bound to the table's most strongly correlated measure pair (OBSERVED, sessions 11–12).** The pair is fixed per data source and only the category rotates:

| Data source | Slot-1 measure pair | Batches |
|---|---|---|
| `RETAILDEMO_2` | `Country_Lat` by `State_Lat` (occasionally the `_Long` pair) | 15 of 15 |
| `PRODUCTS` | `Cost` by `Retail Price` | 5 of 5 |

Column position is ruled out — in the Data pane's measure list `Country_Lat` is 9th and `State_Lat` 25th of 29, while `Cost` is 1st and `Retail Price` 5th of 9. What both pairs share is near-perfect correlation: a state's latitude tracks its country's, a product's cost tracks its retail price. **This confirms the vendor guide's "measure correlations" mechanism** (§P.3) and locates the real defect: correlation is computed **with no semantic veto**, so on any table carrying coordinates the coordinate pair wins slot 1 every time and the chart sums latitudes into "millions" (longitudes into negative millions). On `PRODUCTS`, where the most-correlated pair happens to be two currency columns, slot 1 produces a **genuinely sensible chart**. Defect 19's fix is therefore to **exclude latitude, longitude, year, identifier and code columns from the measure pool before correlation is computed**, not to re-rank afterwards.

**Slot 1's chart type is a random draw, not a decision (OBSERVED, session 12 — resolves a session-11 UNKNOWN).** Thirteen slot-1 insertions were sampled; **three categories each produced two different chart types from identical inputs**:

| Category | Cardinality | Types produced |
|---|---|---|
| `Department` | 6 | **Butterfly** *and* **Dual axis bar** |
| `Location` | 6 | **Butterfly** *and* **Dual axis bar** |
| `Open` | 1 | **Dual axis bar-line** *and* **Dual axis bar** |
| `ChannelType` | 3 | Dual axis bar |
| `Transaction Time of Day` | 3 | Dual axis bar-line |
| `Age Bucket` | 7 | Butterfly |
| `Country` | 7 | Butterfly |
| `Storechain` | 3 | Dual axis bar-line |
| `MDY` | 6 | Dual axis bar |

Same category, same measure pair, same caption, different object. The distribution across 13 samples — Butterfly 4, Dual axis bar 5, Dual axis bar-line 4 — is consistent with a **uniform random draw from the three two-measure comparison types**. The date-versus-nominal hypothesis is dead: `MDY`, `Location` and `Department` share a classification and all three types appear among them. **There is no encoding decision here to reverse-engineer, and none to copy.**

**The slot structure holds on a second, unrelated table (OBSERVED, session 12).** Adding `PRODUCTS` produced the same four slots with that table's columns: `<cat>, Cost by Retail Price` · `<cat> by Frequency` (filled by `Product Category` in 5 of 5) · free-form · `Date Order was Delivered by <measure>`. The structure is the engine, not an artefact of one dataset.

**Multi-source scoping (OBSERVED, session 12 — resolves a session-11 UNKNOWN).** With two sources loaded the combobox lists both, **auto-switches to the newly added one** and regenerates. No card in six batches mixed columns from two tables. The pane's source selector is **not independent**: changing the source in the **Data** pane switched the Suggestions pane too — one selection exposed in two places.

**Three independent blindnesses (each OBSERVED):**
- **Non-deterministic.** Seven Refreshes on unchanged inputs gave seven different column sets; Refresh discards the current list and there is no pinning or history, so a suggestion seen and not taken is gone (defect 53).
- **Selection-blind.** With `Brand Name` selected and confirmed `aria-selected="true"` in the Data pane, ten generated suggestions used it **zero times** (defect 52).
- **Report-blind.** After `Department by Frequency` was inserted as a treemap, three consecutive Refreshes offered it again (defect 51). **This directly contradicts the vendor guide**, which states that items already used are not reused in newly generated suggestions — see §P.3.

**Insertion (OBSERVED).** Double-click inserts into the current page — note this *works* here, unlike the object library where double-click appends instead (defect 27). Right-click offers *Add to current page*, *Add to new page* and *Delete*. An inserted card is **consumed** and a new card appears in its place; a **deleted** card is **not** replaced. Undo labels are descriptive throughout: `Undo: Add object Butterfly - Location 1`, `Undo: Add object Treemap - Department 1`, `Undo: Add object Word cloud - ChannelType 1`, `Undo: Add object Time - Date 1`, and for a new page `Undo: New page Page 2 with object types: Dual axis bar-line chart` (plural "types" for one object). **Delete produces no undo entry and no toast** (defect 50).

**What a suggestion fills.** Required roles plus data tips, and nothing else:

| Inserted object | Assigned | Left empty |
|---|---|---|
| Dual axis bar – MDY | Category `MDY` · Measure (bar) `Country_Lat` · Measure (bar 2) `State_Lat` · Data tips ×3 | Lattice rows/columns, Animation, Hidden |
| Butterfly – Location | Category `Location` · Measure (bar) `Country_Lat` · Measure (bar 2) `State_Lat` · Data tips ×3 | — |
| Treemap – Department | Tile `Department` · Size `Frequency` · Data tips ×2 | Color |
| Word cloud – ChannelType | Word `ChannelType` · Size `Year` · Data tips ×2 | Color |
| Time – Date | Time axis `Date` · Measure `StoreNum` · Data tips ×2 | Group |

**Naming is inconsistent with itself (OBSERVED).** The card says `Department by Frequency`; the object it creates is titled `Frequency of Department`. The card says `MDY, Country_Lat by State_Lat`; the object is titled `Country_Lat, State_Lat by MDY`. The operands swap and the preposition changes, so a user cannot match a suggestion to the object it produced (defect 54). A third caption form, `<x> of Frequency Percent`, appears for percent-of-total measures, and the trailing term is sometimes the literal word `Category` — which is **not a column in this table** but the Data pane's group heading, and the corresponding role in the inserted object was left empty (defect 55).

**Two rendering faults seen in the cards themselves:** `Transaction Date/Time by 12 week RFM Bucket` drew both axis titles and **no marks at all** (defect 56); `MDY, Country_Lat by State_Lat` rendered its date axis as **unordered clock times** (`12:09:00, 9:09:00, 10:09:00, 11:09:00, 8:09:00, 1:10:00`) from a column the Data pane classifies as a date.

**This is a fourth chart-choosing code path.** Session 9 found the canvas auto-chart resolver and the Suggest pane disagreeing; session 10 added the viewer's "(recommended)" conversion ranking; this session shows the Suggest pane is not a resolver at all but a template rotation. Defect 35 stands and widens.

#### G.2e Multi-item drag-and-drop: the drop resolver (OBSERVED, session 13)

Selecting several data items and dragging them onto an **empty canvas** runs a different resolver from the single-item automatic chart. Measured on `PRODUCTS` (748K orders, 23 categories, 9 measures); the object identity was read from the Data Roles pane header each time, not from the undo entry.

| Dropped set | Object created | Role assignment |
|---|---|---|
| 1 category | **Bar chart** | Category; **Measure auto-filled with `Frequency`** |
| 1 category + 1 measure | **Bar chart** | Category, Measure |
| 1 category + 2 measures | **Bar chart** | Category; **both** measures in the Measure role |
| 1 **date** + 1 measure | **Time series plot** | Time axis, Measure |
| 2 categories | **List table** | Columns ×2 |
| 2 categories + 1 measure | **List table** | Columns ×3 — the measure enters as a plain column |
| 2 measures | **Heat map** | Axis items ×2; **Color auto-filled with `Frequency`** |
| 3 measures | **Heat map** | Axis items ×2; Color = the third measure |
| **4 measures** | **Correlation matrix** | `Show correlations: Within one set of measures`; Measures ×4 |
| 5 items including `Frequency` | **Correlation matrix** | **`Frequency` silently dropped**; the 4 real measures used |

**The rules:** two or more categories → List table, everything folded into `Columns`; exactly one category → Bar chart, or Time series plot if that category is a date, with all measures stacked into `Measure`; no category → Heat map for 2–3 measures and **Correlation matrix for 4 or more**. `Frequency`, the synthetic row-count measure, is excluded from a correlation set without comment.

**Scatter is substituted without disclosure, and the undo entry leaks the discarded choice.** Three drops whose object is not a scatter plot produced an undo entry naming one (`Add Scatter - Cost 1 …` for the 2-, 3- and 4-measure drops), while the 5-item drop was labelled `Add Correlation - Cost 1 …` correctly. Read as: the resolver picks **Scatter**, then substitutes a binned heat map (748K points will not plot) or a correlation matrix, and writes the undo entry from the **pre-substitution** decision. The substitution is never shown to the user (defect 59).

#### G.2f Drop targets — a three-zone model (OBSERVED, session 13)

| Target | Behaviour | Undo grammar |
|---|---|---|
| **Empty canvas** | New object per §G.2e | `Add <name> with data items <list>` |
| **The gutter around an existing object** | New object, **split in that direction** — verified on the left and right gutters | `Add <name> with data items <list>` |
| **An object's body** | Assigns to a compatible role: **replaces** a filled single-item role, **appends** to a multi-item role | `Replace <old> from <object> with <new>` |
| **A named role slot** in the Data Roles pane | Assigns to that role, and **also appends the item to `Data tip values`** | `Assign <item> to <object>` |
| **A chip inside a multi-item role** | Reorders within the role | `Reorder items of <object> in <role> role` |

**There is no in-object "edge zone".** Drops 8px, 28px and 68px inside the object's right border all behaved as body drops; only a drop past the border, in the canvas gutter, created a split.

**The body-drop resolver ignores empty optional roles, silently.** On a bar chart with `Category` filled and `Group` empty, dragging a second category onto the **body** did nothing — no change, no undo entry, no message — while the same item dropped on the **`Group` slot** was accepted immediately (defect 58). A measure dropped on the `Category` slot was likewise refused in silence.

**Mid-drag feedback is UNKNOWN.** Rows carry `draggable="true"`, so the app uses HTML5 drag-and-drop; synthesised pointer events do not start a drag and a real one cannot be paused. Drop-target highlighting, insertion indicators and cursor states were not observed — every outcome above was read from the result and the undo entry.

#### G.2g The geo-map family: one object, seven layers (OBSERVED, session 14)

Dropping a geography item alone on the canvas creates **`Geo coordinate - <item> 1`**. Its Options pane carries **Graph Frame → Change type**, and that dialog lists **seven layer types** — **Bubble · Scatter · Cluster · Contour · Line · Pie · Region**. Switching the layer **renames the object** (`Geo cluster - …`, `Geo region 1`, `Geo pie - …`), so what the object library presents as several geo objects is **one object with a layer property**. Undo: `Undo: Change type to Cluster for Geo coordinate - Geographic Item 1 1`.

| Layer | Roles (`*` = required) |
|---|---|
| **Scatter** (Geo coordinate) | Geography\*, Size, Color, Data tip values, Data label, Hidden, Animation |
| **Cluster** (Geo cluster) | as Scatter |
| **Bubble** (Geo bubble) | Geography\*, **Size\***, Color, Data tip values, Data label, Hidden, Animation |
| **Region** (Geo region) | **Geography\***, **Color\***, Data tip values, Data label, **Data values**, Hidden, Animation |
| **Pie** (Geo pie) | Geography\*, Size, **Measure**, **Category\***, Data tip values, Data label, Hidden, Animation |
| **Contour** (Geo contour) | Geography\*, **Color** — only two roles |
| **Line** (Geo line) | Geography\*, **Width**, Color, **Pattern**, Data tip values, Data label, Hidden, Animation |

**A geography item's source type decides which layers it can serve.** A **lat/long** item drives point layers (Scatter, Cluster, Bubble, Pie, Contour); a **name/code lookup** item drives point **and** region layers, because it carries both a centroid and a polygon; **Line** needs a path geography that neither produces. **The mismatch is handled by silent deletion** — switching a lat/long-backed map to **Region**, and a lookup-backed map to **Line**, both **cleared the Geography role entirely**, leaving a blank placeholder ("Color by Geography" with an *Assign data* button) and no message (defect 64). Compare defect 18, which silently *re-maps* roles; this one discards them.

**Verified rendering.** Geo coordinate: 213 city points on an OpenStreetMap basemap. Geo cluster: grey count bubbles (5, 61, 79, 33, 6, 2). Geo region: a working choropleth (*"Frequency of Geographic Item 2"*, countries on a 15K–1.2M ramp) with the required Color role **auto-filled with `Frequency`**. An **ⓘ on the rendered object** reads *"No matches were found for supplied geography data items: England."* — the unmapped value is disclosed on the object as well as in the creation dialog.

**Map background (Options → Geo Maps).** A **Map background** checkbox, a **Map service** field with a browse button, and a **Transparency** slider. The service browser is a filterable tree with a thumbnail and description per entry: **Automatic** — *"selects a background map automatically based on the report theme that is currently displayed. For example, the High Contrast map is selected when the high contrast theme is displayed"* — and **OpenStreetMap**, which expands to **Standard · Light · Dark · High Contrast**. **Esri ArcGIS Online** services sit behind a third-party terms dialog (Accept / Decline, stored under *Settings → Geographic Mapping*); that consent was deliberately not answered, so the Esri catalogue is **UNKNOWN**. The object also gains an **Enable zoom and pan** option that non-map objects lack — the setting behind the viewport control cluster recorded in session 10.

**A custom-map report that renders nothing (OBSERVED).** `150_305_Using a Custom Geo Map`, opened read-only with its required prompts satisfied, rendered an **empty page**. The viewer pane names an object (`Facility Locations`) while `role="application"` returns zero objects and the pane answers *"Select an object to see its roles."* A geography item whose provider is missing takes the whole object down silently (defect 65).

#### G.2h Statistical objects and statistics-flavoured chart options (OBSERVED, session 15)

The Statistics and Machine Learning role tables in §G.1 were **re-verified item by item in a sandbox and match exactly**. What follows is what those tables do not say.

**An unconfigured statistical object renders a complete worked example.** Inserting *Nonparametric logistic regression* with no data draws:

> **Nonparametric Logistic Regression of Example Data** · Event: **(none selected)** · Fit: **KS (Youden) 0** · Observations: **0 of 0**

above a **four-panel grid** — **Fit Summary** (p-value bars) · **Iteration Plot** (Objective Function vs Step) · **Spline Plot** · **Confusion Matrix** — all on example data, with a central **Assign data** button. The author sees the model's panel layout and its header vocabulary before committing a single column. This is the "placeholder sample data" strength (Strength 9) at its most useful.

**Cluster, configured** (`Variables` = `Customer Age`, `Margin`) renders **two stacked panels** — a cluster-centroid strip plot keyed by **Cluster ID**, and a **parallel coordinates plot** of coloured polylines — under a header carrying **two** disclosures:

> **Cluster** · **Observations: 646K of 2.3M** · **Polylines: 72**

The dropped-row figure matches the logistic regression's exactly, so the drop is driven by missing values in the chosen measures and is reported consistently; `Polylines: 72` names its own truncation. Same discipline as the decision tree's `Observations: 100 of 100`.

**Model comparison takes no roles at all** — the pane answers *"Roles are not supported for the selected object."* — and states its precondition in a modal:

> **No Comparable Models** — "There are no models in the report which can be compared. To compare models, there must be at least two models which use the same **partition**, **response data item**, **event level**, and **group by** data items."

Four named, checkable conditions: excellent content, delivered as a **modal that blocks the properties pane and re-fires on every selection**, so the object cannot be inspected — only deleted (defect 69).

**The regressions' required markers overstate the requirement.** Four effect roles each carry `*` on Linear regression, GLM and Logistic regression, yet the object runs once **any one** is filled (defect 72).

##### Statistics-flavoured chart options

| Object → section | Settings |
|---|---|
| **Box plot → Box Plot** | Box direction · **Measure layout: Automatic \| Separate axes \| Shared axis** · **Outliers: Ignore \| Show \| Hide** (default **Hide**) · Hide outliers · Outlier bin outlines · Averages. Style adds a dedicated **Fill** and **Outlier Gradient** pair |
| **Histogram → Histogram** | Direction · Transparency · **Bin range: System-determined values \| Measure values** · Set a fixed bin count · **Bin count (2-100)** — the valid range is stated in the label |
| **Scatter plot → Fit Line** | **Type: None (default) \| Best fit \| Linear \| Quadratic \| Cubic \| PSpline** · Transparency · an ⓘ beside the label |

The box plot's three-way **Ignore / Show / Hide** is a real distinction most tools collapse into a checkbox — *ignore* excludes outliers from the statistics, *hide* computes but does not draw them — but the UI never explains which is which and **defaults to Hide**, so whiskers are computed from data the reader never sees (defect 70). The histogram's inline `(2-100)` is the right pattern and makes the forecast horizon's silent rejection of 0 and 9999 (defect 15) look worse by comparison (defect 73). A scatter plot ships with **no fit line** and the setting sits four sections down the Options pane (defect 74).

#### G.2i Fitted models, Model comparison, and the last two charts (OBSERVED, session 16)

**A fitted model carries a live header and a handoff.** With `Response` = `ChannelType` and `Predictors` = `Customer Age`, `Margin`:

> **Decision Tree of ChannelType** · Event: **Store ▾** · Fit: **KS (Youden) 0.3872 ▾** · Observations: **2.3M of 2.3M** · **Create pipeline ▾**

`Event ▾` picks the modelled level, `Fit ▾` picks the statistic and shows its value inline, `Observations` gives rows used of rows available, and **`Create pipeline ▾` → Add to new project · Add to existing project** promotes the fitted model into a Model Studio pipeline project — the seam between the exploratory tool and the ML workbench, offered on the object itself. (Not clicked: it creates a project outside the report.) Panels: Decision tree → **Tree · Variable Importance · icicle · Confusion Matrix**; Forest → **Variable Importance · Error Plot (Misclassification Rate vs Number of Trees) · Confusion Matrix**. A long fit shows a **"Loading…" spinner over the greyed example-data placeholder**.

**Model comparison is configured by a dialog, not by roles.** Inserting it opens **Add Model Comparison**: `Data:` · `Response:` · `Event level:` shown as **fixed facts inherited from the candidate models**, then `Available models:` with **Select all** and a checkbox per model; **OK is disabled until one is ticked**. Output:

> **Model Comparison of ChannelType** · Event: **Store**

| Panel | Content |
|---|---|
| **Fit Statistic ⓘ** | one bar per model of the chosen statistic — Decision tree ≈ **0.39**, Forest ≈ **0.10** on KS (Youden). **The winner is drawn in the accent colour, the loser in grey** |
| **Confusion Matrix** | Observed × Predicted lattice **faceted by Model** |
| **Relative Importance Plot** | Variable × Model heat strip with a Relative Importance colour legend |

This is the most clearly designed object in the product — one question, three linked panels, a colour-coded verdict — and it is worth copying wholesale.

**Two objects, same columns, different populations (OBSERVED).** `Cluster` on `Customer Age` + `Margin` reported **646K of 2.3M**; `Decision tree` and `Forest` on the same two columns reported **2.3M of 2.3M**. The tree-based models tolerate missing predictor values where the cluster drops those rows — a defensible choice that is **never stated in the UI**, so two objects on one page silently describe different populations (defect 75).

**The last two statistics-flavoured graphs:**

| Object | Roles (`*` = required) |
|---|---|
| **Parallel coordinates plot** | **Variables\*** — a single role, the same shape as Cluster |
| **Vector plot** | **X axis\*, Y axis\*, X Origin\*, Y Origin\*** · Color, Group, Lattice columns, Lattice rows, Data tip values, Hidden |

The vector plot is the only object whose four asterisks are all **structurally necessary** (it draws an arrow from origin to endpoint) — a useful contrast with the regressions, whose four asterisks mean "any one of these" (defect 72).

#### G.3 Capability boundaries (do not invent beyond these)
- No zoom or pan on standard charts; the Overview axis is the only navigational aid.
- No period-over-period comparison on any chart; time calculations exist **only** as Data-pane calculated items.
- No relative date filtering anywhere in the filter or control UI (Section H.6).
- No distinct-count aggregation in the aggregation menus.
- No `COALESCE`/`IFNULL`; missing values are handled by `Missing()`, `NotMissing()`, `IsSet()`, `NumMiss()`.
- No statistical reference lines (mean, median, percentile) — constants and parameters only.


---

<!-- ===== Source: data-model.md ===== -->

## Data Model and State Model

> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

### I. Data Model (conceptual, from observable behaviour)

```
User ──owns──> Report ──has──> Page ──has──> Object ──has──> RoleAssignment ──references──> DataItem
                  │               │             ├──has──> Filter ├──has──> Rank
                  │               │             ├──has──> DisplayRule
                  │               │             └──has──> Action (ObjectLink | PageLink | ReportLink | UrlLink | ParameterLink)
                  │               └──has──> Control (report-level controls attach to Report)
                  ├──uses──> DataSource ──exposes──> DataItem (Category | Measure | AggregatedMeasure | Date | Geography | Hierarchy | CustomCategory | CalculatedItem | Parameter | Partition)
                  ├──has──> CommonFilter
                  ├──has──> Theme/Style
                  └──has──> PageTemplate (report-scoped save target)
```

| Entity | Observed attributes | Relationships | Create | Edit | Delete | States |
|---|---|---|---|---|---|---|
| Report | name, location (after save), summary, thumbnail object, created/modified by+date, viewer customization level, insights allowed, export policy, fixed size, theme, palettes, persistence flag | 1..n Page, 0..n DataSource, 0..n CommonFilter | New report | Editor | Close (confirm) / Recycle Bin | Unsaved → Saved → Modified; Editing ↔ Viewing |
| Page | name (required), type (Basic/Hidden/Pop-up), padding, direction (vertical default), avoid scrollbars, control placement, visibility limits | belongs to Report; 0..n Object, 0..n Control | "+" / template | Options, ⋮ | Delete (needs ≥2 pages) | Basic / Hidden / Pop-up |
| Object | name (auto, follows data), title mode (Automatic/Custom/None), alt text, selection enabled, data limit override, reload flag, style, layout flags | belongs to Page; has roles, filters, ranks, rules, actions | Objects pane / data item / template / suggestion / convert | Right rail + context menus | Delete / Undo | Placeholder → Configured → Rendered → Capped / Empty / Error |
| DataSource | name, table, library, row count, columns, modified metadata | belongs to Report; exposes DataItem | Add data / Import / Join / Aggregation | Replace, Refresh, Edit aggregated data | Remove | Loaded / Loading / Failed (join timeout) |
| DataItem | label, **name-in-data** (the physical column — both halves are shown on the item’s hover card, with distinct count and format), classification (Category/Geography/Measure), format, aggregation default, distinct count, **sensitivity flag** (a quasi-identifier badge whose hover text reads *"… includes information that might identify an individual when combined with other information"*, **inherited by derived items**), outlier flag, expression, "used by" list | belongs to DataSource | Auto on load, or + New data item | Edit properties (inline) | Hide / Delete (varies) | — |
| **GeographyItem** | name, **basedOn** (any DataItem — the picker is not type-filtered), **source** = `nameOrCodeLookup` \| `provider` \| `latLong`, plus per-source fields: *lookup* → one of ten **contexts** (country names / ISO 2, 3, numeric / SAS map IDs / subdivision names / subdivision map IDs / US state names / US state abbreviations / US ZIP); *provider* → registered provider + ID column + optional lat/long; *latLong* → latitude column, longitude column, **coordinate space** (Web Mercator \| WGS84 \| OSGB36 \| Singapore Transverse Mercator \| Custom PROJ string). Derived at create time: **mappedPercent**, **unmappedValues[]**, and which **layer families** it can serve (point \| region) | a DataItem subtype, in its own **Geography** group in the Data pane; inherits the source item's sensitivity flag | New data item ▸ Geography item | the same dialog | delete | Unconfigured / Validating / `N% mapped` / provider-missing (renders nothing — defect 65) |
| CalculatedItem | name, expression, auto-detected format, optional Scope (Custom intersection / Grand total) | a DataItem subtype | dialog | dialog | delete | Valid / Invalid (blocks OK) |
| Parameter | name, type (Character/Numeric/Date/Datetime), multiple values, include missing, format, default (literal or expression) | referenced by controls, filters, calculations | dialog | dialog | delete | — |
| Filter | target item, condition type, values/range, include-missing, detail vs aggregated, continuous vs discrete, inverted | on Object; CommonFilter is report-scoped | Filters pane | card + ⋮ | Delete filter | Active / Reset / Empty-result |
| Rank | category, subset (Top/Bottom × count/percent), count, rank-by measure, ties, All Other | on Object | Ranks pane | card | trash | — |
| DisplayRule | label, target, operator, value (constant or measure), style, intersections, alerts flag | on Object (scoped Object or Measure) | dialog | pencil | trash | — |
| Action/Link | type (Filter / Linked selection / Page / Report / URL / Parameter), source, target, options | on Object or Page | Actions pane | checkbox + ⋮ | untick | — |
| Control | control type, roles, required, initial value, multi-select, search, missing option, placement scope (report/page/body) | on Report or Page | drag to strip | Options | delete | Empty / Selected / Required-unset |
| DataView *(DOCUMENTED)* | reusable data-item customizations bound to a source, shareable between users | belongs to DataSource | Save data view | Manage data views | delete | — |
| DataSourceMapping *(DOCUMENTED)* | pairs of corresponding items across two sources; formats must match | between two DataSources | Map data | Map data | delete | — |

**UNKNOWN:** persistence format of a saved report, permission model beyond the observed "Limit visibility to specified users", versioning, concurrent editing, and how common filters are stored.

---

### J. State Model

**Report**
```
New(unsaved) ──edit──> Modified ──Save──> Saved ──edit──> Modified
     │                                   │
     └──Close──> [Save? / Don't save? / Cancel]
Saved ──Close──> closed ; any state ──session loss──> Recoverable ──Restore──> reopened
```
Capabilities gated by `Saved`: Export, Share, Copy link, Copy embeddable markup, Distribute, Localize, Comments, Evaluate Performance, page Export/Copy link/Save as template, About this report.

**Object**
```
Inserted(placeholder, synthetic sample data)
   → RolesPartial (required role unfilled → still placeholder)
   → Querying ("Loading…")
   → Rendered
        ├─ RowCapped   (ⓘ "Only N rows of the data appear.")
        ├─ TieCapped   (ⓘ "…too many ties associated with the rank.")
        ├─ EmptyResult ("No data matches the current filters.")
        └─ Refused     (e.g. Model comparison: "No Comparable Models")
   → Maximized ↔ Restored
   → Deleted (undoable)
```

**Page:** `Basic ↔ Hidden ↔ Pop-up` (Hidden/Pop-up require ≥2 pages; both undo as "Hide page").

**Editor mode:** `Editing ↔ Viewing` (rails hidden, menus differ, AI icon disappears, selections carry over).

**Expression:** `Empty → Invalid(n errors, OK greyed) ↔ Valid(OK enabled)`; the preview grid keeps the **last valid** result while invalid.

**Automatic actions mode:** `Off → One-way ↔ Two-way ↔ LinkedSelection`; entering any mode destroys manual object links; every transition clears control selections.


---

<!-- ===== Source: interaction-model.md ===== -->

## Interaction Model

> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

### H. Interaction Model

#### H.1 Pointer semantics (OBSERVED)
| Gesture | Target | Behaviour |
|---|---|---|
| Single click | Chart mark | Select/deselect; tooltip card; filters or highlights linked objects |
| Single click | Object frame | Select object → drives every right-pane tab |
| Single click | Canvas background | Deselect; auto-collapses unpinned panes |
| **Double click** | Chart mark (view mode) | **Triggers page links / drill** — a single click never does |
| Single click | **Underlined axis label** on a hierarchy | **Drills down one level.** Text-object hyperlinks also open on a single click; only chart *marks* require the double-click |
| Double click | Objects-pane entry | Insert object at the next free slot |
| Double click | Template / list-dialog row | Commit the selection (single click only highlights — a recurring trap) |
| Double click | Dual-list item | Move it across |
| Right click | Object, data item, page tab, column header | Context menu (20–25 items, submenus, greyed entries) |
| Hover | Data item row | Reveals "Edit properties" pencil and a lineage card |
| Hover | Chart mark | Data tip listing every assigned role |
| Hover | Object frame | Reveals ⋮ and maximize affordances |
| Drag | Data item → object / canvas / control strip | Assign role, create object, or create a prompt |
| Drag | Object edge / corner | Resize within the layout grid |
| Drag | Slider handle, overview-axis handle, filter range | Adjust a range (snaps to integers) |
| Scroll | Grids and long menus | Virtualized scrolling (grids are canvas-rendered) |

#### H.2 Selection model
Single-select for chart marks and objects; multi-select checkboxes inside List controls and category filters. Selections persist across an edit↔view mode switch. Every automatic-action mode switch **clears control selections**.

**Data pane selection (OBSERVED, session 13 — corrects two earlier notes).** Click selects one; **Ctrl+click and Cmd+click toggle an item in or out**; **Shift+click selects a range**. Mixed selections **may span the Category and Measure groups**, and a selection **survives virtualised scrolling** — rows scrolled out of view stay selected and are carried by a later drag. Checkboxes appear on **every** row as soon as anything is selected, and the pane grows a **`Clear selection (n)`** link stating the count. The earlier notes that "ctrl-click didn't multi-select" and that "the checkbox only renders on hover" were both wrong; the first came from a dead click coordinate on the list's clipped last row.

#### H.2b Drill-down (OBSERVED, session 6)
A hierarchy in a category role turns the axis labels into links. A single click drills one level; the object grows **its own breadcrumb** (`All Order Date Hierarchy › 2014 ˅`) with a level menu, and that breadcrumb **truncates to the current level when the object is narrow**. Drill is **per object** — nothing else on the page follows it.

#### H.3 Undo / redo (a strength worth copying)
Undo works in **view mode as well as editing** (OBSERVED: *"Undo: Change Continent Selector from North America to Europe"*), so readers can step back through their own exploration — a strong pattern most viewers lack. Undo labels are fully descriptive and expose the exact operation: "Undo: Assign Customer Age, Sales to Crosstab - Region 1", "Add section with template", "Change label on data item from X to Y", "Change the option showRowNumbers for List table - City 1 to true". Rejected inputs create **no** undo entry. Redo is present. No auto-save of user edits during a session, but unsaved state is persisted for crash recovery.

#### H.3b Drag-and-drop semantics (OBSERVED, session 13)

Drag is the product's primary construction gesture and it carries a **three-zone target model** — empty canvas, the gutter around an object, and the object itself — plus role slots and role chips. The full table, the multi-item drop resolver and the silent-refusal defects are in `visualizations.md` §G.2e–G.2f. Two interaction facts belong here:

- **A drop on an object's body resolves to a role, not to layout.** A drop *past* the object's border, in the canvas gutter, splits the layout instead. There is no in-object edge zone — 8px inside the border still behaves as a body drop.
- **Refusals are silent in both directions.** A body drop the resolver cannot place, and a type-mismatched drop on a role slot, both produce no change, no toast and no undo entry.

**Seven undo grammars exist for one operation family** — `Add <name> with data items <list>` (canvas drop), `Add object <name>` (Suggestions insert), `Replace <old> from <object> with <new>` (body drop), `Assign <item> to <object>` (role-slot drop), `Reorder items of <object> in <role> role` (chip reorder) `New page <name> with object types: <type>`, and — the least informative — `Change option "fitLineType"`, which exposes the **raw internal camelCase key** and drops both the object name and the new value (defect 71). Each is readable on its own — the product's real strength — but they share no sentence pattern (defect 63).

#### H.4 Progressive disclosure
Panes auto-collapse unless pinned; property sections are collapsible; advanced settings hide behind ⋮ menus; the expression editor is the escape hatch behind every filter and calculation; a settings search box spans the Options pane.

#### H.5 Confirmation and safety
Confirmations appear **only** for closing unsaved work and for actions that require a save. Destructive configuration changes (deleting links by switching action modes) use a toast with Undo instead of a prompt. Deleting objects and pages is immediate, undoable, and never confirmed.

#### H.6 Filtering model (the product's core semantic)
Three independent layers, which the UI does not unify:
1. **Object filters** — defined per object in the Filters pane; can be promoted to **common filters** reusable across objects and pages.
2. **Controls (prompts)** — report-level (all pages), page-level (all objects on the page, cascading into other controls), or body-level (filter nothing until explicitly linked).
3. **Actions** — object links (Filter or Linked selection), page-wide automatic modes, page/report/URL links.

**Critical for reimplementation — and the disclosure is asymmetric (OBSERVED on a production report, session 6).** In the **editor's** Filters pane, filters arriving from controls and links are **invisible**. In the **viewer's** side pane they *are* disclosed: selecting a filtered object shows `Permanent Filters: None` and `Interactive Filters: Product Category = 'Clothes'`. So the reader can audit the filter stack and the author configuring it cannot. A rebuild should show one merged, inspectable filter stack in **both** modes.

**Missing values are handled inconsistently across the three layers (OBSERVED):**
| Surface | Default for missing |
|---|---|
| Object filter (numeric, category, date) | **Included** (`OR Missing(x)` in the generated logic) |
| List control | Present as a selectable value "(missing values)", unselected |
| Slider control | **Excluded, even at full range**, until "Missing values option" is enabled |
| Custom category grouping | Silently folded into "Other" |
| Invert selection | Also inverts the include-missing setting |

**Relative dates:** absent from filters and controls. Only expressions provide `Now()` and the five periodic functions. **A reimplementation should add first-class relative ranges (last N days, MTD/QTD/YTD, rolling windows).**

#### H.6b Control cascades, and what the viewer discloses (OBSERVED, session 10)

**A control can filter another control.** In a parameter report, the *Benchmark Country Selector*'s own Filters pane read `Interactive Filters: Continent Name = 'Asia'`, and its value list held exactly the seven Asian countries. A control is an ordinary filter target like any chart, and the cascade is disclosed in the viewer (never in the editor — defect 11).

**A parameter change reprices everything downstream in one pass.** Switching the benchmark from Russian Federation to China recomputed the `+/- vs Benchmark` column for every row, re-sorted the bar chart and rescaled its axis, and produced one undo entry: *"Undo: Change Benchmark Country Selector from Russian Federation to China"* — the same label grammar as every other undo.

**Required controls drop the clear affordance.** An optional drop-down's value list opens with **`Clear filter`**; a control marked **(required)** offers no such entry. There is no "(All)" member either way.

#### H.7 Keyboard
No shortcut reference exists in Help. Observed: Esc closes menus and dialogs — and **inside a dialog's dropdown it closes the entire dialog, discarding work** (a defect to avoid). Enter commits inline fields. Tab focus rings are drawn. Full shortcut map: **UNKNOWN**.

**Correction (OBSERVED, session 10).** "No documented keyboard-shortcut surface" is false as an absolute. The **Comments pane** ends with a literal instruction: *"Press **Ctrl+Enter** to expand or collapse replies for a comment. Press **F2** to interact with the comment or reply."* A second appears in the **Opened reports** panel, where every row carries *"Press **Delete** to close the report"* and the list ends with **Close all reports**. These are the only shortcuts the product discloses anywhere, and each is discoverable only by opening the one surface that prints it. Help still carries no shortcut reference. For the rebuild: the shortcuts should exist **and** be listed in one place.


---

<!-- ===== Source: design-system.md ===== -->

## Design System and Responsive Behaviour

> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

### L. Design System

All values measured from live computed styles at a 1214×731 viewport, light theme.

#### L.1 Typography
| Token | Value |
|---|---|
| Family | A single humanist sans across the whole product (vendor font `Anova UI`; substitute your own — Inter, Source Sans 3 or system-ui behave equivalently) |
| Base body | 14px / weight 400 / colour `#1B1D22` |
| Banner and pane titles | 16px / 400 / line-height 22.4px (1.4) |
| Rail tab labels, section labels | 16px and 12–14px |
| Buttons | 14px / 400 |
| Small control text | 12px |
| Crosstab heading style default | 9pt **bold** |
| Weights in use | 400 regular, 700 for headings/totals; no light weights observed |
| Alternate font (defect) | Crosstab display-rule text defaults to a different family from the report font — unify this in a rebuild |

#### L.2 Colour
| Role | Value | Notes |
|---|---|---|
| Primary / brand bar | `#0664D0` | Banner background and avatar |
| Link / interactive text | `#0664D0` | Same hue as primary |
| Text primary | `#1B1D22` | |
| Text disabled | `#C3C8D0` | Greyed menu items keep full opacity |
| Chart label grey | `#6D7585` | Axis and legend text |
| App background | `#F4F4F6` | Canvas surround |
| Rail / subtle surface | `#F9FAFB` | |
| Surface / cards / panes | `#FFFFFF` | |
| Border / divider | `#DDDFE4` | 1px |
| Single-series accent | `#4398F9` | Default bar/line colour |
| Categorical palette (6 sampled, in assignment order) | `#EC80CE` pink · `#54B6A4` teal · `#F28D44` orange · `#97C03F` green · `#A570E8` purple · `#4398F9` blue | Sampled from a 6-category legend; the theme editor offers **8 fill swatches** and 8 line/marker swatches, so the palette is at least 8 long and the remaining entries were not sampled. Each mark is outlined in a ~10% darker shade of its fill (e.g. `#D272B7` under `#EC80CE`) |
| Dedicated **Missing** colour | theme-level swatch | A palette slot reserved for missing values — worth copying |
| Dedicated **Other** colour | grey | For the "Other" bucket |
| Gradient | 2-stop light → blue | For continuous colour roles |
| Semantic success / warning / error | **UNKNOWN** | No success, warning or error colour appeared in any observed state; validation uses red text with a red field outline, and severity counters are monochrome |
| Themes | Dark / **Light** (default) / High Contrast / custom | Theme switching is report-level |

#### L.3 Layout
| Token | Value |
|---|---|
| Banner height | 38px |
| Toolbar height | 44px |
| Left icon rail width | 34px (expands to show labels) |
| Left pane width | 338px |
| Right pane width | 384px |
| AI side panel width | ~460px overlay |
| Rail tab hit height | 53px |
| Canvas gutter | ~16px around objects |
| Object padding | 8–16px; padding is an explicit per-object option (off by default) |
| Grid | Objects fill the page in a flex/grid layout with Extend/Shrink width and height flags; page direction vertical by default |

#### L.4 Components
| Token | Value |
|---|---|
| Border radius | **2px** everywhere (buttons, inputs, cards) — a deliberately square, dense look |
| Border width | 1px, `#DDDFE4` |
| Shadows | None on panes or cards; elevation comes from borders. Menus and modals use a light drop shadow |
| Button height | 28px, padding 4px 8px |
| Icon buttons | 22–24px targets, ~16px glyphs |
| Input height | ~28px |
| Checkbox | ~16px |
| Table row height | Condensed by default; alternating row background on; horizontal and vertical rules on |
| Focus | Visible focus ring; disabled items remain focusable |

#### L.4b Spacing, motion and layering (OBSERVED, session 18)

**Spacing** — base **4px**, rhythm **8px**. Measured distribution of left padding across app elements: `8px` dominant, then `16`, `6`, `4`, `2`, `32`. Scale: 4 · 8 · 12 · 16 · 24 · 32.

**Motion** — the product is almost motionless. Of 375 sampled elements **only 18 carry any transition**, and every one is the same:

| Token | Value |
|---|---|
| duration | **100ms** |
| easing | **`cubic-bezier(0, 0.5, 0.2, 1)`** |
| property | `background-color, border-color` |

There is **no entrance, exit or layout animation anywhere**. Motion exists only to soften hover and active colour changes. For a dense information tool this is a defensible and fast choice — copy the discipline, add `prefers-reduced-motion` support, and keep the set to three durations (100 / 160 / 240ms) on one easing.

**Layering** — observed z-indices are shallow (`0`, `1`, `2`, `4`, `5`); stacking is handled by DOM order and portals rather than a numeric scale. A rebuild should name its layers (`base` · `sticky` · `dropdown` · `overlayPane` · `modal` · `toast` · `tooltip`) and never write a raw z-index.

**Focus** — a **3px outline applied on `:focus-visible`** (programmatic focus does not trigger it), which is the correct modern implementation.

**Theme mechanism** — no `data-theme` attribute or theme class was found on the document root, and the app's own CSS custom properties were not separable from browser-extension variables in this environment. **UNKNOWN**; specify it rather than copy it.

#### L.5 Visual language summary for the rebuild
Dense, flat, information-first: one saturated brand blue used sparingly for the banner and links, near-black text, 2px radii, hairline borders instead of shadows, generous use of grey surfaces to separate rails from canvas, and a soft mid-saturation categorical palette that stays legible against white. Copy the *system*; choose your own hues.

---

### M. Responsive Behaviour

**Directly observed:** the 1214×731 desktop viewport, plus two narrower effective widths reached by page zoom (see below). Real tablet and phone devices, and the PWA, were **not** observed.

**Observed from the stylesheets (OBSERVED):** breakpoints at **`min-width: 768px`, `992px`, `1200px`**, plus a **print** stylesheet.

| Breakpoint | Layout change | Components hidden | Components collapsed | Navigation | Charts | Tables |
|---|---|---|---|---|---|---|
| ≥1200px | Three-column: rail + left pane + canvas + right pane | — | Panes auto-collapse when unpinned | Full rail with optional labels | Canvas-rendered, redraw on resize | Virtualized, fit-to-width |
| 992–1199px | **UNKNOWN** | | | | | |
| 768–991px | **UNKNOWN** | | | | | |
| <768px | **UNKNOWN** | | | | | |
| Print | Dedicated stylesheet exists; page "Export as PDF" is the sanctioned path | | | | | |

**Narrow-width behaviour, measured by shrinking the effective CSS viewport (OBSERVED, session 10).** The browser window could not be resized in this environment — `resize_window` reported success while `window.outerWidth` stayed at 1600 — so the viewport was narrowed with page zoom instead.

| Effective width | Observed |
|---|---|
| ~1214px | Report title and toolbar icons share one 44px row |
| **~607px** | The report title moves to **its own row above the toolbar**; a **button-bar control overflows with ‹ › arrows**; the prompt bar stays in one row; the canvas is unchanged |
| **~405px** | The banner title truncates (*"SAS® Visual Analytics - E…"*); the **report prompt strip becomes horizontally scrollable**; the canvas is unchanged with a vertical scrollbar only |

**Nothing ever stacks.** Controls overflow or scroll sideways and the report canvas keeps its absolute layout at every width. Throughout, `window.matchMedia('(max-width:768px)')` stayed **false** while the chrome visibly re-laid-out — so this responsiveness is driven by **measured container width in JavaScript, not CSS media queries** (OBSERVED for the behaviour; INFERRED — confidence High — for the mechanism). The `768 / 992 / 1200` breakpoints in the stylesheet therefore do not govern what was seen here.

Real device and PWA rendering remain unobserved.

**Author-controlled responsiveness (OBSERVED):** per-object *Specify / Extend / Shrink* width and height flags, page-level *Avoid scrollbars*, report-level *Set fixed report size*, and a *Precision container* for absolute placement. These make layout behaviour an authoring decision rather than a purely automatic one — a pattern worth reproducing.

**Recommendation:** treat the authoring experience as desktop-only (≥1200px) and build a separate, genuinely responsive **read-only viewer** for tablet and phone.


---

<!-- ===== Source: observed-architecture.md ===== -->

## Observed system architecture — session 17

Everything here was read from the running client: resource timings, network request lines, DOM/runtime structure. **No source code, tokens, cookies or session identifiers were captured**, and the one browser API that would have exposed query strings with identifiers refused to return them — noted where that leaves a gap.

---

### 1. Client payload — the headline number

| Measure | Value |
|---|---|
| **Total transferred** | **63.4 MB** |
| JavaScript | **45.5 MB across 135 files** |
| **WebAssembly** | **12.9 MB** (`ltjs-wasm.wasm`) + a 324 KB JS loader |
| CSS | 1.3 MB across 13 files |
| Fonts | 0.4 MB (4 × woff2) |
| Resources total | 250 |
| DOMContentLoaded | ~2.9 s · load ~3.1 s (warm cache, 20-core client) |

Largest single assets: the 13.2 MB `.wasm`, then JS chunks of **6.7 / 6.6 / 5.8 / 5.3 / 4.8 MB**.

**Bundling:** webpack code-splitting — `runtime.<hash>.js` plus numbered chunks (`83369.<hash>.js`, `11680.<hash>.bundle.js`), content-hashed for cache-busting.

**No mainstream UI framework was detectable** — React, Angular, Vue, Ember and Dojo all probed negative, and no `ng-version` attribute exists. The only app global is `sas`. Read as: a **proprietary in-house component framework**, not an off-the-shelf one.

---

### 2. The rendering engine is compiled, not scripted

`/SASVisualAnalytics/<build-hash>/ltjslib/ltjs-wasm.js` + `ltjs-wasm.wasm` — a **13 MB WebAssembly module** loaded at boot. Alongside it:

| Probe | Result |
|---|---|
| Canvas elements on a one-chart page | **1** |
| SVG elements on the same page | **335** (icons and chrome) |
| Canvas context | **2D** — not WebGL |
| Device-pixel vs CSS size | 402×446 vs 402×446 (DPR 1 on this display) |

So: **application chrome is DOM + SVG; every data visual is drawn by a WASM engine through the Canvas 2D API.** This single fact explains a cluster of behaviours documented across earlier sessions —

- no data values in the DOM or the accessibility tree (defect 30), because nothing is rendered as elements;
- objects carrying `role="application"` with only a descriptive name;
- pixel-identical output between the browser, PDF export and the mobile app, because one engine draws all of them;
- charts that redraw rather than reflow on resize.

It is a defensible trade: one renderer, every surface. The cost is accessibility, and the subject pays it in full.

---

### 3. Service topology

Every service is a flat top-level namespace on one host. Observed in a single session:

| Namespace | Calls | Owns |
|---|---|---|
| `SASVisualAnalytics` | 160 | The SPA itself — bundles, WASM, service workers |
| `localization` | 15 | `/localization/bundles` — **2.7 MB** of message bundles |
| `thumbnails` | 13 | `/thumbnails/jobs/<uuid>` — asynchronous report thumbnail generation |
| `reportTemplates` | 10 | `/reportTemplates/objects/<uuid>` — object and page templates |
| `drive` | 9 | `/drive/items`, `/drive/actions`, `/drive/ancestries/drive-recommendations` — the content tree and the Recommendations feed |
| `preferences` | 5 | `/preferences/preferences/@currentUser` — read **and written back** (`POST`) |
| `identities` | 5 | `/identities/users/@currentUser`, `/identities` |
| `fonts` | 4 | `/fonts/css`, `/fonts/families`, `/fonts/files/<id>` — a font *service*, not static assets |
| `authorization` | 4 | `/authorization/bulkDecision`, `/authorization/decisions` — **batch permission evaluation** |
| `SASLogon` | 3 | `/SASLogon/info`, per-service silent OAuth |
| `appRegistry` | 2 | `/appRegistry/applications/applicationTree`, `/appRegistry/types` |
| `reportData` | — | the query engine (below) |
| `maps` | 2 | `/maps/providers`, `/maps/providers/US%20County%20Data` |
| `reportImages` | — | `/reportImages/images/<id>.svg`, `defaultReportThumbnail.svg` |
| `files` | — | `/files/files/<uuid>/content` — **autosave** (below) |
| `notifications`, `catalog`, `featureFlags`, `deploymentData`, `reports`, `transfer` | — | notifications feed, `/catalog/search/facets`, `/featureFlags/enabled`, `/deploymentData/cadenceVersion` |

**Two patterns worth copying:**

1. **`/authorization/bulkDecision`** — permissions are evaluated in **batches**, not per object. A UI that greys dozens of commands needs dozens of decisions; asking once is the difference between a responsive toolbar and a chatty one.
2. **A `fonts` service with `/fonts/css` and `/fonts/families`** — typography is server-governed, so themes and exports stay consistent with the browser.

**Query grammar.** Collection endpoints use an RQL-like filter language, visible in the notifications call:

```
GET /notifications/notifications
      ?start=0&limit=32767
      &sortBy=creationTimeStamp:descending
      &filter=and(eq(read, false), eq(recipientId, '<user>'))
```

`start` / `limit` / `sortBy=<field>:<direction>` / `filter=and(eq(...), eq(...))`. One grammar across services is right. **`limit=32767` is not** — the client asks for 32,767 notifications rather than paging.

---

### 4. The query protocol, end to end

#### 4.1 Session
```
POST   /reportData/executors              → 201   create a data-session executor
DELETE /reportData/executors/<uuid>       → 204   tear it down
```
One executor per data session. It is deleted when the report closes or the data source changes, and re-created immediately.

**An observed failure mode:** `POST /reportData/executors` → **`449`**, then an immediate retry → `201`. HTTP 449 ("Retry With") is a **non-standard Microsoft extension**, not in RFC 9110. Using it to mean "re-establish and try again" works, but any standards-compliant proxy or client library is entitled to treat it as an unknown 4xx and give up. **Use `409 Conflict` or `503` with `Retry-After` instead.**

#### 4.2 Jobs
```
POST /reportData/jobs
       ?indexStrings=true
       &embeddedData=limited
       &executorId=<executor-uuid>
       &wait=30
       &jobId=<executor-uuid>_c<N>
       &sequence=<n>
       [&dataDefinitions=dd<NN>]           → 201
```

| Parameter | Meaning (inferred from behaviour — confidence High) |
|---|---|
| `indexStrings=true` | return strings as **dictionary indices** rather than repeated literals |
| `embeddedData=limited` | **embed the result in the response when it is small; spill to files when it is not** — this is why many jobs have no result fetch at all |
| `wait=30` | **long-poll**: hold the connection up to 30 s for the result rather than polling |
| `jobId=<executor>_c<N>` | `c<N>` is a **client-side monotonic counter that continues across executors** — a fresh executor was observed starting at `c429` |
| `sequence=<n>` | a **per-executor** counter, restarting at 1 |
| `dataDefinitions=dd<NN>` | present on the job that **registers or refreshes a definition**; absent on jobs that reuse one |

#### 4.3 Results, when they spill
```
GET /reportData/results/<executorId>_<executorId>_c<N>/files/dd<NN>.csv       → 200
GET /reportData/results/<executorId>_<executorId>_c<N>/files/dd<NN>index.csv  → 200
```
Two files per data definition: the **result** and its **string index** (the dictionary that `indexStrings=true` produced). Note the composite key repeats the executor id twice.

#### 4.4 A single chart creation, captured clean
Dropping one category on an empty canvas produced exactly **two** calls:

```
POST …&jobId=<exec>_c429&sequence=6                      → 201
POST …&jobId=<exec>_c430&sequence=7&dataDefinitions=dd69 → 201
```

and **no result fetch** — the bar chart's 6 rows came back embedded. Two round trips from gesture to rendered chart over a 2.3M-row table.

**The design to copy:** one long-lived session, one job per object, dictionary-encoded strings, results embedded when small and spilled to addressable files when large, and a long-poll instead of a poll loop. That is a well-shaped protocol.

**The design to fix:** a chatty job stream. Across one editing session the counter ran past **`c430`** with many jobs producing no fetched result. Batch the jobs for a page into one request.

---

### 5. Persistence: there is no client state

| Store | Contents |
|---|---|
| `localStorage` | **0 keys** |
| `sessionStorage` | **0 keys** |
| IndexedDB | one database, `product-aidr@1` |

**The client keeps nothing.** Unsaved work is pushed to the server continuously:

```
PUT /files/files/<uuid>/content   → 200
```

…observed **interleaved with the query jobs**, firing on essentially every change. That is the mechanism behind "unsaved state is persisted for crash recovery" and behind *Restore previous session* on the landing page. User preferences are written the same way (`POST /preferences/preferences/@currentUser`).

**Trade-off to make deliberately:** server-side autosave gives you crash recovery and cross-device continuity for free, and costs a write per keystroke-equivalent. A rebuild should debounce and diff rather than PUT whole content, and should keep a local mirror so an offline blip does not lose work.

---

### 6. Two service workers, and the PWA seam

```
scope /                        → /SASVisualAnalytics/pwa/root-service-worker.js
scope /SASVisualAnalytics/     → /SASVisualAnalytics/webapp-service-worker.js
```

A **root-scoped PWA worker** plus an **app-scoped worker**. This is the concrete mechanism behind the documented "consumption uses a PWA" story, and it is how a 63 MB client becomes tolerable on a second visit.

---

### 7. What this adds to the defect list

| # | Observed | Required in the rebuild |
|---|---|---|
| 77 | **A 63.4 MB client payload** — 45.5 MB of JavaScript in 135 files plus a 12.9 MB WebAssembly module, before any data is queried | Budget the initial bundle; defer the rendering engine and the analytics chunks until an object needs them |
| 78 | **`449` used as a retry signal on executor creation** — a non-standard status a compliant client may abandon on | `409` or `503` with `Retry-After` |
| 79 | **A chatty job stream** — one job per object per change, a counter past `c430` in a single session, many jobs producing no fetched result | Batch a page's jobs into one request; coalesce changes within a frame |
| 80 | **`limit=32767` on a collection fetch** instead of paging | Page every collection, and make the page size a server concern |
| 81 | **2.7 MB of localization bundles loaded up front** for one locale | Load one locale, and split messages by route |

---

### 8. Where the evidence stops

- **Request and response bodies were not read** — only methods, paths, query parameters, statuses and sizes. The job payload's internal shape (how a role assignment becomes a query) is therefore **inferred from behaviour, not observed**.
- **No authentication material was captured.** The per-service silent OAuth flow (`/SASLogon/oauth/authorize?client_id=sas.<service>`) is documented from URL shape alone; the token exchange, lifetimes and refresh behaviour are **UNKNOWN**.
- Precise job latencies are **not** reported: the browser's resource-timing buffer was full from page load, and the one API that would have returned the newer entries refused because the URLs carry identifiers. The qualitative figures from hands-on use — roughly 10–14 s for a first chart over 2.3M rows, 60–90 s for a Forest fit — are timings I measured by waiting, not by instrumentation.


---

<!-- ===== Source: unknowns-closed.md ===== -->

## Closing the UNKNOWN register — session 19

Worked through the five outstanding items. Two are now resolved, one partly, one is blocked by your own instruction, one by tooling.

#### Safety log
- All model work happened in a **new blank sandbox**, closed with **Don't save**.
- **One project was created in your account, with your explicit authorisation** — see §2. I did not delete it, because your standing rules forbid me performing deletes.
- The **Esri terms dialog was left unanswered**, as you instructed. No response is recorded against your account.
- `130_551_Creating a Bar Chart` was not touched.

---

### 1. Machine Learning objects — 3 of 6 fitted, 6 of 6 role-verified

All six role schemas in `visualizations.md` §G.1 were **re-verified against the live object** and match. Three are now fitted and rendered.

| Object | Roles (verified) | Fit | Observations | Panels |
|---|---|---|---|---|
| **Forest** (session 16) | Response\*, Predictors\*, Partition ID, Frequency, Weight | KS (Youden) **0.1000** | **2.3M of 2.3M** | Variable Importance · **Error Plot** (Misclassification Rate vs Number of Trees) · Confusion Matrix |
| **Bayesian network** | Response\*, Predictors\*, **Partition ID only** | KS (Youden) **0.2855** | **646K of 2.3M** | **Network** (node-link: predictors → target) · **Variables in Network** (BIC Score) · **Model Selection** · Confusion Matrix |
| **Gradient boosting** | Response\*, Predictors\*, Partition ID, Frequency, Weight | KS (Youden) **0.3986** | **2.3M of 2.3M** | Variable Importance · **Iteration Plot** (Misclassification Rate vs Number of Trees) · Confusion Matrix |
| Factorization machine | Response\*, Predictors\* *(no optional roles)* | — | — | not fitted |
| Neural network | Response\*, Predictors\* + optional | — | — | not fitted |
| Support vector machine | Response\*, Predictors\* + optional | — | — | not fitted |

#### 1.1 The Bayesian network's Model Selection panel
A small-multiples plot of **Misclassification Rate** across four structure families — **Structure · Markov blanket · Naive · Parent-child** — each with sub-ticks 1–5 for the number of parents, and a **green star marking the selected model**. A compact, honest way to show *"here is the search space and here is what I chose"*. Together with Model comparison's colour-coded winner, that is two places the product marks a verdict visually; both are worth copying.

#### 1.2 Defect 75 gets a third data point — and it is now unambiguous
Same two predictors (`Customer Age`, `Margin`), same response, same table:

| Object | Observations |
|---|---|
| Cluster | **646K of 2.3M** |
| Bayesian network | **646K of 2.3M** |
| Decision tree | 2.3M of 2.3M |
| Forest | 2.3M of 2.3M |
| Gradient boosting | 2.3M of 2.3M |

Two distinct missing-value policies, split cleanly along model family, **never stated anywhere in the UI**. A reader comparing a cluster and a tree on one page is comparing two different populations. This is now a five-object finding rather than a two-object one.

#### 1.3 A model-quality aside
On this data the ranking is Gradient boosting 0.3986 > Decision tree 0.3872 > Bayesian network 0.2855 > **Forest 0.1000**. A forest scoring an order of magnitude below a single tree on the same inputs is the kind of result a **Model comparison** object exists to surface — and it does, immediately and visually.

---

### 2. Create pipeline — RESOLVED (and it created something)

**Authorised by you.** From the fitted Gradient boosting object: **Create pipeline ▾ → Add to new project**.

#### 2.1 What happened
1. The button showed **"Creating pipeline…"** inline.
2. **The tab navigated away from Visual Analytics** to `/SASModelStudio/` — the whole application context was replaced, with no warning and no new tab.
3. Model Studio rendered a full-screen error: **"The application has encountered a serious error and must be reloaded."** with *Copy the full error to the clipboard* and **Reload**.
4. **Reload recovered it, and the project had in fact been created.**

#### 2.2 What it created
| | |
|---|---|
| App | SAS Model Studio → Projects |
| Project | **`Interactive Project`** |
| Type | Data Mining and Machine Learning |
| Modified by | your account · Sep 23, 2026, 10:46 AM |

**Delete it at:** Model Studio → Projects → ⋮ on the *Interactive Project* card → Delete.

#### 2.3 What the handoff actually produces — and it is good
The project opens with four tabs: **Data · Pipelines · Pipeline Comparison · Insights**.

**Data tab** — a variable grid (`Variable Name · Label · Type · Role · Assess for Bias`) with a per-variable properties panel (Role · Level · Order · Transform · Impute). The VA roles were carried across and translated:

| In Visual Analytics | In Model Studio |
|---|---|
| Response `ChannelType` | **Target** |
| every other column | **Input** |
| `_dmIndex_` (generated) | **Key** |
| `age` / "Customer Age", `City` | **Rejected** |

> **A mismatch worth flagging:** `Customer Age` was an assigned **predictor** in the VA object and arrived **Rejected** in the pipeline. The handoff does not preserve the predictor set.

There is also an **"Assess for Bias"** column on every variable — a fairness feature with no counterpart anywhere in Visual Analytics.

**Pipelines tab** — a tab named **`Interactive-Model Pipeline`** containing a **complete, runnable four-node DAG**:

```
Data  →  Visual Data Preparation  →  Gradient Boosting  →  Model Comparison
```

with a **Run pipeline** button, a **+** to add further pipelines, and a properties panel per node (the Data node reads *"Defines all the information about the data set."*).

**This is the right design.** The promoted model does not arrive as an orphan node — the handoff wraps it in a data-prep step and a model-comparison step, so the analyst lands in a working pipeline. **Copy the pattern: a promotion should produce something runnable, not a fragment.** Fix the three faults around it: do not hijack the tab, do not crash on arrival, and carry the predictor set across.

#### 2.4 A bonus capture — the platform's own application map
The Applications menu enumerates the whole platform, which is the best available answer to *"where does an analytics tool sit in a suite?"*:

- **Favorites:** Explore and Visualize · Build Custom Graphs
- **Analytics Life Cycle:** Discover Information Assets · Manage Data · **Explore and Visualize** · Build Models · Manage Models · Build Decisions · Develop Code and Flows
- **Administration:** Build Custom Graphs · Manage Themes · Explore Lineage · Manage Environment · Manage Workflows

The reporting tool is **one station of seven** on an explicit analytics life cycle, with the model workbench immediately downstream. That framing is why *Create pipeline* exists at all.

---

### 3. Esri ArcGIS basemap catalogue — BLOCKED BY INSTRUCTION

You chose *leave it unanswered*. The consent dialog remains unanswered and **no response is stored against your account**. Without acceptance the catalogue is **Automatic** + **OpenStreetMap {Standard · Light · Dark · High Contrast}**. The Esri catalogue stays **UNKNOWN by choice**, not by limitation.

---

### 4. Mid-drag visual feedback — BLOCKED BY TOOLING

Rows carry `draggable="true"`, so the app uses HTML5 drag-and-drop. Synthesised `mousedown`/`mousemove` sequences do not initiate a drag (verified in session 13), and a real drag cannot be paused mid-flight for a screenshot with the available tooling. Drop-target highlighting, insertion indicators and cursor states remain **UNKNOWN** — and `UI_UX_SPECIFICATION.md` §6.2 therefore **specifies** them rather than copying them.

### 5. Custom geography provider authoring — BLOCKED BY PERMISSION

*New provider · Edit provider · Delete provider* are greyed in this deployment (defect 68). Not a tooling limit — the capability is not granted to this account.

### 6. Geo line with a real path geography — NOT ATTEMPTED THIS ROUND

Requires a path-capable geography item, which neither the ten built-in lookup vocabularies nor the single registered provider (*US County Data*) can produce. Remains **UNKNOWN**.

### 7. Export / Share / Copy link / embeddable markup, Play report / Edit playback — NOT ATTEMPTED THIS ROUND

These can be opened and cancelled without downloading, sharing or saving, which would document their options safely. Budget went to the model work and the pipeline handoff instead. **Still open, and safely doable next session.**

---

### 8. New defects

| # | Observed | Required in the rebuild |
|---|---|---|
| 82 | **Promoting a model hijacks the tab and crashes the destination.** *Create pipeline → Add to new project* replaced the Visual Analytics session with Model Studio, which rendered *"The application has encountered a serious error and must be reloaded."* The project had been created; one Reload recovered it | Open the destination in a new tab; never replace unsaved authoring context; do not ship a handoff whose landing page fails |
| 83 | **The handoff loses the predictor set.** `Customer Age`, an assigned predictor in the source object, arrived **Rejected** in the generated pipeline | Carry every role assignment across, and report anything the destination cannot represent |
| 84 | **Two missing-value policies across the model family, never disclosed** — Cluster and Bayesian network use 646K of 2.3M rows; Decision tree, Forest and Gradient boosting use all 2.3M *(supersedes and strengthens defect 75)* | State the policy per object and warn when two objects on a page disagree about the population |
