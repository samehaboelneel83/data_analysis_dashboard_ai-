# SAS Visual Analytics vs Datalytics — Feature Comparison

**Sources.**
- **SAS side:** the reverse-engineering bundle in `SAS/` — `visual-analytics-complete-v2.md` (19 live observation sessions against SAS Viya, Sep 2026) plus the `va-spec/` files. Everything is *observed behaviour* of the running product, not marketing.
- **Datalytics side:** `README.md`, the existing course-based `SAS_COMPARISON.md` (whose ✅ means "executed by a test on every surface"), and direct checks of the codebase (`AI_data_tool/data_analytics/`).

**Legend:** ✅ have · 🔶 partial (real but narrower) · 🟡 exists in backend/mechanism, weak or no UI · ❌ missing

---

## 1. Data connectivity & preparation

| Capability | SAS VA (observed) | Datalytics |
|---|---|---|
| Connect to databases / warehouses | ✅ CAS libraries | ✅ **45 connectors** incl. Snowflake, BigQuery, Databricks, ClickHouse, Trino + admin **custom connector presets** with locked fields |
| File upload | ✅ Import data | ✅ CSV / XLSX / JSON / Parquet / XML, 100 MB |
| Import vs live query | ✅ (CAS in-memory) | ✅ Import **and DirectQuery** |
| Auto profiling on load (types, distinct counts, stats) | ✅ distinct counts, sensitivity shields, outlier dots | ✅ 6-stage sync: discover → profile → sample → infer keys → semantic types → **drift detection**; PII detection + masking |
| Calculated items with expression editor (live validation, error positions) | ✅ live "(n)" error count, squiggles, results preview | ✅ formula language, sandbox, + **custom functions** (named, parameterized, reusable) |
| Aggregated measures with scope (ForAll / group / filter context) | ✅ Scope: Custom intersection / Grand total | ✅ `TOTAL()`, `BYGROUP()`, `CALC()` — evaluated at each widget's grain |
| Quick calculations (% of total, difference, rank…) | ✅ | ✅ on widgets and from the field list |
| Custom categories (group values, intervals) | ✅ + AI group generation | ✅ Group & Bin builder (compiles to a calculated column) |
| Hierarchies + instant date hierarchies | ✅ | ✅ |
| Geography as a **classification on the column** | ✅ Category / Geography classification | ✅ classified once with a boundary set; every map inherits |
| **New Geography Item dialog with live validation** ("86% mapped, 1 unmapped: England", map preview) | ✅ the best interaction in the product | ❌ matcher exists, but no pre-commit match-rate validation panel |
| Parameters (character / numeric / date, defaults, driven by controls) | ✅ | ✅ (`@parameter` in rank counts, `set_param` button actions) |
| **Partitions** (training/validation split as a data item, feeding Partition ID roles) | ✅ | 🔶 automated_prediction makes its own split; no first-class partition item |
| Joins between sources | ✅ (join editor timed out when observed) | ✅ prep join step + materialize |
| Prep pipeline / dataflows as first-class objects | 🔶 in-report data prep only | ✅ **ahead** — non-destructive prep steps, dataflows with own schedule & permissions, materialize with governance refusals |
| Scheduled refresh | ✅ (CAS reload) | ✅ scheduler with backoff, advisory locks, monitoring page |
| **Data views** (reusable per-source item customizations, shareable, admin default) | ✅ (DOCUMENTED) | ✅ org-wide, admin default-on-upload |
| **Data source mapping** (map items across two sources so one action filters both) | ✅ (DOCUMENTED — formats must match) | ❌ |
| Source-table viewer with stated limits | ✅ ~150K rows / 10K cols / 5M cells, message when exceeded | ✅ Data grid + **in-place cell editing as a reversible prep step** |
| Lineage (which report uses which dataset/source) | ❌ | ✅ **ahead** |
| Aggregation menu on a data item | ✅ 20 (no distinct count in menu) | ✅ **24 incl. distinct count** |
| Semantic typing driving safe defaults | ❌ — sums latitudes, years, IDs (the root of ~⅓ of its 76 catalogued defects) | ✅ semantic types + role inference exist; **enforcement as an aggregation veto is partial** |

**Verdict: level, Datalytics slightly ahead** (dataflows, lineage, drift, PII, custom connectors). SAS's remaining unique cards: the geography validation dialog UX, data source mapping, first-class partitions.

## 2. Objects & visualization catalogue

SAS ships **78 object types**: 2 tables, 30 graphs, 10 geo maps, 5 controls, 6 analytics, 5 containers, 5 content, 8 statistics, 6 ML, 1 saved component. Datalytics ships **67 widget types** (53 server-side shapers).

