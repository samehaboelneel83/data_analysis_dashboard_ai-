# Frontend UI/UX Improvements — Make Datalytics as Easy as SAS

**Method.** Tested live on 23 Sep 2026 in Chrome against the running app (`localhost:3001`, admin account, fresh dashboards "UI Test 1" and "UI Test 2" on *Demo — Sales*), comparing each flow against SAS VA's observed interaction model (`SAS/visual-analytics-complete-v2.md`). Every finding below was **reproduced in the browser**, not read from code.

**The headline.** Datalytics's *engine-side* UX is already strong — cross-filter chips, evidence-based suggestions, drag-to-canvas auto-charts. Where SAS is easier is the **first ten minutes**: starting a report, getting data in, getting the first chart configured, and undoing a mistake. Almost every fix below is frontend-only.

---

## A. Keep these — already as good as or better than SAS (don't regress them)

| What | Observed |
|---|---|
| **Drag a field onto the canvas → instant chart** | Dragging `region` created an auto-named **"Count by region"** bar chart with the count measure, rendered immediately. This *is* SAS's signature auto-fill move. |
| **Cross-filter transparency** | Clicking the Asia Pacific bar: chip strip `region = Asia Pacific ×` + `Clear all`, a **`1 filter ×`** badge on every receiving widget, linked-highlight on the source. Better disclosed than SAS. |
| **Field rows carry distinct counts** (`region - 4`, `country - 14`) | SAS parity. |
| **Suggest pane** | Cards labeled **"FROM THIS DATA'S INSIGHTS"** with the evidence in the caption (`cost moves with target (r = 0.87)`), a mini-preview, and `+ Add to page`. SAS's suggestions are random and unexplained; ours are accountable. |
| **Object-to-edit dropdown** in the properties panel + settings **filter box** | Matches SAS's object selector + options search. |
| **Σ quick calculations** from the field list (distinct values, % of rows, saved at widget grain) | SAS parity — but see B7 (sticky popover bug). |
| Right-click **context menu exists** on marks (copy link, CSV/Excel/image export) | Keep, and extend (C6). |

---

## B. The changes — ordered by impact

### B1. Add undo/redo to the builder — the single biggest gap ⭐
- **Tested:** added a widget, pressed **Ctrl+Z → nothing happened**. The only recovery is delete-by-hand or version history.
- **SAS:** every edit is a named, reversible step, shown on toolbar buttons: *"Undo: Assign Customer Age to Crosstab - Region 1"*. It's why users explore fearlessly, and the spec calls it one of the three ideas the product rests on.
- **Frontend change:** a command stack in the builder state (each mutation registers `{do, undo, sentence}`); `Ctrl+Z`/`Ctrl+Shift+Z`; two toolbar buttons whose tooltip shows the sentence; a small history dropdown. Rejected/invalid inputs must create no entry.
- Files: `pages/ReportBuilder.tsx` (state mutations), `components/report/WidgetConfigPanel.tsx` (config edits route through the same dispatcher).

### B2. Fix the "add data later" golden path — it is broken ⭐
- **Tested (UI Test 1):** create dashboard with *"— No dataset (add later) —"* → add Bar Chart → go to **Data** tab → attach *Demo — Sales* → return: the widget's Dimension dropdown **still offers no columns**, the FIELDS list stays empty, and the HIERARCHY panel still reads *"Attach a dataset to this report to browse columns"*. No message, no remedy — the user is stuck. (Creating "UI Test 2" **with** the dataset chosen upfront works fine.)
- **SAS pattern being violated:** *silent refusal* — its worst defect family; and its empty pickers at least say "No data items available for role."
- **Frontend change:** attaching a dataset must (a) set it as the report's primary, (b) refresh the fields list and every unbound widget's role pickers, (c) clear the stale empty-state text. And any empty role picker should say **why** and offer the fix: *"No dataset attached — Add data"* as a link.

### B3. Make the first minute look like SAS's first minute
Three small changes that together give the "4 clicks to a chart" feel:

1. **"New dashboard" opens the builder immediately.** Today a name is required upfront in a form (Name* → Create & Open). SAS auto-names ("Report 1") and you name it when you save. → Create with an auto-name, put the name in the title bar as an inline-editable field, drop the blocking form. Keep an optional dataset pick as a *first-run overlay inside the builder* instead.
2. **A real dataset picker.** The create form's dataset `<select>` is a raw, unsorted list mixing test junk (`kjhkjhkjhkjh`, `sss`, `2`) with real data, no search. SAS's Choose Data dialog has search, Recent/Favorites, and a preview. → One picker dialog (search + recents + row/column counts), reused everywhere a dataset is chosen.
3. **A canvas empty state that teaches.** Today: grey area + *"Click a widget from the left panel to add it here."* SAS: illustration + *"Drag objects **or data items** onto the page, or start from a **page template**"* + a Select-a-template button. → Empty page shows three actions: **Add data** (if none), **Drag a field or chart here**, **Start from a template**. The drag-a-field hint matters most, because that gesture (A. above) is our best feature and nothing advertises it.

