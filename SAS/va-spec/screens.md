# Screen Inventory

> Part of the Visual Analytics reverse-engineering deliverable. Sibling files: `application-map.md`, `screens.md`, `activities.md`, `components.md`, `visualizations.md`, `data-model.md`, `interaction-model.md`, `design-system.md`, `implementation-spec.md`, `screenshots/`.
> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

## C. Screen Inventory

### C.1 Primary screens

| # | Screen | Purpose | Key regions | Empty state | Notes |
|---|---|---|---|---|---|
| S1 | Landing / Home | Find or create a report | Folder list, search, sort + view toggles, result grid, "New report", What's New rail | Folder with no items shows the grid empty | Session recovery card appears when an unsaved session exists |
| S2 | Report Editor — blank | Start a report | Rail, empty canvas, right pane | Canvas: illustration + "Design a Report" + "Drag objects or data items onto the page, or start from a page template" + **Select a template** button | Data pane empty state: "To begin, add or import data." + Add data / Import data + Recently Used Data (5 links) |
| S3 | Report Editor — populated | Build and configure | Same, with objects on canvas | — | Object selection drives every right-pane tab |
| S4 | Report Editor — object maximized | Focus one object | Canvas fills; rails restricted | Data pane: "The Data pane is not available when an object is maximized" | Restore view via context menu |
| S5 | Report Viewer | Consume | Toolbar, page tabs, objects, optional side pane | Empty report: "No content to display." | Rails hidden; AI assistant icon disappears |
| S6 | Pop-up page (viewer) | Drill target | Modal with page name, ×, Close, Export as PDF, resize grip | — | Opened by **double-click** on a linked object |
| S7 | AI assistant side panel | Conversational help | Welcome, 3 starter chips (Add a data source / Add a visual / Help me get started), prompt box with attach, disclaimer | Welcome state is the empty state | "AI-generated content. Evaluate accuracy and suitability before use." |

### C.2 Rail panes (left)

| Pane | Contents | Empty / special states |
|---|---|---|
| Data | Source dropdown + source-actions menu, search, **+ New data item**, tree grouped Category / Measure / Aggregated Measure with distinct counts and badges (sensitive-data shield, outlier dots), per-item hover **Edit properties** and right-click menus | No data → Add data / Import data + recent list. Maximized object → unavailable message |
| Objects | 10 groups: Tables (2), Graphs (30), Geo Maps (10), Controls (5), Analytics (6), Containers (5), Content (5), Statistics (8), Machine Learning (6), Objects With Data (1) = 78 + search; ⋮ → Expand/Collapse, Show or hide objects, Sort (Name ✓ / Recent), Show object groups, Reorder groups, Import custom graph | List scrolls back to top after each insert |
| Outline | Tree of pages → objects, **+ New Page**, delete (greyed with one page), filter, "Clear selection" | Single page → delete greyed |
| Suggestions | Live-rendered chart previews with captions, a **data-source combobox** (one source at a time), **Refresh** and **Add more suggestions** — both disabled until data is loaded. **No ⋮ pane menu** (the only pane without one). Batches of **4 or 5**, not the documented 4. Right-click a card: **Add to current page · Add to new page · Delete** | **Empty state is literally blank** (defect 48). Cards are nameless `<canvas>` to assistive tech (defect 49). See `visualizations.md` §G.2d for the generation engine |
| Report Review | Severity counters (High / Medium / Low), findings with per-item quick-fix ⋮, **Evaluate Performance** link, filter box, ⋮ (sort/filter/export) | "No issues need to be reviewed. However, some issues can be found only after evaluating the report's performance." |

### C.3 Property panes (right)

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

### C.3b Viewer side pane, as seen on a production report (OBSERVED, session 6)

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

### C.3c Viewer side pane, corrected across nine reports (OBSERVED, session 10)

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

### C.3d Report prompt bar (OBSERVED, session 10)

A report-scoped prompt strip sits **above the page tab strip**, with a **▲ chevron that collapses the whole strip**. One report carried three controls in a single row: a **button bar** (six continents, none selected), a **drop-down** showing the greyed placeholder `Facility Country`, and a **text input** with placeholder `Enter Facility City...`.

A drop-down control's value list carries **`Clear filter`** as its first entry — and a control marked **(required)** does **not** offer it. That is the cleanest expression of `required` in the product.

### C.4 Dialog inventory (all observed; every one was cancelled)

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

### C.4b New Geography Item, in full (OBSERVED, session 14)

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

### C.5 State catalogue (empty / loading / error / confirmation / selection)

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
