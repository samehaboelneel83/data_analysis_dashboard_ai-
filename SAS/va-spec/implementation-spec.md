# Implementation Specification — for an AI coding agent

> Part of the Visual Analytics reverse-engineering deliverable. Sibling files: `application-map.md`, `screens.md`, `activities.md`, `components.md`, `visualizations.md`, `data-model.md`, `interaction-model.md`, `design-system.md`, `screenshots/`.
> **Evidence labels:** OBSERVED · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.
> **Evidence base:** nineteen hands-on sessions against `vfl-026.engage.sas.com` — fourteen in never-saved sandbox reports, and two (sessions 6 and 10) read-only in View mode on **saved, production, multi-page reports** built by report authors, nine reports in all. Nothing was saved, exported, shared, deleted or overwritten in any session, and no confirmation dialog was ever accepted. Section P alone is documentation rather than observation.


## APPLICATION ARCHITECTURE

### Frontend

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

### State

| Scope | Holds | Notes |
|---|---|---|
| **Global** | Current user, theme, open documents (multi-document switcher), notifications, feature flags | The subject keeps several reports open at once; model documents as a collection, not a singleton |
| **Document** | The whole `ReportDefinition`: pages, objects, roles, filters, ranks, rules, actions, controls, calculated items, parameters | Undo/redo is a stack of typed, labelled mutations over this tree — see Interaction requirements below |
| **Session / local** | Selection (object, marks), active pane per rail, pin state, expanded sections, maximized object, edit vs view mode | Selection must survive a mode switch (OBSERVED) |
| **Server** | Table metadata, column profiles, query results, saved reports, templates, common filters | Cache results per (object, query hash); invalidate on role, filter, rank or aggregation change |
| **Ephemeral** | In-flight jobs, toasts, dialog state, drag payload | Cancel in-flight jobs when a new one supersedes them for the same object |

**Autosave vs save.** The subject persists unsaved editor state server-side for crash recovery while keeping an explicit Save for the document itself (INFERRED — confidence: Medium-High, from a `POST` then `PATCH` to a files service and a "Restore previous session" affordance). Copy that split: recover work without silently publishing it.

### Data Model

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

### Visualization

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

### Routing

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

### Reusable Components

Full inventory with states, inputs and interactions in `components.md`. Minimum set to build:

`AppBanner · Toolbar · IconRail · SidePane · PaneHeaderMenu · SearchField · DataItemRow · InlinePropertyEditor · ObjectLibraryList · Canvas · PageTabStrip · ObjectFrame · ChartRenderer · DataGrid · RoleGroup · TypeFilteredPicker · DualListPicker · FilterCard · RankCard · ControlWidget (dropdown | buttonbar | list | slider | textinput) · FilterBreadcrumb · PropertySection · Dropdown · ColorPicker · PlacementPicker · ExpressionEditor · ResultsPreviewGrid · Modal · Toast · Tooltip · HoverCard · ContextMenu · SeverityCounter · ThumbnailCard · AssistantPanel`

Not needed (the subject has none): breadcrumb navigation, pagination, command palette.

### Interactions

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

### Responsive

Breakpoints observed in the subject's stylesheets: **768 / 992 / 1200**, plus a print stylesheet. Actual sub-desktop layouts were never observed (UNKNOWN).

| Range | Layout behaviour |
|---|---|
| ≥1200px | Full authoring: rail + left pane + canvas + right pane |
| 992–1199px | Collapse one pane to overlay; canvas keeps priority |
| 768–991px | Viewer-oriented: rails become sheets; editing degraded or blocked |
| <768px | **Read-only viewer only.** Stack objects one per row; controls become sheets |
| Print | Page-per-page layout; honour the report's fixed-size setting |

Author-controlled sizing is part of the model, not just CSS: per-object specify/extend/shrink width and height, page-level "avoid scrollbars", report-level fixed size, and an absolute-positioning container. Reproduce these as document properties.

### Design System

Tokens and component metrics in `design-system.md`. The system in one paragraph: dense and flat, one saturated brand colour used only for the banner and links, near-black text, **2px radii**, hairline 1px borders instead of shadows, grey surfaces separating rails from canvas, a 6+ colour mid-saturation categorical palette, and dedicated palette slots for **missing** and **other** values. Build tokens as `--color-*`, `--space-*`, `--radius-*`, `--font-*`; ship light, dark and high-contrast themes from day one, since the subject's theme switch is report-level and users expect it.

---

## Implementation Priority

| Priority | Scope | Contents |
|---|---|---|
| **P0** | Core application | Shell (banner, toolbar, rails, modal host) · document model + undo/redo · data source loading with column classification · object insert with placeholder rendering · role schema + type-filtered pickers · query engine (executor, job queue, cached columnar results) · bar/line/pie/table renderers · save, close-with-confirmation, single-document routing |
| **P1** | Main analytics workflow | Options/Roles/Filters/Ranks panes · object filters with an explicit unified missing-value policy · Top/Bottom N in true rank order · aggregation menu with a safe default per column type · crosstab with source-level totals and subtotals · pages, page types, page tabs · viewer mode with an accessible table fallback · addressable routes for report/page/object/mode |
| **P2** | Advanced visualization | Remaining mark families and the full 78-type role catalogue · geo maps with the provider/lat-long prerequisite surfaced in the picker · calculated items and the expression editor with edit-time validation · custom categories, hierarchies, parameters · display rules · cell visualizations · data labels, axis and legend options |
| **P3** | Secondary features | Controls/prompts at report, page and body scope · object/page/report/URL links and cross-filter modes · filter breadcrumb · page templates · common filters · data views and data-source mapping · export (PDF, package) · comments and sharing · report linter with quick fixes |
| **P4** | Polish | Auto chart-type inference · suggestion engine filtered by column semantics · AI assistant · insights and outlier detection · forecasting and statistical/ML objects · playback/slideshow · localization · PWA and a separate mobile viewer |