### B4. Reorganize the left panel: fields first, charts grouped ⭐
- **Tested:** the left panel is ~60 flat chart buttons (CHARTS → KPI/TABLES → MAPS → LAYOUT → ANALYTICS), then TEMPLATES, then REPORT FILTERS, and only then **FIELDS** and DATASETS — the field list needs a long scroll to reach, and shows *"Select a widget to add fields"* until a widget is selected.
- **SAS:** left rail = 5 icon tabs (**Data first**, Objects, Outline, …); the object library is grouped, collapsible and searchable; the data pane is always one click away. Its recommendations explicitly warn against a flat chart menu ("users cannot choose between Needle plot and Dot plot from a list").
- **Frontend change:** turn the single scrolling panel into **tabs**: `Fields` (default when data is attached) · `Charts` (collapsible groups, keep the search) · `Templates`. Fields are always listed once a dataset is attached — browsing data must not require selecting a widget first. Report filters move to the Filters surface; Outline/Suggest/Review already live in the top strip.

### B5. Widget placeholder + assign-data on the tile
- **Tested:** a new Bar Chart is an empty dashed frame reading *"Configure widget to see data"* — the fix is in the right panel, but nothing points there, and the panel opens on **Title / RTL / Transparent background** (cosmetics) rather than data.
- **SAS:** every new object renders **synthetic sample data** ("Measure by Category") behind an **"Assign data"** button; the canvas is never blank; clicking the button opens the roles pane.
- **Frontend change:** each renderer gets a static sample dataset drawn dimmed at ~40% opacity with an **"Assign data"** button overlaid; the button opens the config panel directly on the **Data roles** chip. When required roles are missing, the panel auto-opens on Data roles with the required ones marked ( * ), not on "All".

### B6. Upgrade role pickers from bare `<select>`s
- **Tested:** roles are native dropdowns ("— select column —"), no type icons, no counts, no required marks, and an empty one explains nothing.
- **SAS:** typed "+ Add" pickers that list **only compatible columns**, show the item type, mark required roles, grey out single-item roles once filled.
- **Frontend change:** a shared `RolePicker` component: searchable popover listing compatible fields with type icon + distinct count, red `*` on required roles, and an empty state that names the cause (*no dataset / no column of this type*) with the one-click fix. Reuse it in the config panel and in the (new) on-tile Assign data flow.
- Also fix the drop rule: dropping a field **onto an existing widget** should fill that widget's next empty compatible role (with a drop-highlight naming the role) — today it creates a *new* chart even when dropped on an empty widget. Keep drop-on-empty-canvas = create.

### B7. Small frictions found while testing (cheap, each < a day)
1. **Sticky Σ popover** — the quick-calc menu opens on hover and stays open through unrelated actions (it survived ~10 subsequent clicks and screenshots). Make it click-toggled and dismiss on outside click / Esc.
2. **Tooltip shows the internal key** — hovering a bar reads `value : 514`; it should read the measure's display name (`count`). Same class of bug as the fixed `value2` legend defect — route all mark labels through one naming function.
3. **Stale empty states** — "Attach a dataset…" after attaching (B2); "No saved templates yet" while the Save box sits enabled with no widget selected but says *"Select a widget first"* only in placeholder text.
4. **Context menu on marks is export-only** — add data actions: *Keep only / Exclude this value*, *Drill / go to linked page*, *Explain this value*, *Sort*, *Change aggregation*. SAS's mark menu is 20+ items; ours has 4.
5. **Toolbar crowding** — the header shows Copy link · Share · Access · Present · Print · PDF · Subscribe + 6 palette dots + Edit mode, above a 12-tab strip (Report/Data/Model/Outline/Suggest/Review/Comments/Parameters/Schedule/Ask/Insights/More). Group: **Share ▾** (link/share/access/embed), **Export ▾** (print/PDF), and move Model/Parameters/Schedule under **More**. The strip also mixes *modes* (Report/Data/Model) with *panes* (Outline/Suggest/Review/Comments) — visually separate the two kinds (left-aligned modes, right-aligned panes) so switching mode doesn't feel like losing your page.
6. **Data mode replaces the canvas entirely.** Attaching data means leaving the report view. Consider making dataset attach available from the Fields tab (B4) so the common case never leaves Report mode; keep Data mode for profiling/prep.

---

## C. Priority order for implementation

| # | Change | Why this order |
|---|---|---|
| 1 | B1 undo/redo | Biggest single ease-of-use gap vs SAS; unblocks fearless exploration everywhere else |
| 2 | B2 add-data-later fix | A broken golden path that strands new users; small fix |
| 3 | B5 + B6 placeholder, Assign data, role pickers | Turns "insert → hunt through panel" into SAS's "insert → see something → click Assign data" |
| 4 | B4 left panel tabs, fields first | Structural, touches layout — do after the pickers so fields drag into good targets |
| 5 | B3 instant create + dataset picker + empty state | Polishes the first minute |
| 6 | B7 the six small frictions | Batch them; each is independent |

**Definition of done (test it like this):** a first-time user, starting from Home, reaches a rendered, filtered chart on *Demo — Sales* in **≤ 6 clicks with no scrolling and no dead ends**, can undo every one of those steps with Ctrl+Z, and at no point sees an empty control that doesn't say why it's empty and how to fix it.

---

*Companion files: `SAS_VA_FEATURE_COMPARISON.md`, `MISSING_IN_DATALYTICS.md`, `MASTER_PLAN.md`. This file covers frontend ease-of-use only; feature gaps live in the gap register.*