| Family | SAS VA | Datalytics |
|---|---|---|
| Tables: list table, crosstab, totals/subtotals recomputed at their own grain, cell visualizations | ✅ (its best table work — non-additive-safe totals verified) | ✅ crosstab + 16 aggregations, running calcs; cell visualizations (data bars) |
| Core graphs (bar, line, pie, scatter, bubble, heat map, histogram, box, treemap, word cloud, waterfall, KPI) | ✅ | ✅ |
| Specialty graphs (butterfly, dual-axis family, needle, step, numeric series, schedule/Gantt, vector, parallel coords, bubble-change) | ✅ | ✅ most (butterfly, needle, dual-axis, parallel coords confirmed in renderers); vector/bubble-change unverified |
| **Lattice / small multiples on any chart** (Lattice rows + columns roles) | ✅ on ~20 graph types | 🔶 `SmallMultiplesRenderer` exists — one renderer, not a universal role on every chart |
| Reference lines | ✅ | ✅ (per-renderer) |
| **Overview axis** (brushable mini-chart for navigation) | ✅ the only zoom/pan aid | ❌ |
| Animation role (animate over a date) | ✅ on bar/bubble/pie/etc. | ❌ |
| Data tip values role (extra tooltip fields) | ✅ | 🔶 tooltips show assigned roles; a dedicated "extra tooltip fields" role is not confirmed |
| Controls: drop-down, button bar, list, slider, text input | ✅ 5 types, convertible | ✅ incl. `slicer_mode: text` for high-cardinality columns |
| Containers: stacking, tabs, scrolling, **precision (overlap + layers)**, prompt | ✅ 5 | ✅ 5 modes incl. precision over a background image |
| Content: image, web content, **job content (run server code)**, data-driven content (custom visual) | ✅ | ✅ image/web/`script` tile (admin-gated Python) / **two-way custom visuals** |
| Custom graph templates (author a new chart type with its own roles) | ✅ separate Graph Builder app; templates declare their own role names | ✅ **Custom Graph** in-product (layered marks) — no separate app needed |
| Saved components ("Objects With Data") | ✅ (with a destructive insert bug) | ✅ widget templates + page templates (index-based refs, roles deliberately unbound) |
| Placeholder sample data before roles are assigned ("never a blank canvas") | ✅ every object renders synthetic data + "Assign data" | ❌ widgets are empty until configured |
| **Auto-fill required measure** (drop a category → instant row-count chart) | ✅ | 🔶 multi-field drop rules build the right chart, but the drop-category→Frequency instant render pattern is not the default flow |
| Convert object type in place, with a recommended target | ✅ 43 targets, viewer recommends one | 🔶 type switching exists; no recommendation, no role-remap preview |
| Row-cap / tie-cap / dropped-rows disclosure | 🔶 present but hidden behind tiny ⓘ | 🔶 partial — an explicit truncation contract is not systematic |

**Verdict: level on catalogue breadth.** SAS's real edges here are *universal lattice roles*, *placeholder-first rendering*, *overview axis*, and *animation*; Datalytics's are the script tile, two-way custom visuals, and in-product custom graph authoring.

## 3. Roles & configuration model

| Capability | SAS VA | Datalytics |
|---|---|---|
| Typed role schemas per object; pickers only show compatible columns | ✅ the product's spine | ✅ `ROLE_SPECS` (frontend) + `REQUIRED_ROLES` (server), pinned by a parity test |
| Role schemas as **data, not code** (custom templates add roles without deploy) | ✅ | 🔶 registry exists in code; custom graph adds layers, not arbitrary named roles |
| Required roles enforced; single-item roles grey out when full | ✅ | ✅ |
| Aggregation override per role item; format per item | ✅ | ✅ |
| Object names/titles that follow their data | ✅ "Bar 1" → "Bar - Region 1" | 🔶 auto titles exist; naming discipline not one shared function |
| Options pane with settings search | ✅ | ✅ properties search terms in config panel |
| Object picker to reach any object without clicking the canvas | ✅ | ✅ |

**Verdict: level** — this is the one SAS core idea Datalytics already copied properly.

## 4. Interactivity