**Sequencing note.** P0 and P1 together deliver the product's actual value proposition — a person who cannot write a query builds a correct, filtered, cross-linked report. Everything in P2–P4 is breadth. The subject's own weaknesses cluster in P1 semantics (missing values, totals, ranks, aggregation defaults), so that is where the rebuild earns its advantage.

---

## Traceability

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

## Supporting detail (observed behaviour behind the requirements above)

### Observed query protocol (OBSERVED at the network layer; no credentials or tokens recorded)

**Query protocol (OBSERVED at the network layer, no credentials or tokens recorded):**
- One **executor** is created per data session: `POST /reportData/executors` → 201.
- Every object's query is a **job** posted to that executor: `POST /reportData/jobs?indexStrings=true&embeddedData=true|limited&executorId=<id>&wait=30&jobId=<executorId>_c<N>&sequence=<n>&dataDefinitions=dd<N>` → 201. `wait=30` indicates long-polling.
- Results are fetched as files: `GET /reportData/results/<jobId>/files/dd<N>.csv` and a companion `dd<N>index.csv` (string index — consistent with `indexStrings=true` dictionary-encoding category values).
- Supporting services observed: `/dataTables/dataSources/{source}/tables/{table}` and `/casManagement/…` (table metadata), `/visualAnalyticsAdministration/defaultReportDataViews?filter=eq(dataTableUri,…)`, `/catalog/instances?filter=eq(resourceId,…)` (asset catalogue), `/annotations/annotations?resourceUri=…`, `/folders/folders/@myHistory/histories` (recently used), `/notifications/notifications?…`, `/files/files` (`POST` then `PATCH` — **INFERRED: unsaved-state autosave powering session recovery, confidence: Medium-High**).
- Auth is per-service silent OAuth: a first call returns an auth challenge, the client is bounced through `/SASLogon/oauth/authorize?client_id=sas.<service>` and the call is retried. **Do not replicate this pattern** — use one session token across your services.

**Build it as:** a single-page client with a **query engine per data source**, a **job queue with sequence numbers**, **columnar/dictionary-encoded result transport**, and **canvas-rendered charts and grids**. Charts and data grids alike are drawn to `<canvas>`: DOM and accessibility-tree queries for cell text return nothing, while a single `<canvas>` element carries the rendered pixels (**OBSERVED** by DOM inspection; the performance motive is **INFERRED — confidence: High**). The cost is that no cell text exists in the DOM, so pair canvas rendering with an accessible table or ARIA summary, which the subject lacks.

### Build order (superseded by the P0–P4 table above; kept for rationale)
1. **Data layer** — table metadata, column classification (category/measure/date), distinct counts, aggregation engine, row caps.
2. **Object model** — object types with typed role schemas; the role schema *is* the product's contract (Section G.1 is a complete specification of 78 of them).
3. **Canvas and pages** — layout with extend/shrink flags, page types, templates.
4. **Property panes** — Options / Roles / Filters / Ranks / Rules / Actions, each scoped by selection.
5. **Interaction layer** — controls, links, modes, breadcrumb.
6. **Authoring aids** — expression editor, calculated items, custom categories, hierarchies.
7. **Viewer** — read-only mode, side pane, drill, export.
8. **Assistive** — suggestions, review/lint, AI panel.

### Patterns to copy (these are the product's real strengths)
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

### Defects to fix (observed failure modes, each a product opportunity)
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

### Terminology map (avoid vendor-flavoured names)
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

### Acceptance criteria (verifiable against this document)
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

## P. Cross-check against vendor training material

**Source:** a user-supplied structured guide derived from the vendor's own training course (EYVA152, *SAS Visual Analytics 1 for SAS Viya: Basics*, stated release LTS 2025.09). **This is documentation, not observation.** Sections A–O were produced under a no-documentation rule; nothing below has been re-verified in the running app, and the training release differs from the observed deployment. Claims from it are labelled **DOCUMENTED**. Where the two disagree, the observed behaviour in Sections A–O governs, because it came from the build in front of us.

### P.1 Where the documentation confirms what was observed
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

### P.2 New facts that resolve items previously marked UNKNOWN
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

### P.3 Divergences and cautions
1. **Different build.** The guide targets LTS 2025.09; the observed deployment is a "Viya for Learners" environment whose pane labels differ slightly ("Suggestions" / "Report Review" vs "Suggest" / "Review"). Treat documented specifics as version-dependent.
2. **Documentation describes intent; observation captured behaviour.** The guide does not mention any of the 25 defects in Section O.4 — the Sum-by-default hazard, the four inconsistent missing-value policies, the `ToToday` year-to-date anchoring, ranks rendering alphabetically, or automatic actions deleting manual links. A rebuild driven only by the documentation would reproduce those faults.
3. **Page ranges in the guide's lesson index are unreliable** by its own admission, and several lessons resolved to no range, so it is not a complete map of the course.
4. **Copyright:** the guide quotes vendor slide notes verbatim in places. Those passages are the vendor's text — use the *facts* in a rebuild, not the wording, and do not carry that material into shipped documentation.

### P.4 Net effect on this specification
Sections A–O are unchanged in substance. The documentation adds **four entities** (`DataView`, `DataSourceMapping`, a first-class `ReportDefinition` artefact, and the geographic-provider concept) and **one architectural confirmation** (definition-versus-result separation, client-side rendering). Section I's data model should gain `DataView` and `DataSourceMapping`; Section O.1's architecture recommendation is corroborated rather than revised.

---

## UNKNOWN / NOT OBSERVABLE

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
