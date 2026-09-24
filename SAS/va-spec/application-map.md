# Application Map — overview, sitemap and routes

> Part of the Visual Analytics reverse-engineering deliverable. Sibling files: `application-map.md`, `screens.md`, `activities.md`, `components.md`, `visualizations.md`, `data-model.md`, `interaction-model.md`, `design-system.md`, `implementation-spec.md`, `screenshots/`.
> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

## A. Application Overview

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

## B. Sitemap

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

## K. Routing Model

**Finding (OBSERVED): the application has effectively one route.** `https://<host>/SASVisualAnalytics/` never changed while creating a report, loading data, adding objects, switching pages, opening dialogs, entering view mode or closing a report. No path segments, no query string, no hash fragment.

| Route | Screen | Parent | Entry | Parameters | Required state |
|---|---|---|---|---|---|
| `/SASVisualAnalytics/` | Landing, editor and viewer alike | — | direct navigation | none observed | authenticated session |
| `/SASLogon/oauth/authorize?client_id=sas.<service>&redirect_uri=…` | Silent per-service OAuth | — | triggered by first call to each backend service | client_id, redirect_uri, response_type, state | — |

**Consequences for a reimplementation (and an improvement to make):** report, page, object selection and view mode are **not addressable**, so no deep links, no browser Back/Forward within the app, and no bookmarkable state. The product compensates with in-app "Copy link…" commands (**UNKNOWN** what URL they emit — the action is gated behind saving). **Recommendation:** give the rebuild real routes, e.g. `/reports/:reportId/pages/:pageId?mode=view&object=:objectId&filters=…`.

### B.4 Where this application sits in its platform (OBSERVED, session 19)

The suite's Applications menu enumerates the whole platform, which is the clearest available answer to *"where does a reporting tool sit in an analytics suite?"*:

| Group | Applications |
|---|---|
| **Favorites** | Explore and Visualize · Build Custom Graphs |
| **Analytics Life Cycle** | Discover Information Assets · Manage Data · **Explore and Visualize** · Build Models · Manage Models · Build Decisions · Develop Code and Flows |
| **Administration** | Build Custom Graphs · Manage Themes · Explore Lineage · Manage Environment · Manage Workflows |

The reporting tool is **one station of seven** on an explicit life cycle, with the model workbench immediately downstream — which is why a fitted model in a report offers **Create pipeline** at all (`visualizations.md` §G.2i, and the UNKNOWN register).
