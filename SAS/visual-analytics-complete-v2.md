# Visual Analytics Tool — Complete Reverse-Engineering Deliverable

All documents merged into one file: overview and recommendations first, then the specifications, then the session-by-session findings in chronological order (sessions 6 → 19). Each original file is a top-level section with its headings shifted down one level.

## Contents

**Overview**

1. [Visual Analytics Tool — reverse-engineering deliverable](#visual-analytics-tool--reverse-engineering-deliverable) — `README.md`
2. [Recommendations — what to build, in what order, and what to leave behind](#recommendations--what-to-build-in-what-order-and-what-to-leave-behind) — `RECOMMENDATIONS.md`

**Specifications**

3. [Visual Analytics Tool — UI/UX Reverse-Engineering & Implementation Specification](#visual-analytics-tool--uiux-reverse-engineering--implementation-specification) — `SAS_VA_implementation_spec__1_.md`
4. [Implementation Specification — for an AI coding agent](#implementation-specification--for-an-ai-coding-agent) — `implementation-spec.md`
5. [UI/UX Specification — analytics platform](#uiux-specification--analytics-platform) — `UI_UX_SPECIFICATION.md`
6. [Platform blueprint — building a professional data analytics product](#platform-blueprint--building-a-professional-data-analytics-product) — `PLATFORM_BLUEPRINT.md`

**Session findings**

7. [Findings from a live, saved, production report](#findings-from-a-live-saved-production-report) — `saved_report_findings.md`
8. [Session 7 — exhaustive pass over the remaining unexplored surfaces](#session-7--exhaustive-pass-over-the-remaining-unexplored-surfaces) — `session7_exhaustive_pass.md`
9. [Session 8 — closing the remaining exploration list](#session-8--closing-the-remaining-exploration-list) — `session8_exhaustive_pass.md`
10. [Session 9 — the automatic chart resolver, derived empirically](#session-9--the-automatic-chart-resolver-derived-empirically) — `session9_automatic_charts.md`
11. [Favorites crawl — live observation session 10](#favorites-crawl--live-observation-session-10) — `favorites_crawl.md`
12. [The Suggestions pane — exhaustive pass (session 11)](#the-suggestions-pane--exhaustive-pass-session-11) — `suggestions_pane_deep_dive.md`
13. [Resolving the two open Suggestions questions — session 12](#resolving-the-two-open-suggestions-questions--session-12) — `suggestions_conflicts_resolved.md`
14. [Data pane, multi-select and drag-and-drop — exhaustive pass (session 13)](#data-pane-multi-select-and-drag-and-drop--exhaustive-pass-session-13) — `data_dragdrop_deep_dive.md`
15. [Geography items and the geo-map family — exhaustive pass (session 14)](#geography-items-and-the-geo-map-family--exhaustive-pass-session-14) — `geography_deep_dive.md`
16. [Statistical objects and statistics-flavoured charts — exhaustive pass (session 15)](#statistical-objects-and-statistics-flavoured-charts--exhaustive-pass-session-15) — `statistics_deep_dive.md`
17. [Model comparison, fitted models and the last two charts — session 16](#model-comparison-fitted-models-and-the-last-two-charts--session-16) — `model_comparison_and_ml.md`
18. [Observed system architecture — session 17](#observed-system-architecture--session-17) — `observed_architecture.md`
19. [Closing the UNKNOWN register — session 19](#closing-the-unknown-register--session-19) — `unknowns_closed.md`

---

<!-- ===== Source: README.md ===== -->

## Visual Analytics Tool — reverse-engineering deliverable

A complete implementation specification for building a new analytics product with similar functionality, workflows, information architecture, interaction patterns and visual language — **without copying proprietary source code, brand assets, wordmarks, icons or product naming.**

**Subject:** SAS Visual Analytics, "Explore and Visualize" module (SAS Viya for Learners deployment).
**Method:** six live observation sessions driving the running application through a browser, plus one cross-check against vendor training material. No vendor source code was read. All work happened in blank, never-saved sandbox reports on a 2.34M-row sample table; no existing report was opened, modified, saved, shared, exported or deleted.
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
| `implementation-spec.md` | **Start here to build.** Architecture, state, data model, visualization config, routing, components, interactions, responsive, design system, P0–P4 priorities, patterns to copy, 25 defects to fix, acceptance criteria, vendor-documentation cross-check, and the UNKNOWN list |
| `screenshots/` | Capture manifests by area. **No image files** — see the note in any manifest for why, and what to re-capture |

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

<!-- ===== Source: SAS_VA_implementation_spec__1_.md ===== -->

## Visual Analytics Tool — UI/UX Reverse-Engineering & Implementation Specification

**Subject application:** SAS Visual Analytics, "Explore and Visualize" module (SAS Viya for Learners deployment, host `vfl-026.engage.sas.com`).
**Purpose of this document:** enable an AI coding agent to build a *functionally similar* analytics product — same information architecture, workflows, interaction patterns and visual language — **without copying proprietary source code, brand assets, wordmarks, icons or product naming.**
**Method:** six live observation sessions driving the running application through a browser. No vendor documentation was consulted. All work happened in blank, never-saved sandbox reports on the sample table `RETAILDEMO_2` (2,339,245 rows, 57 columns, Aug 2009 – Jan 2010). No existing report was opened, modified, saved, shared, exported or deleted.
**Observation dates:** 22 Sep 2026.

#### Provenance of the observations
Sessions 1–5 covered the left rail and toolbar, the right-hand property panes, the full object library, data preparation, and interactivity; their findings are recorded in five companion inventory files. **Session 6 (this one)** added the material those files do not contain: the landing/home screen, design tokens measured from live computed styles, the categorical palette sampled from rendered pixels, the network/query protocol, the single-route finding, CSS breakpoints, canvas rendering, the Report Review empty state, rank tie caps, crosstab subtotal verification on both axes, and the AI assistant panel.

#### Evidence labelling used throughout
- **OBSERVED** — seen directly in the running UI.
- **INFERRED — confidence: High / Medium / Low** — deduced from observed behaviour.
- **UNKNOWN** — could not be determined from the UI.

#### Legal / originality constraints for the implementing agent
1. Do not copy the vendor's name, logo, icon set, typeface (`Anova UI` is a licensed vendor font), theme names, or any screenshot.
2. The measured design tokens in Section L are a *description of proportions and roles* — reproduce the **system** (38px banner, 34px rail, 2px radii, one accent colour), not the exact brand hue, unless the colour is generic.
3. Terminology such as "Crosstab", "Key value", "Data roles", "Display rules", "Lattice" is vendor-flavoured. Section O suggests neutral equivalents.
4. No proprietary source was read; everything here is black-box behaviour.

---

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
| Suggestions | Auto-generated chart thumbnails with captions, source dropdown, refresh, "add more" (+4 per click) | Suggestions can be statistically nonsensical (see Section O risks) |
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

#### C.4 Dialog inventory (all observed; every one was cancelled)

| Dialog | Trigger | Required fields | Refusal behaviour observed |
|---|---|---|---|
| Choose Data | Add data / role "+ Add" with no source | table selection | "You must select an item." when a table is previewed but not selected |
| New Calculated Item | + New data item | Name*, valid expression | OK greyed until expression parses |
| Expression editor (also Advanced Filter, Apply data filter, Parameter value) | several | expression | Inline error count "(n)", red squiggle, gutter marker, messages such as "Unexpected >", type mismatch, "Division by zero is undefined." |
| New Hierarchy | + New data item | Name and items are marked required | **OK stays enabled with nothing entered and then does nothing, silently** |
| New Custom Category | + New data item | Name, groups | AI "Generate value groups" available for categories only |
| New Geography Item | + New data item | Name*, Based on*, Geography data source* | OK with no provider silently refused |
| New Parameter | + New data item | Name, Type | — |
| New Partition | + New data item | Name*, percentages | Training 100 → "The value must be less than 100." |
| Custom sort | category right-click | ≥1 item | OK greyed at 0; **partial order accepted** |
| Format | Format ▸ / pencil | — | Width > 32 → "The value cannot be greater than 32." |
| New Scope | Calculated item Scope + | scope type | Custom intersection (default) / Grand total |
| New Display Rule | Display Rules + | operator + value | **Rule with no colour accepted, does nothing** |
| Add URL Link | Actions | URL | "Open URL" greyed until a URL is typed |
| Select a Template | empty page | template selection | **Single click does not select** → "You must select a template."; double-click applies |
| Manage Page Templates | template dialog | — | Vendor templates locked (badge); custom ones have Edit/Delete |
| Edit Playback | view ⋮ | seconds | min 3 / max 3,600 with explicit messages |
| Save confirmation | Close with unsaved changes | — | "Do you want to save '<name>' before it is closed?" → Save / Don't save / Cancel |
| Evaluate Performance gate | Report Review | saved report | "You must save a report before you can analyze its performance." |
| No Comparable Models | insert Model comparison | two comparable models | Blocking explanatory dialog on insert |

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
- **Entry:** Objects pane (double-click or drag); Data pane item → "Add to current page"/"Add to new page"; Suggestions pane thumbnail; page template.
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
- **Entry:** rail → Suggestions.
- **Result:** thumbnails generated from the source; drag one onto the page; "add more" yields +4 each time.
- **Risk:** suggestions can be statistically meaningless (summed latitudes, summed years, months sorted by value).
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

### F. Component Inventory

| Component | Purpose | Location | Variants | States | Inputs | Outputs | Interactions | Responsive |
|---|---|---|---|---|---|---|---|---|
| App banner | Global identity + system actions | Top, full width, 38px | one | static | — | menu opens | click; opens side panels | Fixed height (UNKNOWN below 768px) |
| Report toolbar | Document-level actions | Below banner, 44px | edit / view variants | enabled, disabled (unsaved report) | — | commands | click; ⋮ opens menu | Fixed |
| Icon rail | Switch left panes | Left, 34px | 5 tabs; labels can be shown | selected, hover, focus ring | — | pane change | click; "»" toggles labels | Fixed |
| Side pane (left/right) | Hold panes | 338px left, 384px right | pinned / unpinned | pinned, auto-collapse | — | — | pin icon; collapse chevron; auto-collapse on canvas click | Fixed widths |
| Pane header + ⋮ | Pane-level config | Top of each pane | — | — | — | menu | click | — |
| Search / filter box | Narrow lists | Data, Objects, Options, Filters, dialogs | plain | empty, typing, cleared | text | filtered list | live filter; **text can persist across dialogs (defect)** | — |
| Data item row | Represent a column | Data pane | category / measure / aggregated / date / geography | default, hover (reveals Edit properties), selected, badged (sensitive, outlier) | — | selection | click, right-click (20+ actions), hover card, drag to canvas | — |
| Inline property editor | Rename/reclassify | Data pane | measure / category / date variants | expanded | name, classification, format, aggregation | item update | pencil toggles | — |
| Object library list | Insert objects | Objects pane | grouped, sortable | — | — | insert | double-click, drag | Scrolls to top after insert (defect) |
| Canvas | Host objects | Centre | page-scoped | empty, populated, maximized | drops | layout | drag, drop, resize handles, right-click | Scrolls; "Avoid scrollbars" option |
| Page tab strip | Switch pages | Above canvas | Basic / Hidden / Pop-up (eye-slash icon) | active, inactive | — | page change | click, ⋮ menu, "+" | Disappears in view mode when only one Basic page |
| Object frame | Wrap a visualization | Canvas | any object type | default, selected (border + handles), hover (⋮ + maximize), maximized, loading, error, capped | roles | queries | click, double-click, right-click, drag, resize, maximize | Extend/shrink width and height flags |
| Chart canvas | Render marks | Inside object frame | 30 graph types + 10 geo | placeholder, rendered, empty, capped | query result | pixels | hover tooltip, click select, double-click drill; **rendered to `<canvas>`, not DOM** | Redraws on resize |
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
| Thumbnail card | Suggest or open | Suggestions, Landing | chart thumbnail / report card | — | — | insert or open | drag / click | Grid reflows |
| AI panel | Assistive chat | Right overlay | — | welcome, conversation | prompt | response | chips, type, attach | ~460px overlay |

**Not present (OBSERVED absence):** breadcrumb navigation for pages, pagination controls (grids scroll virtually), a command palette, and any documented keyboard-shortcut surface (Help has no shortcut reference).

---

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

**Geo maps (10)** — roles are grouped per map layer.

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

#### G.3 Capability boundaries (do not invent beyond these)
- No zoom or pan on standard charts; the Overview axis is the only navigational aid.
- No period-over-period comparison on any chart; time calculations exist **only** as Data-pane calculated items.
- No relative date filtering anywhere in the filter or control UI (Section H.6).
- No distinct-count aggregation in the aggregation menus.
- No `COALESCE`/`IFNULL`; missing values are handled by `Missing()`, `NotMissing()`, `IsSet()`, `NumMiss()`.

---

### H. Interaction Model

#### H.1 Pointer semantics (OBSERVED)
| Gesture | Target | Behaviour |
|---|---|---|
| Single click | Chart mark | Select/deselect; tooltip card; filters or highlights linked objects |
| Single click | Object frame | Select object → drives every right-pane tab |
| Single click | Canvas background | Deselect; auto-collapses unpinned panes |
| **Double click** | Chart mark (view mode) | **Triggers page links / drill** — a single click never does |
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

#### H.3 Undo / redo (a strength worth copying)
Undo labels are fully descriptive and expose the exact operation: "Undo: Assign Customer Age, Sales to Crosstab - Region 1", "Add section with template", "Change label on data item from X to Y", "Change the option showRowNumbers for List table - City 1 to true". Rejected inputs create **no** undo entry. Redo is present. No auto-save of user edits during a session, but unsaved state is persisted for crash recovery.

#### H.4 Progressive disclosure
Panes auto-collapse unless pinned; property sections are collapsible; advanced settings hide behind ⋮ menus; the expression editor is the escape hatch behind every filter and calculation; a settings search box spans the Options pane.

#### H.5 Confirmation and safety
Confirmations appear **only** for closing unsaved work and for actions that require a save. Destructive configuration changes (deleting links by switching action modes) use a toast with Undo instead of a prompt. Deleting objects and pages is immediate, undoable, and never confirmed.

#### H.6 Filtering model (the product's core semantic)
Three independent layers, which the UI does not unify:
1. **Object filters** — defined per object in the Filters pane; can be promoted to **common filters** reusable across objects and pages.
2. **Controls (prompts)** — report-level (all pages), page-level (all objects on the page, cascading into other controls), or body-level (filter nothing until explicitly linked).
3. **Actions** — object links (Filter or Linked selection), page-wide automatic modes, page/report/URL links.

**Critical for reimplementation:** filters arriving from controls and links are **invisible** in the object's Filters pane; the only shared surface is the optional filter breadcrumb. A better product would show one merged, inspectable filter stack.

**Missing values are handled inconsistently across the three layers (OBSERVED):**
| Surface | Default for missing |
|---|---|
| Object filter (numeric, category, date) | **Included** (`OR Missing(x)` in the generated logic) |
| List control | Present as a selectable value "(missing values)", unselected |
| Slider control | **Excluded, even at full range**, until "Missing values option" is enabled |
| Custom category grouping | Silently folded into "Other" |
| Invert selection | Also inverts the include-missing setting |

**Relative dates:** absent from filters and controls. Only expressions provide `Now()` and the five periodic functions. **A reimplementation should add first-class relative ranges (last N days, MTD/QTD/YTD, rolling windows).**

#### H.7 Keyboard
No shortcut reference exists in Help. Observed: Esc closes menus and dialogs — and **inside a dialog's dropdown it closes the entire dialog, discarding work** (a defect to avoid). Enter commits inline fields. Tab focus rings are drawn. Full shortcut map: **UNKNOWN**.

---

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
| DataItem | label, name-in-data, classification (Category/Geography/Measure), format, aggregation default, distinct count, sensitivity flag, outlier flag, expression, "used by" list | belongs to DataSource | Auto on load, or + New data item | Edit properties (inline) | Hide / Delete (varies) | — |
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

### K. Routing Model

**Finding (OBSERVED): the application has effectively one route.** `https://<host>/SASVisualAnalytics/` never changed while creating a report, loading data, adding objects, switching pages, opening dialogs, entering view mode or closing a report. No path segments, no query string, no hash fragment.

| Route | Screen | Parent | Entry | Parameters | Required state |
|---|---|---|---|---|---|
| `/SASVisualAnalytics/` | Landing, editor and viewer alike | — | direct navigation | none observed | authenticated session |
| `/SASLogon/oauth/authorize?client_id=sas.<service>&redirect_uri=…` | Silent per-service OAuth | — | triggered by first call to each backend service | client_id, redirect_uri, response_type, state | — |

**Consequences for a reimplementation (and an improvement to make):** report, page, object selection and view mode are **not addressable**, so no deep links, no browser Back/Forward within the app, and no bookmarkable state. The product compensates with in-app "Copy link…" commands (**UNKNOWN** what URL they emit — the action is gated behind saving). **Recommendation:** give the rebuild real routes, e.g. `/reports/:reportId/pages/:pageId?mode=view&object=:objectId&filters=…`.

---

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

#### L.5 Visual language summary for the rebuild
Dense, flat, information-first: one saturated brand blue used sparingly for the banner and links, near-black text, 2px radii, hairline borders instead of shadows, generous use of grey surfaces to separate rails from canvas, and a soft mid-saturation categorical palette that stays legible against white. Copy the *system*; choose your own hues.

---

### M. Responsive Behaviour

**Directly observed:** only the 1214×731 desktop viewport. The window could not be narrowed in this environment, so tablet and mobile renderings were **not** observed.

**Observed from the stylesheets (OBSERVED):** breakpoints at **`min-width: 768px`, `992px`, `1200px`**, plus a **print** stylesheet.

| Breakpoint | Layout change | Components hidden | Components collapsed | Navigation | Charts | Tables |
|---|---|---|---|---|---|---|
| ≥1200px | Three-column: rail + left pane + canvas + right pane | — | Panes auto-collapse when unpinned | Full rail with optional labels | Canvas-rendered, redraw on resize | Virtualized, fit-to-width |
| 992–1199px | **UNKNOWN** | | | | | |
| 768–991px | **UNKNOWN** | | | | | |
| <768px | **UNKNOWN** | | | | | |
| Print | Dedicated stylesheet exists; page "Export as PDF" is the sanctioned path | | | | | |

**Author-controlled responsiveness (OBSERVED):** per-object *Specify / Extend / Shrink* width and height flags, page-level *Avoid scrollbars*, report-level *Set fixed report size*, and a *Precision container* for absolute placement. These make layout behaviour an authoring decision rather than a purely automatic one — a pattern worth reproducing.

**Recommendation:** treat the authoring experience as desktop-only (≥1200px) and build a separate, genuinely responsive **read-only viewer** for tablet and phone.

---

### N. Screenshots

**Constraint — no image files are attached.** The browser automation available for this work can display a screen to the operator but cannot write image files to disk, and the mandated capture paths (Firefox `Ctrl+Shift+S`, Chrome DevTools "Capture node screenshot") are unreachable from it. Rather than substitute prose for images silently, this section indexes the **documented states** each screenshot would have shown; every one was directly observed and is described in the section named.

| ID | Screen | Route | State | Action that produced it | Key elements | Described in |
|---|---|---|---|---|---|---|
| V01 | Landing | `/SASVisualAnalytics/` | Populated, Recommendations selected | Initial load | Folder list, search, sort, grid/list toggle, cards, New report, recovery card | C.1 S1 |
| V02 | Editor | same | Blank report, empty canvas | New report | Rail, "Design a Report", Select a template, empty Data pane | C.1 S2 |
| V03 | Editor | same | Data loaded | Recently Used Data → table | Item tree, distinct counts, sensitivity shields | C.2 Data |
| V04 | Editor | same | Object placeholder | Double-click Bar chart | Synthetic "Measure by Category" sample + Assign data | C.5 |
| V05 | Editor | same | Rendered chart | Assign Region (+ auto Frequency) | "Frequency of Region", descending bars | G.2 |
| V06 | Editor | same | Grouped chart + legend | Add Department to Group | 6-colour categorical legend | L.2 |
| V07 | Editor | same | Data Roles pane | Select object → Roles tab | 8 role groups, greyed "+ Add" on full single roles | G.1 |
| V08 | Editor | same | Options pane with sections expanded | Options tab with an object selected | Collapsible sections, Totals and Subtotals (the pane's settings-search box exists but was never exercised) | C.3 |
| V09 | Editor | same | Crosstab with totals + subtotals, nested both axes | Enable Totals and Subtotals | "Subtotal: ASIA", "Subtotal: Maple" | G.2 |
| V10 | Editor | same | Filters pane, category filter | + New filter | Value checkboxes, frequency bars, Include missing ✓ | C.3, H.6 |
| V11 | Editor | same | Ranks pane | + New rank | Subset, Count 10, Rank by, Ties, All Other | D.A8 |
| V12 | Editor | same | Actions pane | Actions tab | Automatic actions, Object/Page/Report/URL Links | D.A10 |
| V13 | Editor | same | Expression editor | + New data item → Calculated item | Toolbar, line-numbered editor, error count, Results grid | D.A6 |
| V14 | Editor | same | Empty-result error | Filter to a non-matching value | Axis frame + "No data matches the current filters." | C.5 |
| V15 | Editor | same | Row-cap notice | Bar chart on 1.7M categories | ⓘ "Only 3,000 rows of the data appear." | C.5 |
| V16 | Editor | same | Tie-cap notice | Rank with Ties on | ⓘ "…too many ties associated with the rank." | D.A8 |
| V17 | Editor | same | Loading | Object re-query | Spinner + "Loading…" | C.5 |
| V18 | Editor | same | Outline pane | Rail → Outline | Page/object tree, New Page | C.2 |
| V19 | Editor | same | Suggestions pane | Rail → Suggestions | Thumbnail cards with captions | C.2 |
| V20 | Editor | same | Report Review pane | Rail → Report Review | Severity counters, Evaluate Performance | C.2 |
| V21 | Editor | same | AI side panel | Banner AI icon | Welcome, 3 chips, prompt box, disclaimer | C.1 S7 |
| V22 | Editor | same | Context menu on a chart | Right-click a mark | 25-item menu with submenus | H.1 |
| V23 | Editor | same | Page ⋮ menu + Page type submenu | Page tab ⋮ | Basic ✓ / Hidden / Pop-up (greyed with one page) | D.A12 |
| V24 | Editor | same | Template dialog | Select a template | List/grid toggle, Manage Templates | D.A13 |
| V25 | Viewer | same | View mode | Pencil toggle | Rails hidden, tabs for Basic pages only | D.A16 |
| V26 | Viewer | same | Pop-up page modal | Double-click a linked mark | Modal, ×, Close, Export as PDF, resize grip | C.1 S6 |
| V27 | Editor | same | Save confirmation | ⋮ → Close on an unsaved report | "Do you want to save …?" Save / Don't save / Cancel | C.4 |
| V28 | Editor | same | Selected + hover | Click then hover a mark | Highlight, dimmed peers, data tip | C.5 |

---

### O. Implementation Specification

#### O.1 Recommended architecture (INFERRED from observed behaviour — confidence: High)

**Query protocol (OBSERVED at the network layer, no credentials or tokens recorded):**
- One **executor** is created per data session: `POST /reportData/executors` → 201.
- Every object's query is a **job** posted to that executor: `POST /reportData/jobs?indexStrings=true&embeddedData=true|limited&executorId=<id>&wait=30&jobId=<executorId>_c<N>&sequence=<n>&dataDefinitions=dd<N>` → 201. `wait=30` indicates long-polling.
- Results are fetched as files: `GET /reportData/results/<jobId>/files/dd<N>.csv` and a companion `dd<N>index.csv` (string index — consistent with `indexStrings=true` dictionary-encoding category values).
- Supporting services observed: `/dataTables/dataSources/{source}/tables/{table}` and `/casManagement/…` (table metadata), `/visualAnalyticsAdministration/defaultReportDataViews?filter=eq(dataTableUri,…)`, `/catalog/instances?filter=eq(resourceId,…)` (asset catalogue), `/annotations/annotations?resourceUri=…`, `/folders/folders/@myHistory/histories` (recently used), `/notifications/notifications?…`, `/files/files` (`POST` then `PATCH` — **INFERRED: unsaved-state autosave powering session recovery, confidence: Medium-High**).
- Auth is per-service silent OAuth: a first call returns an auth challenge, the client is bounced through `/SASLogon/oauth/authorize?client_id=sas.<service>` and the call is retried. **Do not replicate this pattern** — use one session token across your services.

**Build it as:** a single-page client with a **query engine per data source**, a **job queue with sequence numbers**, **columnar/dictionary-encoded result transport**, and **canvas-rendered charts and grids**. Charts and data grids alike are drawn to `<canvas>`: DOM and accessibility-tree queries for cell text return nothing, while a single `<canvas>` element carries the rendered pixels (**OBSERVED** by DOM inspection; the performance motive is **INFERRED — confidence: High**). The cost is that no cell text exists in the DOM, so pair canvas rendering with an accessible table or ARIA summary, which the subject lacks.

#### O.2 Build order
1. **Data layer** — table metadata, column classification (category/measure/date), distinct counts, aggregation engine, row caps.
2. **Object model** — object types with typed role schemas; the role schema *is* the product's contract (Section G.1 is a complete specification of 78 of them).
3. **Canvas and pages** — layout with extend/shrink flags, page types, templates.
4. **Property panes** — Options / Roles / Filters / Ranks / Rules / Actions, each scoped by selection.
5. **Interaction layer** — controls, links, modes, breadcrumb.
6. **Authoring aids** — expression editor, calculated items, custom categories, hierarchies.
7. **Viewer** — read-only mode, side pane, drill, export.
8. **Assistive** — suggestions, review/lint, AI panel.

#### O.3 Patterns to copy (these are the product's real strengths)
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

#### O.4 Defects to fix in the rebuild (observed failure modes, each a product opportunity)
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
| 11 | Filters from controls and links invisible in the Filters pane | One merged, inspectable filter stack per object |
| 12 | Text input prompt is exact and case-sensitive despite offering prefix suggestions | Match what the autocomplete implies; offer contains/starts-with |
| 13 | Single click highlights but does not select in template and list dialogs | Single click selects |
| 14 | **Esc inside a dropdown closes the whole dialog and discards the work** | Esc closes only the innermost layer |
| 15 | Silent rejections (pie "Other" 101%, forecast horizon 0/9999, Hierarchy OK with no name, Geography OK with no provider) | Always explain a refusal |
| 16 | Display rule with no colour accepted and does nothing | Require a visual effect or warn |
| 17 | Duplicate data-item names accepted silently | Warn and disambiguate |
| 18 | Converting an object to an incompatible type silently re-maps roles (a date became a *Color*) | Preview the mapping and require confirmation |
| 19 | Suggestions propose meaningless charts (summed latitudes, summed years) | Filter suggestions by column semantics |
| 20 | Object library scrolls back to the top after every insert; search text persists across dialogs | Preserve scroll position; scope search state |
| 21 | Two-way filter mode makes a list control filter itself to one value | Exclude a control from its own filter scope |
| 22 | Clicking the "All Other" bar clears the filter instead of filtering to its members | Filter to the bundled members |
| 23 | Everything renders to canvas with no accessible equivalent; no keyboard shortcut surface | Provide an accessible table view, ARIA summaries and a documented, discoverable shortcut map |
| 24 | Single route; no deep links, no browser history | Addressable routes for report, page, object and view mode |
| 25 | Fonts inconsistent by default (report font vs crosstab rule font) | One type system |

#### O.5 Terminology map (avoid vendor-flavoured names)
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

#### O.6 Acceptance criteria (verifiable against this document)
1. A user can go from an empty report to a rendered, filtered, cross-linked two-page report **without writing a query** (Journey J1).
2. Every object type declares a role schema; pickers offer only type-compatible columns; required roles are enforced (Section G.1).
3. Totals, subtotals and "other" buckets are recomputed from source rows at their own level — proven for Average on both axes, and for a distinct-count grand total (Section G.2).
4. Missing values behave identically in every filtering surface and are always disclosed (Defect 2).
5. Truncation, tie caps and dropped rows are always visible and explained (Defects 3, 6; Strength 5).
6. Undo covers every configuration change with a descriptive label, and no mode switch destroys configuration (Strength 3, Defect 10).
7. Report, page, object and mode are addressable by URL (Defect 24).
8. The viewer is keyboard-navigable and exposes an accessible equivalent of every canvas-rendered visual (Defect 23).

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
| Suggestions can be statistically poor | Explains the engine: suggestions are driven by **cardinality and measure correlations**, and items already used are not reused in newly generated suggestions |

#### P.2 New facts that resolve items previously marked UNKNOWN
| Previously UNKNOWN | DOCUMENTED answer | Consequence for the rebuild |
|---|---|---|
| Saved-report persistence format | The report **definition** is a separate artefact from the runtime result — the vendor calls it **BIRD** (Business Intelligence Report Definition) and treats it as the recipe the browser renders, with query results embedded into it | Confirms the Section O.1 split. Model the document as `ReportDefinition` JSON (pages → objects → roles → filters/actions) and keep results entirely out of it |
| What "data views" are | A reusable, shareable set of data-item customizations bound to a data source — explicitly **not** a database view | Add a `DataView` entity: classification, format, aggregation and naming overrides that travel with the source across reports |
| What "Map data" does | **Data-source mapping** connects corresponding items across two sources so one action can filter both; mapped items' **formats must match** | Add `DataSourceMapping` (source item ↔ target item) and validate format compatibility at mapping time |
| Whether a tablet/phone layout exists | Consumption is via browser, an installable **PWA**, and a separate **mobile app** with its own discovery/connection flow | Section M's recommendation stands and is strengthened: build a desktop authoring surface and a distinct mobile viewer, rather than reflowing the editor |
| Why the Geography role offered nothing | Geographic items need either latitude/longitude columns or a **geographic data provider**; custom polygon shapes require a provider, and defining providers is permission-gated | The empty picker was a missing prerequisite, not a bug. In a rebuild, say so in the picker and link to the fix |
| How the automatic chart picks a type | Chosen from the **number and type** of dropped items (the documented example: four measures → correlation matrix) | Specify an auto-chart resolver as a documented mapping from (count, types) → object type, and show the user why it chose what it chose |
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
- Tablet and mobile layouts — **partially resolved (DOCUMENTED, Section P.2):** consumption uses a PWA and a separate mobile app rather than a reflowed editor. The actual rendering at each CSS breakpoint (768 / 992 / 1200) is still unobserved.
- Full keyboard shortcut map; Help exposes no shortcut reference.
- Semantic success / warning / error colours — none appeared in any observed state.
- AI assistant behaviour once a prompt is sent; AI custom-category group generation.
- Join editor (the join query timed out before the editor opened) and Import data. **Map data and data views are now explained (DOCUMENTED, Section P.2)** but were never exercised.
- Geo map rendering with real geography (no geography item was created). The empty Geography picker is explained by the missing lat/long or provider prerequisite (DOCUMENTED, Section P.2).
- Model comparison with two compatible models; "Create pipeline".
- Alert subscriptions; Comments (require a saved report).
- The 79th object counted by the Show/Hide Objects dialog but absent from the tree.
- Server-side effects of any action, and all backend implementation details.


---

<!-- ===== Source: implementation-spec.md ===== -->

## Implementation Specification — for an AI coding agent

> **Evidence labels:** OBSERVED · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.


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
| 11 | Filters from controls and links invisible in the Filters pane | One merged, inspectable filter stack per object |
| 12 | Text input prompt is exact and case-sensitive despite offering prefix suggestions | Match what the autocomplete implies; offer contains/starts-with |
| 13 | Single click highlights but does not select in template and list dialogs | Single click selects |
| 14 | **Esc inside a dropdown closes the whole dialog and discards the work** | Esc closes only the innermost layer |
| 15 | Silent rejections (pie "Other" 101%, forecast horizon 0/9999, Hierarchy OK with no name, Geography OK with no provider) | Always explain a refusal |
| 16 | Display rule with no colour accepted and does nothing | Require a visual effect or warn |
| 17 | Duplicate data-item names accepted silently | Warn and disambiguate |
| 18 | Converting an object to an incompatible type silently re-maps roles (a date became a *Color*) | Preview the mapping and require confirmation |
| 19 | Suggestions propose meaningless charts (summed latitudes, summed years) | Filter suggestions by column semantics |
| 20 | Object library scrolls back to the top after every insert; search text persists across dialogs | Preserve scroll position; scope search state |
| 21 | Two-way filter mode makes a list control filter itself to one value | Exclude a control from its own filter scope |
| 22 | Clicking the "All Other" bar clears the filter instead of filtering to its members | Filter to the bundled members |
| 23 | Everything renders to canvas with no accessible equivalent; no keyboard shortcut surface | Provide an accessible table view, ARIA summaries and a documented, discoverable shortcut map |
| 24 | Single route; no deep links, no browser history | Addressable routes for report, page, object and view mode |
| 25 | Fonts inconsistent by default (report font vs crosstab rule font) | One type system |

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
8. The viewer is keyboard-navigable and exposes an accessible equivalent of every canvas-rendered visual (Defect 23).

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
| Suggestions can be statistically poor | Explains the engine: suggestions are driven by **cardinality and measure correlations**, and items already used are not reused in newly generated suggestions |

#### P.2 New facts that resolve items previously marked UNKNOWN
| Previously UNKNOWN | DOCUMENTED answer | Consequence for the rebuild |
|---|---|---|
| Saved-report persistence format | The report **definition** is a separate artefact from the runtime result — the vendor calls it **BIRD** (Business Intelligence Report Definition) and treats it as the recipe the browser renders, with query results embedded into it | Confirms the Section O.1 split. Model the document as `ReportDefinition` JSON (pages → objects → roles → filters/actions) and keep results entirely out of it |
| What "data views" are | A reusable, shareable set of data-item customizations bound to a data source — explicitly **not** a database view | Add a `DataView` entity: classification, format, aggregation and naming overrides that travel with the source across reports |
| What "Map data" does | **Data-source mapping** connects corresponding items across two sources so one action can filter both; mapped items' **formats must match** | Add `DataSourceMapping` (source item ↔ target item) and validate format compatibility at mapping time |
| Whether a tablet/phone layout exists | Consumption is via browser, an installable **PWA**, and a separate **mobile app** with its own discovery/connection flow | Section M's recommendation stands and is strengthened: build a desktop authoring surface and a distinct mobile viewer, rather than reflowing the editor |
| Why the Geography role offered nothing | Geographic items need either latitude/longitude columns or a **geographic data provider**; custom polygon shapes require a provider, and defining providers is permission-gated | The empty picker was a missing prerequisite, not a bug. In a rebuild, say so in the picker and link to the fix |
| How the automatic chart picks a type | Chosen from the **number and type** of dropped items (the documented example: four measures → correlation matrix) | Specify an auto-chart resolver as a documented mapping from (count, types) → object type, and show the user why it chose what it chose |
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
- Tablet and mobile layouts — **partially resolved (DOCUMENTED, Section P.2):** consumption uses a PWA and a separate mobile app rather than a reflowed editor. The actual rendering at each CSS breakpoint (768 / 992 / 1200) is still unobserved.
- Full keyboard shortcut map; Help exposes no shortcut reference.
- Semantic success / warning / error colours — none appeared in any observed state.
- AI assistant behaviour once a prompt is sent; AI custom-category group generation.
- Join editor (the join query timed out before the editor opened) and Import data. **Map data and data views are now explained (DOCUMENTED, Section P.2)** but were never exercised.
- Geo map rendering with real geography (no geography item was created). The empty Geography picker is explained by the missing lat/long or provider prerequisite (DOCUMENTED, Section P.2).
- Model comparison with two compatible models; "Create pipeline".
- Alert subscriptions; Comments (require a saved report).
- The 79th object counted by the Show/Hide Objects dialog but absent from the tree.
- Server-side effects of any action, and all backend implementation details.


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

<!-- ===== Source: saved_report_findings.md ===== -->

## Findings from a live, saved, production report

**Report examined:** `102_111_Viewing a Report Using the Progressive Web App (PWA)`
**Location:** `/Courses/VISUAL/` · **Created:** 5 Apr 2024 · **Modified:** 24 Oct 2025 · **Data source:** `PRODUCTS` (Orion Star Sports and Outdoors sample)
**Observed:** 23 Sep 2026, in **View mode**, read-only.

#### Why this matters
Every previous session used blank, never-saved sandbox reports. That left a structural blind spot: roughly a dozen features are gated behind saving, and nothing could be observed about how a *designed* report actually composes objects. This is the first observation of a real, populated, multi-page report built by a report author.

#### Safety log
- The report was found open in **Editing** mode. I switched to **View mode** immediately so no interaction could alter it, and did everything read-only from there.
- Nothing was saved, exported, shared, copied, deleted or commented on. No confirmation dialog appeared at any point.
- Viewer-session state I changed for testing (a prompt selection and one drill) was **restored** to the state I found it in: Continent = North America, no drill.
- Two dialogs were opened and closed without action: the "Details" pop-up page and "About This Report".

---

### 1. Report structure

| Page | Type | Composition |
|---|---|---|
| **Report Overview** | Basic | Pure documentation page built from Text objects: OVERVIEW, PAGES and UPDATE SCHEDULE headings (orange, dashed rule), a page-link list, a data-refresh timestamp, and a contact email |
| **Supplier Analysis** | Basic | Continent Selector (button bar, page-scoped) · Supplier Locations (geo coordinate map) · Supplier Details (list table with gauge cell visualization) · Quantity Sold and Profit Generated by Month (dual-axis bar-line) · Profit by Year and Month (waterfall on a date hierarchy) · Details text link |
| **Product Analysis** | Basic | Quantity and Profit by Product Category (treemap) · Profit by Product Group (diverging bar) · **Stacking Container** holding two ranked bar charts (Orders, Profit) · Profit and Number of Orders by Time (dual-axis line) · Details text link |
| **Details (Supplier Analysis)** | Pop-up | In-context documentation, opened from a text hyperlink |
| **Details (Product Analysis)** | Pop-up | Same pattern |

**The composition pattern worth copying:** every analysis page carries a "View **details** about this page" text link that opens a pop-up page explaining what the page contains. The report documents itself from inside, and the overview page acts as a table of contents with page links. Neither requires any feature a rebuild wouldn't already have.

---

### 2. Object configurations read from the viewer's Data Settings pane

| Object | Type | Roles as configured |
|---|---|---|
| Supplier Locations | Geo coordinate ("Scatter - Supplier Country") | **Geography:** Supplier Country · **Color:** Average Products per Supplier (aggregated measure) · **Data tips:** Supplier Country, Average Products per Supplier, Number of Suppliers |
| Quantity and Profit by Product Category | Treemap | **Tile:** Product Category · **Size:** Quantity · **Color:** Profit · **Data tips:** Product Category, Quantity, Profit, Number of Orders |
| Profit by Year and Month | Waterfall | **Category:** Order Date **Hierarchy** · **Measure:** Profit (Difference from previous parallel period) · **Data tips:** both |
| Supplier Details | List table | Supplier Name, Number of Products, Profit (+ gauge cell visualization) |
| Top 10 Cities (×2) | Bar charts in a Stacking Container | Each has its own rank: "Top 10 of City by Profit" / by Orders |

This is the first confirmation that the role catalogue holds up in production: a geography item works, a hierarchy sits in a category role, and an aggregated period calculation sits in a measure role.

---

### 3. Findings that correct or extend the specification

#### 3.1 Correction — the viewer *does* disclose cross-filters
Session 5 found that filters arriving from controls and links are invisible in the **editor's** Filters pane, and the spec lists that as defect #11. In the **viewer's** side pane it is different: selecting a filtered object shows

> Permanent Filters: None · Interactive Filters: **Product Category = 'Clothes'**

So disclosure exists for readers but not for authors. The defect is narrower than written, and stranger: the person configuring the report is the one kept in the dark.

#### 3.2 Correction — a measure toggle that isn't a parameter
The "Orders | Profit" toggle under *Top 10 Cities* looks like a parameter swapping a measure. The object list shows it is a **Stacking Container** holding two complete bar charts, with the button bar navigating between them. The pop-up documentation confirms it in the author's own words. Consequence for a rebuild: containers with a navigation control are the sanctioned way to offer "same chart, different measure", and it costs one object per variant.

#### 3.3 Extension — undo works in View mode
The viewer toolbar's Undo is live and descriptive: **"Undo: Change Continent Selector from North America to Europe"**. Readers can step back through their own exploration. The spec described undo as an authoring feature only; it is actually the same mechanism extended to consumption, and it is a strong pattern — most BI viewers make you rebuild a filter state by hand.

#### 3.4 Extension — drill-down mechanics
A date hierarchy in a category role makes the axis labels into links. Observed behaviour:
- A **single click** on an underlined axis label drills down. (Chart *marks* still need a double-click for page links — the two gestures do not collide.)
- The object grows its **own breadcrumb**: `All Order Date Hierarchy › 2014 ˅`, with a chevron for the level menu.
- The breadcrumb **truncates to just the current level** when the object is narrow, which is how it appeared before I widened the canvas.
- Drill is **per object**. Nothing else on the page followed it.

#### 3.5 Extension — display rules can be banded ranges rendered as a gauge
The Profit column's rule set, read from the viewer's Display Rules pane, which doubles as the legend:

| Band | Colour |
|---|---|
| −600,000 ≤ x < 0 | red |
| 0 ≤ x < 400,000 | yellow |
| 400,000 ≤ x ≤ 900,000 | green |

Placement: "Right of text, with Profit as x". This is a **three-band range rule** rendered as a miniature gauge inside the cell — richer than the single-operator rules seen in the sandbox, and the clearest example of the product's conditional-formatting model. A negative value renders red inside the same left-anchored track rather than extending left of a zero baseline.

#### 3.6 Correction — save is not the only gate
The sandbox showed Export, Share, Copy link and Copy embeddable markup greyed, and the spec attributes that to the report being unsaved. On this **saved** report the menu splits:

| Enabled | Disabled |
|---|---|
| Export, View source table, Edit report, Play report, Edit playback, About this report, Reopen, Close | **Save a copy, Share report, Copy link…, Copy embeddable markup…** |

So sharing and copying are **permission-gated as well as save-gated**. A rebuild needs two distinct reasons-why in its disabled states: "not saved yet" and "you don't have rights", and should say which applies.

#### 3.7 Extension — Comments in practice
Comments are per-object (the pane carries its own object selector), have a **1,000-character limit** with a live remaining count, a search affordance, and an empty state ("No comments are available."). I did not post one.

#### 3.8 Extension — geo map controls
The map exposes its own control cluster on hover: search, expand, layer selector, locate, and zoom in/out. These are map-specific and have no equivalent on other chart types — the only object observed with built-in zoom and pan.

---

### 4. Defects confirmed in production

These were found in a sandbox and dismissed as artefacts of an empty report. They are all present in a polished, published report.

1. **Ranked bars render alphabetically, not in rank order.** "Top 10 Cities by Profit" lists Barcelona, Berlin, Frankfurt, Hamburg, London, Madrid, Milano, München, Paris, Roma. To find the top city you compare bar heights. A "Top 10" chart that cannot be read top-to-bottom defeats its own purpose, and switching the toggle changes the membership silently (Amsterdam out, Hamburg in).
2. **Text objects clip without any indication.** The overview page renders "…can be used by executives, marketing managers, and sales representatives to" and stops mid-sentence. The full sentence is in the DOM; there is no scrollbar, no ellipsis, no overflow affordance. A reader cannot tell text is missing.
3. **Cross-filtering has no page-level disclosure.** Clicking a treemap tile re-filtered three objects and rescaled their axes. The only on-canvas evidence is a thin border on the clicked tile; this page has no filter breadcrumb enabled. A reader arriving mid-session cannot tell the page is filtered.
4. **Axis label thinning hides most categories.** "Profit by Product Group" draws roughly 40 bars and labels four of them. The rest are unidentifiable without hovering.

---

### 5. What this resolves in the specification

| Previously | Now |
|---|---|
| "Geo map rendering with real geography — not observed" | **Observed**: geography item + aggregated colour measure, working |
| "Hierarchy drill — not explored" | **Observed**: single-click label drill, per-object breadcrumb, truncation behaviour |
| "Comments — refused until saved" | **Observed**: per-object scope, 1,000-char limit, search, empty state |
| "Export / Share / Copy link — greyed on unsaved report" | **Corrected**: split between save-gating and permission-gating |
| "Filters from controls and links are not listed" | **Corrected**: true in the editor, false in the viewer |
| "Display rules — single operator conditions" | **Extended**: banded range rules rendered as in-cell gauges |
| "Undo is an authoring feature" | **Extended**: undo also covers viewer interactions, with the same descriptive labels |
| "Parameters — not exercised" | **Still unknown.** The apparent parameter toggle turned out to be a stacking container |

### 6. Still not observed
Alert subscriptions (the link exists in the viewer's Display Rules header; clicking it could create a real subscription), Export output, Play report / slideshow, View source table, PWA and mobile rendering — which is, with some irony, the subject this report was built to teach.


---

<!-- ===== Source: session7_exhaustive_pass.md ===== -->

## Session 7 — exhaustive pass over the remaining unexplored surfaces

**Subject:** SAS Visual Analytics, Explore and Visualize (`vfl-026.engage.sas.com`).
**Method:** live observation in a new, **never-saved** sandbox report on RETAILDEMO_2. No documentation used for the observations.
**Date:** 23 Sep 2026.
**Purpose:** close the "not explored" list carried by the specification, and re-test two claims that later evidence had cast doubt on.

#### Safety log
- All work in a fresh unsaved sandbox ("Report 1"). No existing report was opened or altered.
- Nothing saved, exported, shared, distributed or localized. Menus were enumerated programmatically without clicking the publishing items.
- One dialog completed deliberately (New Geography Item — creates a report-local data item in the sandbox only). All other dialogs cancelled or closed.
- No confirmation dialog appeared during the pass.

---

### 1. Lattice (small multiples) — previously unexplored

| Aspect | Observed |
|---|---|
| Role type | **Multi-item**: the picker uses checkboxes and an Apply button, unlike single-item roles |
| Result | The chart becomes a panel grid — one column per category value (6 departments), sharing the category axis on the left, with a labelled lattice header row at the bottom |
| Axes | Each panel repeats the measure axis starting at 0; only the outermost panel shows the upper tick label |
| Labels | Panel headers truncate without a tooltip ("electro…") |
| Side effect | Department was **auto-added to Data tip values** |
| **Defect** | **Applying a lattice silently re-sorted the chart from value order to alphabetical order.** Before: ASIA, EU, US_AT, US_MW, LATA… (descending frequency). After: ASIA, EU, LATA, US_AT, US_CS… (alphabetical). Nothing announced the change |

This is the third instance of the same class of bug already in the spec: sort state is fragile and changes silently when the object is reconfigured.

### 2. Reference lines — previously unexplored

| Aspect | Observed |
|---|---|
| Creation | Options → Reference Lines → + New reference line. Created **instantly**, no dialog, with a pre-filled computed default (131,145 on a 0–200,000 axis) |
| Settings | Label (free text, empty), Value, Axis (greyed — fixed to the measure axis), Line style (pattern, width 1–6, colour) |
| **Value options** | A typed constant, or **+ New parameter**. That is all |
| Rendering | Drawn in **every lattice panel**, above the bars |
| **Capability boundary** | There is **no aggregate reference line** — no "average", "median" or "percentile of the measure". A moving target must be maintained by hand or driven by a parameter |

For a rebuild: offer statistical reference lines (mean, median, percentile, target vs actual). Their absence here is a real gap, not a stylistic choice.

### 3. Parameters — previously unexplored, now exercised end to end

The full loop works, and it is the mechanism behind most "interactive" reports:

```
Slider control ──(Parameter Link: range start)──► Parameter "Cutoff" ──(Value)──► Reference line
      user drags                                    numeric, default 100000            line moves live
```

| Aspect | Observed |
|---|---|
| Creation paths | Data pane → + New data item → Parameter, **or** inline from any control that accepts one ("+ New parameter" inside the reference-line Value dropdown) |
| **Context sensitivity** | Created from a reference line, the dialog **locks Type to Numeric** and disables "Multiple values". Created from the Data pane, Type offers Character / Numeric / Date / Datetime |
| Fields | Name, Type, Multiple values, Format (COMMA12.2 default for numeric), Default value, "Edit as expression" |
| Consumption | A parameter appears wherever a parameter is accepted — reference-line values, control parameter links, calculated items, filters |
| Writing to it | A control writes via **Actions → Parameter Links** (a slider exposes *range start* and *range end* separately) |
| Result | Dragging the slider moved the reference lines in all six lattice panels immediately |

### 4. Containers — previously unexplored

| Aspect | Observed |
|---|---|
| Types | Precision, Prompt, Scrolling, Stacking, Standard |
| Stacking container appearance | An empty frame with **‹ › navigation arrows** and a ⋮ menu |
| **Populating** | **Double-clicking an object in the library never nests it** — the object is appended to the page instead. Objects must be **dragged** into the container |
| After populating | The container renders a **tab strip**: `‹ Key value 1 ›`. This is exactly the "Orders / Profit" switcher seen in the production report |
| Actions | With a container selected the Actions pane states **"Actions cannot be created from the selected object."** Containers cannot be interaction sources |
| Roles | "Roles are not supported for the selected object" (already known) |

Consequence for the spec: the stacking container is the sanctioned way to offer "same chart, different measure", and it costs one full object per variant.

### 5. Geography items — previously unexplored, and it unlocks the geo maps

The Geography role that reported "No data items available for role." in session 3 was **a missing prerequisite, not a bug**.

**Creation dialog (New Geography Item)** — the best-designed validation surface seen anywhere in this product:

| Field | Values |
|---|---|
| Name | required |
| Based on | any item (the new item is a duplicate of it) |
| Geography data source | **Geographic name or code lookup** (default) / Geographic data provider / Latitude and longitude in data |
| Name or code context | Country or Region Names, ISO 2-letter, ISO 3-letter, ISO numeric, SAS Map ID, Subdivision names, US state names/abbreviations, US ZIP… |
| **Live preview** | A map plus a **match-rate readout: "86% mapped"** and a named list of failures: **"1 of 1 unmapped values: England"** |

**After creation:** the geography item carries a globe icon, and the Geo region map's Geography picker offers it. The map rendered immediately ("Frequency of Geographic Item 1") with shaded regions and a gradient legend.

**Render-time disclosure:** the object shows an ⓘ reading **"No matches were found for supplied geography data items: England."** — the unmatched value is named again at render time.

**Pattern to copy:** state the match rate *and name the failures* before committing, then repeat the warning on the object. Contrast this with row caps elsewhere in the product, which say only "Only 3,000 rows of the data appear" and never say which rows.

### 6. Correction — menu gating has three different causes, not one

The specification says Export, Share, Copy link and similar are "greyed on an unsaved report". That conflated three distinct gates. Measured directly:

| Report state | Export | Copy link / embeddable markup | Distribute / Localize | Share report | About this report |
|---|---|---|---|---|---|
| Unsaved, **no data** (session 1) | greyed | greyed | greyed | greyed | greyed |
| **Unsaved, with data and objects** (this session) | **enabled** | **enabled** | **enabled** | greyed | greyed |
| **Saved**, opened in view mode (session 6) | enabled | greyed | n/a in view mode | greyed | **enabled** |

So the three gates are:
1. **Content** — an empty report disables almost everything; adding data and one object enables Export, Copy link, embeddable markup, Distribute and Localize even while unsaved.
2. **Save** — "About this report" needs a saved report (it shows stored metadata).
3. **Permission** — "Share report" was disabled in every state, and on the saved report Copy link and Save a copy were disabled too. These follow the user's rights, not the document's state.

A rebuild must distinguish them in the UI, because "why is this greyed out?" has three different answers and the product never says which applies.

### 7. Accessibility — refinement of an earlier claim

Earlier sessions established that charts and grids render to `<canvas>` with no cell text in the DOM, and the spec concluded there is "no accessible equivalent". More precisely:

| Layer | State |
|---|---|
| `<canvas>` element | No `aria-label`, no `role`, no `tabindex` |
| Object wrapper | **`role="application"`** with a descriptive **`aria-label`**: "Frequency of Region, Bar chart"; "Frequency of Geographic Item 1, Geo region"; "Key value 1" |
| Data values | **Not present in the DOM or the accessibility tree** |

So an assistive-technology user is told an object exists, what it is called and what type it is — but not a single value it contains. `role="application"` also instructs screen readers to hand keystrokes to the app, which obliges the app to implement complete keyboard interaction; no keyboard-shortcut documentation exists anywhere in the product (Help offers only Learning Center, Help Center and an FAQ).

**Requirement for the rebuild:** keep the canvas for performance, but pair every object with a real accessible representation (a visually-hidden table or an ARIA summary of the plotted series), and publish a keyboard map.

### 8. Interface options (per-user editor toggles)
`More → Interface options` contains exactly three: **Disable auto-refresh**, **Disable object overlays**, **Disable layout guides**. All are per-user editor preferences rather than report properties.

---

### Status of the specification's "not explored" list

| Item | Status after this session |
|---|---|
| Parameters | **Resolved** — created, bound to a control, consumed by a reference line |
| Containers (all five) | **Resolved** for Stacking; the other four were enumerated but only Stacking was populated |
| Lattice rows / columns | **Resolved** |
| Reference lines | **Resolved**, including the aggregate-line boundary |
| Geography item creation | **Resolved**, including validation and render-time disclosure |
| Geo map with real geography | **Resolved** (Geo region) |
| Hierarchy drill | Resolved in session 6 (date hierarchy, viewer) |
| Interface options | **Resolved** |
| Accessibility of canvas objects | **Resolved** — role and name exposed, values not |
| Custom sort applied to an object | Still not exercised |
| Overview axis, data skins, measure layout | Still not exercised |
| Insights / outlier analysis on a populated report | Not available in this session's toolbar state |
| Import data, join editor, alerts, Export output, source table | Deliberately not exercised (they write, publish, or previously hung) |

### New defects to add to the rebuild list

| # | Observed | Requirement |
|---|---|---|
| 26 | Applying a lattice silently re-sorts the chart from value order to alphabetical | Preserve sort across reconfiguration, or announce the change |
| 27 | Containers cannot be populated by double-click, only by drag, with no affordance saying so | Support both, and show a drop target |
| 28 | Reference lines support only constants and parameters | Offer mean, median and percentile lines |
| 29 | Disabled menu items never say why, and there are three different reasons | Give each disabled control a reason: needs content, needs saving, needs permission |
| 30 | Objects expose an accessible name and role but no data | Provide a real accessible representation of the plotted values |


---

<!-- ===== Source: session8_exhaustive_pass.md ===== -->

## Session 8 — closing the remaining exploration list

**Subject:** SAS Visual Analytics, Explore and Visualize. **Method:** live observation, new never-saved sandbox on RETAILDEMO_2. **Date:** 23 Sep 2026.
**Scope:** the items session 7 left open — custom sort, measure layout / axis ranges, insights, the source-table viewer — plus two re-tests.

#### Safety log
Fresh unsaved sandbox only. Nothing saved, exported, shared or published. The source-table viewer was opened read-only and closed; its ⋮ menu was enumerated without clicking. No confirmation dialog appeared.

---

### 1. Multiple measures and axis ranges

**Default layout.** Adding a second measure to a bar chart produces **two side-by-side panels**, each with its own axis (Frequency 0–400,000; Sales 0–25 millions), and the title becomes "Frequency, Sales by Region". Measures are not overlaid.

**X Axis Range** (Options → Layout) has three values:

| Value | Behaviour |
|---|---|
| **Different per cell** (default) | Each measure panel scales independently |
| Same within each column | Shared scale per lattice column |
| Same for all cells | One scale across every panel |

**Defect observed.** Choosing "Same for all cells" put Frequency (max ≈500,000) on Sales's 0–25 million scale, rendering **the entire Frequency panel as invisible slivers**, and relabelling its axis "Frequency (millions)". No warning was given that a series had become unreadable. A rebuild should detect incompatible magnitudes and either refuse the shared scale or offer a log scale.

**Anomaly (observed once, cause not established).** Applying "Same for all cells" also **inverted the category order** (ASIA moved from top to bottom), and reverting the setting to "Different per cell" did **not** restore it. Both X- and Y-axis "Reverse order" checkboxes were unchecked throughout, so that setting was not the cause. Recorded as a single observation, not a reproducible rule.

### 2. Custom sort — how it actually applies

Creating a custom sort (Data pane → category right-click → Custom sort) opens a dual-list dialog: Category Data (10) → Sorted Items, with filter, move arrows and reorder buttons. I moved two of ten values across (US_NE, then LATA) and clicked OK.

| Question | Answer |
|---|---|
| Does the chart change when the custom sort is created? | **No.** The chart kept its existing sort (Frequency: Descending) |
| How is it applied? | Only by setting the object to sort **by that category** — right-click → Sort → "Region: Ascending" |
| What happens to values left out? | **Sorted values come first in the defined order; the remaining eight fall back to alphabetical.** Final order: US_NE, LATA, then ASIA, EU, US_AT, US_CS, US_MW, US_SE, US_SW, US_WC |
| Is the custom sort discoverable from the object? | **No.** The sort submenu still reads only "Region: Ascending / Descending" — nothing indicates a custom order is in force |

**Requirement for a rebuild:** name the custom order in the sort menu ("Region: Custom order") and say what happens to unlisted members.

### 3. Insights — an outlier advisor, not a general insight engine

The toolbar button, whose label is literally **"Insights were found"**, opens a popover titled **Outliers**: "The following data items are used by objects in the report and might be influenced by outliers:", a button **Analyze Objects for Impact**, and the suspect measure listed (Sales) with its own ⓘ. It is a narrow, specific feature — worth copying as a data-quality advisor, but it is not automated narrative insight.

### 4. View source table — the raw-data viewer

| Aspect | Observed |
|---|---|
| Entry | Data source menu → "View <table> source table" |
| Header | Table name, **Columns: 57 · Rows: 2,339,245**, grid/list view toggle |
| Grid | Row numbers, column headers with **per-type icons** (category, numeric, currency), raw row-level values |
| Toolbar | Grid options, Save (greyed), Undo/Redo (greyed), ⋮ → Discard view changes, Refresh data, Column header |
| **Size gate** | A banner: **"Some features are not available due to the large size of the table."** with a help link and a dismiss × |

This is the live confirmation of the documented threshold (roughly 150K rows / 10K columns / 5M cells): past it, editing and some functions are withdrawn and the product says so up front. Good pattern — it degrades explicitly rather than silently.

### 5. Re-tests of two earlier findings

| Earlier finding | Re-test result |
|---|---|
| Typing drops the letters "e" and "g" in the Data pane filter (session 2: "Region" → "Rion") | **Did not reproduce.** "Region" typed cleanly and the field value read exactly `"Region"`. The defect is **intermittent**, not deterministic — downgrade it in the spec accordingly |
| Lattice silently re-sorts a chart (session 7) | Consistent with this session: sort state changes as a side effect of unrelated settings, and is not restored by undoing the cause |

---

### Exploration list — final status

| Item | Status |
|---|---|
| Custom sort | **Resolved**, including partial-order semantics |
| Measure layout / X Axis Range | **Resolved**, including the invisible-series defect |
| Insights / outlier advisor | **Resolved** |
| View source table | **Resolved**, including the size gate |
| Data skins, overview axis, grouping style | Options enumerated in session 2; still not individually exercised |
| Import data, join editor, alerts, Export output, Play report | **Deliberately not exercised** — they upload, publish, subscribe, or previously hung the application |

### Defects added to the rebuild list

| # | Observed | Requirement |
|---|---|---|
| 31 | A shared axis across measures of different magnitudes renders one series invisible, with no warning | Detect incompatible magnitudes; refuse, warn, or offer a log scale |
| 32 | A custom sort is invisible from the object and applies only when sorting by that category; unlisted members silently fall back to alphabetical | Name the custom order in the sort menu and state the fallback |
| 33 | Changing an axis-range setting inverted the category order, and reverting did not restore it (observed once) | Treat ordering as explicit state that survives unrelated setting changes |


---

<!-- ===== Source: session9_automatic_charts.md ===== -->

## Session 9 — the automatic chart resolver, derived empirically

**Subject:** SAS Visual Analytics, Explore and Visualize. **Data:** PRODUCTS (the same source the vendor's "Working with Automatic Charts" lesson uses). **Date:** 23 Sep 2026.
**Why:** the automatic-chart rule was the one substantive claim in the specification carried as **DOCUMENTED** rather than observed — the training guide states the type is chosen from the number and type of dropped items, giving "four measures → correlation matrix" as its example. This session derives the rule by experiment.

#### Safety log
A saved training report (`101_112_Working with Automatic Charts`) was open when this session began. It was a **blank exercise template** — data loaded, two items pre-selected, empty canvas — so adding anything would have modified someone's saved report. I closed it untouched (no save prompt appeared, confirming nothing had changed) and reproduced the exercise in my own never-saved sandbox on the same data. Nothing saved, exported or published. Every object was removed with Undo after its type was recorded.

#### Method
For each combination: select the data item(s) in the Data pane → right-click → **Add to current page** → read the resulting object type from the undo label (which names it precisely, e.g. *"Undo: Add Scatter - Cost 1 with data items Cost, Retail Price"*) → Undo.

---

### The decision table (OBSERVED)

| Items dropped | Automatic chart chosen | Object named |
|---|---|---|
| 1 category | **Bar chart** | Bar - Continent Name 1 |
| 1 category, very high cardinality (748K distinct) | **Bar chart** (unchanged) | Bar - Order ID 1 |
| 1 measure | **Histogram** | Histogram - Cost 1 |
| 1 date | **Time series plot** | Time - Date Order was Delivered 1 |
| 1 category + 1 measure | **Bar chart** | Bar - Continent Name 1 (with both items) |
| 2 measures | **Scatter plot** | Scatter - Cost 1 |
| 3 measures | **Scatter plot** | Scatter - Frequency 1 (3 items) |
| 4 measures | **Scatter plot** | Scatter - Cost 1 (4 items) |

**Implied rule (INFERRED — confidence: High).** The resolver keys on the *classification* of the items, not their content:
- any measure alone → distribution view (histogram);
- any date → time view;
- a category, with or without a measure → categorical comparison (bar);
- two or more measures with no category → relationship view (scatter).

### Two findings that matter more than the table

#### 1. The documented "four measures → correlation matrix" did not reproduce
The training guide's worked example states that four measures can yield a correlation matrix. In this build, **two, three and four measures all produced a scatter plot.** Either the rule is release-specific, or it depends on something the guide does not state (correlation strength between the chosen columns, for instance). Recorded as a **DOCUMENTED-vs-OBSERVED divergence**; the observed behaviour governs, and a rebuild should not assume a correlation-matrix branch exists.

#### 2. The resolver ignores cardinality entirely
Dropping **Order ID — 748,000 distinct values** produced an ordinary bar chart. The result is unreadable: a solid block of bars with a frequency axis of 0–5, truncated at the row cap and disclosed only by the small ⓘ. The automatic chart made no attempt to rank, bucket, or refuse.

This is the sharper contrast with the **Suggest pane**, which the vendor documentation says *is* driven by cardinality and correlation. So the product contains two different automatic-chart engines with different intelligence, and the one reached by the most common gesture — dragging a column onto the canvas — is the naive one.

**Requirement for a rebuild.** An auto-chart resolver should consider three things, not one:
1. **Classification** (category / measure / date / geography) — as the subject does.
2. **Cardinality** — above a threshold, rank to Top N or bucket the remainder rather than drawing thousands of marks.
3. **Column semantics** — an identifier-like column (`*_ID`, near-unique, integer-keyed) should never become a bar chart's category; offer a count, a distinct-count tile, or refuse with an explanation.

And it should say what it decided and why, with a one-click way to change it — the subject silently picks and leaves the user to work out that the chart is meaningless.

---

### Defects added to the rebuild list

| # | Observed | Requirement |
|---|---|---|
| 34 | The automatic chart ignores cardinality: a 748K-distinct identifier column becomes a bar chart, rendering as an unreadable solid block capped at 3,000 rows | Consider cardinality and column semantics; rank, bucket or refuse, and explain the choice |
| 35 | Two automatic-chart engines coexist (canvas auto-chart and the Suggest pane) with different intelligence, and the naive one is on the primary gesture | One resolver, consistently applied and explained |

### Specification status

| Claim | Before | Now |
|---|---|---|
| Automatic chart selection rule | DOCUMENTED (vendor guide) | **OBSERVED** — decision table above |
| "Four measures → correlation matrix" | DOCUMENTED | **Did not reproduce**; scatter in all multi-measure cases |
| Auto-chart resolver recommendation (spec §O) | Generic | Sharpened into three inputs and an explain-the-choice requirement |


---

<!-- ===== Source: favorites_crawl.md ===== -->

## Favorites crawl — live observation session 10

**Subject:** SAS Visual Analytics, Explore and Visualize, `vfl-026.engage.sas.com`
**Scope agreed with the user:** the account's **favorite reports**, **full per-object pass**.
**Observed:** 23 Sep 2026. Everything read-only, in View mode.

#### Safety log
- Every report opened **directly in View mode** — the product's default for a report opened from the content list. No report was switched to Editing at any point.
- Nothing was saved, exported, shared, copied, deleted, renamed, favorited/unfavorited or commented on.
- **No confirmation dialog appeared** at any point. One error dialog appeared and was closed: *"You cannot select a folder for this operation."* (caused by a mis-aimed click in the Open dialog, not by a destructive action).
- Viewer-session state changed for testing and **restored**: one parameter selection in `230_132` (Benchmark Country Selector, Russian Federation → China → undone back to Russian Federation, verified). One outlier analysis was run (read-only computation). Browser zoom was changed and restored to 100%.
- All eight reports opened during the crawl were **closed at the end via “Close all reports”**. No confirmation dialog appeared — none had been modified. The session finished back on the landing page.

---

### 1. The favorites inventory

**Count: 96 items** (the grid reserves scroll height for 97 rows including the header). The list could never be read in full in one pass — see defect 39.

Captured names (two passes, partially disjoint — the union below is 89 of the 96):

<details><summary>Pass A — home page grid (70 names)</summary>

101_112, 101_113, 101_121, 101_122, 101_131, 101_132, 101_142, 120_071, 120_072, 120_102, 120_103, 120_104, 120_105, 120_222, 120_242, 120_251, 120_252, 120_311, 120_322, 120_331, 120_411, 120_421, 120_422, 120_423, 120_431, 120_442, 130_101, 130_102, 130_103, 130_105, 130_107, 130_201, 130_202, 130_203, 130_302, 130_303, 130_401, 130_402, 130_403, 130_404, 130_501, 130_502, 130_503, 140_101, 140_102, 140_201, 140_203, 140_302, 140_303, 140_403, 140_404, 140_501, 140_502, 140_602, 140_603, 140_702, 140_703, 140_801, 140_802, 140_803, 150_102, 150_202, 150_301, 150_302, 150_303, 160_111, 160_121, 170_201, 170_202, 170_303
</details>

<details><summary>Pass B — Open dialog (81 names, includes items pass A missed)</summary>

102_102, 102_111, 120_312, 120_426 (+ Solution), 120_441, 120_446 (+ Solution), 130_551 (+ Solution), 130_552 (+ Solution), 150_201, 150_203, 150_305, 160_131, 160_151 (+ Solution), 160_161 (+ Solution), 170_101, 170_202_Page to Import, 170_203, 170_302, 170_504, 170_505, 170_506, 180_204, 180_252 (+ Solution), 180_253 (+ Solution), 180_254 (+ Solution), 180_401, 180_403, 180_502, 210_111 (+ solution), 210_221 (+ solution), 210_311 (+ solution), 210_421 (+ solution), 220_232 (+ Solution), 220_233 (+ Solution), 220_234 (+ Solution), 220_521 (+ _Solution), 220_621 (+ _solution), 220_624 (+ solution), 220_625 (+ solution), 230_122 (+ solution), 230_132 (+ solution), 230_142 (+ solution), 310_131 (+ _solution)
</details>

Twenty-three of the favorites are paired **exercise / Solution** reports. Five are authored by the account itself (`student`): 120_426, 120_446, 130_551, 130_552, 160_151 — with 130_105 and 140_102 also last modified by `student`.

---

### 2. Reports crawled in this wave

| # | Report | Why chosen | Objects |
|---|---|---|---|
| 1 | **160_151_Applying a Color-Mapped Display Rule** | authored by the account | Treemap, Bubble plot, Bar chart, List table |
| 2 | **230_132_Creating a Character Parameter solution** | parameters were UNKNOWN | 2 drop-down controls, Bar, List table |
| 3 | **210_221_Creating a Network Analysis - solution** | network object never observed | Geo network, Network analysis, drop-down |
| 4 | **210_311_Creating a Path Analysis - solution** | path object never observed | Path analysis, Bar |
| 5 | **210_421_Creating a Decision Tree - solution** | ML object never observed | Decision tree, Scatter plot |
| 6 | **210_111_Analyzing a Forecast - solution** | forecasting never observed | Forecasting |
| 7 | **310_131_Creating_a_Custom_Graph_Template_solution** | custom templates were UNKNOWN | Custom graph, List table |
| 8 | **180_502_Testing a Report on a Mobile Device** | responsive behaviour was UNKNOWN | report prompts, image, text, 4 pages |

---

### 3. Object role schemas read from the viewer (all OBSERVED)

| Object | Roles as configured |
|---|---|
| Treemap | **Tile** Product Line · **Size** Number of Products · **Data tips** Product Line, Number of Products |
| Bubble plot | **X axis** Quantity · **Y axis** Profit · **Size** Number of Products · **Group** Product Line · **Data tips** ×4 |
| Bar chart | **Category** Product Category · **Measure** Number of Products · **Group** Product Line |
| List table | **Columns** (ordered list) |
| Drop-down control | **Category** (one data item) |
| **Geo network** | **Source** from_loc · **Target** to_loc · **Size** MaxWind · **Color** Category |
| **Network analysis** | **Levels** `Type - DriveTrain - Make` (a hierarchy) · **Color** Origin |
| **Path analysis** | **Event** Grouped Pages · **Sequence order** time · **Transaction identifier** id · **Weight** purchase |
| **Decision tree** | **Response** Iris Species · **Predictors** (4 measures) |
| **Forecasting** | **Time axis** Transaction Date · **Measure** Sales Rep Actual · **Underlying factors** Market Penetration, Order Marketing Cost |
| **Custom graph** (`Custom Bar Line Graph_solution`) | **Shared Category** Transaction Month · **Shared Measure** Profit · **Line Grouping** Product Brand |

#### 3.1 The role catalogue is not a closed set — custom templates declare their own roles
The custom-graph object's type name is the **template's own name**, and its roles are **author-named** ("Shared Category", "Shared Measure", "Line Grouping") — names that appear in no built-in object. **Consequence for the rebuild: role schemas must be data, loaded per object type, never hardcoded per chart class.** This is the single most structural finding of the wave.

---

### 4. The viewer side pane, corrected and extended

Session 6 described this pane from one report. Eight more reports sharpen it.

| Fact | Detail |
|---|---|
| Tabs | Rail labels **Roles · Rules · Filters · Ranks · Comments**; the pane header for the first says **"Data Settings"** — two names for one thing |
| Object selector | A combobox that is **hierarchical**: report → group → objects. The group is the **data source** in one report (`Products`) and the **page** in others (`Page 1`, `Ungrouped Network Analysis`) — grouping level is not consistent |
| Report-level selection | Roles shows *"Select an object to see its roles."*; Rules shows a `Report` scope row |
| Rules tab | Holds **two** sub-tabs: **Display Rules** and **Alert subscriptions**. Controls (drop-down lists) get **Display Rules only** — alert subscriptions is object-type-conditional |
| Comments | Per object; **1,000-character limit** with a live remaining count; empty state *"No comments are available."*; supports **replies** |

#### 4.1 The Filters pane has four kinds of section, not two
Session 6 recorded `Permanent Filters` / `Interactive Filters`. Across this wave a filtered object shows up to four:

| Section | Example observed |
|---|---|
| `Permanent Filters` | `None` in every object observed |
| `Interactive Filters` | `Continent Name = 'Asia'`, `Year = 2015` |
| One section **named after the data item**, holding the object's own filter | `Iris Species` → `In(Iris Species, 'Setosa', 'Virginica') OR Missing(Iris Species)` |
| An **object-type-specific** section | `Path Filter` → `PathContains(Grouped Pages, 'Buy')` |

The `… OR Missing(x)` disclosure documented from the editor is confirmed verbatim in the viewer.

#### 4.2 Controls cascade, and the cascade is disclosed
In `230_132` the **Benchmark Country Selector is itself filtered by the Continent Selector** — its Filters pane reads `Interactive Filters: Continent Name = 'Asia'`, and its value list held exactly the seven Asian countries. A control is an ordinary filter target like any chart.

---

### 5. Features observed for the first time

#### 5.1 "View insights" — automated outlier analysis in the viewer
A toolbar button beside fullscreen. It opens a popover:

> **Outliers** — "The following data items are used by objects in the report and might be influenced by outliers:" → **Analyze Objects for Impact** → `Profit ⓘ`, `Quantity ⓘ`

Pressing the button runs an analysis with a **determinate progress bar to 100%**, then reports *"One or more objects is impacted by outliers."* and lists, per measure, the affected objects with a **Details** link. Details opens a generated narrative report:

> **Outliers of Profit** — *"Are There Outliers Values of Profit?"* · "There are 103791 outlier values of Profit. When Profit is grouped by Product Line, these outliers change the sum of a group by more than 5%. It is also possible that a group consists entirely of outliers." · a distribution strip with the outlier band highlighted · *"What are the Details of these Outliers?"* · *"What Groups Are Affected by Profit Outliers?"*

| Product Line | Including Outliers | Excluding Outliers | Outlier Impact | Difference |
|---|---|---|---|---|
| Children | $429,751.38 | $392,846.91 | 8.59% | 36904.47 |
| Clothes & Shoes | $1,951,938.94 | $1,526,401.89 | 21.80% | 425537.045 |
| Outdoors | $1,687,084.95 | $738,539.67 | 56.22% | 948545.28 |
| Sports | $4,190,631.55 | $2,325,525.28 | 44.51% | 1865106.27 |

**A strong pattern worth copying** — the product proactively tells a *reader* that the numbers they are looking at are outlier-driven, and quantifies it per group.

#### 5.2 Objects can be re-typed from the viewer, and the product recommends one
The viewer object menu carries **"Change Treemap to ▸"**. For a (1 category, 1 measure) treemap the offered targets were:

**Bar chart (recommended)**, Butterfly chart, Crosstab, Dot plot, Dual axis bar chart, Dual axis bar-line chart, Dual axis line chart, Gauge, Key value, Line chart, List table, Needle plot, Numeric series plot, Pie chart, Scatter plot, Step plot, Targeted bar chart, Waterfall chart, Word cloud — 19 targets, the current type excluded.

The **"(recommended)"** marker is a second, previously unseen instance of the automatic-chart resolver: given a role signature it can rank alternative encodings. Session 9 found two chart-choosing engines; this is a third surface for the same decision, and it disagrees with neither so far.

#### 5.3 Forecasting is a full what-if environment, in the viewer
The forecasting object renders **actual points + model line + a confidence band** past a vertical forecast divider, with each **underlying factor in its own stacked panel**. Its top-right carries a **"What if ▾"** menu:

| Mode | Dialog contents |
|---|---|
| **Scenario analysis** | chart/table view toggle · **History cutoff** slider · **Adjust ▾** · **Reset ▾** · Undo/Redo · **Apply** (disabled until changed) · editable points on the **factor** series |
| **Goal seeking** | the same, plus **Bounds ▾**, and the editable points are on the **target** series instead |

- **Adjust** offers: *Set all to constant value · Add value to all · Add percentage to all · Progressively add value*, with a numeric Value field.
- **Reset** offers: *Factor: Order Marketing Cost* · *Reset all* — reset is per factor.
- **Bounds** is a table **Factor | Lower Bound | Upper Bound**, both defaulting to *Unbounded*.
- Two underlying factors were assigned in the roles, but **only one (Order Marketing Cost) appears as a panel, in Reset, and in Bounds** — the model selects which factors it actually uses and the UI silently shows only those. *(INFERRED — confidence Medium; the selection criterion is not disclosed.)*

#### 5.4 Analytic objects contain their own tab strip
The decision tree renders a header line —

> **Decision Tree of Iris Species** · Event: **Virginica** · Fit: **False Positive Rate 0.020 ▾** · Observations: **100 of 100**

— above an **in-object tab strip with ‹ › scroll arrows**: **Decision Tree · Icicle · Variable Importance · Assessment**. Each is a different rendering of one model. Nothing else in the product nests a tab strip inside an object frame, and the "Observations: 100 of 100" line is the clearest row-disclosure the product has shown anywhere.

#### 5.5 Network, path and geo objects have viewport controls
Session 6 recorded the geo map as the only object with zoom and pan. That is wrong: the **path analysis** object exposes the same on-hover cluster (fit, pan, zoom in, zoom out) beneath its ⋮ and maximize. Read as: objects that lay out in a **free 2-D space** (map, network, path) get viewport controls; objects on a **category/value grid** do not.

#### 5.6 Path analysis discloses fabricated ordering
A footer ⓘ on the path object reads:

> "An artificial sequence order was generated for 6 paths that contains simultaneous events."

The product tells the reader it invented ordering where the data had ties. That is exactly the disclosure discipline the rest of the product lacks (compare defects 2, 3, 7, 8) — and the sentence is ungrammatical.

#### 5.7 The first keyboard shortcuts the product actually discloses
The Comments pane ends with:

> "Press **Ctrl+Enter** to expand or collapse replies for a comment. Press **F2** to interact with the comment or reply."

A second one turned up in the **Opened reports** panel: each row carries the hint *"Press **Delete** to close the report"*, and the list ends with **Close all reports**.

The spec previously recorded "no documented keyboard-shortcut surface (Help has no shortcut reference)". That stands for Help, but **is now false as an absolute**: shortcuts exist and are disclosed *inline, in two panes, discoverable only by opening them*.

#### 5.8 Report-level prompt bars, and dependent controls
`180_502` carries a **report prompt bar above the page tabs** with three controls in a row — a **button bar** (Africa · Asia · Europe · North America · Oceania · South America, none selected), a **drop-down** showing the greyed placeholder `Facility Country`, and a **text input** with placeholder `Enter Facility City...`. A **▲ chevron** collapses the whole strip.

A drop-down control's value list carries **`Clear filter`** as its first entry — and a control marked **(required)** does **not** offer it. That is the cleanest expression of `required` seen anywhere in the product.

---

### 6. Responsive behaviour — the UNKNOWN, now partly resolved

`resize_window` reported success but `window.outerWidth` stayed at 1600, so the window never actually resized; nothing below comes from a real viewport change. Narrowing the **effective CSS viewport** with page zoom (≈607px and ≈405px) did exercise the app's own width handling:

| Effective width | Observed |
|---|---|
| ~1214px | Report title and toolbar icons share one row |
| **~607px** | Title moves to **its own row above the toolbar**; the **button-bar control overflows with ‹ › arrows**; prompt bar still one row; canvas unchanged |
| **~405px** | Banner title truncates to *"SAS® Visual Analytics - E…"*; the **prompt strip becomes horizontally scrollable**; canvas unchanged, vertical scrollbar only |

**Nothing ever stacks.** Controls overflow or scroll sideways; the report canvas keeps its absolute layout and is never reflowed. `window.matchMedia('(max-width:768px)')` remained `false` throughout while the chrome visibly re-laid-out — so **this responsiveness is driven by measured container width in JS, not by CSS media queries.** *(OBSERVED for the behaviour; INFERRED — confidence High — for the mechanism.)*

For the rebuild: do the opposite. Stack the prompt bar, wrap the button bar, and give the canvas a reflow mode.

---

### 7. New defects (continuing the master numbering at 36)

| # | Observed behaviour | Required behaviour in the rebuild |
|---|---|---|
| 39 | **A virtualised list silently drops most of its rows.** The home page favorites grid declares `aria-rowcount=97`, reserves the full scroll height, renders placeholder rows for all of them — and **never loads past 70**. Scrolling to the bottom, bouncing, and re-firing scroll events do not help. Two passes over the same list returned **partially disjoint sets** | Load what you claim; if a page is still loading, say so in the row instead of leaving a blank that looks like data |
| 40 | **The content search ignores the identifier people actually use.** `160_151` returns a relevance-ranked list of unrelated reports; `210_111` returns the entire library. `Color-Mapped` finds the report instantly. Digit/underscore tokens are dropped and the query silently degrades to "everything" | Match literal substrings of the name, and never return a full listing as if it were a result set |
| 41 | **Text inputs drop specific characters.** In the Open dialog's search box, `Analyzing a Forecast` became `aAnalyinaForcast`; `Forecast` became `Forcast` on three separate attempts, including when **e** was sent as its own discrete key press; a stray leading `a` was prepended every time; and a second entry appended instead of replacing (`Network AnalysisNtwork An`). Session 2 saw the same class of fault in the Data pane filter and it was logged as intermittent — it is **reproducible** here | Fix the input handler; never let a keyboard-shortcut layer swallow printable characters |
| 42 | **A generated insight ships an unfilled authoring placeholder to the reader.** The *Outliers of Profit* dialog renders the heading *"What are the Details of these Outliers?"* followed by the literal text **`<Double-click to enter text here>`** | Never render an unbound template slot; drop the section or fill it |
| 43 | **A generated table mixes formatted and raw numbers.** In the same dialog, *Including/Excluding Outliers* are currency-formatted (`$429,751.38`) while *Difference* is raw (`425537.045`, `36904.47`) | One format resolution for every numeric column in generated output |
| 44 | **Accessible names are inconsistent between object types.** The bar chart announces *"+/- vs Benchmark by Customer Country, Bar chart"*; the list table beside it announces *"List table - Customer Country 1"* — the internal object name, with no type suffix and no data description | One naming rule: description + type, for every object |
| 45 | **A color-mapped display rule is invisible in the Display Rules pane.** `160_151` exists to demonstrate one; its colours are visibly mapped and consistent across three objects; the viewer's Display Rules pane shows an empty `Report` scope and nothing else | List every rule that affects rendering, including value-to-colour mappings, in the pane named after them |
| 46 | **Narrow layouts scroll sideways instead of stacking** (section 6) | Stack, wrap, reflow |

#### Defects sharpened rather than added
- **Defect 29 (disabled items never say why)** gains a **fourth** cause. On the account's **own** report, `Save a copy`, `Copy link…` and `Copy embeddable markup…` are **enabled** while **`Share report` is still greyed** — as it was on a course report owned by someone else, and in an empty unsaved sandbox. Share is therefore disabled **deployment-wide**, not by content, save state or per-object permission. Four causes, one undifferentiated grey.
- **Defect 11 (invisible cross-filters)** is unchanged in the editor and confirmed disclosed in the viewer, now in four section kinds (§4.1).

---

### 8. Surfaces catalogued for the first time

**Content-list row context menu** (right-click a report in the library):
Open report · Show in folder · Remove from favorites · Add as shortcut · Copy · Export… · Export as PDF · ~~Share…~~ · Copy link… · Copy embeddable markup… · Authorization… · Manage this content

**Viewer ⋮ menu** (on the account's own saved report):
Home · New · Open · Save a copy · Reopen report · Close · Edit report · View source table ▸ · Export ▸ · ~~Share report~~ · Copy link… · Copy embeddable markup… · Play report · Edit playback · Interface options ▸ · Expand controls · About this report

New items here: **Play report**, **Edit playback**, **Expand controls**, and **Interface options ▸ → Disable object overlays** (the hover ⋮ / maximize affordances can be switched off report-wide).

**Viewer object ⋮ menu:** Export ▸ · Copy link… · Copy embeddable markup… · Change *\<type\>* to ▸ · View with SAS® Graphics Accelerator

**Open dialog:** left tree (Recent · My Favorites · My Folder · SAS Content · Shared with Me · Recycle Bin) · results grid · right details panel with **Details / Comments** tabs and collapsible **Thumbnails · Properties · More** · Name field · Type selector · Open/Cancel. Empty state: *"Select an item to see its information."* Refusal observed: *"You cannot select a folder for this operation."* The Properties section exposes a **folder URI** (`/folders/folders/<uuid>`) and a "modified by" line carrying the account's email address.

---

### 9. What this resolves in the specification

| Previously | Now |
|---|---|
| "Parameters — not exercised. **Still unknown**" | **OBSERVED** — a character parameter driving a benchmark comparison, a required control with no clear affordance, and a cascading control chain |
| Forecasting — never observed | **OBSERVED** — roles, confidence band, factor panels, scenario analysis, goal seeking, bounds |
| Network / path / decision tree — never observed | **OBSERVED** — full role schemas for all three, plus in-object tab strips |
| Custom graph templates — UNKNOWN | **OBSERVED** — and they prove role schemas must be data |
| "Geo map rendering with real geography" | **OBSERVED again**, now with a **geo network** variant (Source/Target geography roles) |
| Tablet and mobile layouts — UNKNOWN | **Partly resolved** (§6). Real device rendering and the PWA remain unobserved |
| "No documented keyboard-shortcut surface" | **Corrected** — Ctrl+Enter and F2 are disclosed inline in the Comments pane |
| "Alert subscriptions — a pane, not exercised" | **Corrected** — it is a sub-tab of the Rules pane, and absent for control objects |
| Comments "require a saved report" | Confirmed, and now seen on four more reports with identical limits |

### 10. Still not observed after this wave

- What the **Apply** button does in scenario analysis / goal seeking (never pressed — it changes the viewer's model state).
- **Fit ▾** on the decision tree (the criterion selector) and the *Variable Importance* / *Assessment* sub-views' contents.
- The **expression** behind any calculated item or parameter — visible only in the editor, which was deliberately not entered.
- **Play report / Edit playback** behaviour.
- **Export**, **Copy link**, **Copy embeddable markup**, **Authorization**, **Manage this content** output — all involve leaving the app or writing something.
- Real mobile/tablet rendering and the PWA.
- The 7 favorites in the union gap (96 counted, 89 named).

---

### 11. Next wave

All eight reports were closed cleanly with **Close all reports** — no prompt, nothing to save. The app is back on the landing page, My Favorites.

Remaining favorites of highest value, in order: `220_625_Adding Scopes to an Aggregation solution` (aggregation scopes — an open question from session 4), `120_312_Applying a Data View`, `150_305_Using a Custom Geo Map`, `140_101`/`140_102` (object templates), `180_252_Localizing a Report`, `170_101_Viewer Capabilities`, then the account's own exercises `120_426`, `120_446`, `130_551`, `130_552`, `160_161` against their Solution pairs.


---

<!-- ===== Source: suggestions_pane_deep_dive.md ===== -->

## The Suggestions pane — exhaustive pass (session 11)

**Subject:** SAS Visual Analytics, Explore and Visualize, `vfl-026.engage.sas.com`
**Method:** a **new blank sandbox report** (`Report 1`), data source `RETAILDEMO_2` (2,339,245 rows × 57 columns). No existing report was opened or touched.
**Observed:** 23 Sep 2026.

#### Safety log
- All work happened in a **new, never-saved report**, per the standing rule.
- One confirmation dialog appeared, on close: **"Do you want to save 'Report 1' before it is closed?" — Save / Don't save / Cancel.** I clicked **Don't save**, discarding the sandbox. Nothing was written.
- No existing report was opened, modified, saved, exported, shared or deleted.

---

### 1. Where it lives and what it contains

The **Suggestions** pane is the fourth tab of the left rail: `Data · Objects · Outline · Suggestions · Report Review`.

| Element | Detail |
|---|---|
| Header | `Suggestions` — **no ⋮ pane menu**, unlike every other pane in the product |
| Data source combobox | `Select to add data` when empty; the source name once loaded. Suggestions are **scoped to one data source at a time** |
| **Refresh** button | Regenerates the list from scratch, back to a single batch |
| **Add more suggestions** button | Appends another batch without discarding the current one |
| Card list | Vertically scrolling, one card per suggestion |

Both buttons are **disabled until a data source is loaded**, and — see defect 48 — the empty pane shows **no text at all**.

#### 1.1 Card anatomy
A card is: a `••••` drag handle, a **live-rendered `<canvas>` preview** (a real chart, not a static thumbnail), and a caption underneath. There is **no hover affordance** — no ⋮, no insert button, no tooltip. Long captions truncate with an ellipsis and no title attribute.

**Right-click** is the only menu: **Add to current page · Add to new page · Delete**.

---

### 2. The engine is a fixed slot rotation with randomised column picks

Ten batches were captured (initial load, seven Refreshes, three "Add more"). Every batch had the same shape. This is the core finding.

| Slot | Caption template | Chart type produced | Frequency |
|---|---|---|---|
| **1** | `<varying category>, Country_Lat by State_Lat` (or the `_Long` pair) | A **two-measure comparison** — Butterfly, Dual axis bar, or Dual axis bar-line | **10 of 10 batches** |
| **2** | `<category> by Frequency`, or `<category>, Frequency by Category` | **Treemap** | **10 of 10 batches** — with `Department` filling it in 9 of 10 |
| **3** (and 4 in five-card batches) | free-form, e.g. `ChannelType by Cost`, `Age Bucket by Storeage`, `<x> of Frequency Percent` | varies (Word cloud observed) | varies |
| **last** | `<date column> by <varying measure>` — `Transaction Date/Time by …` or `Date by …` | **Time series plot** | **10 of 10 batches** |

Batch size is **4 or 5**, not fixed, and not disclosed.

**Slot 1 is effectively hardwired to the two latitude/longitude columns.** Across every batch the measure pair was `Country_Lat / State_Lat` or `Country_Long / State_Long`; only the category rotated (Location, Transaction Time of Day, Transaction Day of Week, ChannelType, Department, Country, MDY, Region_2, Region, Storechain). The resulting charts sum latitudes into "millions" and, for longitudes, into negative millions.

#### 2.1 The engine is non-deterministic
Seven Refreshes on an unchanged data source with an unchanged selection produced seven **different** column sets. Only the slot templates were stable. This is a different kind of engine from the canvas auto-chart resolver (session 9), which was deterministic for a given role signature — a fourth chart-choosing code path with its own behaviour.

#### 2.2 It ignores the Data pane selection entirely
With `Brand Name` selected in the Data pane and confirmed selected (`aria-selected="true"`), two Refreshes produced ten suggestions, **none of which used Brand Name**. The pane is scoped to the data source, never to what the user is looking at.

#### 2.3 It ignores what is already on the page
After inserting `Department by Frequency` as a treemap, three further Refreshes offered **`Department by Frequency` again in all three**. The engine has no view of the report's existing content.

#### 2.4 Slot 1's chart type varies, and the rule is not determined
Four slot-1 insertions gave three different types:

| Category | Classification | Type produced |
|---|---|---|
| `MDY` | date | **Dual axis bar chart** |
| `Location` | nominal | **Butterfly chart** |
| `Storechain` | nominal | **Dual axis bar-line chart** |

A date/nominal split would explain the first two but not the third. **UNKNOWN** — the selection rule needs more trials than this session ran.

---

### 3. Insertion

| Gesture | Result |
|---|---|
| **Double-click a card** | Inserts into the current page, splitting the canvas. Works — unlike the object library, where double-click appends and containers refuse it (defect 27) |
| **Right-click ▸ Add to current page** | Same result |
| **Right-click ▸ Add to new page** | Creates a page and puts the object on it |
| **Drag** | The card is `draggable="true"` |

Undo labels, all descriptive:

- `Undo: Add object Dual axis bar - MDY 1`
- `Undo: Add object Treemap - Department 1`
- `Undo: Add object Word cloud - ChannelType 1`
- `Undo: Add object Time - Date 1`
- `Undo: Add object Butterfly - Location 1`
- `Undo: New page Page 2 with object types: Dual axis bar-line chart` — note the plural "object types" for a single object

**An inserted card is consumed** — it disappears from the list, and a new card appeared in its place. **A deleted card is not replaced** (5 cards → 4, no backfill).

#### 3.1 Roles the suggestions fill

| Inserted object | Roles assigned | Roles left empty |
|---|---|---|
| Dual axis bar – MDY | Category `MDY`, Measure (bar) `Country_Lat`, Measure (bar 2) `State_Lat`, Data tips ×3 | Lattice rows/columns, Animation, Hidden |
| Butterfly – Location | Category `Location`, Measure (bar) `Country_Lat`, Measure (bar 2) `State_Lat`, Data tips ×3 | — |
| Treemap – Department | Tile `Department`, Size `Frequency`, Data tips ×2 | **Color** |
| Word cloud – ChannelType | Word `ChannelType`, Size `Year`, Data tips ×2 | **Color** |
| Time – Date | Time axis `Date`, Measure `StoreNum`, Data tips ×2 | **Group** |

Every suggestion fills the required roles and the data tips, and leaves the optional grouping/colour roles empty.

---

### 4. Caption grammar is inconsistent with itself and with the object

Three grammars are in play for the same chart:

| Surface | Example |
|---|---|
| Card caption, form A | `Department by Frequency` |
| Card caption, form B | `MDY, Country_Lat by State_Lat` |
| Card caption, form C | `Transaction Year of Frequency Percent` |
| Resulting **object title** | `Frequency of Department` · `Country_Lat, State_Lat by MDY` |

The card says *"Department by Frequency"*; the object it creates is titled *"Frequency of Department"* — **the operands swap and the preposition changes**. A user cannot match a suggestion to the object it produced by reading either label.

The trailing term is also ambiguous: sometimes a data item (`by Frequency`, `by State_Lat`), sometimes the literal word **`Category`** (`ChannelType, Year by Category`) — and `Category` is **not a column in this table**, it is the Data pane's group heading. The object produced from that card had its colour/grouping role empty.

---

### 5. Quality of the suggestions

Of 16 suggestions captured in one accumulated run, **6 were semantically meaningless** on their face:

| Suggestion | Why it is nonsense |
|---|---|
| `Location, Country_Lat by State_Lat` | Sums latitudes across 2.3M rows |
| `Transaction Time of Day, Country_Long by State_Long` | Sums longitudes; renders negative millions |
| `Promotion ID, Region_2_Lat by Region_Lat` | Sums latitudes, grouped by an identifier |
| `Country, Region_2_Long by Region_Long` | Sums longitudes |
| `Storechain by TransID` | Sums transaction IDs |
| `Promotion ID by Loyalty Card` | Two identifiers |

Two further faults were observed in rendered cards:

- **`Transaction Date/Time by 12 week RFM Bucket` rendered an empty plot area** — both axis titles drawn, no marks. A suggestion that produces nothing was still offered.
- **`MDY, Country_Lat by State_Lat` rendered its date axis as clock times** — `12:09:00, 9:09:00, 10:09:00, 11:09:00, 8:09:00, 1:10:00` — unordered, from a column the Data pane classifies as a date.

An inserted word cloud read `Year (billions)` in its legend, with "Internet" rendered enormous — the sum of a **year** column used as a size measure.

---

### 6. New defects (continuing the master numbering at 48)

| # | Observed behaviour | Required behaviour in the rebuild |
|---|---|---|
| 48 | **The empty Suggestions pane says nothing.** With no data loaded it renders a disabled combobox, two disabled icons and blank space — while the Data pane next to it says *"To begin, add or import data."* and the property panes say *"Select an object to see its …"* | Every pane states what it needs and what it will do |
| 49 | **Suggestion cards are invisible to assistive technology.** Each card is a `<canvas>` inside `role="application"` with an **empty `aria-label`**, so a screen-reader user gets a nameless application region and no chart, no caption and no type. Report objects at least carry a descriptive name (defect 30) | Give every card an accessible name that states the chart type and the data items, and offer a text list view |
| 50 | **Dismissing a suggestion is irreversible and silent.** Right-click ▸ Delete removes the card with **no toast, no undo entry** — the undo label still reads the previous action. Everything else in the product is undoable with a descriptive label (Strength 3) | Make dismissal undoable, and remember it so the same suggestion is not re-offered |
| 51 | **The engine re-suggests what is already on the page.** Three consecutive Refreshes offered `Department by Frequency` after it had been inserted as a treemap | Exclude, or at least demote, charts already present |
| 52 | **Suggestions ignore the user's selection.** With `Brand Name` selected in the Data pane, ten generated suggestions used it zero times | Bias suggestions toward what the user has selected; that is the moment they are asking a question |
| 53 | **The engine is non-deterministic with no way to get a result back.** Seven Refreshes on unchanged inputs gave seven different sets; there is no pinning, no history, and Refresh discards the current list. A suggestion seen and not taken is gone | Make generation reproducible, or let the user pin and go back |
| 54 | **Card caption and resulting object title use opposite grammars.** `Department by Frequency` becomes `Frequency of Department`; `MDY, Country_Lat by State_Lat` becomes `Country_Lat, State_Lat by MDY` | One naming function, used by both surfaces |
| 55 | **A caption names a role the object does not use.** `ChannelType, Year by Category` produced a word cloud whose Color role is empty, and `Category` is not a column in the table | Captions describe only what the object will actually contain |
| 56 | **A suggestion that renders nothing is still offered.** `Transaction Date/Time by 12 week RFM Bucket` drew both axes and no marks | Drop empty results before showing them |
| 57 | **Batch size is undisclosed and variable** (4 or 5), and "Add more suggestions" gives no indication of how many exist or whether the well has run dry | State the count; disable the control when exhausted |

#### Defect sharpened rather than added
- **Defect 19** ("suggestions propose meaningless charts") is confirmed and given a mechanism: it is not occasional bad luck but **slot 1 of a fixed rotation, permanently bound to the latitude/longitude columns**. Fixing the ranking is not enough; the template itself is wrong.
- **Defect 41** (inputs dropping characters) is **narrowed**: the Data pane's Filter box accepted `Cat` intact in this session. The fault is specific to the Open dialog's search box, not to every text input.

---

### 7. What the rebuild should take from this

**Copy:** the shape. A live-rendered preview, one gesture to insert, an insertion that fills the required roles and the tooltips, and a descriptive undo entry — that is a good interaction, and it is faster than building the chart by hand.

**Do differently:**
1. **Rank on column semantics, not position.** Latitude, longitude, year, identifier and code columns must never be offered as summed measures. This one rule removes 6 of the 16 suggestions observed.
2. **Condition on the user.** Selection in the data pane, and what is already on the page, are the two cheapest signals available, and both are ignored.
3. **Make it reproducible and reversible.** Deterministic generation, pinning, undoable dismissal, remembered dismissals.
4. **One naming function** shared by the card, the object title and the accessible name.
5. **Validate before offering.** If the query returns nothing, do not show the card.


---

<!-- ===== Source: suggestions_conflicts_resolved.md ===== -->

## Resolving the two open Suggestions questions — session 12

**Method:** a second **new blank sandbox report**, `RETAILDEMO_2` (2.34M × 57) then `PRODUCTS` added alongside it. No existing report opened or touched.
**Observed:** 23 Sep 2026.

#### Safety log
One confirmation dialog on close — *"Do you want to save 'Report 1' before it is closed?"* — answered **Don't save**. Nothing written. Every insertion made during the probe was undone immediately.

---

### Q1. What picks slot 1's chart type? — **Nothing. It is random.**

Session 11 left this UNKNOWN on three observations. Thirteen now exist, and three categories each produced **two different chart types from identical inputs**:

| Category | Cardinality | Types produced |
|---|---|---|
| **Department** | 6 | **Butterfly** *and* **Dual axis bar** |
| **Location** | 6 | **Butterfly** (s11) *and* **Dual axis bar** (s12) |
| **Open** | 1 | **Dual axis bar-line** *and* **Dual axis bar** |
| ChannelType | 3 | Dual axis bar |
| Transaction Time of Day | 3 | Dual axis bar-line |
| Age Bucket | 7 | Butterfly |
| Country | 7 | Butterfly |
| Storechain | 3 | Dual axis bar-line (s11) |
| MDY | 6 | Dual axis bar (s11) |

Same category, same measure pair, same caption text, different object. Distribution across 13 samples: Butterfly 4, Dual axis bar 5, Dual axis bar-line 4 — consistent with a **uniform random draw from the three two-measure comparison types**.

The date/nominal hypothesis from session 11 is dead: `MDY` and `Location` and `Department` all have the same classification and all three types appear among them.

**Consequence:** the pane does not choose a chart. It picks a template slot, fills it with sampled columns, and then rolls a die for which of the three compatible types to render. There is no encoding decision to reverse-engineer, and none to copy.

---

### Q2. Two data sources — **strictly scoped, never mixed, and tied to the Data pane**

| Question | Answer (OBSERVED) |
|---|---|
| Does the combobox list both? | Yes — `RETAILDEMO_2`, `PRODUCTS` |
| Which is shown after adding a second source? | It **auto-switches to the newly added one** and regenerates |
| Are suggestions ever cross-source? | **No.** Every card in 6 batches used columns from one table only |
| Is the pane's source selector independent? | **No** — changing the source in the **Data** pane switched the Suggestions pane too. They are one selection, exposed twice |

---

### Q3. The vendor-documentation conflict — **I was wrong, and the correction matters**

Session 11 recorded that the guide's claim (suggestions driven by *cardinality and measure correlations*, and *items already used are not reused*) "failed to reproduce". Running the engine against a **second table** shows that verdict was too broad.

#### 3.1 The correlation claim is *supported*, and explains the nonsense
Slot 1's measure pair is fixed per data source:

| Data source | Slot-1 measure pair | Batches |
|---|---|---|
| RETAILDEMO_2 | `Country_Lat` by `State_Lat` (occasionally the `_Long` pair) | 15 of 15 |
| PRODUCTS | `Cost` by `Retail Price` | 5 of 5 |

Position is ruled out: in the Data pane's measure list, `Country_Lat` is 9th and `State_Lat` is 25th of 29; on PRODUCTS, `Cost` is 1st and `Retail Price` is 5th of 9. What both pairs share is that they are the table's **most strongly correlated measures** — a state's latitude tracks its country's; a product's cost tracks its retail price.

**So the documented mechanism is real. The defect is that correlation is computed with no regard to semantics.** Two latitude columns are near-perfectly correlated *and* meaningless to sum, so on any table carrying coordinates the coordinate pair wins slot 1 every time. On PRODUCTS, where the most-correlated pair happens to be two currency columns, **slot 1 produces a genuinely sensible chart**.

This reframes defect 19 a third time, and lands on the real fix: **correlation is a fine candidate generator, but it needs a semantic veto.** Latitude, longitude, year, identifier and code columns must be excluded from the measure pool before correlation is ever computed.

#### 3.2 The "already used are not reused" claim still fails
Unchanged from session 11: `Department by Frequency` was re-offered in three consecutive Refreshes after being inserted. Defect 51 stands.

#### 3.3 The cardinality claim is neither confirmed nor refuted
Slot 2 was filled by `Department` (cardinality 6 of ~20 categories) on RETAILDEMO_2 and `Product Category` (12) on PRODUCTS — in both cases repeatedly, in both cases neither the lowest nor the highest cardinality in the table. Something is picking a stable favourite per table; cardinality alone does not explain which. **UNKNOWN.**

---

### 4. The slot structure holds on a second, unrelated table

| Slot | RETAILDEMO_2 | PRODUCTS |
|---|---|---|
| 1 | `<cat>, Country_Lat by State_Lat` | `<cat>, Cost by Retail Price` |
| 2 | `<cat> by Frequency` — `Department` 9/10 | `<cat> by Frequency` — `Product Category` 5/5 |
| 3 | free-form | free-form |
| last | `Transaction Date/Time by <measure>` | `Date Order was Delivered by <measure>` |

Same four slots, same templates, different columns. The structure is the engine, not an artefact of one dataset.

---

### 5. Net effect on the specification

| Claim | Status |
|---|---|
| "Slot 1 is hardwired to the latitude/longitude columns" (session 11) | **Corrected** — slot 1 is bound to the table's most-correlated measure pair, which on a table with coordinates is the coordinate pair |
| "Slot-1 chart type rule — UNKNOWN" | **Resolved** — there is no rule; it is a random draw from three types |
| "Multi-source behaviour — UNKNOWN" | **Resolved** — per-source, never mixed, selector shared with the Data pane |
| "The vendor's cardinality/correlation claim failed to reproduce" | **Corrected** — the correlation half is supported; the reuse half still fails; the cardinality half is undetermined |
| Defect 19 | Re-scoped: the fix is a **semantic veto on the measure pool**, not better ranking |
| Defect 53 (non-determinism) | **Widened** — randomness covers the chart type too, not just the columns |


---

<!-- ===== Source: data_dragdrop_deep_dive.md ===== -->

## Data pane, multi-select and drag-and-drop — exhaustive pass (session 13)

**Method:** a **new blank sandbox report**, data source `PRODUCTS` (748K orders; 23 categories, 9 measures). No existing report opened or touched.
**Observed:** 23 Sep 2026.

#### Safety log
One confirmation dialog on close — *"Do you want to save 'Report 1' before it is closed?"* — answered **Don't save**. Nothing written. Every experimental object was undone between trials.

---

### 1. Selection mechanics — two earlier claims were wrong

| Gesture | Behaviour (OBSERVED) |
|---|---|
| Click | Selects one item, replacing the selection |
| **Ctrl+click** | **Toggles an item into or out of the selection.** Verified add *and* remove |
| **Cmd+click** | Same as Ctrl+click |
| **Shift+click** | Selects the range between the anchor and the target |
| Across the Category / Measure group boundary | **Allowed** — mixed selections hold for ctrl+click and for shift-ranges that span the boundary |
| Across a virtualised scroll | **The selection persists.** Selected rows scrolled out of view stay selected and are carried by a later drag |

**Correction 1.** An earlier session recorded that "ctrl-click didn't multi-select". It does. The original observation is explained by a dead click coordinate on the list's clipped last row — a plain click there did nothing either.

**Correction 2.** An earlier session recorded that the row "checkbox only renders on hover". In fact **checkboxes appear on every row as soon as anything is selected**, and the pane grows a **`Clear selection (n)` link that states the count**. With nothing selected there are no checkboxes and no link.

**The one real accessibility fault:** `aria-selected="true"` exists only on *rendered* rows. Scroll a selected item out of the virtualised list and it disappears from the accessibility tree entirely, while the logical selection is still live — the `Clear selection (3)` link is the only remaining evidence, and it is at the bottom of the pane.

---

### 2. The multi-item drop decision table

Every row below: select the listed items in the Data pane, drag onto **empty canvas**, read the object and its roles.

| Dropped set | Object created | Role assignment |
|---|---|---|
| 1 category | **Bar chart** | Category; **Measure auto-filled with `Frequency`** |
| 1 category + 1 measure | **Bar chart** | Category, Measure |
| 1 category + 2 measures | **Bar chart** | Category; **both measures in the Measure role** |
| 1 **date** + 1 measure | **Time series plot** | Time axis, Measure |
| 2 categories | **List table** | Columns ×2 |
| 2 categories + 1 measure | **List table** | Columns ×3 — the measure goes in as a column, not a measure role |
| 2 measures | **Heat map** | Axis items ×2; **Color auto-filled with `Frequency`** |
| 3 measures | **Heat map** | Axis items ×2; Color = the third measure |
| **4 measures** | **Correlation matrix** | `Show correlations: Within one set of measures`; Measures ×4 |
| 5 items incl. `Frequency` | **Correlation matrix** | **`Frequency` is silently dropped**; the 4 real measures are used |

#### 2.1 The rules behind it
1. **Two or more categories → List table**, and everything else in the set is folded into `Columns`. Measures lose their measure-ness.
2. **Exactly one category → Bar chart**, or **Time series plot** if that category is a date. Measures fill the `Measure` role, several at a time.
3. **No category:** 2–3 measures → **Heat map**; **4 or more → Correlation matrix**.
4. `Frequency` — the synthetic row-count measure — is dropped from a correlation set without comment.

#### 2.2 This settles an open conflict with the vendor documentation
Session 9 recorded that the guide's "**4 measures → correlation matrix**" rule "does not reproduce". It reproduces exactly — **on the drop path**. Session 9 tested the *single-item canvas auto-chart* path, which is a different resolver. Both observations were right about their own path; the spec's blanket non-reproduction note was too broad and is corrected.

#### 2.3 Scatter is silently substituted, and the undo entry leaks the original choice
Three drops whose object is **not** a scatter plot nonetheless produced an undo entry naming one:

| Dropped | Undo entry says | Object actually created |
|---|---|---|
| 2 measures | `Add Scatter - Cost 1 …` | **Heat 1** (heat map) |
| 3 measures | `Add Scatter - Cost 1 …` | **Heat 1** (heat map) |
| 4 measures | `Add Scatter - Cost 1 …` | **Correlation 1** (correlation matrix) |

A 5-measure drop, by contrast, was labelled `Add Correlation - Cost 1 …` correctly.

The reading: the resolver first chooses **Scatter**, then substitutes a binned heat map (748K points would not plot) or a correlation matrix, and **the undo entry is written from the pre-substitution decision**. The substitution itself is never disclosed — the user is given a heat map with no explanation, and the one place the original intent surfaces is a label that now names an object the report does not contain.

---

### 3. Drop targets — a three-zone model

| Target | Behaviour | Undo grammar |
|---|---|---|
| **Empty canvas** | Creates a new object per §2 | `Add <name> with data items <list>` |
| **The gutter around an existing object** (between the object and the canvas edge) | Creates a **new object, split in that direction** — verified on the right gutter and the left gutter | `Add <name> with data items <list>` |
| **An object's body** | Assigns to a compatible role: **replaces** a filled single-item role, **appends** to a multi-item role | `Replace <old> from <object> with <new>` |
| **A named role slot in the Data Roles pane** | Assigns directly to that role, and **also appends the item to `Data tip values`** | `Assign <item> to <object>` |
| **A chip inside a multi-item role** | Reorders within the role | `Reorder items of <object> in <role> role` |

**There is no in-object "edge zone".** Drops at 8px, 28px and 68px inside the object's right border all behaved as body drops; only a drop *past* the border, in the canvas gutter, created a split. An earlier guess to the contrary was tested and is wrong.

#### 3.1 The body-drop resolver ignores empty optional roles — silently
A bar chart with `Category` = Supplier Country (filled), `Group` = **empty**. Dragging a second category onto the **object body** did **nothing**: no object change, no undo entry, no message. Dragging **the same item onto the `Group` slot** worked immediately. So a compatible, empty, optional role was available and the body-drop resolver declined to use it — and said nothing.

#### 3.2 Type mismatches are refused silently
Dragging a measure onto the `Category` role slot produced no change and no message. The typed-role discipline is right; the silence is not.

---

### 4. Six undo grammars for one operation family

Collected across this session and the last two, all for "put a thing somewhere":

1. `Add Bar - Product Line 1 with data items Product Line` — canvas drop
2. `Add object Treemap - Department 1` — Suggestions pane insert
3. `Replace Frequency from Bar - Supplier Country 1 with Cost` — body drop over a filled role
4. `Assign Supplier Continent to Bar - Supplier Country 1` — role-slot drop
5. `Reorder items of Bar - Supplier Country 1 in Data tip values role` — chip reorder
6. `New page Page 2 with object types: Dual axis bar-line chart` — suggestion to a new page (plural "types" for one object)

Each is descriptive and readable on its own — the product's real strength — but they share no sentence pattern, no word order, and no convention for naming the object.

---

### 5. New defects (continuing at 58)

| # | Observed behaviour | Required behaviour in the rebuild |
|---|---|---|
| 58 | **A body drop is silently ignored when the resolver's preferred role is full, even though an empty compatible role exists.** The same item dropped on the role slot is accepted | Fall through to the next compatible empty role, or refuse with a reason and show the eligible targets |
| 59 | **Scatter is substituted for a heat map or a correlation matrix without disclosure, and the undo entry names the object that was *not* created** (three of four multi-measure drops) | Disclose the substitution in the object ("binned: 748K points"), and write the undo entry from the object that exists |
| 60 | **`Frequency` is silently dropped from a correlation set.** Five selected measures produced a four-measure matrix with no note | Say which items were excluded and why |
| 61 | **Two categories plus a measure produce a List table that demotes the measure to a plain column** — the measure-ness is discarded with no indication a chart was possible | Offer the crosstab/chart alternative, or state why a table was chosen |
| 62 | **Selection is invisible to assistive technology once scrolled.** `aria-selected` lives only on rendered rows in the virtualised list; a three-item selection can report as zero | Maintain an accessible selection summary independent of virtualisation |
| 63 | **Six different undo grammars for one operation family** (§4) | One sentence pattern: verb, item, role, object |

#### Corrections to earlier entries
- **"Ctrl-click doesn't multi-select"** — **wrong**, removed. Ctrl and Cmd both toggle; shift ranges; selections span groups and survive scrolling.
- **"The row checkbox only renders on hover"** — **wrong**. Checkboxes render on every row once a selection exists, and a `Clear selection (n)` link states the count.
- **"The vendor's 4-measures→correlation-matrix rule does not reproduce"** (session 9) — **narrowed**: it reproduces exactly on the **drop** path; session 9 tested the single-item auto-chart path.

---

### 6. Not observed

**Mid-drag visual feedback.** The pane's rows carry `draggable="true"`, so the app uses HTML5 drag-and-drop; synthesised pointer events did not start a drag and the tooling cannot pause a real one mid-flight. Drop-target highlighting, insertion indicators and cursor states are therefore **UNKNOWN** — the outcomes above were all read from the result and the undo entry, not from the drag itself.

Also untested: dropping onto a **container**, dropping between two existing objects, and drag-and-drop of an item already assigned to a role out of that role.


---

<!-- ===== Source: geography_deep_dive.md ===== -->

## Geography items and the geo-map family — exhaustive pass (session 14)

**Method:** a **new blank sandbox report** on `RETAILDEMO_2` (2.34M rows, 57 columns), plus one favorited sample report opened read-only.
**Observed:** 23 Sep 2026.

#### Safety log
- All construction happened in a **new, never-saved report**. Closed with **Don't save**; nothing written.
- **A third-party terms-and-conditions dialog appeared and I did not answer it.** Opening the map-service browser raised *"To access Esri ArcGIS Online Services for mapping data, you must acknowledge that you have read and accepted the additional terms and conditions… you can change your response via the Geographic Mapping section of the SAS Visual Analytics settings"* with **Accept / Decline**. Accepting terms is outside what I do without your say-so, and **Decline also records a stored response**, so I dismissed it with the **×** instead. No response was recorded either way. If you want the Esri basemap catalogue enumerated, that needs your explicit go-ahead.
- One sample report was opened read-only in View mode and closed. Nothing saved, exported or shared.

---

### 1. Data-item mapping — what the pane actually exposes

**The hover card is the mapping surface.** Hovering a data item shows:

| Field | Example |
|---|---|
| Name | `City` |
| Distinct values | `213` |
| **Name in data** | `City` — the **physical column name**, kept separate from the display name |
| Format | `$` |

So every data item is a **mapping** of a display name, classification and format onto a physical column, and the pane discloses both halves. A rebuild needs the same split (`label` vs `columnName`) as a first-class concept.

**Data items carry a PII classification.** Three columns showed a shield badge whose hover text reads:

> "City includes information that might identify an individual when combined with other information."

A **quasi-identifier warning**, attached to the data item and **inherited by anything derived from it** — the geography item built on `City` inherited the badge. Nothing in the spec covered this. It is a strong pattern: classify once at the column, propagate down the derivation chain.

---

### 2. The New Geography Item dialog — the standing UNKNOWN, resolved

| Field | Detail |
|---|---|
| **Name*** | prefilled `Geographic Item 1` |
| **Based on*** | a dropdown of **all 57 columns** — categories, measures and dates alike, **not type-filtered**. Note under it: *"The new geography item will be a duplicate of this item."* |
| **Geography data source*** | three radio options, below |
| Right panel | a **live validation panel**: `N% mapped`, a **Preview** selector, a rendered map, and a list of unmapped values |

#### 2.1 Source option A — Geographic name or code lookup
A **Name or code context** dropdown with exactly ten built-in geocoding vocabularies:

Country or Region Names · Country or Region ISO 2-Letter Codes · Country or Region ISO 3-Letter Codes · Country or Region ISO Numeric Codes · Country or Region SAS Map ID Values · Subdivision (State, Province) Names · Subdivision (State, Province) SAS Map ID Values · US State Names · US State Abbreviations · US ZIP Codes

**Capability boundary:** there is **no city-level lookup and no non-US postal lookup**. City-level geography must come from coordinates or a custom provider.

#### 2.2 Source option B — Geographic data provider
Reveals **Geographic data provider** (a dropdown plus a ⋮ menu), **ID column**, and a **Latitude/Longitude in data** checkbox. In this deployment:

- the provider catalogue holds exactly one entry, **US County Data**;
- the ⋮ menu offers **New provider · Edit provider · Delete provider**, **all three greyed**;
- the validation panel reads *"Mapping information not available."* and **OK is disabled**.

So custom providers are an admin-registered catalogue, and authoring them is permission-gated — a fifth flavour of undifferentiated greying (defect 29).

#### 2.3 Source option C — Latitude and longitude in data
Reveals **Latitude (y)**, **Longitude (x)** and **Coordinate space**.

- The lat/long pickers **are** type-filtered — 37 numeric columns of 57, categories and dates excluded. (The `Based on` picker above is not. Same dialog, two different disciplines.)
- **Coordinate space** offers: **Web Mercator · World Geodetic System (WGS84) · British National Grid (OSGB36) · Singapore Transverse Mercator · Custom**.
- **Custom** exposes a **PROJ string** field with an inline example: *"Invalid value for custom coordinate space. Syntax example for WGS84: `+proj=longlat +datum=WGS84 +no_defs`"* — shown **immediately on selecting Custom, before any input**, so an untouched required field is reported as invalid.

#### 2.4 The validation panel is the best thing in the dialog
It attempts the mapping live and reports:

| Configuration | Result |
|---|---|
| `Based on` = a measure (`12 week RFM`), lookup = Country Names | **0% mapped**, *"5 of 13 unmapped values: 10, 11, …"* |
| `Based on` = `Country`, lookup = Country Names | **86% mapped**, *"1 of 1 unmapped values: **England**"* |
| `Based on` = `City`, lat/long = `City_Lat`/`City_Long`, WGS84 | **100% mapped**, unmapped list disappears |

`England` failing against ISO country names is exactly the real-world trap this panel exists to catch. **Copy this pattern**: show the match rate and name the failures before the item is created.

**Preview** toggles between **Scatter** (centroids) and **Region** (filled polygons) — which is also how the author learns which map layers the item will support.

**Creation undo:** `Undo: New geography item Geographic Item 1 on data RETAILDEMO_2`.

**The Data pane grows a third group, `Geography`**, alongside Category and Measure, and the new item shows its distinct count (`Geographic Item 1 - 213`) and inherits the PII badge.

---

### 3. The geo-map family is one object with a swappable layer

Dropping a geography item alone on the canvas produces **`Geo coordinate - <item> 1`**. Its Options pane carries a **Graph Frame → Change type** control, and that dialog lists **seven layer types**:

**Bubble · Scatter · Cluster · Contour · Line · Pie · Region**

Switching the layer **renames the object** (`Geo cluster - …`, `Geo region 1`, `Geo pie - …`), so what the object library presents as separate geo objects is one object with a layer property. Undo: `Undo: Change type to Cluster for Geo coordinate - Geographic Item 1 1`.

#### 3.1 Complete role catalogue per layer (OBSERVED)

| Layer | Roles (`*` = required) |
|---|---|
| **Scatter** (Geo coordinate) | Geography\*, Size, Color, Data tip values, Data label, Hidden, Animation |
| **Cluster** (Geo cluster) | as Scatter |
| **Bubble** (Geo bubble) | Geography\*, **Size\***, Color, Data tip values, Data label, Hidden, Animation |
| **Region** (Geo region) | **Geography\***, **Color\***, Data tip values, Data label, **Data values**, Hidden, Animation |
| **Pie** (Geo pie) | Geography\*, Size, **Measure**, **Category\***, Data tip values, Data label, Hidden, Animation |
| **Contour** (Geo contour) | Geography\*, **Color** — only two roles |
| **Line** (Geo line) | Geography\*, **Width**, Color, **Pattern**, Data tip values, Data label, Hidden, Animation |

#### 3.2 A geography item's source type decides which layers it can serve
- A **lat/long** item drives point layers (Scatter, Cluster, Bubble, Pie, Contour).
- A **name/code lookup** item drives point **and** region layers — it carries both a centroid and a polygon.
- **Line** needs a path geography that neither produces.

**And the mismatch is handled by silent deletion.** Switching a lat/long-backed map to **Region** **cleared the Geography role entirely**, leaving a blank placeholder object ("Color by Geography" with an *Assign data* button) and no message. Switching a lookup-backed map to **Line** did the same. Compare defect 18 — that one *re-maps* roles silently; this one *discards* them.

#### 3.3 Rendering, confirmed end to end
- **Geo coordinate:** 213 city points on an OpenStreetMap basemap.
- **Geo cluster:** grey count bubbles (5, 61, 79, 33, 6, 2) that aggregate nearby points.
- **Geo region:** a working choropleth, *"Frequency of Geographic Item 2"*, countries shaded on a 15K–1.2M colour ramp, with the required Color role **auto-filled with `Frequency`**.
- An **ⓘ on the rendered object** reads *"No matches were found for supplied geography data items: England."* — the unmapped value is disclosed on the object, not only in the creation dialog. Another disclosure pattern worth copying.

---

### 4. Map background and basemap services

The Options pane has a **Geo Maps** section: a **Map background** checkbox, a **Map service** field with a browse button, and a **Transparency** slider (0%).

The Map Service browser is a filterable tree with a **thumbnail preview** and a description per entry:

| Entry | Notes |
|---|---|
| **Automatic** | *"selects a background map automatically based on the report theme that is currently displayed. For example, the High Contrast map is selected when the high contrast theme is displayed."* |
| **OpenStreetMap** | expands to **Standard · Light · Dark · High Contrast** |

**A theme-aware basemap that swaps to a high-contrast tileset under the high-contrast theme is a genuinely good accessibility pattern** and costs nothing to reproduce.

**Esri ArcGIS Online** services are available only after accepting third-party terms, stored per user under *Settings → Geographic Mapping*. That consent gate was not answered (see the safety log), so the Esri catalogue is **UNKNOWN**.

The object also gains an **Enable zoom and pan** option that non-map objects do not have — the setting behind the viewport control cluster recorded in session 10.

---

### 5. A custom-map report that renders nothing

`150_305_Using a Custom Geo Map`, opened read-only with its required prompts satisfied (`Africa` / `Egypt`), rendered a **completely empty page**. The viewer side pane names an object, **`Facility Locations`**, but `role="application"` returns **zero** objects and the pane answers *"Select an object to see its roles."*

The likely cause is that the custom map provider the geography item depends on is not registered in this deployment — consistent with the provider catalogue holding only *US County Data*. Whatever the cause, the product's behaviour is the finding: **a geography item whose provider is missing takes the whole object down silently** — no error, no placeholder, no named roles, nothing for a reader to act on.

---

### 6. New defects (continuing at 64)

| # | Observed behaviour | Required behaviour in the rebuild |
|---|---|---|
| 64 | **Switching a map's layer type silently discards an incompatible Geography assignment**, leaving a blank object with no message — lat/long → Region, and lookup → Line, both verified | Refuse the switch with a reason, or offer to convert the geography item; never delete a required role silently |
| 65 | **A geography item whose provider is unavailable takes its whole object down silently.** The object renders nothing, is absent from the accessibility tree, and its roles cannot be inspected even in the viewer pane | Render a named error placeholder that states the missing provider |
| 66 | **`Based on` in the New Geography Item dialog is not type-filtered** — all 57 columns including measures and dates, in the same dialog whose lat/long pickers *are* filtered. Choosing a measure yields `0% mapped` and a list of integers | Apply the product's own typed-picker discipline consistently |
| 67 | **Selecting a Custom coordinate space reports "Invalid value" before the user has typed anything** | Do not mark an untouched required field invalid; show the syntax example as help text |
| 68 | **The geography-provider authoring commands (New / Edit / Delete provider) are greyed with no explanation** — a fifth distinct cause of greying alongside content, save, permission and deployment | Say which one applies |

#### Corrections and confirmations
- **UNKNOWN resolved:** "Creating a geography item from scratch is still unexercised" — now fully exercised, all three source types, with the complete option catalogues above.
- **UNKNOWN resolved:** "The empty Geography picker is explained by the missing lat/long or provider prerequisite (DOCUMENTED)" — confirmed by observation, and the prerequisite is now precisely stated.
- **Session-10 note sharpened:** geo objects' zoom/pan comes from an explicit **Enable zoom and pan** option, not an implicit map behaviour.
- **Still UNKNOWN:** the Esri ArcGIS basemap catalogue (consent gate not answered); the custom-map provider authoring flow (greyed); geo **Line** rendering with a real path geography; the icon and distance-based-selection sample reports.


---

<!-- ===== Source: statistics_deep_dive.md ===== -->

## Statistical objects and statistics-flavoured charts — exhaustive pass (session 15)

**Method:** a **new blank sandbox report** on `RETAILDEMO_2` (2.34M rows, 57 columns).
**Observed:** 23 Sep 2026.

#### Safety log
- The tab opened with **`130_551_Creating a Bar Chart`** — one of the account's own saved reports — sitting in **Editing** mode. I did not touch it. All work happened in a **separate new blank report** opened alongside it, and `130_551` was left open exactly as found.
- The sandbox was closed with **Don't save** at the usual prompt. Nothing written.

---

### 1. Exact group membership

The object library's statistics-relevant groups, read in full:

| Group | Members |
|---|---|
| **Statistics (8)** | Cluster · Decision tree · Generalized additive model · Generalized linear model · Linear regression · Logistic regression · **Model comparison** · Nonparametric logistic regression |
| **Machine Learning (6)** | Bayesian network · Factorization machine · Forest · Gradient boosting · Neural network · Support vector machine |
| **Analytics (6)** | Automated explanation · Automated prediction · Forecasting · Network analysis · Path analysis · Text topics |
| Statistics-flavoured **Graphs** | Box plot · Correlation matrix · Heat map · Histogram · **Parallel coordinates plot** · Scatter plot · **Vector plot** · Bubble change plot · Comparative time series plot |

**A correction to the geo count while I was in the library.** The **Geo Maps** group lists **ten** entries — Geo bubble · cluster · contour · coordinate · **line** · **line-coordinate** · network · pie · region · **region-coordinate** — while session 14's layer *Change type* dialog offered **seven**. The two extra (`line-coordinate`, `region-coordinate`) are **composites**, so a geo object can carry **more than one layer at once**. Session 14's "one object, one swappable layer" is therefore incomplete: it is one object with a **layer stack**.

---

### 2. The Statistics role catalogue (OBSERVED)

| Object | Roles (`*` = marked required) |
|---|---|
| **Cluster** | **Variables\*** — a single role, and the picker accepts **categories as well as measures** |
| **Decision tree** | Response\*, Predictors\*, Partition ID, Frequency, Weight, **Node details** |
| **Linear regression** | Response\*, Continuous effects\*, Classification effects\*, Interaction effects\*, Partition ID, Group by, Frequency, Weight |
| **Generalized linear model** | as Linear regression, plus **Offset** |
| **Logistic regression** | as Generalized linear model |
| **Generalized additive model** | Response\*, **Spline effects\***, Continuous effects, Classification effects, Interaction effects, Partition ID, Frequency, Weight, Offset |
| **Nonparametric logistic regression** | as Generalized additive model |
| **Model comparison** | **"Roles are not supported for the selected object."** — it takes no data at all |

**The asterisk is misleading on the regressions.** Four effect roles each carry a required marker, yet the object runs as soon as **any one** of them is filled (consistent with the logistic-regression behaviour recorded earlier). A required marker that means "one of these four" needs different notation.

**The GAM / nonparametric pair is the same schema as the regressions with `Continuous effects` demoted and `Spline effects` promoted** — a clean, readable family resemblance that a rebuild should preserve.

---

### 3. What an unconfigured statistical object shows

Inserting **Nonparametric logistic regression** with no data renders a complete worked example:

> **Nonparametric Logistic Regression of Example Data**
> Event: **(none selected)** · Fit: **KS (Youden) 0** · Observations: **0 of 0**

…above a **four-panel grid** — **Fit Summary** (p-value bars) · **Iteration Plot** (Objective Function vs Step) · **Spline Plot** (Spline(Measure) vs Measure) · **Confusion Matrix** (Observed × Predicted) — all drawn from example data, with a central **Assign data** button.

So the documented "objects render placeholder sample data" strength extends to the statistical family, and it carries real teaching weight: the author sees the model's **panel layout and its header vocabulary** before committing any columns. Worth copying.

---

### 4. Cluster, configured

`Variables` = `Customer Age`, `Margin`:

> **Cluster** · **Observations: 646K of 2.3M** · **Polylines: 72**

rendered as **two stacked panels** — a cluster-centroid strip plot over `Customer Age` keyed by **Cluster ID**, and a **parallel coordinates plot** (Cluster ID | Customer Age | Margin) of coloured polylines.

Two disclosures in one header: the **dropped-row count** (`646K of 2.3M` — the same figure the logistic regression reported, so the drop is driven by missing values in the chosen measures and is reported consistently), and a **polyline cap** (`Polylines: 72`) that names its own truncation. This is the product at its best, and it is the same pattern as the decision tree's `Observations: 100 of 100`.

---

### 5. Model comparison — a precondition, stated well, delivered badly

The object accepts no roles. Selecting it raises a modal:

> **No Comparable Models** — "There are no models in the report which can be compared. To compare models, there must be at least two models which use the same **partition**, **response data item**, **event level**, and **group by** data items."

The *content* is excellent: four named, checkable conditions. The *delivery* is not — the dialog is **modal, blocks the properties pane, and re-fires every time the object is selected**, so the object cannot be inspected at all until it is deleted.

---

### 6. Statistics-flavoured chart options

#### 6.1 Box plot → Options → **Box Plot**
| Setting | Values |
|---|---|
| Box direction | dropdown |
| **Measure layout** | **Automatic · Separate axes · Shared axis** |
| **Outliers** | **Ignore outliers · Show outliers · Hide outliers** — default **Hide outliers** |
| Hide outliers | checkbox |
| Outlier bin outlines | checkbox |
| Averages | checkbox |

Style adds a dedicated **Fill** and **Outlier Gradient** colour pair.

**The three-way `Ignore / Show / Hide` is a genuinely good distinction** — *ignore* excludes outliers from the statistics, *hide* computes but does not draw them, *show* draws them — and most tools collapse it into one checkbox. But the UI never explains which is which, and **the default is `Hide`**, so out of the box a box plot's whiskers are computed from data the reader cannot see and is not told about.

#### 6.2 Histogram → Options → **Histogram**
| Setting | Values |
|---|---|
| Direction | dropdown |
| Transparency | 0% |
| **Bin range** | **System-determined values · Measure values** |
| Set a fixed bin count | checkbox |
| **Bin count (2-100)** | numeric — **the valid range is stated in the label** |

That inline range is the right pattern, and it makes the contrast sharper: the forecasting object silently rejects a horizon of 0 or 9999 with no range anywhere (defect 15). The same product does it well in one place and badly in another.

#### 6.3 Scatter plot → Options → **Fit Line**
**Type: None (default) · Best fit · Linear · Quadratic · Cubic · PSpline**, plus a Transparency slider and an ⓘ beside the label.

A fit line is **off by default** on a scatter plot — the statistical affordance most readers expect is one they must go find.

---

### 7. A seventh undo grammar, and the worst one

Changing the fit-line type produced:

> `Undo: Change option "fitLineType"`

The **raw internal camelCase key**, with **no object name and no new value**. Compare the fuller form recorded earlier — *"Change the option showRowNumbers for List table - City 1 to true"* — which at least names the object and the value, though it also leaks the internal key. This is now the **seventh** distinct undo grammar in the family (see `interaction-model.md` §H.3b) and the least informative.

---

### 8. New defects (continuing at 69)

| # | Observed behaviour | Required behaviour in the rebuild |
|---|---|---|
| 69 | **Model comparison's "No Comparable Models" modal re-fires on every selection** and blocks the properties pane, so the object cannot be inspected or configured — only deleted | State the precondition **in** the object's placeholder, not in a modal; never re-raise an informational dialog on selection |
| 70 | **Box plots hide outliers by default** — computed but not drawn, with nothing on the object saying so — and the `Ignore` / `Hide` distinction (excluded from the statistics vs merely not drawn) is never explained | Show outliers by default; label the three modes by what they do to the statistics |
| 71 | **Option-change undo entries expose raw internal option keys** (`Change option "fitLineType"`) and, in this form, drop the object name and the new value entirely | Name the setting in the user's words, the object, and the new value |
| 72 | **Four effect roles each carry a required asterisk on the regression objects while only one need be filled** | Use a distinct marker for "one of these", and say which ones are still outstanding |
| 73 | **Numeric limits are disclosed inconsistently** — the histogram states `Bin count (2-100)` in its label while the forecast horizon silently rejects 0 and 9999 with no range shown anywhere (defect 15) | State every numeric range in the control |
| 74 | **A scatter plot offers no fit line by default**, and the setting is four sections down the Options pane | Offer the fit line where the chart is, not only in a properties tree |

#### Corrections
- **`visualizations.md` §G.1 group counts**: the **Geo Maps** group has **ten** entries, two of them composite layer stacks (`Geo line-coordinate`, `Geo region-coordinate`). Session 14's "one object with a swappable layer" becomes **one object with a layer stack**.
- **Model comparison** moves from "never exercised" to "**exercised; precondition documented**" — two compatible models were still not built, so the comparison output itself remains UNKNOWN.

---

### 9. Still not observed
- The **Machine Learning** group (Bayesian network, Factorization machine, Forest, Gradient boosting, Neural network, Support vector machine) — roles not captured.
- **Model comparison output** with two compatible models.
- The **Fit ▾** fit-statistic catalogue on the tree/regression objects (~20 entries with inline definitions, recorded earlier from logistic regression but not re-enumerated here).
- **Parallel coordinates plot** and **Vector plot** as standalone objects.


---

<!-- ===== Source: model_comparison_and_ml.md ===== -->

## Model comparison, fitted models and the last two charts — session 16

**Method:** a **new blank sandbox report** on `RETAILDEMO_2` (2.34M rows). Two real models were fitted and compared.
**Observed:** 23 Sep 2026.

#### Safety log
`130_551_Creating a Bar Chart` was again open in Editing mode and was **not touched**; all work happened in a separate new report, closed with **Don't save**. One handoff action (**Create pipeline → Add to new project**) was deliberately **not** clicked, because it creates a project outside the report.

---

### 1. Model comparison — the standing UNKNOWN, resolved

Two models were built with a matching signature: **Response `ChannelType`**, **Predictors `Customer Age`, `Margin`**, no partition, auto event level.

#### 1.1 It is configured by a dialog, not by roles
Inserting the object opens **Add Model Comparison**:

| Field | Value |
|---|---|
| Data: | `RETAILDEMO_2` |
| Response: | `ChannelType` |
| Event level: | `Store` |
| Available models: | **Select all** · `Decision tree - ChannelType 1` · `Forest - ChannelType 1` |

Checkboxes per model; **OK stays disabled until at least one is ticked**. The data source, response and event level are shown as **fixed facts derived from the candidate models**, not as editable fields — the comparison's identity is inherited, which is exactly why the precondition (same partition, response, event level, group by) exists.

#### 1.2 The output
> **Model Comparison of ChannelType** · **Event: Store**

Three panels:

| Panel | Content |
|---|---|
| **Fit Statistic ⓘ** | A bar per model of the selected statistic — here **KS (Youden)**: Decision tree ≈ **0.39**, Forest ≈ **0.10**. **The winning model's bar is drawn in the accent colour and the loser's in grey**, so the verdict is legible before reading a number |
| **Confusion Matrix** | A lattice of Observed × Predicted **faceted by Model**, with a `Model: Decision… / Forest -…` footer strip |
| **Relative Importance Plot** | Variable × Model heat strip with a **Relative Importance** colour legend, so predictor importance can be compared across models |

**This is the best-designed object in the product.** It answers one question — *which model is better, and why* — in three linked panels, with the answer colour-coded. A rebuild should copy the shape wholesale.

---

### 2. Fitted models carry a live header and a handoff

A **fitted** Decision tree reads:

> **Decision Tree of ChannelType** · Event: **Store ▾** · Fit: **KS (Youden) 0.3872 ▾** · Observations: **2.3M of 2.3M** · **Create pipeline ▾**

| Element | Behaviour |
|---|---|
| **Event ▾** | picks the modelled event level |
| **Fit ▾** | picks the fit statistic and shows its current value inline |
| **Observations** | rows used of rows available |
| **Create pipeline ▾** | **Add to new project · Add to existing project** — promotes the fitted model into a Model Studio pipeline project |

`Create pipeline` resolves the *"Create pipeline — never exercised"* UNKNOWN at the menu level. It is the seam between the exploratory tool and the full ML workbench, and it is offered **on the object itself**, not buried in a menu.

Panels observed: Decision tree → **Tree · Variable Importance · (icicle) · Confusion Matrix**; Forest → **Variable Importance · Error Plot (Misclassification Rate vs Number of Trees) · Confusion Matrix**. The Forest showed an explicit **"Loading…" spinner over a greyed example-data placeholder** for roughly a minute — the long-running-model state, captured.

#### 2.1 A genuine inconsistency: two objects, same columns, different row counts
| Object | Variables | Observations |
|---|---|---|
| **Cluster** (session 15) | `Customer Age`, `Margin` | **646K of 2.3M** |
| **Decision tree** (this session) | `Customer Age`, `Margin` (as predictors) | **2.3M of 2.3M** |
| **Forest** | same | **2.3M of 2.3M** |

Same data, same two columns, **1.7M rows difference**. The tree-based models evidently tolerate missing predictor values while the cluster drops those rows — a defensible modelling choice that is **never stated anywhere in the UI**. A reader comparing a cluster and a tree on one page is comparing two different populations without being told.

---

### 3. The last two charts

| Object | Roles (`*` = required) |
|---|---|
| **Parallel coordinates plot** | **Variables\*** — a single role, the same shape as Cluster |
| **Vector plot** | **X axis\***, **Y axis\***, **X Origin\***, **Y Origin\*** · Color, Group, Lattice columns, Lattice rows, Data tip values, Hidden |

The vector plot is the only object in the catalogue with **four genuinely required roles** — it draws an arrow from (`X Origin`, `Y Origin`) to (`X axis`, `Y axis`), so all four are structurally necessary. Worth contrasting with the regressions, whose four asterisks mean "any one of these" (defect 72).

---

### 4. New defects (continuing at 75)

| # | Observed behaviour | Required behaviour in the rebuild |
|---|---|---|
| 75 | **Two objects on the same page fit the same two columns over different populations without saying so** — Cluster used 646K rows, Decision tree and Forest used all 2.3M | State the missing-value policy per object, and warn when two objects on a page disagree about the population |
| 76 | **The Model comparison dialog presents Data, Response and Event level as bare labels** with no indication that they are inherited from the candidate models and cannot be changed | Say where a fixed value came from |

---

### 5. What is still unobserved after sixteen sessions
- Five of the six **Machine Learning** objects (Bayesian network, Factorization machine, Gradient boosting, Neural network, Support vector machine) — roles are catalogued in §G.1, but only **Forest** has been fitted and rendered.
- **Create pipeline** beyond its menu — the Model Studio project it creates.
- The **Esri ArcGIS** basemap catalogue (consent gate deliberately unanswered).
- **Mid-drag visual feedback**; custom geography **provider authoring**; **Geo line** with a real path geography.
- **Export / Share / Copy link / embeddable markup** output, and **Play report / Edit playback**.


---

<!-- ===== Source: observed_architecture.md ===== -->

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

<!-- ===== Source: unknowns_closed.md ===== -->

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