| Capability | SAS VA | Datalytics |
|---|---|---|
| Cross-filtering (automatic page modes: one-way / two-way / linked selection) | ✅ (but switching modes **destroys** manual links) | ✅ all four modes, per page, survives reload, works on shared links/embeds, incl. maps |
| Manual per-pair actions (filter / highlight) | ✅ | ✅ |
| Filter breadcrumb strip naming what filters the page | ✅ optional | ✅ always rendered, chips with named remove |
| Three-layer filter model (object filters / controls / actions) | ✅ but the layers are **invisible to each other** — its "strangest defect" | ✅ + review pane walks the interaction graph and names dead edges (**SAS has nothing like this**) |
| Common filters shared across the report | ✅ | ✅ |
| Post-aggregate (HAVING) filters | ✅ "filter aggregated values" | ✅ |
| Ranks (top/bottom N, ties, All Other, parameterized count) | ✅ (renders rank results alphabetically — defect) | ✅ incl. `@parameter` counts |
| Custom sort, multi-column sort | ✅ | ✅ |
| Report / page prompt bars, cascading controls | ✅ | ✅ |
| Display rules (color, icons, banded ranges/gauge, value-vs-measure comparison) | ✅ | ✅ |
| Page links / drill to pop-up page (double-click) | ✅ Basic / Hidden / **Pop-up page types** | 🔶 drill-through and page links exist; no hidden/pop-up **page types** |
| Report links, URL links, parameter links | ✅ | ✅ (button actions: navigate, bookmark, URL, other report, set parameter) |
| Bookmarks | ✅ | ✅ |
| **Descriptive undo/redo on every edit** ("Undo: Change X from A to B") — in editor *and viewer* | ✅ its signature strength | ❌ **version history only** — no interactive undo stack in the builder |
| Relative date filters (last N days, MTD/QTD/YTD) | ❌ absent everywhere (defect #9) | 🔶 not surfaced as first-class filter UI either — open opportunity for both |
| Selection persists across edit/view switch | ✅ | ✅ (state carried in report) |

**Verdict: Datalytics ahead** on the filter/action architecture and its auditability; **SAS clearly ahead on undo** — the single biggest UX gap left.

## 5. Pages, layout, viewer & consumption

| Capability | SAS VA | Datalytics |
|---|---|---|
| Multi-page reports, drag-grid canvas | ✅ flex/grid + extend/shrink flags | ✅ 12-column grid, multi-page |
| Page templates (built-in + save your own) | ✅ curated, thumbnails | ✅ built-ins + own (no thumbnails) |
| Page types: Basic / **Hidden** / **Pop-up** (modal drill target) | ✅ | ❌ |
| Page visibility limited to users/roles | ✅ | 🔶 folder/workspace-level sharing instead of per-page |
| Precision/absolute placement, page background image | ✅ | ✅ |
| Fixed report size / avoid scrollbars options | ✅ | 🔶 |
| Edit ↔ View as two skins of one document | ✅ | ✅ builder vs shared/embed view |
| Viewer side pane: read-only roles, display-rule legend, **filter logic disclosure** (`…OR Missing(x)`), ranks, comments | ✅ | 🔶 filter strip yes; a full "why am I seeing this" pane, partial |
| **Comments** on reports | ✅ (needs saved report) | ✅ CommentsPane |
| Playback / kiosk slideshow | ✅ Play report + Edit playback (3–3600 s) | ✅ kiosk playback (8s, any key exits) |
| **Viewer "View insights"** (automated outlier analysis on an object) | ✅ | 🔶 Insights Hub is dataset-level; not per-object in viewer |
| Re-type an object from the **viewer**, with a recommendation | ✅ | ❌ |
| Report Review / linter (accessibility + performance, severities, quick fixes) | ✅ + Evaluate Performance | ✅ review pane + interaction-graph audit (**broader than SAS's**); no performance profiler |
| Multi-document interface (N reports open, switcher) | ✅ | ❌ one report at a time |
| Session crash recovery ("Restore previous session") | ✅ server-side autosave of unsaved state | 🔶 version history protects saved edits; no unsaved-session recovery |
| Localization of report text | ✅ Localize report | ✅ translations pane + full **RTL/Arabic** (SAS side not observed doing RTL) |
| Themes | ✅ Dark/Light/High Contrast/custom; theme-aware basemaps | ✅ 6 themes + dash/pattern second channel for greyscale/color-blind printing |
| Deep links / addressable URLs | ❌ **one route for the whole app** (defect #24) | ✅ real routes (React SPA with pages, shared links, embeds) |

**Verdict: mostly level.** SAS's unique cards: pop-up/hidden pages, viewer object insights/re-typing, MDI, session recovery, Evaluate Performance.

## 6. Statistics, ML & forecasting

| Capability | SAS VA (base + observed Statistics/ML objects) | Datalytics |
|---|---|---|
| Forecasting with confidence band | ✅ | ✅ AutoETS |
| Forecast **what-if scenario** (move underlying factors) | ✅ full what-if environment in the viewer | ✅ `forecast_scenario` (OLS on time + factors, p-values, extrapolation flagged) |
| Forecast **goal seeking** ("when does it reach X?") | ✅ | ✅ `forecast_goal` |
| Automated explanation (what drives a variable) | ✅ | ✅ `explain` + guarded generated sentence |
| Automated prediction with champion selection | ✅ | ✅ tree + forest + linear/logistic on one split, with dumb baseline |
| **Score new rows against a saved champion** | ✅ | ✅ `prediction_models` (column order travels, unseen values reported, denied-column refusal) |
| Statistics **objects on the canvas** with model headers + sub-tabs (Fit Summary / Residuals / Odds Ratio / Confusion Matrix), population disclosure ("646K of 2.3M") | ✅ 8 objects: cluster, decision tree, GLM, GAM, linear, logistic, nonparametric logistic, **Model comparison** | 🔶 the *math* exists in the analysis catalogue (OLS, logistic, mixed, survival…), but not as canvas objects with tabbed diagnostic panels |
| **Model comparison** (three-panel verdict, winner colored) | ✅ | ❌ |
| ML objects: forest, gradient boosting, neural net, SVM, factorization machine, Bayesian network | ✅ 6 objects (5 unexercised in observation) | 🔶 forest/GBM inside automated_prediction; no NN/SVM/FM/BN |
| Hypothesis testing (t-test/ANOVA, chi-square, pairwise) | ❌ not in the product story | ✅ **ahead** |
| Regression with mixed models, survival analysis | ❌ | ✅ **ahead** |
| Effect sizes beside p-values | ❌ | ✅ **ahead** |
| Anomaly detection, association rules, key influencers, segmentation | 🔶 outlier flags only | ✅ full set |
| Network analysis w/ centrality metrics, path analysis | ✅ network + path objects (path discloses fabricated ordering) | ✅ network with 4 centralities, communities, predicted links; sankey/path |
| Text topics | ✅ + sentiment, 30+ languages | 🔶 topics ✅ (NMF), sentiment ❌, English stop words only |

**Verdict: Datalytics ahead on analytic substance; SAS ahead on analytic *presentation*** — models as living canvas objects with diagnostic tabs and a comparison verdict.

## 7. AI & assistive

| Capability | SAS VA | Datalytics |
|---|---|---|
| NL → SQL question answering | ❌ (assistant panel exists; effect unknown; no NL query surface observed) | ✅ agent with explicit graph, RLS-inherited, repair ladder, offline-capable |
| Chat copilot that edits the dashboard | ❌ | ✅ |
| Persona-driven whole-dashboard generation, every tile executed before offering | ❌ | ✅ |
| Model-free suggestion path (deterministic, ~4s) | ❌ | ✅ |
| Suggestions pane | ✅ but **random**: slot rotation, non-deterministic, ignores selection/page, proposes summed latitudes | ✅ profiled + validated + executed — already the "one accountable resolver" SAS lacks |
| Automatic chart type resolver on drop | ✅ but ignores cardinality; four disagreeing resolvers | ✅ one documented rule set; unplaceable fields named |
| AI custom-category generation | ✅ | ❌ (small) |
| Assistant invokes the statistical catalogue | ❌ | ✅ |
| Insight detection (trend, standout, laggard, correlation, outliers, quality) w/ novelty ranking | 🔶 outlier advisor only | ✅ |

**Verdict: Datalytics far ahead.** The SAS spec's own recommendation ("one resolver, reproducible, explainable, semantic veto") is closer to Datalytics's current state than SAS's.

## 8. Geography

| Capability | SAS VA | Datalytics |
|---|---|---|
| Geo object family | ✅ 10 (incl. **geo contour**, geo line-coordinate/region-coordinate layer stacks) | ✅ 9 (no contour, no explicit multi-layer stack object) |
| Layer stack on one map (region + coordinate layers combined) | ✅ | 🔶 |
| Sub-national regions bundled (states, provinces, ZIP) | ✅ provider-backed | 🔶 bring-your-own GeoJSON/TopoJSON boundary sets |
| Geography item from name lookup / provider / lat-long, **with validation preview** | ✅ | 🔶 classification + matcher (name / ISO-2 / ISO numeric); no validation dialog |
| Tile basemaps, theme-aware | ✅ OSM + Esri; High Contrast swap | 🔶 built-in world geometry; tile URL deferred until customer tile server exists |
| Drive-time / demographics / routing | ✅ Esri Premium (paid) | ❌ (out of scope) |
| Radius selection, pins | ✅ | ✅ radius-lasso filter; author pins (non-broadcasting by design) |
| Viewport controls (zoom to data, saved viewport) | ✅ | ✅ maps frame their data |
| Cross-filter from map geometry | 🔶 | ✅ by data value, 9 widgets |

**Verdict: SAS ahead** — the one structural lead it retains (supply of geometry + provider ecosystem + contour/layer stacks).

## 9. Sharing, delivery & operations

| Capability | SAS VA | Datalytics |
|---|---|---|
| Share link (no account), embed with SDK/allow-list | ✅ | ✅ |
| PDF export (report/page/object) | ✅ + page setup, TOC | ✅ |
| Data export (CSV/Excel), export policy governance | ✅ | ✅ + admin export policy |
| Image export per object | ✅ | ✅ |
| **Offline report package** | ✅ | ❌ |
| Scheduled email distribution | ✅ | ✅ + delivery log |
| Chat channel delivery | ✅ Teams | ✅ any webhook (Teams/Slack) |
| Alerts on conditions | ✅ display-rule alerts + subscriptions | ✅ dataset-condition alerts, rising-edge |
| Mobile app / PWA / M365 add-in | ✅ all three | ❌ responsive web only |
| SSO | ✅ Viya platform | ✅ OIDC + SAML per org |
| RLS / column security | ✅ / 🔶 (hide-item only, explicitly *not* a security control) | ✅ / ✅ **ahead** (columns removed pre-shaper, one enforcement point, AI included) |
| Quotas per tenant | 🔶 platform-level | ✅ 4 independent limits |
| Audit, monitoring pages, health probes, OTel | 🔶 Environment Manager (separate app) | ✅ in-product |
| Air-gapped / offline install | ❌ (cloud/licensed Viya) | ✅ **ahead** — offline bundle, no CDN, self-hosted LLM |
| Version history with restore | 🔶 autosave/conflict | ✅ snapshots, restore is undoable |

**Verdict: split.** SAS ahead on *distribution surfaces* (packages, mobile, M365); Datalytics ahead on governance, operations, and deployability.

## 10. Architecture & UX system (from the SAS blueprint's own judgement)

| Idea | SAS VA today | Datalytics today |
|---|---|---|
| Definition separate from results (BIRD) | ✅ | ✅ (report JSON + query API) |
| Batched page queries | ❌ one job per object | 🔶 per-widget requests |
| Truncation contract (`rowsScanned`/`rowsReturned`/reason on every result) | ❌ tiny ⓘ | 🔶 partial disclosures |
| Dictionary-encoded transport, inline-small/reference-large | ✅ | 🔶 |
| Canvas rendering + **accessible projection** | ❌ canvas only, no a11y layer | 🔶 DOM/SVG charts (inspectable) but no systematic ARIA table per chart |
| Addressable URLs | ❌ | ✅ |
| ≤2 MB initial JS | ❌ 45 MB + 13 MB WASM | ✅ (Vite SPA, orders of magnitude smaller) |
| Reason codes on every disabled control / refusal | ❌ five causes, one grey | 🔶 |
| Command-log undo, one sentence grammar | 🔶 (seven inconsistent grammars, but undo exists everywhere) | ❌ |
| Batch authorization decisions API | ✅ (its best API idea) | ❌ |

---

## Scorecard

| Area | Winner |
|---|---|
| Data connectivity & prep | **Datalytics** (slight) |
| Object catalogue breadth | Level (78 vs 67; different unique items each) |
| Role/config model | Level |
| Interactivity architecture | **Datalytics** — except **undo**, where SAS wins outright |
| Pages & viewer experience | **SAS** (slight: pop-up pages, viewer insights, MDI, session recovery) |
| Statistics substance | **Datalytics** |
| Statistics presentation (model objects, comparison) | **SAS** |
| AI / assistive | **Datalytics**, decisively |
| Geography | **SAS** |
| Sharing surfaces (mobile, packages) | **SAS** |
| Governance, security, ops, deployment | **Datalytics**, decisively |
| UX polish patterns (undo, disclosure, validation previews) | **SAS** |

**One-line summary:** Datalytics already has the better *engine, governance and AI*; SAS still has the better *hand-feel* — undo, disclosure, validation previews, model-object presentation, geography supply, and consumption surfaces. The gap list and plan (see `MISSING_IN_DATALYTICS.md` and `MASTER_PLAN.md`) close exactly that.
